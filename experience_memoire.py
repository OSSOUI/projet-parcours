"""Experience memoire : la reference gelee (A) contre le sens de la veille (E), 10 graines.

Protocole : resultats/PROTOCOLE_MEMOIRE.md. Ce fichier et le protocole sont geles
avant le premier run (empreintes dans resultats/memoire_gel.json) : le lancement
refuse de partir si l'un des deux a change depuis.

    python3 experience_memoire.py --plan          # runs prevus, cout, ce qui existe deja
    python3 experience_memoire.py --geler         # ecrit les empreintes (une seule fois)
    python3 experience_memoire.py --lancer        # runs manquants, dans l'ordre fixe, reprise possible
    python3 experience_memoire.py --analyser      # analyses fixees d'avance, une fois les 10 paires completes

Pendant le lancement, seuls des controles techniques sont affiches (run complet,
modeles, consigne, part des prompts qui montrent le sens) : aucune mesure de
resultat avant que les 10 paires soient la.
"""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import math
import os
import random
import shutil
import statistics
import sys
import time
import types
import urllib.request

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import emergence  # noqa: E402
import experience  # noqa: E402
from ephemere import indicateurs as I  # noqa: E402

RUNS = os.path.join(RACINE, "runs")
PROTOCOLE = os.path.join(RACINE, "resultats", "PROTOCOLE_MEMOIRE.md")
GEL = os.path.join(RACINE, "resultats", "memoire_gel.json")
LANCEMENT = os.path.join(RACINE, "resultats", "memoire_lancement.json")
SORTIE = os.path.join(RACINE, "resultats", "memoire_experience.json")

GRAINES = list(range(100, 110))
# A des graines 100 a 104 : la serie de reference gelee du 3 novembre, telle quelle.
A_GELES = {100 + i: f"exp_reference_llm_reference_{i + 1:02d}" for i in range(5)}
# Options de A : celles de la reference, lues dans experience.py pour ne pas les recopier.
OPTIONS_A = list(experience.CONFIGURATIONS["llm_reference"]["options"])
# E : la meme chose, plus le sens de la veille, plus l'ombre sans_souvenirs (une ombre
# ne touche pas au monde : verifier_comparabilite.py le montre sur les 5 runs geles).
assert OPTIONS_A[-3:] == ["--ombres", "sans_discours", "sans_social"]
OPTIONS_E = OPTIONS_A + ["sans_souvenirs", "--memoire-sens"]
COMMUNES = types.SimpleNamespace(agents=20, jours=25, fournisseur="ollama", pause=0.0)
MODELES = {"qwen2.5:7b": "845dbda0ea48", "qwen2.5:3b": "357c53fb659c"}
EMPREINTE_CONSIGNE = "ceb1fc47a4f9"
# Ordre fixe : chaque nouvelle graine en A puis en E, entrelacees avec E des graines gelees.
ORDRE = [x for k in range(5) for x in (("A", 105 + k), ("E", 105 + k), ("E", 100 + k))]
# Cout mesure sur la reference : 3,50 s par appel (2 268 a 2 999 s pour 636 a 861 appels).
S_PAR_APPEL = 3.50
PERMUTATIONS = 1000            # ombres, par agent (comme emergence.py)
ENUMERATION_MAX = 2 ** 18      # au-dela, permutation par agent tiree au hasard
T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
         9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145}
LLM = ("llm_petit", "llm_grand")


def nom_run(condition, graine):
    if condition == "A" and graine in A_GELES:
        return A_GELES[graine]
    return f"exp_memoire_{condition}_g{graine}"


def chemin_run(condition, graine):
    return os.path.join(RUNS, nom_run(condition, graine) + ".jsonl")


