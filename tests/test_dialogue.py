"""Verifications des conversations privees (A2) et de la sortie structuree,
sans aucun appel reseau : un client factice repond a la place du modele.

    python3 tests/test_dialogue.py
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import mesures_llm as M  # noqa: E402
from ephemere.agents_llm import (DEFINITIONS_SENS, SCHEMA_DECISION, SCHEMA_REPLIQUE,  # noqa: E402
                                 DecideurLLM, valider)
from ephemere.contrat import SENS  # noqa: E402
from ephemere.contrat import verifier as conforme  # noqa: E402
from ephemere.dialogue import Dialogue  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.monde import Monde  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


class Client:
    """Renvoie les reponses de la file et garde ce qu'on lui a demande."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.derniere_mesure = {}

    def json(self, systeme, consigne, taille="llm_petit", **options):
        self.appels.append({"consigne": consigne, "taille": taille, **options})
        self.derniere_mesure = {"taille": taille, "latence_s": 0.1}
        return self.reponses.pop(0) if self.reponses else None


class Journal:
    def __init__(self):
        self.evenements = []

    def ecrire(self, schema, **corps):
        self.evenements.append({"schema": schema, **corps})


def agent(i, moteur="llm_petit", categorie="tendance"):
    return {"id": i, "nom": i.capitalize(), "profil": "suiveur", "groupe": "g", "moteur": moteur,
            "porte": True, "categorie": categorie, "sens": "", "memoire": [], "personnalite": "",
            "minutes_porte": 0}


print("Sortie structuree")
bonne = {"porte": True, "categorie": "ironie", "sens": "s", "publication": "", "destinataire": "",
         "raison": "r"}
verifier("une decision complete respecte le schema", valider(bonne, SCHEMA_DECISION) == [])
verifier("champ manquant, type faux et categorie hors liste sont tous signales",
         len(valider({"porte": "oui", "categorie": "licorne"}, SCHEMA_DECISION)) == 6)
verifier("un champ en trop est signale", valider({**bonne, "humeur": "x"}, SCHEMA_DECISION)
         == ["champ en trop : humeur"])
verifier("les schemas tirent leur liste de sens du contrat",
         SCHEMA_REPLIQUE["properties"]["categorie"]["enum"] ==
         SCHEMA_DECISION["properties"]["categorie"]["enum"])
c = Client([{"texte": "bof", "categorie": "ringard"}])
r = DecideurLLM(c, "llm_petit", structure=True).repondre(agent("a"), agent("b"), [("B", "salut")])
verifier("avec --sortie-structuree, le schema part dans l'appel",
         c.appels[0].get("schema") is SCHEMA_REPLIQUE and r["valide"])
c = Client([{"texte": "bof", "categorie": "ringard"}])
DecideurLLM(c, "llm_petit").repondre(agent("a"), agent("b"), [("B", "salut")])
verifier("sans l'option, aucun schema n'est envoye", "schema" not in c.appels[0])
c = Client([{"texte": "bof", "categorie": "ringard", "humeur": "x"}])
r = DecideurLLM(c, "llm_petit", structure=True).repondre(agent("a"), agent("b"), [("B", "x")])
verifier("reponse hors schema : incident schema_non_respecte",
         not r["valide"] and r["incident"]["nature"] == "schema_non_respecte")

print("\nConversation")
a, b, r_ = agent("ali"), agent("bea", categorie="ironie"), agent("reg", moteur="regles")
monde = Monde([a, b, r_], None)
c = Client([{"texte": "je trouve ca ridicule", "categorie": "ironie"},
            {"texte": "tu as peut-etre raison", "categorie": "ironie"}])
dec = DecideurLLM(c, "llm_petit")
dialogue = Dialogue({"ali": dec, "bea": dec, "reg": None}, max_par_jour=1)
journal = Journal()
h = Horloge(0)
h.aller_a(1440)
dialogue.noter(monde, "ali", "reg", "salut", 1440)
verifier("pas de conversation avec un agent a regles", dialogue.en_attente == [])
dialogue.noter(monde, "ali", "bea", "tu le portes, toi ?", 1440)
dialogue.noter(monde, "bea", "ali", "et toi ?", 1440)
dialogue.mener(journal, monde, h)
rep = [e for e in journal.evenements if e["schema"] == "replique.v1"]
verifier("3 repliques : le message, puis Bea, puis Ali (2 appels)",
         [(e["tour"], e["agent"]) for e in rep] == [(2, "bea"), (3, "ali")] and len(c.appels) == 2)
