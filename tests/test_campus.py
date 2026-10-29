"""Verifications du pont : l'etat reconstruit a partir du flux, en v1 et en v2.

La scene Godot n'affiche que ce que Campus lui envoie. Si l'etat reconstruit
est faux, la scene ment ; ce test est donc celui de la visualisation.

    python3 tests/test_campus.py      (quelques secondes : un run v2 de 10 jours)
"""
import json
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere.campus import Campus  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def rejouer(chemin):
    campus = Campus(en_direct=False)
    cle = os.path.basename(chemin).rsplit(".", 1)[0]
    with open(chemin, encoding="utf-8") as f:
        evenements = [json.loads(l) for l in f if l.strip()]
    for e in evenements:
        campus.appliquer(dict(e), cle)
    return campus, evenements


print("Run v1 enregistre")
chemin_v1 = os.path.join(RACINE, "runs", "exp_complet_baseline_01.jsonl")
verifier("le run de reference existe", os.path.exists(chemin_v1), chemin_v1)
if os.path.exists(chemin_v1):
    c, evts = rejouer(chemin_v1)
    dernier = [e for e in evts if e["schema"] == "indicateurs.v1"][-1]
    etat = c.instantane()
    verifier("modele social v1", etat["modele_social"] == "v1")
    verifier("pas de reseau en v1", etat["liens"] == [])
    verifier(f"adoption reconstruite = dernier releve ({dernier['taux_adoption']:.0%})",
             abs(c.indicateurs()["taux_adoption"] - dernier["taux_adoption"]) < 1e-9)
    verifier("l'etat se serialise en JSON", bool(json.dumps(etat, ensure_ascii=False)))

print("\nRun v2")
nom = "_test_campus_v2"
subprocess.run([sys.executable, os.path.join(RACINE, "simuler.py"), "--modele-social", "v2",
                "--tout-regles", "--agents", "20", "--jours", "10", "--graine", "3",
                "--energie", "non", "--nom", nom], check=True, capture_output=True)
try:
    c, evts = rejouer(os.path.join(RACINE, "runs", f"{nom}.jsonl"))
finally:
    for s in (".jsonl", ".direct.jsonl", ".rejets.jsonl"):
        p = os.path.join(RACINE, "runs", nom + s)
        if os.path.exists(p):
            os.remove(p)
etat = c.instantane()
reseau = next(e for e in evts if e["schema"] == "reseau.v1")
verifier("modele social v2", etat["modele_social"] == "v2")
verifier(f"les {len(reseau['liens'])} liens du reseau sont transmis",
         len(etat["liens"]) == len(reseau["liens"]))
verifier("chaque lien relie deux agents connus",
         all(l["a"] in c.agents and l["b"] in c.agents for l in etat["liens"]))
dernier = [e for e in evts if e["schema"] == "indicateurs.v1"][-1]
verifier(f"adoption reconstruite = dernier releve ({dernier['taux_adoption']:.0%})",
         abs(c.indicateurs()["taux_adoption"] - dernier["taux_adoption"]) < 1e-9)
derniere, changement = {}, {}
for e in evts:
    if e["schema"] == "decision.v2":
        derniere[e["agent"]] = e
        if e["sources"]:
            changement[e["agent"]] = e
verifier("chaque agent garde les termes de son dernier score",
         all(c.agents[a]["termes"] == d["termes"] for a, d in derniere.items()))
verifier("croyances transmises (sens percu, confiance)",
         all(c.agents[a]["sens_percu"] == d["sens_percu"]
             and c.agents[a]["confiance"] == d["confiance"] for a, d in derniere.items()))