def empreinte(chemin):
    with open(chemin, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


# --- controles techniques (pendant le lancement) ------------------------------------

def controler(chemin, condition, graine):
    """Ce qui rend un run recevable, sans rien mesurer de son resultat."""
    evs = lire(chemin)
    tete, fin = evs[0], evs[-1]
    modeles = {m["modele"]: m["empreinte"] for m in (tete.get("modeles") or {}).values()}
    perceptions = [e for e in evs if e["schema"] == "perception.v1"]
    avec_sens = sum(any("sens_affiche" in s for s in p["souvenirs"]) for p in perceptions)
    avec_decision = sum(any(s["genre"] == "decision" for s in p["souvenirs"]) for p in perceptions)
    ombres = OPTIONS_E[OPTIONS_E.index("--ombres") + 1:-1] if condition == "E" else \
        OPTIONS_A[OPTIONS_A.index("--ombres") + 1:]
    ecarts = []
    if fin["schema"] != "bilan.v1" or fin.get("interrompu"):
        ecarts.append("run incomplet ou interrompu")
    if tete.get("graine") != graine:
        ecarts.append(f"graine {tete.get('graine')}")
    if (tete.get("nb_agents"), tete.get("jours"), tete.get("mode")) != (20, 25, "synchrone"):
        ecarts.append("taille, duree ou mode")
    if modeles != MODELES:
        ecarts.append(f"modeles {modeles}")
    if tete.get("empreinte_prompt") != EMPREINTE_CONSIGNE:
        ecarts.append(f"consigne {tete.get('empreinte_prompt')}")
    if tete.get("temperature") != 0.9 or tete.get("sortie_structuree") or \
            tete.get("definitions") != "courtes" or (tete.get("conversation") or {}).get("par_jour"):
        ecarts.append("parametres du modele")
    if list(tete.get("ombres") or []) != ombres:
        ecarts.append(f"ombres {tete.get('ombres')}")
    if bool(tete.get("memoire_sens")) != (condition == "E"):
        ecarts.append(f"memoire_sens {tete.get('memoire_sens')}")
    if condition == "A" and avec_sens:
        ecarts.append("sens affiche dans un run A")
    return {"run": os.path.basename(chemin)[:-6], "condition": condition, "graine": graine,
            "recevable": not ecarts, "ecarts": ecarts,
            "decisions_llm": len(perceptions),
            "prompts_avec_sens_sur_prompts_avec_decision": [avec_sens, avec_decision],
            "appels": fin.get("appels"), "duree_s": fin.get("duree_run_s"),
            "incidents": fin.get("incidents"), "empreinte": empreinte(chemin)}


def modeles_ollama():
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=10) as r:
        return {m["name"]: m["digest"][:12] for m in json.load(r)["models"]}


# --- mesures ---------------------------------------------------------------------------

def decisions(evs):
    """Agents LLM, leurs decisions dans l'ordre, et les ombres par masque."""
    pop = {a["id"] for e in evs if e["schema"] == "population.v1"
           for a in e["agents"] if a["moteur"] in LLM}
    dec = [(e["agent"], e["t_sim"], e["valide"], e["categorie"], e["porte"])
           for e in evs if e["schema"] == "decision.v1" and e["agent"] in pop]
    ombres = {}
    for e in evs:
        if e["schema"] == "ombre.v1" and e["agent"] in pop:
            ombres.setdefault(e["masque"], {})[(e["agent"], e["t_decision"])] = e
    return pop, dec, ombres


def gardes_par_agent(dec, cle=3):
    """Pour chaque agent : (gardes, paires) d'une decision valide a la suivante.

    cle=3 : le sens (critere principal). cle=4 : le port du ruban (secondaire).
    Une decision en incident n'est ni comptee ni prise comme reference.
    """
    prec, compte = {}, {}
    for d in dec:
        agent, valide = d[0], d[2]
        if not valide:
            continue
        g, n = compte.get(agent, (0, 0))
        if agent in prec:
            compte[agent] = (g + (prec[agent] == d[cle]), n + 1)
        prec[agent] = d[cle]
    return compte


def taux(compte):
    g = sum(v[0] for v in compte.values())
    n = sum(v[1] for v in compte.values())
    return g / n if n else None


def persistance_corrigee(dec):
    """Persistance moins celle qu'on attendrait si l'agent tirait ses sens au hasard
    dans sa propre distribution du run (somme des p_k au carre)."""
    par_agent = {}
    for d in dec:
        if d[2]:
            par_agent.setdefault(d[0], []).append(d[3])
    compte = gardes_par_agent(dec)
    attendu = 0.0
    for agent, (_, n) in compte.items():
        sens = par_agent[agent]
        attendu += n * sum((sens.count(s) / len(sens)) ** 2 for s in set(sens))
    n = sum(v[1] for v in compte.values())
    return (sum(v[0] for v in compte.values()) - attendu) / n if n else None


