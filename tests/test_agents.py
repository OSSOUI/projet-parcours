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
    # Francais courant, en role : ne doit PAS etre pris pour un assistant.
    ("'en tant que' en role non signale",
     bonne_reponse(categorie="ironie",
                   raison="En tant que membre du club d'humour, je le porte pour m'en moquer"),
     None),
    ("'je ne peux pas' en role non signale",
     bonne_reponse(porte=False, categorie="aucun_sens",
                   raison="je ne peux pas le mettre a l'atelier, ca gene au tour"), None),
    ("'cependant, il' en role non signale",
     bonne_reponse(sens="c'est notre truc, cependant, il commence a se voir partout"), None),
    ("refus net en role non signale",
     bonne_reponse(porte=False, categorie="aucun_sens",
                   sens="je ne peux pas suivre tout le monde comme ca",
                   raison="je refuse de le porter"), None),
    # Vraies postures d'assistant : toujours reperees.
    ("'en tant qu'assistant'",
     bonne_reponse(raison="En tant qu'assistant, je ne porte rien"), "posture_assistant"),
    ("'je ne peux pas donner d'avis'",
     bonne_reponse(sens="Je ne peux pas donner d'avis sur une mode"), "posture_assistant"),
    ("'je suis un modele de langage'",
     bonne_reponse(publication="je suis un modele de langage"), "posture_assistant"),
    # Cas observes dans le run d'essai du 21/10 (qwen2.5:3b).
    ("reponse en italien",
     bonne_reponse(porte=False, categorie="ironie",
                   sens="Io nonne questo gesto come una risposta ironica",
                   publication="Questa risposta nonne il rubino, ma una sfumatura di ironia",
                   raison="Voglio contrastare la tendenza senza fare una vera protesta"),
     "hors_langue"),
    ("'je prends part' sans porter",
     bonne_reponse(porte=False, categorie="suivre_la_foule",
                   sens="Je prends part a l'engouement pour le ruban.",
                   raison="Je veux etre vu comme partant avec la tendance."),
     "incoherence_texte_etat"),
    ("'je choisis de ne pas porter le ruban' coherent",
     bonne_reponse(porte=False, categorie="aucun_sens",
                   sens="Je choisis de ne pas porter le ruban aujourd'hui.",
                   raison="Je refuse de porter le ruban, je prefere attendre."), None),
    ("'je choisis de porter le ruban' coherent",
     bonne_reponse(porte=True, categorie="tendance",
                   sens="Je choisis de porter le ruban aujourd'hui.", raison="ca me plait"),
     None),
    ("faute de frappe ramenee", bonne_reponse(categorie="suivre_la_folle"), None),
    ("vraie invention refusee", bonne_reponse(categorie="seulement_circulaire"),
     "categorie_hors_liste"),
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
verifier("le prompt definit chaque sens du ruban",
         "- ironie : on le porte pour s'en moquer" in c)
verifier("le prompt separe la lecture du signe et le geste",
         "VEUT DIRE" in c and "que tu le portes ou non" in c)
verifier("le systeme impose le francais", "francais" in SYSTEME)
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

print("\n6. Un echange survit a toute la duree d'un run, meme chez une pionniere (A1)")
from ephemere.monde import memoriser
pionniere = {"memoire": []}
pionniere["memoire"] = memoriser(pionniere["memoire"], {
    "genre": "echange", "t_sim": 600, "t_sim_lisible": "J01 10:00",
    "fait": "Lea m'a dit : \"garde-le\"", "raison": ""})
for demi_journee in range(2, 2 * 25):     # cadence 720 : deux decisions par jour
    pionniere["memoire"] = memoriser(pionniere["memoire"], {
        "genre": "decision", "t_sim": demi_journee * 720,
        "t_sim_lisible": f"J{demi_journee // 2 + 1:02d}", "fait": "j'ai decide de porter",
        "raison": ""})
verifier("l'echange du J01 est encore en memoire au J25",
         any(m["genre"] == "echange" for m in pionniere["memoire"]))
verifier("il figure dans les souvenirs injectes", "J01 10:00" in souvenirs(pionniere))
verifier("les decisions restent plafonnees",
         sum(m["genre"] == "decision" for m in pionniere["memoire"]) <= 8)

