"""Evaluation hors simulation d'une architecture hybride : B (reflexes) et C' (decision courte).

Rien n'est modifie : ni le moteur, ni les journaux, ni les runs. Aucun nouveau run.

  reconstruction  chaque run est rejoue dans la boucle du simulateur avec les reponses
                  enregistrees ; on capture, pour chaque decision LLM, le prompt EXACT
                  que le simulateur a construit, sa perception, et ce que le moteur a
                  regles aurait decide au meme instant. Le monde rejoue doit etre
                  identique au journal (sinon le run est ecarte).
  B (reflexes)    regles candidates appliquees aux perceptions : couverture, accord avec
                  la decision LLM enregistree, desaccords, effets d'une substitution
                  statique (adoption, persistance, emergence), effets indirects
                  (publications perdues, souvenirs futurs touches). AUCUN appel LLM.
  C' (--llm)      NOUVEAUX appels Qwen, memes modeles, meme temperature, memes graines :
                    A'  le prompt original, repose tel quel (bruit du modele : plafond d'accord)
                    C'  le meme prompt, mais la sortie reduite a porte + categorie (schema)
                  Deux passes separees, dans le meme ordre, pour que le cache de prefixe
                  d'Ollama n'avantage pas l'une sur l'autre.

    python3 evaluation_hybride.py runs/exp_reference_llm_reference_0[1-5].jsonl ../projet-parcours/runs/exp_memoire_A_g105.jsonl
    python3 evaluation_hybride.py --llm runs/exp_reference_llm_reference_01.jsonl ../projet-parcours/runs/exp_memoire_A_g105.jsonl
"""
import argparse
import contextlib
import io
import json
import os
import re
import statistics
import sys
import tempfile
import time
import types

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import emergence  # noqa: E402
import simuler  # noqa: E402
from ephemere import population  # noqa: E402
from ephemere.agents_llm import SYSTEME, DecideurLLM, detecter_derive  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.journal import Journal  # noqa: E402
from ephemere.llm import ClientLLM, extraire_json  # noqa: E402
from ephemere.monde import Monde  # noqa: E402
from ephemere.rag import Base  # noqa: E402
from ephemere.regles_v1 import Regles  # noqa: E402
from rejeu_integration import monde_de  # noqa: E402
from verifier_comparabilite import VOLATILS, lire, premier_ecart  # noqa: E402

SORTIE = os.path.join(RACINE, "resultats", "evaluation_hybride")
LLM = ("llm_petit", "llm_grand")
MODELES = {"llm_grand": "qwen2.5:7b", "llm_petit": "qwen2.5:3b"}
DEBUT_SORTIE = "Reponds par un objet JSON avec exactement ces six champs :"
FIN_COURTE = "Reponds uniquement par ton objet JSON, sans aucun texte avant ni apres."
SCHEMA_COURT = {"type": "object",
                "properties": {"porte": {"type": "boolean"},
                               "categorie": {"type": "string", "enum": list(SENS)}},
                "required": ["porte", "categorie"], "additionalProperties": False}
CAMPUS = re.compile(r"(\d+) etudiants sur (\d+)")


# ------------------------------------------------------------------ reconstruction
class Rejeu:
    """Rend la reponse enregistree et garde le prompt construit par le simulateur."""

    graine = 0

    def __init__(self, reponses):
        self.reponses, self.dernier = reponses, None
        self.derniere_mesure, self.dernier_brut = {}, None

    def json(self, systeme, consigne, taille="llm_petit", cle=None, **_):
        self.derniere_mesure = {"latence_s": 0.0}
        _, agent, t = cle.split(":")
        self.dernier = {"systeme": systeme, "consigne": consigne, "taille": taille, "cle": cle}
        self.dernier_brut = self.reponses.get((agent, int(t)))
        return None if self.dernier_brut is None else extraire_json(self.dernier_brut)


class Capture:
    """Enveloppe d'un decideur LLM : note le prompt, la perception, et la decision
    que le moteur a regles aurait prise au meme instant (calculee AVANT, sur une copie)."""

    def __init__(self, decideur, client, regles, notes):
        self.decideur, self.client, self.regles, self.notes = decideur, client, regles, notes

    def decider(self, agent, monde, t_sim, horloge_lisible=""):
        r = self.regles.decider(dict(agent), monde, t_sim, horloge_lisible)
        d = self.decideur.decider(agent, monde, t_sim, horloge_lisible)
        self.notes.append({"agent": agent["id"], "t": t_sim, **self.client.dernier,
                           "perception": {k: d["perception"].get(k) for k in
                                          ("vue", "messages", "souvenirs")},
                           "regles": {"porte": r["porte"], "categorie": r["categorie"]}})
        return d


