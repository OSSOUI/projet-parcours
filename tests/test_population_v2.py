"""Verifications des graines separees et de la population v2, sans appel LLM.

Etape 1 : chaque flux a sa graine, changer l'un ne touche pas les autres.
Etape 2 : les profils fixent des distributions de traits et le moteur, pas
un comportement.

    python3 tests/test_population_v2.py
"""
import os
import statistics
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import population_v2
from ephemere.contrat import ENVELOPPE, verifier as conforme
from ephemere.graines import FLUX, deriver, graines
from ephemere.population import resume

CONFIG = os.path.join(RACINE, "config", "tessaline_v2.json")
echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def pop(r, n=20, **autres):
    return population_v2.construire(CONFIG, n, graines(r, **autres))[0]


print("Etape 1 : graines separees")
g = graines(3)
verifier("cinq flux", set(g) == set(FLUX) | {"moteurs"})
verifier("flux tous differents", len(set(g.values())) == len(g))
verifier("meme r, memes graines", graines(3) == g)
verifier("r change toutes les graines sauf moteurs",
         all(graines(4)[f] != g[f] for f in FLUX) and graines(4)["moteurs"] == g["moteurs"])
autre = graines(3, reseau=7)
verifier("un flux surcharge ne change que lui",
         autre["reseau"] == deriver(7, "reseau")
         and all(autre[f] == g[f] for f in g if f != "reseau"))
code = "from ephemere.graines import graines; print(graines(3))"
sortie = subprocess.run([sys.executable, "-c", code], cwd=RACINE, capture_output=True,
                        text=True, check=True).stdout.strip()
verifier("memes graines dans un autre processus", sortie == str(g))
try:
    graines(0, meteo=1)
    verifier("flux inconnu refuse", False)
except ValueError:
    verifier("flux inconnu refuse", True)

print("\nEtape 1 : la population ne depend que de son flux")
verifier("meme r, meme population", pop(5) == pop(5))
verifier("autre reseau, meme population", pop(5, reseau=9) == pop(5))
verifier("autres evenements et dynamique, meme population",
         pop(5, evenements=9, dynamique=9) == pop(5))
a, b = pop(5), pop(6)
verifier("autre r, autres traits", [x["traits"] for x in a] != [x["traits"] for x in b])
verifier("autre r, memes profils et memes moteurs",
         [(x["id"], x["profil"], x["moteur"]) for x in a]
         == [(x["id"], x["profil"], x["moteur"]) for x in b])

print("\nEtape 2 : traits")
config = population_v2.charger(CONFIG)
tirages = {}
for r in range(1000):
    for x in pop(r):
        tirages.setdefault(x["profil"], []).append(x["traits"])
for profil, ts in sorted(tirages.items()):
    spec = config["profils"][profil]
    for t in population_v2.TRAITS:
        m = statistics.mean(v[t] for v in ts)
        verifier(f"{profil:16s} {t:12s} moyenne {m:.2f} (attendu {spec[t]})",
                 abs(m - spec[t]) < 0.03)
    verifier(f"{profil:16s} seuil dans {spec['seuil']}",
             all(spec["seuil"][0] <= v["seuil"] <= spec["seuil"][1] for v in ts))
tous = [v for ts in tirages.values() for v in ts]
verifier("traits dans [0, 1]",
         all(0 <= v[t] <= 1 for v in tous for t in population_v2.TRAITS))
verifier("affinites dans [-1, 1], une par groupe",
         all(set(v["affinites"]) == set(config["groupes"])
             and all(-1 <= a <= 1 for a in v["affinites"].values()) for v in tous))
fortes = [v["distinction"] for v in tirages["suiveur"] if v["distinction"] > 0.7]
verifier(f"un suiveur peut tirer une forte distinction ({len(fortes)} sur "
         f"{len(tirages['suiveur'])} au-dessus de 0,7)", len(fortes) > 0)
propre = [x["traits"]["affinites"][x["groupe"]] for r in range(200) for x in pop(r)]
verifier(f"affinite moyenne pour son propre groupe {statistics.mean(propre):.2f} > 0",
         statistics.mean(propre) > 0.3)

print("\nEtape 2 : moteurs")
x20 = pop(0)
verifier("le moteur ne depend que du profil",
         all(x["moteur"] in config["profils"][x["profil"]]["moteurs"] for x in x20))
compte = resume(x20)["par_moteur"]
verifier(f"a 20 agents : 4 llm_grand, 6 llm_petit, 10 regles ({compte})",
         compte == {"llm_grand": 4, "llm_petit": 6, "regles": 10})
llm = lambda agents: [x["id"] for x in agents if x["moteur"] != "regles"]
verifier("les memes agents sont LLM a chaque repetition",
         all(llm(pop(r)) == llm(x20) for r in range(50)))
verifier("pionniers a l'atelier et porteurs au depart",
         all(x["groupe"] == "atelier_design" and x["porte"]
             for x in x20 if x["profil"] == "pionnier"))
verifier("cadence quotidienne pour tous", all(x["cadence_min"] == 1440 for x in x20))
verifier("aucune personnalite v1 heritee",
         all(x["personnalite"] == "" for x in x20) and "personnalites" not in config)

print("\nEtape 2 : tailles et contrat")
for n in (50, 100):
    agents = pop(0, n=n)
    par_profil = resume(agents)["par_profil"]
    verifier(f"{n} agents, minimums respectes ({par_profil})",
             len(agents) == n and all(par_profil.get(p, 0) >= s.get("minimum", 0)
                                      for p, s in config["profils"].items()))
    verifier(f"{n} agents, identifiants uniques", len({x["id"] for x in agents}) == n)
evt = {"schema": "population.v2", "run": "test", "t_sim": 0, "t_sim_lisible": "J01 00:00",
       "t_emission": "2026-10-27T00:00:00.000", "t_traitement": None,
       "agents": population_v2.decrire(x20), "resume": resume(x20), "graines": graines(0)}
verifier("population.v2 conforme au contrat", conforme(evt) == (True, None), conforme(evt))
verifier("l'enveloppe n'a pas change", set(ENVELOPPE) <= set(evt))

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
