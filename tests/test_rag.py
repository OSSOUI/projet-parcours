"""Verifications de la base de connaissances (exigences F1, F2, C6).

Aucun appel reseau, aucun appel LLM : un client factice suffit.

    python3 tests/test_rag.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ephemere import population
from ephemere.agents_llm import DecideurLLM, requete_de
from ephemere.contrat import verifier
from ephemere.monde import Monde
from ephemere.rag import Base, decouper

echecs = []


def verif(nom, condition, detail=""):
    print(f"  {'ok  ' if condition else 'ECHEC'} {nom} {detail if not condition else ''}")
    if not condition:
        echecs.append(nom)


class ClientFactice:
    def __init__(self):
        self.derniere_mesure = {}
        self.derniere_consigne = ""

    def json(self, systeme, consigne, taille="llm_petit"):
        self.derniere_consigne = consigne
        self.derniere_mesure = {"taille": taille, "latence_s": 0.4}
        return {"porte": True, "categorie": "tendance", "sens": "ca se repand",
                "publication": "", "destinataire": "", "raison": "mon groupe s'y met"}


base = Base("corpus")

print("1. Le corpus se charge")
r = base.resume()
verif("au moins 8 documents", r["documents"] >= 8, str(r))
verif("decoupe en passages", r["passages"] > r["documents"], str(r))
verif("les mots vides sont retires", "le" not in decouper("le ruban et la mode"))

print("\n2. Filtre temporel (C6)")
q = "enquete rubans apparaissent poignets personne ne revendique"
avant = [d["id"] for d in base.chercher(q, 8, "residence_b", k=3)]
apres = [d["id"] for d in base.chercher(q, 9, "residence_b", k=3)]
verif("l'article du jour 9 est absent au jour 8", "criee_enquete_ruban" not in avant,
      str(avant))
verif("il apparait au jour 9", "criee_enquete_ruban" in apres, str(apres))

print("\n3. Filtre par groupe")
q2 = "charte association article membres"
dehors = [d["id"] for d in base.chercher(q2, 20, "residence_b", k=5)]
dedans = [d["id"] for d in base.chercher(q2, 20, "atelier_design", k=5)]
verif("la charte de l'atelier est invisible depuis la residence B",
      "charte_atelier" not in dehors, str(dehors))
verif("elle est visible pour un membre de l'atelier",
      "charte_atelier" in dedans, str(dedans))

print("\n4. Deux profils ne cherchent pas la meme chose (F1, A3)")
agents, config = population.construire("config/tessaline.json", 14, 3)
pionnier = next(a for a in agents if a["profil"] == "pionnier")
refractaire = next(a for a in agents if a["profil"] == "refractaire")
verif("les requetes different", requete_de(pionnier) != requete_de(refractaire))
verif("la requete du pionnier parle de distinction",
      "distinguer" in requete_de(pionnier))
verif("celle du refractaire parle de refus", "refuser" in requete_de(refractaire))

print("\n5. Les passages retrouves entrent bien dans le prompt (F1)")
monde = Monde(agents, config.get("perception"))
client = ClientFactice()
d = DecideurLLM(client, "llm_grand", base=base, k=3).decider(
    pionnier, monde, 12 * 1440, "J13 00:00")
consigne = client.derniere_consigne
verif("le prompt a une section documentaire", "lu ou entendu dire" in consigne)
rec = d["recuperation"]
verif("au moins un passage retrouve", len(rec["resultats"]) >= 1,
      str(len(rec["resultats"])))
if rec["resultats"]:
    premier = rec["resultats"][0]
    verif("le passage retrouve figure mot pour mot dans le prompt",
          premier["passage"][:60] in consigne)
    verif("sa source est citee dans le prompt", premier["source"] in consigne)
    verif("il est accessible a l'agent",
          premier["jour"] <= 13, f"jour {premier['jour']}")

print("\n6. L'evenement de recuperation respecte le contrat (F2)")
evt = {"schema": "recuperation.v1", "run": "t", "t_sim": 17280,
       "t_sim_lisible": "J13 00:00", "t_emission": "now", "t_traitement": None,
       "agent": pionnier["id"], "requete": rec["requete"],
       "resultats": [{"id": x["id"], "score": x["score"]} for x in rec["resultats"]],
       "nb_resultats": len(rec["resultats"]), "corpus": {"passages_demandes": 3}}
ok, raison = verifier(evt)
verif("il est conforme", ok, str(raison))

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