print("\n7. Le fil ne montre que les messages nouveaux, et le relais les remontre")
from ephemere import commandes
from ephemere.horloge import Horloge
agents, config = population.construire("config/tessaline.json", 8, 1)
monde = Monde(agents, config.get("perception"))
lecteur, auteur = agents[0], agents[1]
monde.publier(auteur["id"], "premier message", 600)
verifier("un message publie est visible", len(monde.fil_visible(lecteur, 700)) == 1)
verifier("un message futur est invisible (C6)", len(monde.fil_visible(lecteur, 500)) == 0)
monde.marquer_lu(lecteur, 700)
verifier("un message deja lu n'est plus remontre", monde.fil_visible(lecteur, 900) == [])
monde.publier(auteur["id"], "deuxieme message", 1000)
verifier("seul le nouveau message est remontre",
         [m["texte"] for m in monde.fil_visible(lecteur, 1100)] == ["deuxieme message"])
monde.marquer_lu(lecteur, 1100)
commandes.appliquer({"nature": "relais_massif"}, monde, Horloge(1200))
verifier("apres le relais massif, tout le fil redevient a lire",
         len(monde.fil_visible(lecteur, 1300)) == 3)

print("\n8. Le relais massif ne gonfle pas le temps de port (lassitude)")
import simuler
populaire = next(a for a in agents if a["profil"] == "figure_populaire")
populaire.update(porte=True, minutes_porte=1920, derniere_decision=11520)
h = Horloge(11520 + 960)
commandes.appliquer({"nature": "relais_massif"}, monde, h)
simuler.appliquer(populaire, {"porte": True, "categorie": "tendance", "sens": "x",
                              "raison": ""}, monde, h)
verifier("seules les 960 minutes ecoulees s'ajoutent",
         populaire["minutes_porte"] == 1920 + 960, f"(obtenu {populaire['minutes_porte']})")

print("\n9. Un temoin LLM est cloisonne comme un agent a regles (B3)")
agents, config = population.construire("config/tessaline_cloisonne.json", 20, 3)
monde = Monde(agents, config.get("perception"))
temoin = next(a for a in agents if a["groupe"] != "atelier_design")
etranger = next(a for a in agents if a["groupe"] != temoin["groupe"])
voisin = next((a for a in agents if a["groupe"] == temoin["groupe"]
               and a["id"] != temoin["id"]), None)
monde.publier(etranger["id"], "message d'un autre groupe", 600)
if voisin:
    monde.publier(voisin["id"], "message du groupe", 600)
client = ClientFactice([bonne_reponse()])
DecideurLLM(client, "llm_petit").decider(temoin, monde, 700, "J01 11:40")
c = client.derniere_consigne
verifier("le prompt ne donne pas le compteur du campus", "etudiants sur" not in c)
verifier("le prompt ne montre pas le fil des autres groupes",
         "message d'un autre groupe" not in c)
if voisin:
    verifier("le prompt montre encore le fil du groupe", "message du groupe" in c)
verifier("un echange adresse a un autre groupe n'arrive pas",
         monde.adresser(etranger["id"], temoin["nom"], "salut", 700, "J01") is None)

print("\n10. Le mode asynchrone tient quand les modeles reflechissent (C4)")
import random
import tempfile
import types
from ephemere.journal import Journal


class Lent:
    def decider(self, agent, monde, t, lisible=""):
        return {"porte": agent["porte"], "categorie": agent["categorie"], "sens": "x",
                "raison": "x", "publication": "", "destinataire": "", "valide": True,
                "mesure": {"latence_s": 6.0}}


agents, config = population.construire("config/tessaline.json", 20, 1)
monde = Monde(agents, config.get("perception"))
h = Horloge(0)
try:
    with tempfile.TemporaryDirectory() as dossier, Journal(dossier, "t", h) as journal:
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            simuler.tourner_asynchrone(
                monde, {a["id"]: Lent() for a in agents}, journal, h,
                types.SimpleNamespace(jours=3, releve_min=1440, minutes_par_seconde=5.0),
                random.Random(1))
    ok = True