def permutation_agents(valeurs, statistique, graine=0):
    """p unilaterale d'une permutation par agent : chaque agent echange ses deux
    cotes d'un bloc (toutes ses decisions ensemble). Exacte si 2^n est petit.

    valeurs : liste, par agent, de (cote1, cote2) ; statistique(liste) -> nombre.
    """
    observe = statistique(valeurs)
    n = len(valeurs)
    if 2 ** n <= ENUMERATION_MAX:
        tirages = itertools.product((False, True), repeat=n)
        total, methode = 2 ** n, "exacte"
    else:
        rng = random.Random(graine)
        tirages = ([rng.random() < 0.5 for _ in range(n)] for _ in range(PERMUTATIONS))
        total, methode = PERMUTATIONS, "tiree"
    au_moins = 0
    for echange in tirages:
        v = [(b, a) if e else (a, b) for (a, b), e in zip(valeurs, echange)]
        au_moins += statistique(v) >= observe - 1e-12
    p = au_moins / total if methode == "exacte" else (1 + au_moins) / (1 + total)
    return {"observe": observe, "p": p, "methode": methode, "agents": n}


def ecart_taux(valeurs):
    """Ecart de taux poole : cote2 - cote1, chaque cote etant (gardes, paires)."""
    g1 = sum(v[0][0] for v in valeurs)
    n1 = sum(v[0][1] for v in valeurs)
    g2 = sum(v[1][0] for v in valeurs)
    n2 = sum(v[1][1] for v in valeurs)
    return (g2 / n2 if n2 else 0.0) - (g1 / n1 if n1 else 0.0)


def usage_memoire(dec, ombre):
    """HE3 : garder le sens precedent, decision reelle contre ombre sans_souvenirs.

    Par agent : (gardes de l'ombre, paires), (gardes du reel, paires), sur les seules
    decisions dont le reel et l'ombre sont valides et qui ont une decision valide avant.
    """
    prec, compte = {}, {}
    for agent, t, valide, cat, _ in dec:
        if not valide:
            continue
        o = ombre.get((agent, t))
        if agent in prec and o and o["valide"] and o["reel_valide"]:
            (go, no), (gr, nr) = compte.get(agent, ((0, 0), (0, 0)))
            compte[agent] = ((go + (o["categorie"] == prec[agent]), no + 1),
                             (gr + (cat == prec[agent]), nr + 1))
        prec[agent] = cat
    return compte


def ecart_ombres_par_agent(paires, releves, regroupement, graine=0):
    """Ecart d'accord reel - ombre (comme indicateurs.ecart_ombres), mais la
    permutation echange reel et ombre par AGENT, toutes ses decisions ensemble."""
    reel, ombre = I._series(paires, releves)
    observe, n = I._ecart_moyen(reel, ombre, regroupement)
    if observe is None:
        return {"ecart": None, "p": None}
    agents = sorted({p[0] for p in paires})
    rng = random.Random(graine)
    au_moins = 0
    for _ in range(PERMUTATIONS):
        choisis = {a for a in agents if rng.random() < 0.5}
        echanges = {i for i, p in enumerate(paires) if p[0] in choisis}
        e, _ = I._ecart_moyen(*I._series(paires, releves, echanges), regroupement)
        au_moins += e is not None and e >= observe
    return {"ecart": observe, "p": (1 + au_moins) / (1 + PERMUTATIONS), "releves": n}


def test_signes(succes, n):
    """p unilaterale exacte : P(X >= succes) pour X ~ Binomiale(n, 1/2)."""
    return sum(math.comb(n, k) for k in range(succes, n + 1)) / 2 ** n


def wilcoxon(ecarts):
    """Rangs signes, p unilaterale exacte (ecart > 0), zeros retires, rangs moyens."""
    x = [e for e in ecarts if e != 0]
    if not x:
        return None
    ordre = sorted(range(len(x)), key=lambda i: abs(x[i]))
    rangs = [0.0] * len(x)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and abs(x[ordre[j + 1]]) == abs(x[ordre[i]]):
            j += 1
        for k in range(i, j + 1):
            rangs[ordre[k]] = (i + j) / 2 + 1
        i = j + 1
    w = sum(r for r, e in zip(rangs, x) if e > 0)
    au_moins = sum(1 for signes in itertools.product((0, 1), repeat=len(x))
                   if sum(r for r, s in zip(rangs, signes) if s) >= w - 1e-12)
    return {"w_plus": w, "n": len(x), "p": au_moins / 2 ** len(x)}


def resume_apparie(ecarts):
    n = len(ecarts)
    m = statistics.mean(ecarts)
    s = statistics.stdev(ecarts) if n > 1 else None
    demi = T_975[n - 1] * s / math.sqrt(n) if s is not None else None
    return {"n": n, "ecart_moyen": m, "ecart_type": s,
            "ic95": [m - demi, m + demi] if demi is not None else None,
            "dz": m / s if s else None, "mediane": statistics.median(ecarts)}