verifier("traits transmis", all(a["traits"] for a in c.agents.values()))
verifier("ce que l'agent a vu le dernier jour", all(a["vu"] for a in c.agents.values()))
cites = [s for a in c.agents.values() for s in a["sources"]]
toutes = [s for d in evts if d["schema"] == "decision.v2" for s in d["sources"]]
verifier(f"{len(toutes)} sources citees au total dans le run", len(toutes) > 0)
verifier(f"{len(changement)} agents gardent les sources de leur dernier changement d'avis",
         bool(changement) and all([s["id"] for s in c.agents[a]["sources"]] == d["sources"]
                                  and c.agents[a]["sources_quand"] == d["t_sim_lisible"]
                                  for a, d in changement.items()))
verifier("ces sources sont resolues en phrases",
         all(s["texte"] != "(hors fenêtre)" for s in cites), [s for s in cites][:3])
publications = [e for e in evts if e["schema"] == "publication.v2"]
verifier("les publications v2 entrent dans le fil", bool(c.fil) == bool(publications))
prives = [f for f in c.fil if f["portee"] == "personne"]
verifier("un message prive nomme son destinataire",
         all(f["destinataire"] in {a["nom"] for a in c.agents.values()} for f in prives))
jour = max(e["t_sim"] for e in evts if e["schema"] == "perception.v2")
vus = [(e["agent"], o["qui"]) for e in evts if e["schema"] == "perception.v2"
       and e["t_sim"] == jour for o in e["observations"]]
verifier(f"les regards du plan sont ceux du dernier jour ({len(vus)})",
         [(r[0], r[1]) for r in etat["regards"]] == vus)
verifier("un releve de sens par groupe et par jour (B1)",
         len(etat["sens_groupes"]) == len([e for e in evts if e["schema"] == "indicateurs.v1"]))
fin = etat["sens_groupes"][-1]["groupes"]
verifier("le dernier releve compte chaque agent dans son groupe",
         all(fin[g]["total"] == sum(a["groupe"] == g for a in c.agents.values()) for g in fin)
         and all(fin[g]["porteurs"] == sum(a["porte"] for a in c.agents.values() if a["groupe"] == g)
                 for g in fin))
textes = {e["texte"] for e in publications}
verifier("le fil regroupe les messages identiques",
         len({f["texte"] for f in c.fil}) == len(c.fil)
         and (len(textes) > 12 or sum(f["n"] for f in c.fil) == len(publications)))
verifier("l'etat se serialise en JSON", bool(json.dumps(etat, ensure_ascii=False)))

print("\nContre-tendance")
t = Campus(en_direct=False)
t.appliquer({"schema": "population.v2", "t_sim": 0, "agents": [
    {"id": f"a{i}", "nom": f"A{i}", "groupe": "g", "porte": i < 3} for i in range(10)]}, "t")
ind = {"schema": "indicateurs.v1", "taux_adoption": 0, "sens_dominant": "aucun_sens",
       "part_sens_dominant": 0}
t.appliquer({**ind, "t_sim": 0}, "t")
for i in range(3):
    t.appliquer({"schema": "decision.v2", "agent": f"a{i}", "porte": False, "categorie": "ringard",
                 "t_sim": 1440}, "t")
t.appliquer({**ind, "t_sim": 1440, "t_sim_lisible": "J02 00:00"}, "t")
ct = t.instantane()["contre_tendances"]
verifier("3 abandons le meme jour sur 10 : une contre-tendance reperee",
         len(ct) == 1 and ct[0]["nature"] == "abandon" and ct[0]["qui"] == ["A0", "A1", "A2"])
t.appliquer({"schema": "decision.v2", "agent": "a5", "porte": True, "categorie": "ironie",
             "t_sim": 2880}, "t")
t.appliquer({**ind, "t_sim": 2880}, "t")
verifier("un seul agent qui passe a l'ironie : rien", len(t.instantane()["contre_tendances"]) == 1)

print("\nInjection")
c.appliquer({"schema": "injection.v1", "t_sim": 2880, "t_sim_lisible": "J03 00:00",
             "nature": "relais_massif", "details": {}, "source": "scene_godot"}, c.run)
verifier("une injection est reperee pour la courbe",
         c.instantane()["injections"][-1]["nature"] == "relais_massif")

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