except ValueError as e:
    ok = False
verifier("trois jours avec 30 minutes de reflexion, sans recul d'horloge", ok)

print("\n11. Le delai emission -> traitement est mesure (C7)")
from datetime import datetime, timedelta
from ephemere.campus import Campus
emis = (datetime.now() - timedelta(milliseconds=250)).isoformat(timespec="milliseconds")
campus = Campus()
evt = campus.appliquer({"schema": "decision.v1", "agent": "lea", "porte": True,
                        "t_sim": 600, "t_emission": emis}, "r")
verifier("t_traitement est horodate a la milliseconde", len(evt["t_traitement"]) == 23)
verifier("le delai est calcule", evt["delai_ms"] is not None and evt["delai_ms"] >= 250)
verifier("il remonte dans les indicateurs",
         campus.indicateurs()["delai_traitement_ms"]["n"] == 1)
rejeu = Campus(en_direct=False)
verifier("pas de delai en rejeu", rejeu.appliquer(
    {"schema": "run.v1", "t_sim": 0, "t_emission": emis}, "r")["delai_ms"] is None)

print("\n12. Ce que l'agent a vu est enregistre, et le futur est detecte (A3, B4, C6)")
from ephemere import contrat
from ephemere.agents_llm import controler_c6
agents, config = population.construire("config/tessaline.json", 8, 1)
monde = Monde(agents, config.get("perception"))
lecteur, auteur = agents[0], agents[1]
monde.publier(auteur["id"], "je l'ai vu a la cafet", 600)
client = ClientFactice([bonne_reponse()])
client.dernier_brut = '{"porte": true, "raison": "texte brut"}'
d = DecideurLLM(client, "llm_petit").decider(lecteur, monde, 700, "J01 11:40")
p = d["perception"]
verifier("le message lu figure dans la perception",
         [m["texte"] for m in p["messages"]] == ["je l'ai vu a la cafet"])
verifier("la reponse brute est conservee", p["reponse_brute"] == client.dernier_brut)
verifier("aucune violation C6 dans un contexte sain", p["violations_c6"] == [])
evt = {"schema": "perception.v1", "run": "t", "t_sim": 700, "t_sim_lisible": "J01 11:40",
       "t_emission": "x", "t_traitement": None, "agent": lecteur["id"],
       "moteur": "llm_petit", **p}
verifier("l'evenement perception.v1 est conforme", contrat.verifier(evt) == (True, None))
futur = {"messages": [{"auteur": "lea", "t_sim": 900, "texte": "x"}],
         "souvenirs": [{"genre": "echange", "t_sim": 2000, "fait": "x"}],
         "documents": [{"id": "criee_enquete_ruban", "numero": 0, "jour": 9}]}
verifier("message, souvenir et document du futur sont tous comptes",
         len(controler_c6(futur, 700)) == 3)
verifier("un document du jour meme n'est pas une violation",
         controler_c6({"messages": [], "souvenirs": [],
                       "documents": [{"id": "x", "numero": 0, "jour": 1}]}, 700) == [])

client = ClientFactice([bonne_reponse(categorie="suivre_la_folle")])
d = DecideurLLM(client, "llm_petit").decider(lecteur, monde, 700, "J01 11:40")
verifier("une faute de frappe ramenee est notee dans la perception",
         d["perception"].get("categorie_corrigee") == {"recu": "suivre_la_folle",
                                                      "retenu": "suivre_la_foule"})

print("\n13. L'accord se mesure meme quand 'aucun sens' domine (B1, B3)")
from experience import accord_partage
releve = {"repartition_sens": {"aucun_sens": 12, "tendance": 8, "ironie": 0,
                               "cercle_creatif": 0, "suivre_la_foule": 0, "ringard": 0}}
verifier("40 % sur 'tendance' comptent malgre 60 % de 'aucun sens'",
         abs(accord_partage(releve) - 0.4) < 1e-9)

print("\n14. Un run complet avec LLM factice ne produit aucun evenement rejete")
import contextlib
import io
import tempfile
import types
from ephemere.horloge import Horloge
from ephemere.journal import Journal