verifier("au plus 1 conversation par jour : la seconde n'a pas eu lieu", dialogue.nombre == 1)
verifier("Bea voit le message d'ouverture quand elle repond",
         "Ali : tu le portes, toi ?" in c.appels[0]["consigne"])
verifier("Ali voit la reponse de Bea quand il repond",
         "Bea : je trouve ca ridicule" in c.appels[1]["consigne"])
verifier("chaque replique entre dans la memoire de celui a qui elle s'adresse",
         "je trouve ca ridicule" in monde.agents["ali"]["memoire"][-1]["fait"]
         and "tu as peut-etre raison" in monde.agents["bea"]["memoire"][-1]["fait"])
verifier("la croyance ne change pas pendant la conversation",
         monde.agents["ali"]["categorie"] == "tendance")
enveloppe = {"run": "t", "t_sim": 1440, "t_sim_lisible": "J02 00:00",
             "t_emission": "2026-10-28T00:00:00.000", "t_traitement": None}
verifier("les repliques respectent le contrat (replique.v1)",
         all(conforme({**enveloppe, **e})[0] for e in rep))

c = Client([None])
dialogue = Dialogue({"ali": DecideurLLM(c, "llm_petit"), "bea": DecideurLLM(c, "llm_petit")}, 2)
journal = Journal()
dialogue.noter(monde, "ali", "bea", "alors ?", 2880)
dialogue.mener(journal, monde, h)
inc = [e for e in journal.evenements if e["schema"] == "incident.v1"]
verifier("appel echoue : la conversation s'arrete, l'incident est compte a part",
         len(inc) == 1 and inc[0]["details"]["conversation"] == "c1"
         and [e["valide"] for e in journal.evenements if e["schema"] == "replique.v1"] == [False])

print("\nMesure")
pop = {"schema": "population.v1", "agents": [
    {k: x[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")} for x in (a, b)]}
evs = [pop,
       {"schema": "decision.v1", "agent": "ali", "t_sim": 1440, "porte": True,
        "categorie": "tendance", "moteur": "llm_petit", "valide": True},
       {"schema": "decision.v1", "agent": "bea", "t_sim": 1440, "porte": True,
        "categorie": "ironie", "moteur": "llm_petit", "valide": True},
       {"schema": "replique.v1", "conversation": "c1", "tour": 2, "agent": "bea",
        "destinataire": "ali", "texte": "x", "categorie": "ironie", "t_sim": 1440, "valide": True},
       {"schema": "replique.v1", "conversation": "c1", "tour": 3, "agent": "ali",
        "destinataire": "bea", "texte": "y", "categorie": "ironie", "t_sim": 1440, "valide": True},
       {"schema": "decision.v1", "agent": "ali", "t_sim": 2880, "porte": True,
        "categorie": "ironie", "moteur": "llm_petit", "valide": True}]
conv = M.conversations(evs)
verifier("Ali bouge pendant l'echange (tendance -> ironie), Bea non",
         (conv["bouge_pendant"], conv["participants"]) == (1, 2), conv)
verifier("et Ali garde ironie a sa decision suivante", (conv["bouge_apres"], conv["suivis"]) == (1, 1),
         conv)
verifier("la replique recue compte comme un echange pour A2",
         M.echanges(evs)["avec_message"]["decisions"] == 1)

print("\nDefinitions des sens")
d = DecideurLLM(None, "llm_petit", structure=True)
verifier("par defaut, les definitions courtes des runs", d.definitions is SENS
         and d.schema_decision is SCHEMA_DECISION)
n = DecideurLLM(None, "llm_petit", structure=True, definitions="nettes")
verifier("nettes seulement sur demande, memes noms de sens",
         n.definitions is DEFINITIONS_SENS
         and n.schema_decision["properties"]["categorie"]["enum"] == list(SENS))

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
