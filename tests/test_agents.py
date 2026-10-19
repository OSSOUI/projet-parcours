"""Verifications des agents LLM, sans aucun appel reseau.

Un client factice renvoie des reponses choisies a l'avance, y compris des
reponses volontairement cassees. On verifie que la simulation ne s'arrete
jamais et que chaque derive est reperee et nommee (exigence A4).

    python3 tests/test_agents.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ephemere import population
from ephemere.agents_llm import SYSTEME, DecideurLLM, detecter_derive, souvenirs
from ephemere.monde import Monde

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


class ClientFactice:
    """Imite ClientLLM : renvoie les reponses de la file, dans l'ordre."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.derniere_mesure = {}
        self.appels = 0

    def json(self, systeme, consigne, taille="llm_petit"):
        self.appels += 1
        self.derniere_consigne = consigne
        self.derniere_mesure = {"taille": taille, "latence_s": 0.5,
                                "tokens_entree": 300, "tokens_sortie": 90}
        return self.reponses.pop(0) if self.reponses else None


def bonne_reponse(**extra):
    base = {"porte": True, "categorie": "cercle_creatif",
            "sens": "un code entre nous", "publication": "ca se voit, non ?",
            "destinataire": "", "raison": "je l'ai lance, je l'assume"}
    base.update(extra)
    return base


print("1. Detection des derives (A4)")
cas = [
    ("reponse correcte", bonne_reponse(), None),
    ("appel rate", None, "appel_echoue"),
    ("json illisible", "pas du json", "json_illisible"),
    ("porte invalide", bonne_reponse(porte="oui"), "champ_porte_invalide"),
    ("categorie inventee", bonne_reponse(categorie="licorne"), "categorie_hors_liste"),
    ("posture d'assistant", bonne_reponse(raison="En tant qu'IA, je ne peux pas porter de ruban"),
     "posture_assistant"),
    ("morale d'assistant", bonne_reponse(sens="Il est important de ne pas suivre les modes"),
     "posture_assistant"),
    ("consigne recopiee", bonne_reponse(publication="une chaine vide"), "fuite_de_consigne"),
    ("consigne recopiee bis", bonne_reponse(publication="Chaine vide"), "fuite_de_consigne"),
    ("json imbrique en publication",
     bonne_reponse(publication='{"message":"salut"}'), "fuite_de_consigne"),
    ("dit porter alors qu'il ne porte pas",
     bonne_reponse(porte=False, raison="je porte ce ruban par conviction"),
     "incoherence_texte_etat"),
    ("dit ne pas porter alors qu'il porte",
     bonne_reponse(porte=True, sens="je ne porte pas ce ruban, c'est ridicule"),
     "incoherence_texte_etat"),
    ("negation correcte non signalee",
     bonne_reponse(porte=False, categorie="ringard", sens="je ne le porte pas, c'est fini",
                   raison="plus personne d'interessant ne le met"), None),
]
for nom, reponse, attendu in cas:
    nature, _ = detecter_derive(reponse)
    verifier(nom, nature == attendu, f"(obtenu {nature!r}, attendu {attendu!r})")

print("\n2. Le monde continue quand l'agent deraille (A4)")
agents, config = population.construire("config/tessaline.json", 8, 1)
monde = Monde(agents, config.get("perception"))
agent = agents[0]
avant = (agent["porte"], agent["categorie"])
client = ClientFactice([None])
d = DecideurLLM(client, "llm_petit").decider(agent, monde, 600, "J01 10:00")
verifier("la decision est marquee non valide", d["valide"] is False)
verifier("un incident est attache", d.get("incident", {}).get("nature") == "appel_echoue")
verifier("l'agent garde son etat de la veille", (d["porte"], d["categorie"]) == avant)

print("\n3. Le prompt porte bien le contexte (A1, A3)")
client = ClientFactice([bonne_reponse()])
DecideurLLM(client, "llm_grand").decider(agent, monde, 600, "J01 10:00")
c = client.derniere_consigne
verifier("le prompt nomme l'agent", agent["nom"] in c)
verifier("le prompt porte sa personnalite", agent["personnalite"][:25] in c)
verifier("le prompt porte la date simulee", "J01 10:00" in c)
verifier("le prompt impose la liste fermee", "cercle_creatif" in c and "ringard" in c)
verifier("le systeme interdit explicitement la posture d'assistant",
         "n'es pas un assistant" in SYSTEME and "morale" in SYSTEME)
verifier("le prompt donne ce que l'agent voit dans son groupe",
         agent["groupe"] in c and "le portent" in c)
verifier("le prompt ne parle pas de 'mode' dans la mise en situation",
         "mode" not in c.split("Ce que tu vois")[0].lower())
verifier("la categorie est normalisee avant jugement",
         detecter_derive(bonne_reponse(categorie="Tendance"))[0] is None)

print("\n4. Un echange adresse entre dans la memoire du destinataire (A2, A1)")
emetteur, cible = agents[0], agents[1]
cible["memoire"] = []
touche = monde.adresser(emetteur["id"], cible["nom"], "tu devrais essayer, ca te va",
                        600, "J01 10:00")
verifier("le destinataire est bien trouve", touche == cible["id"])
verifier("le souvenir est range comme un echange",
         cible["memoire"][-1]["genre"] == "echange")
verifier("le souvenir cite l'emetteur", emetteur["nom"] in cible["memoire"][-1]["fait"])
verifier("un nom inconnu ne casse rien",
         monde.adresser(emetteur["id"], "Personne", "coucou", 600, "J01 10:00") is None)

print("\n5. Un echange ancien reste accessible plusieurs jours apres (A1)")
for jour in range(2, 8):
    cible["memoire"].append({"genre": "decision", "t_sim": jour * 1440,
                             "t_sim_lisible": f"J{jour:02d} 09:00",
                             "fait": "j'ai decide de ne pas porter le ruban",
                             "raison": "j'attends de voir"})
texte = souvenirs(cible)
verifier("l'echange du J01 figure encore dans les souvenirs injectes",
         "J01 10:00" in texte and emetteur["nom"] in texte)
verifier("les souvenirs recents y sont aussi", "J07 09:00" in texte)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