def reconstruire(chemin):
    evs = lire(chemin)
    tete = evs[0]
    client = Rejeu({(e["agent"], e["t_sim"]): e["reponse_brute"]
                    for e in evs if e["schema"] == "perception.v1"})
    agents, config = population.construire(os.path.join(RACINE, "config", tete["config"]),
                                           tete["nb_agents"], tete["graine"])
    base = Base(os.path.join(RACINE, tete.get("corpus", "corpus")))
    regles, notes = Regles(), []
    moteurs = {t: Capture(DecideurLLM(client, t, base=base,
                                      memoire_sens=bool(tete.get("memoire_sens"))),
                          client, Regles(), notes) for t in LLM}
    decideurs = {a["id"]: moteurs.get(a["moteur"], regles) for a in agents}
    args = types.SimpleNamespace(jours=tete["jours"], pas_min=simuler.MINUTES_PAR_JOUR,
                                 releve_min=simuler.MINUTES_PAR_JOUR, ombres=[],
                                 telemetrie=None, dialogue=None, pionnieres_simultanees=False)
    with tempfile.TemporaryDirectory() as d:
        with Journal(d, "rejeu", Horloge(0)) as j:
            j.ecrire("run.v2", **{k: v for k, v in tete.items()
                                  if k not in VOLATILS | {"schema", "t_sim", "t_sim_lisible"}})
            j.ecrire("population.v1", resume=population.resume(agents), agents=[
                {k: a[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")}
                for a in agents])
            with contextlib.redirect_stdout(io.StringIO()):
                simuler.tourner_synchrone(Monde(agents, config.get("perception")), decideurs, j,
                                          j.horloge, args)
            chemin_r = j.chemin
        rejoue = lire(chemin_r)
    fidele = premier_ecart(monde_de(evs), monde_de(rejoue)) is None
    originales = {(e["agent"], e["t_sim"]): e for e in evs if e["schema"] == "decision.v1"}
    publications = {(e["agent"], e["t_sim"]) for e in evs if e["schema"] == "publication.v1"}
    for n in notes:
        o = originales[(n["agent"], n["t"])]
        n["original"] = {"porte": o["porte"], "categorie": o["categorie"], "valide": o["valide"]}
        n["publication_originale"] = (n["agent"], n["t"]) in publications
    return evs, notes, fidele


# ------------------------------------------------------------------ regles candidates
def campus(vue):
    m = CAMPUS.search(vue.get("campus") or "")
    return int(m.group(1)) if m else None


def enrichir(notes):
    """Ajoute a chaque decision ce qu'il faut aux regles : decision et vue precedentes."""
    prec = {}
    for n in notes:                      # notes dans l'ordre du simulateur
        p = prec.get(n["agent"])
        vue = n["perception"]["vue"]
        n["prec"] = p
        n["nouveaux_messages"] = len(n["perception"]["messages"] or [])
        n["nouvel_echange"] = bool(p) and any(
            s["genre"] == "echange" and s["t_sim"] > p["t"] for s in n["perception"]["souvenirs"])
        n["campus"], n["groupe"] = campus(vue), len(vue.get("porteurs_groupe") or [])
        if n["original"]["valide"]:
            prec[n["agent"]] = {"t": n["t"], "porte": n["original"]["porte"],
                                "categorie": n["original"]["categorie"], "campus": n["campus"],
                                "groupe": n["groupe"],
                                "stable": bool(p) and (p["porte"], p["categorie"]) ==
                                          (n["original"]["porte"], n["original"]["categorie"])}


def calme(n, tolerance, messages=True):
    """Rien de neuf depuis la decision precedente de l'agent (declencheurs ORIGINAUX)."""
    p = n["prec"]
    return (p is not None and (not messages or not n["nouveaux_messages"])
            and not n["nouvel_echange"]
            and n["campus"] is not None and p["campus"] is not None
            and abs(n["campus"] - p["campus"]) <= tolerance and n["groupe"] == p["groupe"])


# Une regle "garder" reprend la derniere decision EFFECTIVE de l'agent, reflexes compris :
# un reflexe qui garde un reflexe fige l'agent. nom -> (description, statut, nature, condition)
REGLES = {
    "R0_inertie": ("garder la decision precedente, toujours (borne haute de couverture)",
                   "temoin", "garder", lambda n: n["prec"] is not None),
    "R1_rien_de_neuf_strict": ("aucun message nouveau, aucun echange nouveau, meme nombre de "
                               "porteurs sur le campus et dans le groupe -> garder",
                               "pre-enregistrable", "garder", lambda n: calme(n, 0)),
    "R2_rien_de_neuf_tolerant": ("comme R1, mais le campus peut varier d'un etudiant (5 points)",
                                 "exploratoire", "garder", lambda n: calme(n, 1)),
    "R3_stabilite_confirmee": ("R2, et les deux decisions precedentes etaient identiques",
                               "exploratoire", "garder", lambda n: calme(n, 1) and n["prec"]["stable"]),
    "R5_vue_inchangee_messages_ignores": ("meme nombre de porteurs (campus et groupe), aucun "
                                          "echange nouveau ; les messages publics sont IGNORES",
                                          "exploratoire", "garder",
                                          lambda n: calme(n, 0, messages=False)),
    "R6_R5_et_stabilite": ("R5, et les deux decisions precedentes etaient identiques",
                           "exploratoire", "garder",
                           lambda n: calme(n, 0, messages=False) and n["prec"]["stable"]),
    "R4_moteur_a_regles": ("la decision du moteur a regles du projet (regles_v1), toujours",
                           "temoin", "regles", lambda n: True),
}


def accord(paires):
    """paires : (decision reflexe ou C', decision originale), originales valides seulement."""
    n = len(paires)
    if not n:
        return {"n": 0}
    pt = sum(a["porte"] == o["porte"] for a, o in paires)
    ct = sum(a["categorie"] == o["categorie"] for a, o in paires)
    les2 = sum(a["porte"] == o["porte"] and a["categorie"] == o["categorie"] for a, o in paires)
    return {"n": n, "porte": pt / n, "categorie": ct / n, "les_deux": les2 / n,
            "desaccords": {"porte_seul": sum(a["porte"] != o["porte"] and a["categorie"] == o["categorie"]
                                             for a, o in paires),
                           "categorie_seule": sum(a["porte"] == o["porte"] and a["categorie"] != o["categorie"]
                                                  for a, o in paires),
                           "les_deux": sum(a["porte"] != o["porte"] and a["categorie"] != o["categorie"]
                                           for a, o in paires)}}


# ------------------------------------------------------------------ effets d'une substitution
def substituer(evs, remplacements):
    """Journal ou les decisions (agent, t) sont remplacees. Substitution STATIQUE :
    le reste du run (perceptions, publications, decisions suivantes) ne change pas."""
    out = []
    for e in evs:
        if e["schema"] == "decision.v1" and (e["agent"], e["t_sim"]) in remplacements:
            r = remplacements[(e["agent"], e["t_sim"])]
            e = {**e, "porte": r["porte"], "categorie": r["categorie"], "valide": r.get("valide", True)}
        out.append(e)
    return out


def mesures(evs, dist):
    pop = {a["id"]: a for e in evs if e["schema"] == "population.v1" for a in e["agents"]}
    porte = {a: bool(x["porte"]) for a, x in pop.items()}
    adoption, prec, garde, paires = [], {}, 0, 0
    for e in evs:
        if e["schema"] == "decision.v1":
            if e["valide"]:
                porte[e["agent"]] = e["porte"]
                if pop[e["agent"]]["moteur"] in LLM:
                    if e["agent"] in prec:
                        paires += 1
                        garde += prec[e["agent"]] == e["categorie"]
                    prec[e["agent"]] = e["categorie"]
        elif e["schema"] == "indicateurs.v1":
            adoption.append(sum(porte.values()) / len(porte))
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for e in evs:
            if e["schema"] != "ombre.v1":
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            em = emergence.analyser(f.name, dist, 0)
    finally:
        os.unlink(f.name)
    return {"persistance_sens": garde / paires if paires else None,
            "adoption_finale": adoption[-1], "adoption_pic": max(adoption),
            "adoption_moyenne": statistics.mean(adoption),
            "emergence": {l: {k: v.get(k) for k in ("delta_a", "seuil", "emergent")}
                          for l, v in em["seuil_persistance"].items()}}


def indirects(notes, couverts):
    """Ce qu'une substitution change au-dela de la decision elle-meme."""
    publis = sum(1 for n in notes if (n["agent"], n["t"]) in couverts and n["publication_originale"])
    touches = total = 0
    for n in notes:
        souv = {s["t_sim"] for s in n["perception"]["souvenirs"] if s["genre"] == "decision"}
        if souv:
            total += 1
            touches += any((n["agent"], t) in couverts for t in souv)
    return {"publications_perdues": publis,
            "publications_originales": sum(n["publication_originale"] for n in notes),
            "prompts_ulterieurs_avec_souvenir_reflexe": touches / total if total else None}


def evaluer_b(evs, notes, dist):
    enrichir(notes)
    base = mesures(evs, dist)
    sortie = {"decisions_llm": len(notes), "valides": sum(n["original"]["valide"] for n in notes),
              "reference": base, "regles": {}}
    for nom, (desc, statut, nature, condition) in REGLES.items():
        remplace, paires, effectif = {}, [], {}
        for n in notes:                  # dans l'ordre : la chaine des reflexes est suivie
            r = None
            if condition(n):
                r = n["regles"] if nature == "regles" else effectif.get(n["agent"])
            if r is not None:
                remplace[(n["agent"], n["t"])] = r
                if n["original"]["valide"]:
                    paires.append((r, n["original"]))
                effectif[n["agent"]] = r
            elif n["original"]["valide"]:
                effectif[n["agent"]] = {"porte": n["original"]["porte"],
                                        "categorie": n["original"]["categorie"]}
        m = mesures(substituer(evs, remplace), dist)
        sortie["regles"][nom] = {"description": desc, "statut": statut,
                                 "couverture": len(remplace) / len(notes),
                                 "accord": accord(paires), "effets": m,
                                 "indirects": indirects(notes, set(remplace))}
    return sortie


# ------------------------------------------------------------------ C' : nouveaux appels Qwen
def consigne_courte(consigne):
    """Le prompt original, dont seule la partie 'sortie' est reduite a porte + categorie."""
    debut = consigne.index(DEBUT_SORTIE)
    champs = consigne[consigne.index('"porte" :'):consigne.index('"sens" :')].rstrip()
    return (consigne[:debut] + "Reponds par un objet JSON avec exactement ces deux champs :\n\n"
            + champs + "\n\n" + FIN_COURTE)


def appeler(client, n, court):
    consigne = consigne_courte(n["consigne"]) if court else n["consigne"]
    rep = client.json(n["systeme"], consigne, n["taille"], cle=n["cle"],
                      schema=SCHEMA_COURT if court else None)
    m = client.derniere_mesure
    if court:
        valide = (isinstance(rep, dict) and isinstance(rep.get("porte"), bool)
                  and rep.get("categorie") in SENS)
    else:
        valide = isinstance(rep, dict) and detecter_derive(rep)[0] is None
    return {"agent": n["agent"], "t": n["t"], "taille": n["taille"], "valide": valide,
            "porte": rep.get("porte") if valide else None,
            "categorie": rep.get("categorie") if valide else None,
            "publication": bool(str(rep.get("publication") or "").strip()) if valide and not court
            else False,
            "latence_s": m.get("latence_s"), "tokens_entree": m.get("tokens_entree"),
            "tokens_sortie": m.get("tokens_sortie"), "brut": (client.dernier_brut or "")[:600]}


def passe(client, notes, court, chemin_cache):
    """Une passe complete, reprise possible : le cache garde chaque reponse."""
    fait = {}
    if os.path.exists(chemin_cache):
        for l in open(chemin_cache, encoding="utf-8"):
            r = json.loads(l)
            fait[(r["agent"], r["t"])] = r
    with open(chemin_cache, "a", encoding="utf-8") as f:
        for i, n in enumerate(notes):
            if (n["agent"], n["t"]) in fait:
                continue
            r = appeler(client, n, court)
            fait[(r["agent"], r["t"])] = r
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"    {'C' if court else 'A'}' {i + 1}/{len(notes)}", flush=True)
    return [fait[(n["agent"], n["t"])] for n in notes]


def resume_cout(resultats):
    ok = [r for r in resultats if r["latence_s"] is not None]
    par = {}
    for t in LLM:
        x = [r for r in ok if r["taille"] == t]
        if x:
            par[t] = {"n": len(x), "latence_mediane_s": statistics.median(r["latence_s"] for r in x),
                      "latence_p95_s": sorted(r["latence_s"] for r in x)[int(0.95 * (len(x) - 1))],
                      "latence_totale_s": sum(r["latence_s"] for r in x),
                      "tokens_sortie_moyen": statistics.mean(r["tokens_sortie"] for r in x),
                      "tokens_entree_moyen": statistics.mean(r["tokens_entree"] for r in x)}
    lat = sorted(r["latence_s"] for r in ok)
    return {"appels": len(resultats), "valides": sum(r["valide"] for r in resultats),
            "latence_mediane_s": statistics.median(lat), "latence_p95_s": lat[int(0.95 * (len(lat) - 1))],
            "latence_totale_s": sum(lat), "tokens_sortie_total": sum(r["tokens_sortie"] for r in ok),
            "tokens_entree_total": sum(r["tokens_entree"] for r in ok), "par_taille": par}


def evaluer_c(evs, notes, dist, nom):
    tete = evs[0]
    client = ClientLLM("ollama", MODELES, pause=0.0, temperature=tete.get("temperature", 0.9),
                       graine=tete["graine"])
    empreintes = client.empreintes()
    os.makedirs(SORTIE, exist_ok=True)
    print(f"  {nom} : passe A' (prompt original, {len(notes)} appels)", flush=True)
    a = passe(client, notes, False, os.path.join(SORTIE, f"{nom}.a_prime.jsonl"))
    print(f"  {nom} : passe C' (sortie courte, {len(notes)} appels)", flush=True)
    c = passe(client, notes, True, os.path.join(SORTIE, f"{nom}.c_prime.jsonl"))
    out = {"modeles": empreintes, "cout": {"A_prime": resume_cout(a), "C_prime": resume_cout(c)}}
    for cle, res in (("A_prime", a), ("C_prime", c)):
        paires = [(r, n["original"]) for r, n in zip(res, notes)
                  if r["valide"] and n["original"]["valide"]]
        remplace = {(r["agent"], r["t"]): ({"porte": r["porte"], "categorie": r["categorie"]}
                                           if r["valide"] else
                                           {"porte": n["original"]["porte"],
                                            "categorie": n["original"]["categorie"], "valide": False})
                    for r, n in zip(res, notes)}
        out[cle] = {"accord_avec_original": accord(paires),
                    "invalides": sum(not r["valide"] for r in res),
                    "publications_produites": sum(r["publication"] for r in res),
                    "effets": mesures(substituer(evs, remplace), dist)}
    paires = [(c_, a_) for c_, a_ in zip(c, a) if c_["valide"] and a_["valide"]]
    out["accord_C_prime_avec_A_prime"] = accord(paires)
    out["publications_originales"] = sum(n["publication_originale"] for n in notes)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--llm", action="store_true", help="evaluation C' : NOUVEAUX appels Qwen")
    args = p.parse_args()
    dist = emergence.distributions()
    os.makedirs(SORTIE, exist_ok=True)
    for chemin in args.runs:
        nom = os.path.basename(chemin)[:-6]
        t0 = time.perf_counter()
        evs, notes, fidele = reconstruire(chemin)
        print(f"{nom} : {len(notes)} decisions LLM reconstruites, monde rejoue "
              f"{'identique' if fidele else 'DIFFERENT : run ecarte'}", flush=True)
        if not fidele:
            continue
        res = {"run": nom, "fidele": fidele, "graine": evs[0]["graine"],
               "prompt_identique_au_gabarit": all(DEBUT_SORTIE in n["consigne"] for n in notes)}
        if args.llm:
            enrichir(notes)
            res["C_prime"] = evaluer_c(evs, notes, dist, nom)
            cible = os.path.join(SORTIE, f"{nom}.c_prime.json")
        else:
            res["B"] = evaluer_b(evs, notes, dist)
            cible = os.path.join(SORTIE, f"{nom}.b.json")
        res["duree_s"] = round(time.perf_counter() - t0, 1)
        with open(cible, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print(f"  -> {cible}")


if __name__ == "__main__":
    sys.exit(main())
