"""Verifications du monde v2 : observation et canaux (etape 4), sans appel LLM.

    python3 tests/test_monde_v2.py
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import population_v2, reseau
from ephemere.contrat import verifier as conforme
from ephemere.graines import graines
from ephemere.monde_v2 import AccesInterdit, MondeV2, exposition

CONFIG = os.path.join(RACINE, "config", "tessaline_v2.json")
CFG = population_v2.charger(CONFIG)
echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def monde(r=2, cloisonne=False, canal_public=True, **autres):
    g = graines(r, **autres)
    agents, _ = population_v2.construire(CONFIG, 20, g)
    liens = reseau.construire(agents, CFG["reseau"], g["reseau"], cloisonne=cloisonne)
    return MondeV2(agents, liens, CFG["observation"], g["dynamique"],
                   cloisonne=cloisonne, canal_public=canal_public)


def interdit(f):
    try:
        f()
        return False
    except AccesInterdit:
        return True


print("Ce que l'agent ne peut plus connaitre")
m = monde()
ines = m.agents["ines"]
verifier("adoption_percue refusee", interdit(lambda: m.adoption_percue(ines)))
verifier("porteurs_du_groupe refuse", interdit(lambda: m.porteurs_du_groupe(ines)))
verifier("meneurs_porteurs refuse", interdit(lambda: m.meneurs_porteurs()))
verifier("le taux reste calcule pour l'observateur", 0 < m.taux_adoption() < 1)

print("\nObservation")
for aid in sorted(m.agents):
    a = m.agents[aid]
    vu = m.observer(a, 1440)["observations"]
    qui = [o["qui"] for o in vu]
    reseau_vu = {o["qui"] for o in vu if o["via"] in ("fort", "faible")}
    croises = [o for o in vu if o["via"] == "lieu"]
    ok = (aid not in qui and len(qui) == len(set(qui))
          and reseau_vu == set(m.voisins[aid])
          and all(m.agents[o["qui"]]["groupe"] == a["groupe"] for o in croises)
          and len(croises) <= CFG["observation"]["croises"][1]
          and all(o["porte"] == m.agents[o["qui"]]["porte"] for o in vu)
          and all(set(o) == {"id", "qui", "groupe", "porte", "via", "poids"} for o in vu))
    if not ok:
        break
verifier("chacun voit tous ses voisins, jamais lui-meme, et 3 croises au plus dans son lieu", ok, aid)
verifier("une observation ne dit pas le sens, seulement le poignet et le groupe",
         all("categorie" not in o and "sens" not in o for o in vu))
ids = [o["id"] for a in m.agents.values() for o in m.observer(a, 2880)["observations"]]
verifier("identifiants d'observation uniques", len(ids) == len(set(ids)))
avant = {a: (x["porte"], x["categorie"]) for a, x in m.agents.items()}
m.observer(ines, 4320)
verifier("observer ne change l'etat de personne",
         avant == {a: (x["porte"], x["categorie"]) for a, x in m.agents.items()})
croises = lambda mm: [o["qui"] for o in mm.observer(mm.agents["ines"], 1440)["observations"]
                      if o["via"] == "lieu"]
verifier("meme graine dynamique, memes personnes croisees", croises(monde()) == croises(monde()))
verifier("exposition ponderee", exposition([
    {"porte": True, "poids": 1.0}, {"porte": False, "poids": 1.0}, {"porte": True, "poids": 0.3}])
    == 1.3 / 2.3)

print("\nConversation")
m = monde()
de = "ines"
voisin = sorted(m.voisins[de])[0]
etranger = next(a for a in sorted(m.agents) if a != de and a not in m.voisins[de])
verifier("message a un voisin delivre",
         m.adresser(de, m.agents[voisin]["nom"], "tu as vu ce ruban ?", 1500, "J02 01:00") is not None)
verifier("message a un non-voisin refuse",
         m.adresser(de, m.agents[etranger]["nom"], "salut", 1500, "J02 01:00") is None)
verifier("pas encore lu avant son envoi (C6)", m.observer(m.agents[voisin], 1440)["messages"] == [])
lus = m.observer(m.agents[voisin], 1600)["messages"]
verifier("lu une fois, avec son id et le type de lien",
         len(lus) == 1 and lus[0]["id"].startswith("m") and lus[0]["lien"] in ("fort", "faible")
         and m.observer(m.agents[voisin], 1700)["messages"] == [])
verifier("le souvenir garde l'id du message",
         any(s.get("source") == lus[0]["id"] for s in m.agents[voisin]["memoire"]))

print("\nCanal public")
m = monde()
pid = m.publier("ines", "photo du ruban", 1500)
lecteur = next(a for a in m.agents.values() if a["id"] != "ines")
verifier("publication future invisible (C6)", m.observer(lecteur, 1440)["publications"] == [])
pubs = m.observer(lecteur, 1600)["publications"]
verifier("publication lue avec son id", [p["id"] for p in pubs] == [pid])
verifier("lue une seule fois", m.observer(lecteur, 1700)["publications"] == [])
coupe = monde(canal_public=False)
verifier("canal coupe : publication refusee", coupe.publier("ines", "photo", 1500) is None)
verifier("canal coupe : aucune publication lue",
         all(coupe.observer(a, 1600)["publications"] == [] for a in coupe.agents.values()))

print("\nCloisonne")
m = monde(cloisonne=True)
for a in m.agents.values():
    m.publier(a["id"], f"message de {a['nom']}", 1500)
    for b in m.agents.values():
        if b["id"] != a["id"]:
            m.adresser(a["id"], b["nom"], "salut", 1500, "J02 01:00")
fuite = []
for a in m.agents.values():
    vu = m.observer(a, 1600)
    groupes = ({o["groupe"] for o in vu["observations"]}
               | {m.agents[x["de"]]["groupe"] for x in vu["messages"]}
               | {m.agents[p["agent"]]["groupe"] for p in vu["publications"]})
    if groupes - {a["groupe"]}:
        fuite.append(a["id"])
verifier("rien ne vient d'un autre groupe, par aucun canal", not fuite, fuite)

print("\nContrat")
vu = monde().observer(ines, 1440)
evt = {"schema": "perception.v2", "run": "test", "t_sim": 1440, "t_sim_lisible": "J02 00:00",
       "t_emission": "2026-10-27T00:00:00.000", "t_traitement": None, "agent": "ines",
       "moteur": "llm_grand", **vu, "souvenirs": [], "documents": []}
verifier("perception.v2 conforme au contrat", conforme(evt) == (True, None), conforme(evt))

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
