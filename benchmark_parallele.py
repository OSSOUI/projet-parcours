"""Benchmark de la parallelisation (plan de performances, chantier 2). Hors du moteur.

Les prompts EXACTS des decisions sont reconstruits par rejeu (evaluation_hybride.reconstruire),
puis groupes par pas simule, comme en mode synchrone : tous les agents d'un pas decident sur
le meme etat, leurs appels sont independants. Chaque pas est envoye avec N requetes
simultanees ; chaque fil d'execution a SON client (aucun etat partage, contrairement au moteur).

Mesures : duree murale par pas et totale, latence par appel, jetons, decisions et reponses
brutes identiques a la reference N = 1 et a la passe A' deja enregistree, incidents, charge.
Rien n'est modifie : ni moteur, ni simulateur, ni Ollama (son reglage est seulement releve).

    python3 benchmark_parallele.py --essai                       # modele simule, aucun appel
    python3 benchmark_parallele.py --conditions 1,2,4,1,2,4      # NOUVEAUX appels Qwen
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from ephemere.agents_llm import detecter_derive  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from ephemere.llm import ClientLLM  # noqa: E402
from evaluation_hybride import MODELES, reconstruire  # noqa: E402

RUNS = ["runs/exp_reference_llm_reference_01.jsonl", "runs/exp_reference_llm_reference_02.jsonl"]
JOURS = 10
SORTIE = os.path.join(RACINE, "resultats", "benchmark_parallele")
A_PRIME = os.path.join(RACINE, "resultats", "evaluation_hybride")


class Simule:
    """Modele simule pour --essai : reponse fixee par la cle, latence factice."""

    def __init__(self, graine):
        self.graine, self.derniere_mesure, self.dernier_brut = graine, {}, None

    def json(self, systeme, consigne, taille="llm_petit", cle=None, **_):
        time.sleep(0.05 if taille == "llm_petit" else 0.1)
        h = int(hashlib.sha256(f"{self.graine}:{cle}".encode()).hexdigest()[:8], 16)
        r = {"porte": h % 2 == 0, "categorie": list(SENS)[h % 6], "sens": "s", "publication": "",
             "destinataire": "", "raison": f"motif {h % 9}"}
        self.dernier_brut = json.dumps(r)
        self.derniere_mesure = {"latence_s": 0.05, "tokens_entree": 1000, "tokens_sortie": 80}
        return r


def pas_simules():
    """[(run, graine, t, [decisions du pas])], dans l'ordre, sur les JOURS premiers jours."""
    pas = []
    for chemin in RUNS:
        evs, notes, fidele = reconstruire(os.path.join(RACINE, chemin))
        if not fidele:
            raise SystemExit(f"{chemin} : rejeu non fidele, benchmark refuse")
        run = os.path.basename(chemin)[:-6]
        par_t = {}
        for n in notes:
            if n["t"] <= JOURS * 1440:
                par_t.setdefault(n["t"], []).append(n)
        pas += [(run, evs[0]["graine"], t, ns) for t, ns in sorted(par_t.items())]
    return pas


def fabriquer_client(graine, essai):
    if essai:
        return Simule(graine)
    return ClientLLM("ollama", MODELES, pause=0.0, temperature=0.9, graine=graine)


def appel(clients, graine, essai, n):
    """Un appel de decision, avec le client propre a ce fil d'execution."""
    c = clients.__dict__.setdefault(graine, fabriquer_client(graine, essai))
    rep = c.json(n["systeme"], n["consigne"], n["taille"], cle=n["cle"])
    m = dict(c.derniere_mesure)
    valide = isinstance(rep, dict) and detecter_derive(rep)[0] is None
    return {"agent": n["agent"], "t": n["t"], "taille": n["taille"], "valide": valide,
            "porte": rep.get("porte") if valide else None,
            "categorie": rep.get("categorie") if valide else None,
            "brut": (c.dernier_brut or "")[:600], "latence_s": m.get("latence_s"),
            "tokens_entree": m.get("tokens_entree"), "tokens_sortie": m.get("tokens_sortie")}


def memoire_ollama():
    try:
        sortie = subprocess.run(["ps", "-ax", "-o", "rss=,command="], capture_output=True,
                                text=True).stdout
        return round(sum(int(l.split()[0]) for l in sortie.splitlines()
                         if "ollama" in l.lower()) / 1024)
    except (OSError, ValueError):
        return None