def mesurer_run(chemin, dist):
    evs = lire(chemin)
    pop, dec, ombres = decisions(evs)
    sens = gardes_par_agent(dec)
    port = gardes_par_agent(dec, cle=4)
    with contextlib.redirect_stdout(io.StringIO()):
        em = emergence.analyser(chemin, dist, PERMUTATIONS)
    _, _, etats, paires = emergence.lire(chemin)
    h6 = {m: {lec: ecart_ombres_par_agent(paires[m], len(etats), reg)
              for lec, reg in emergence.LECTURES.items()} for m in paires}
    r = {"run": os.path.basename(chemin)[:-6], "agents_llm": len(pop),
         "persistance_sens": taux(sens), "paires": sum(v[1] for v in sens.values()),
         "par_agent": sens, "persistance_corrigee": persistance_corrigee(dec),
         "persistance_port": taux(port), "persistance_releves": em["persistance"],
         "incidents": sum(1 for d in dec if not d[2]), "decisions": len(dec),
         "emergence": em["seuil_persistance"], "ombres_paires": em["ombres"],
         "ombres_par_agent": h6}
    if "sans_souvenirs" in ombres:
        u = usage_memoire(dec, ombres["sans_souvenirs"])
        r["usage_memoire"] = {
            "garde_reel": taux({a: v[1] for a, v in u.items()}),
            "garde_ombre_sans_souvenirs": taux({a: v[0] for a, v in u.items()}),
            "paires": sum(v[1][1] for v in u.values()),
            "test": permutation_agents([u[a] for a in sorted(u)], ecart_taux)}
    return r


def analyser(graines=GRAINES):
    dist = emergence.distributions()
    par_graine = []
    for g in graines:
        a, e = mesurer_run(chemin_run("A", g), dist), mesurer_run(chemin_run("E", g), dist)
        agents = sorted(set(a["par_agent"]) & set(e["par_agent"]))
        intra = permutation_agents([(a["par_agent"][x], e["par_agent"][x]) for x in agents],
                                   ecart_taux)
        par_graine.append({"graine": g, "A": a, "E": e,
                           "ecart_persistance": e["persistance_sens"] - a["persistance_sens"],
                           "e_superieur": e["persistance_sens"] > a["persistance_sens"],
                           "permutation_par_agent": intra})
    n = len(par_graine)
    succes = sum(x["e_superieur"] for x in par_graine)
    ecarts = [x["ecart_persistance"] for x in par_graine]

    def secondaire(cle):
        v = [x["E"][cle] - x["A"][cle] for x in par_graine
             if x["E"][cle] is not None and x["A"][cle] is not None]
        return {**resume_apparie(v), "e_superieur": sum(1 for d in v if d > 0), "wilcoxon": wilcoxon(v)}

    usage = [x["E"]["usage_memoire"] for x in par_graine if "usage_memoire" in x["E"]]
    ecarts_usage = [u["test"]["observe"] for u in usage]
    principal = {
        "critere": "persistance du sens E > A dans au moins 9 graines sur 10",
        "graines_e_superieur": succes, "graines": n,
        "p_signes_unilaterale": test_signes(succes, n),
        "atteint": n == 10 and succes >= 9,
        "taille_effet": resume_apparie(ecarts),
        "wilcoxon": wilcoxon(ecarts),
    }
    lots = {}
    for nom, gs in (("graines_100_104", range(100, 105)), ("graines_105_109", range(105, 110))):
        v = [x["ecart_persistance"] for x in par_graine if x["graine"] in gs]
        if len(v) > 1:
            lots[nom] = {**resume_apparie(v), "e_superieur": sum(1 for d in v if d > 0)}
    return {
        "protocole": os.path.relpath(PROTOCOLE, RACINE),
        "gel": json.load(open(GEL, encoding="utf-8")) if os.path.exists(GEL) else None,
        "principal": principal,
        "secondaires": {
            "S1_persistance_corrigee": secondaire("persistance_corrigee"),
            "S2_persistance_releves": secondaire("persistance_releves"),
            "S3_persistance_port": secondaire("persistance_port"),
            "S4_usage_memoire_E": {**resume_apparie(ecarts_usage),
                                   "runs_ecart_positif": sum(1 for d in ecarts_usage if d > 0),
                                   "p_signes_unilaterale": test_signes(
                                       sum(1 for d in ecarts_usage if d > 0), len(ecarts_usage))}
            if len(ecarts_usage) > 1 else None,
            "S5_par_lot": lots,
        },
        "par_graine": par_graine,
    }