class Repondeur:
    derniere_mesure = {"latence_s": 0.2}
    dernier_brut = "{}"

    def json(self, systeme, consigne, taille):
        return bonne_reponse(publication="on se voit a l'atelier ?")


agents, config = population.construire("config/tessaline.json", 12, 2)
monde = Monde(agents, config.get("perception"))
h = Horloge(0)
llm = DecideurLLM(Repondeur(), "llm_petit")
with tempfile.TemporaryDirectory() as dossier:
    with Journal(dossier, "essai", h) as journal, contextlib.redirect_stdout(io.StringIO()):
        simuler.tourner_synchrone(
            monde, {a["id"]: llm for a in agents}, journal, h,
            types.SimpleNamespace(jours=3, pas_min=1440, releve_min=1440))
        journal.ecrire("energie.v1", **simuler.Energie(False, "essai").arreter())
        coherence = simuler._controler_coherence(journal.chemin)
        journal.ecrire("coherence.v1", **coherence)
        rejets = journal.nb_rejets
verifier("aucun evenement rejete par le contrat", rejets == 0, f"({rejets} rejets)")

print("\n15. La telemetrie en direct note chaque appel sans toucher au run (direct.py)")
import json as _json
agents, config = population.construire("config/tessaline.json", 12, 2)
monde_a = Monde(agents, config.get("perception"))
monde_b = Monde([dict(a, memoire=[]) for a in agents], config.get("perception"))
with tempfile.TemporaryDirectory() as dossier:
    resultats = []
    for monde_x, tele in ((monde_a, None), (monde_b, simuler.Telemetrie(os.path.join(dossier, "t.direct.jsonl")))):
        hx = Horloge(0)
        with Journal(dossier, "x", hx) as journal, contextlib.redirect_stdout(io.StringIO()):
            simuler.tourner_synchrone(
                monde_x, {a["id"]: DecideurLLM(Repondeur(), "llm_petit") for a in monde_x.agents.values()},
                journal, hx, types.SimpleNamespace(jours=2, pas_min=1440, releve_min=1440, telemetrie=tele))
        resultats.append([(a["porte"], a["categorie"]) for a in monde_x.agents.values()])
    tele.fermer()
    with open(os.path.join(dossier, "t.direct.jsonl"), encoding="utf-8") as f:
        lignes = [_json.loads(x) for x in f]
appels = [x for x in lignes if x["type"] == "appel"]
verifier("un debut de pas par jour simule", sum(x["type"] == "debut_pas" for x in lignes) == 2)
verifier("un appel note par decision", len(appels) == sum(len(x["ordre"]) for x in lignes if x["type"] == "debut_pas"))
verifier("chaque appel porte sa latence et ses tokens",
         all(x["latence_s"] == 0.2 and x["duree_s"] >= 0 for x in appels))
verifier("la telemetrie ne change aucune decision", resultats[0] == resultats[1])
verifier("chaque decision LLM a ete controlee", coherence["controles"] > 0)
verifier("zero violation C6 sur le run", coherence["violations"] == 0)


print("\n16. Colibri sert le grand modele, Ollama le petit, adresses venues de l'environnement")
from ephemere.llm import ClientLLM

anciennes = {k: os.environ.pop(k, None) for k in ("COLIBRI_URL", "OLLAMA_URL")}
os.environ["COLIBRI_URL"] = "http://colibri:5000/v1/chat/completions"
os.environ["OLLAMA_URL"] = "http://ollama:11434/v1/chat/completions"
client = ClientLLM("colibri", {"llm_grand": "glm-5.2", "llm_petit": "qwen2.5:3b"})
verifier("le grand modele va a Colibri", client.urls["llm_grand"] == os.environ["COLIBRI_URL"])
verifier("le petit modele va a Ollama", client.urls["llm_petit"] == os.environ["OLLAMA_URL"])
verifier("delai allonge pour Colibri", client.delai_s >= 600)
for k, v in anciennes.items():
    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
client = ClientLLM("ollama", {"llm_grand": "qwen2.5:7b", "llm_petit": "qwen2.5:3b"})
verifier("sans variable, Ollama reste en local",
         set(client.urls.values()) == {"http://localhost:11434/v1/chat/completions"}
         and client.delai_s == 90)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