def serie(pas, n_simultanes, essai):
    clients = threading.local()
    # Echauffement : un appel par taille de modele, hors mesure.
    vus = set()
    for run, graine, t, ns in pas:
        for x in ns:
            if x["taille"] not in vus:
                vus.add(x["taille"])
                appel(clients, graine, essai, x)
    resultats, durees, charges, memoire = [], [], [], []
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=n_simultanes) as pool:
        for run, graine, t, ns in pas:
            debut = time.perf_counter()
            futurs = [pool.submit(appel, clients, graine, essai, x) for x in ns]
            for f, x in zip(futurs, ns):
                resultats.append({"run": run, **f.result()})
            durees.append(time.perf_counter() - debut)
            charges.append(os.getloadavg()[0])
            memoire.append(memoire_ollama())
    return resultats, {"duree_totale_s": time.perf_counter() - t0, "durees_pas_s": durees,
                       "charge_moyenne": statistics.mean(charges),
                       "memoire_ollama_max_mo": max((m for m in memoire if m), default=None)}


def identite(a, b):
    cle = lambda r: (r["run"], r["agent"], r["t"])
    ib = {cle(r): r for r in b}
    paires = [(r, ib[cle(r)]) for r in a if cle(r) in ib]
    dec = sum((x["valide"], x["porte"], x["categorie"]) == (y["valide"], y["porte"], y["categorie"])
              for x, y in paires)
    brut = sum(x["brut"] == y["brut"] for x, y in paires)
    return {"n": len(paires), "decisions_identiques": dec / len(paires) if paires else None,
            "brut_identique": brut / len(paires) if paires else None}


def a_prime():
    out = []
    for chemin in RUNS:
        run = os.path.basename(chemin)[:-6]
        p = os.path.join(A_PRIME, f"{run}.a_prime.jsonl")
        if os.path.exists(p):
            out += [{"run": run, **json.loads(l)} for l in open(p, encoding="utf-8")]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--conditions", default="1,2,4,1,2,4",
                   help="N simultanes, dans l'ordre d'execution (alternance = repetitions)")
    p.add_argument("--essai", action="store_true", help="modele simule : aucun appel")
    args = p.parse_args()
    conditions = [int(x) for x in args.conditions.split(",")]
    os.makedirs(SORTIE, exist_ok=True)
    pas = pas_simules()
    print(f"{len(pas)} pas simules, {sum(len(ns) for *_, ns in pas)} decisions par serie, "
          f"conditions {conditions}{' (ESSAI, modele simule)' if args.essai else ''}", flush=True)
    series, reference = [], None
    for i, n in enumerate(conditions):
        res, mesure = serie(pas, n, args.essai)
        nom = f"{'essai_' if args.essai else ''}{i + 1:02d}_N{n}"
        with open(os.path.join(SORTIE, f"{nom}.jsonl"), "w", encoding="utf-8") as f:
            for r in res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if n == 1 and reference is None:
            reference = res
        lat = sorted(r["latence_s"] for r in res if r["latence_s"] is not None)
        s = {"serie": nom, "N": n, **mesure, "decisions": len(res),
             "incidents": sum(not r["valide"] for r in res),
             "latence_mediane_s": statistics.median(lat), "latence_p95_s": lat[int(0.95 * (len(lat) - 1))],
             "tokens_sortie": sum(r["tokens_sortie"] or 0 for r in res)}
        s["durees_pas_s"] = [round(x, 3) for x in s["durees_pas_s"]]
        series.append((s, res))
        print(f"  {nom} : {s['duree_totale_s']:.0f} s, latence mediane {s['latence_mediane_s']:.2f} s, "
              f"{s['incidents']} incidents", flush=True)
    ref_a = a_prime()
    bilan = {"essai": args.essai, "runs": RUNS, "jours": JOURS, "pas": len(pas),
             "ollama": {k: os.environ.get(k) for k in ("OLLAMA_NUM_PARALLEL", "OLLAMA_MAX_LOADED_MODELS")},
             "series": []}
    duree_ref = statistics.mean(s["duree_totale_s"] for s, _ in series if s["N"] == 1)
    for s, res in series:
        s["gain_vs_N1"] = duree_ref / s["duree_totale_s"]
        s["identite_vs_premiere_N1"] = identite(res, reference)
        s["identite_vs_A_prime"] = identite(res, ref_a) if ref_a and not args.essai else None
        bilan["series"].append(s)
    cible = os.path.join(SORTIE, "essai.json" if args.essai else "bilan.json")
    with open(cible, "w", encoding="utf-8") as f:
        json.dump(bilan, f, ensure_ascii=False, indent=1)
    for s in bilan["series"]:
        i = s["identite_vs_premiere_N1"]
        print(f"  {s['serie']} : gain x{s['gain_vs_N1']:.2f}, decisions identiques a N1 "
              f"{i['decisions_identiques']:.1%}, brut {i['brut_identique']:.1%}")
    print(f"-> {cible}")


if __name__ == "__main__":
    main()
