"""Verifications du reseau social v2 (etape 3), sans appel LLM.

    python3 tests/test_reseau.py
"""
import os
import statistics
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import population_v2, reseau
from ephemere.contrat import verifier as conforme
from ephemere.graines import graines

CONFIG = os.path.join(RACINE, "config", "tessaline_v2.json")
REGLAGE = population_v2.charger(CONFIG)["reseau"]
echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def monde(r, n=20, cloisonne=False, **autres):
    g = graines(r, **autres)
    agents, _ = population_v2.construire(CONFIG, n, g)
    return agents, reseau.construire(agents, REGLAGE, g["reseau"], cloisonne=cloisonne)


print("Reproductibilite et independance des flux")
a, l = monde(4)
verifier("meme r, meme reseau", monde(4)[1] == l)
verifier("autre graine de reseau, meme population, autre reseau",
         monde(4, reseau=8)[0] == a and monde(4, reseau=8)[1] != l)
verifier("autres evenements et dynamique, meme reseau",
         monde(4, evenements=8, dynamique=8)[1] == l)

print("\nForme des liens")
groupe = {x["id"]: x["groupe"] for x in a}
cles = [(x["a"], x["b"]) for x in l]
verifier("ni boucle ni doublon",
         all(x["a"] != x["b"] for x in l) and len(set(map(frozenset, cles))) == len(cles))
verifier("liens forts dans le groupe, poids 1,0",
         all(groupe[x["a"]] == groupe[x["b"]] and x["poids"] == REGLAGE["poids_fort"]
             for x in l if x["type"] == "fort"))
verifier("liens faibles entre groupes, poids 0,3",
         all(groupe[x["a"]] != groupe[x["b"]] and x["poids"] == REGLAGE["poids_faible"]
             for x in l if x["type"] == "faible"))
v = reseau.voisins(l)
verifier("voisins symetriques", all(v[y][x] == p for x in v for y, p in v[x].items()))

print("\nSur 200 graines")
mesures = {}
for n in (20, 50, 100):
    rs = []
    for r in range(200):
        agents, liens = monde(r, n=n)
        faibles = reseau.voisins([x for x in liens if x["type"] == "faible"])
        rs.append({**reseau.resume(agents, liens),
                   "sans_pont": sum(1 for x in agents if not faibles[x["id"]])})
    mesures[n] = {k: statistics.mean(x[k] for x in rs) for k in rs[0]}
    mesures[n]["connexe"] = sum(x["composantes"] == 1 for x in rs) / len(rs)
    m = mesures[n]
    print(f"  --   {n:3d} agents : {m['liens']:.1f} liens, degre fort {m['degre_fort_moyen']:.2f}, "
          f"faible {m['degre_faible_moyen']:.2f}, connexe {m['connexe']:.0%}")
    verifier(f"{n} agents : aucun isole, chacun a au moins un pont",
             m["isoles"] == 0 and m["sans_pont"] == 0)
    verifier(f"{n} agents : reseau connexe dans au moins 95 % des graines", m["connexe"] >= 0.95)
for cle in ("degre_fort_moyen", "degre_faible_moyen"):
    valeurs = [mesures[n][cle] for n in mesures]
    verifier(f"{cle} a peu pres constant a 20, 50 et 100 (ecart {max(valeurs) - min(valeurs):.2f})",
             max(valeurs) - min(valeurs) <= 0.3)

print("\nVariante cloisonnee")
_, c = monde(4, cloisonne=True)
verifier("aucun lien entre groupes", all(groupe[x["a"]] == groupe[x["b"]] for x in c))
verifier("memes liens forts que le reseau normal, sans les ponts",
         c == [x for x in l if x["type"] == "fort"])

print("\nContrat")
evt = {"schema": "reseau.v1", "run": "test", "t_sim": 0, "t_sim_lisible": "J01 00:00",
       "t_emission": "2026-10-27T00:00:00.000", "t_traitement": None,
       "liens": l, "resume": reseau.resume(a, l), "cloisonne": False}
verifier("reseau.v1 conforme au contrat", conforme(evt) == (True, None), conforme(evt))

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