# --- affichage -------------------------------------------------------------------------

def _pc(x, signe=False):
    return "n/a" if x is None else (f"{x * 100:+.1f}" if signe else f"{x * 100:.1f}")


def afficher(r):
    p = r["principal"]
    t = p["taille_effet"]
    print("CRITERE PRINCIPAL (fixe avant les runs) :", p["critere"])
    print(f"  E > A dans {p['graines_e_superieur']}/{p['graines']} graines, test des signes "
          f"unilateral p = {p['p_signes_unilaterale']:.4f} -> "
          + ("ATTEINT" if p["atteint"] else "NON ATTEINT"))
    print(f"  ecart moyen E - A : {_pc(t['ecart_moyen'], True)} points, IC 95 % "
          + (f"[{_pc(t['ic95'][0], True)} ; {_pc(t['ic95'][1], True)}]" if t["ic95"] else "n/a")
          + (f", dz = {t['dz']:.2f}" if t["dz"] is not None else "")
          + (f", Wilcoxon p = {p['wilcoxon']['p']:.4f}" if p["wilcoxon"] else ""))
    print("\nPAR GRAINE   pers. A  pers. E   E-A   p(agents)  corr.A corr.E  "
          "six sens A/E      regroupe A/E      usage memoire E (reel-ombre, p)")
    for x in r["par_graine"]:
        a, e = x["A"], x["E"]
        em = lambda c, l: ("emerg." if c["emergence"][l].get("emergent") else "non") + \
            f" {_pc(c['emergence'][l].get('delta_a'), True)}"
        u = e.get("usage_memoire")
        print(f"  {x['graine']}      {_pc(a['persistance_sens'])}    {_pc(e['persistance_sens'])}  "
              f"{_pc(x['ecart_persistance'], True):>6s}   {x['permutation_par_agent']['p']:.3f}    "
              f"{_pc(a['persistance_corrigee'], True):>5s}  {_pc(e['persistance_corrigee'], True):>5s}  "
              f"{em(a, 'six_sens'):>8s}/{em(e, 'six_sens'):<8s} {em(a, 'regroupe'):>8s}/{em(e, 'regroupe'):<8s}"
              + (f"  {_pc(u['test']['observe'], True)} (p {u['test']['p']:.3f})" if u else ""))
    print("\nSECONDAIRES (E - A par graine, sauf S4)")
    for nom, s in r["secondaires"].items():
        if not s or nom == "S5_par_lot":
            continue
        print(f"  {nom:26s} moyenne {_pc(s['ecart_moyen'], True)} points, IC 95 % "
              + (f"[{_pc(s['ic95'][0], True)} ; {_pc(s['ic95'][1], True)}]" if s["ic95"] else "n/a")
              + f", positif dans {s.get('e_superieur', s.get('runs_ecart_positif'))}/{s['n']}")
    for lot, s in r["secondaires"]["S5_par_lot"].items():
        print(f"  S5 {lot:22s} moyenne {_pc(s['ecart_moyen'], True)} points, "
              f"E > A dans {s['e_superieur']}/{s['n']}")


# --- plan, gel, lancement --------------------------------------------------------------

def plan():
    print(f"A : {' '.join(OPTIONS_A)}")
    print(f"E : {' '.join(OPTIONS_E)}")
    print(f"communes : --agents {COMMUNES.agents} --jours {COMMUNES.jours} "
          f"--fournisseur {COMMUNES.fournisseur} --pause {COMMUNES.pause} --graine <g>\n")
    for g in GRAINES:
        for c in "AE":
            ch = chemin_run(c, g)
            etat = "gele (reference)" if c == "A" and g in A_GELES else \
                ("present" if os.path.exists(ch) else "a produire")
            print(f"  {c} graine {g} : {os.path.basename(ch):42s} {etat}")


def geler():
    if os.path.exists(GEL):
        raise SystemExit(f"{GEL} existe deja : le protocole est gele, on ne le reecrit pas.")
    gel = {"date": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "fichiers": {os.path.relpath(f, RACINE): empreinte(f)
                        for f in (PROTOCOLE, os.path.abspath(__file__))},
           "references_A": {str(g): empreinte(chemin_run("A", g)) for g in A_GELES}}
    with open(GEL, "w", encoding="utf-8") as f:
        json.dump(gel, f, ensure_ascii=False, indent=1)
    print(json.dumps(gel, indent=1))


def verifier_gel():
    if not os.path.exists(GEL):
        raise SystemExit("Protocole non gele : lancer --geler d'abord.")
    gel = json.load(open(GEL, encoding="utf-8"))
    for rel, h in {**gel["fichiers"]}.items():
        if empreinte(os.path.join(RACINE, rel)) != h:
            raise SystemExit(f"{rel} a change depuis le gel du {gel['date']} : arret.")
    for g, h in gel["references_A"].items():
        if empreinte(chemin_run("A", int(g))) != h:
            raise SystemExit(f"le run de reference de la graine {g} a change : arret.")
    return gel


def lancer():
    verifier_gel()
    journal = json.load(open(LANCEMENT, encoding="utf-8")) if os.path.exists(LANCEMENT) else []
    for condition, graine in ORDRE:
        ch = chemin_run(condition, graine)
        if os.path.exists(ch):
            c = controler(ch, condition, graine)
            if c["recevable"]:
                print(f"{condition} {graine} deja la ({c['run']})")
                continue
            # Run rate : on le garde a cote (rien n'est supprime) et on le relance une fois.
            ecarte = ch[:-6] + f".echec_{time.strftime('%H%M%S')}.jsonl"
            shutil.move(ch, ecarte)
            journal.append({"condition": condition, "graine": graine, "ecarte": ecarte,
                            "ecarts": c["ecarts"]})
            if sum(1 for j in journal if j.get("graine") == graine and
                   j.get("condition") == condition and "ecarte" in j) > 1:
                raise SystemExit(f"{condition} {graine} a echoue deux fois : arret, a examiner.")
        if modeles_ollama().get("qwen2.5:7b") != MODELES["qwen2.5:7b"] or \
                modeles_ollama().get("qwen2.5:3b") != MODELES["qwen2.5:3b"]:
            raise SystemExit("Les poids des modeles Ollama ont change : arret.")
        options = (OPTIONS_A if condition == "A" else OPTIONS_E) + ["--graine", str(graine)]
        print(f"{time.strftime('%H:%M')} {condition} graine {graine} -> {os.path.basename(ch)}",
              flush=True)
        chemin, duree = experience.lancer(nom_run(condition, graine), options, COMMUNES)
        c = controler(ch, condition, graine) if chemin and os.path.exists(ch) else \
            {"run": nom_run(condition, graine), "recevable": False, "ecarts": ["echec du lancement"]}
        c["duree_mur_s"] = round(duree)
        journal.append(c)
        with open(LANCEMENT, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=1)
        sens = c.get("prompts_avec_sens_sur_prompts_avec_decision")
        print(f"      {'recevable' if c['recevable'] else 'NON RECEVABLE ' + str(c['ecarts'])}, "
              f"{c.get('appels')} appels, {c.get('incidents')} incidents, {duree / 60:.0f} min"
              + (f", sens montre dans {sens[0]}/{sens[1]} prompts" if condition == "E" and sens else ""),
              flush=True)
        if not c["recevable"]:
            raise SystemExit("run non recevable : arret, a examiner avant de continuer.")
    print("Les 10 paires sont completes.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--geler", action="store_true")
    g.add_argument("--lancer", action="store_true")
    g.add_argument("--analyser", action="store_true")
    g.add_argument("--controler", action="store_true",
                   help="controles techniques des runs presents, sans aucune mesure de resultat")
    p.add_argument("--json", default=SORTIE)
    args = p.parse_args()
    if args.plan:
        return plan()
    if args.geler:
        return geler()
    if args.lancer:
        return lancer()
    if args.controler:
        for c, g in [("A", g) for g in GRAINES] + [("E", g) for g in GRAINES]:
            if os.path.exists(chemin_run(c, g)):
                r = controler(chemin_run(c, g), c, g)
                print(f"{c} {g} {'recevable' if r['recevable'] else r['ecarts']}")
        return
    gel = verifier_gel()
    manquants = [(c, g) for g in GRAINES for c in "AE"
                 if not os.path.exists(chemin_run(c, g)) or not controler(chemin_run(c, g), c, g)["recevable"]]
    if manquants:
        raise SystemExit(f"Analyse refusee : paires incompletes {manquants}. Le protocole "
                         "ne prevoit aucune analyse intermediaire.")
    r = analyser()
    r["gel"] = gel
    afficher(r)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(f"\necrit dans {args.json}")


if __name__ == "__main__":
    sys.exit(main())
