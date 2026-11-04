"""Base experimentale : ombres, modele nul a persistance, ecart reel - ombre.
Aucun appel reseau.

    python3 tests/test_ombres.py
"""
import os
import random
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simuler  # noqa: E402
from ephemere import contrat, population  # noqa: E402
from ephemere import indicateurs as I  # noqa: E402
from ephemere.agents_llm import INCONNU_CAMPUS, INCONNU_GROUPE, DecideurLLM  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.journal import Journal  # noqa: E402
from ephemere.monde import Monde, memoriser  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


class ClientFactice:
    """Repond toujours la meme decision ; garde chaque consigne recue."""

    def __init__(self, reponse):
        self.reponse = reponse
        self.consignes = []
        self.derniere_mesure = {}

    def json(self, systeme, consigne, taille="llm_petit"):
        self.consignes.append(consigne)
        self.derniere_mesure = {"taille": taille, "latence_s": 0.5}
        return dict(self.reponse)


REPONSE = {"porte": True, "categorie": "tendance", "sens": "c'est le moment",
           "publication": "", "destinataire": "", "raison": "je le mets"}

print("1. Les masques retirent le social et rien d'autre")
agents, config = population.construire("config/tessaline.json", 12, 1)
monde = Monde(agents, config.get("perception"))
agent = next(a for a in agents if a["moteur"] != "regles")
autre = next(a for a in agents if a["id"] != agent["id"])
monde.publier(autre["id"], "message public du jour", 600)
agent["memoire"] = memoriser(agent["memoire"], {
    "genre": "echange", "t_sim": 300, "t_sim_lisible": "J01 05:00",
    "fait": f"{autre['nom']} m'a dit : \"souvenir d'echange\"", "raison": ""})
agent["memoire"] = memoriser(agent["memoire"], {
    "genre": "decision", "t_sim": 400, "t_sim_lisible": "J01 06:40",
    "fait": "j'ai decide de porter le ruban", "raison": "souvenir de decision"})
d = DecideurLLM(ClientFactice(REPONSE), agent["moteur"])
complet, _ = d._consigne(agent, monde, 700, "J01 11:40")
discours, _ = d._consigne(agent, monde, 700, "J01 11:40", masque="sans_discours")
social, _ = d._consigne(agent, monde, 700, "J01 11:40", masque="sans_social")
verifier("le prompt complet montre le fil et l'echange",
         "message public du jour" in complet and "souvenir d'echange" in complet)
verifier("sans_discours retire le fil et l'echange",
         "message public du jour" not in discours and "souvenir d'echange" not in discours)
verifier("sans_discours garde l'adoption vue et le souvenir de decision",
         "le portent" in discours and "souvenir de decision" in discours)
verifier("sans_social retire aussi l'adoption vue",
         "le portent" not in social and INCONNU_GROUPE in social and INCONNU_CAMPUS in social)
verifier("sans_social garde le profil et le souvenir de decision",
         agent["nom"] in social and "souvenir de decision" in social)

print("\n2. Une ombre est reposee, journalisee, jamais appliquee")
client = ClientFactice(REPONSE)
decideurs = {a["id"]: (DecideurLLM(client, a["moteur"]) if a["moteur"] != "regles"
                       else simuler.Regles()) for a in agents}
avant = {a["id"]: (a["porte"], a["categorie"]) for a in agents}
args = types.SimpleNamespace(ombres=["sans_discours", "sans_social"], telemetrie=None)
h = Horloge(0)
h.aller_a(1440)
dec = simuler._decider(decideurs, agent, monde, h, 1440, args)
verifier("deux ombres pour un agent LLM", len(dec.get("ombres", [])) == 2)
verifier("trois appels : la decision et ses deux ombres", len(client.consignes) == 3)
verifier("l'ombre ne touche pas l'etat de l'agent",
         (agent["porte"], agent["categorie"]) == avant[agent["id"]])
regle = next(a for a in agents if a["moteur"] == "regles")
verifier("pas d'ombre pour un agent a regles",
         "ombres" not in simuler._decider(decideurs, regle, monde, h, 1440, args))
verifier("appels d'ombres comptes", args.appels_ombres == 2)
with tempfile.TemporaryDirectory() as dossier, Journal(dossier, "t", h) as journal:
    simuler.enregistrer(journal, monde, agent, dec, h)
    rejets = journal.nb_rejets
    lignes = open(journal.chemin, encoding="utf-8").read()
verifier("les ombres sont conformes au contrat", rejets == 0 and lignes.count('"ombre.v1"') == 2)
base = {"schema": "ombre.v1", "run": "r", "t_sim": 0, "t_sim_lisible": "J01 00:00",
        "t_emission": "x", "t_traitement": None, "agent": "a", "masque": "sans_social",
        "t_decision": 0, "porte": True, "categorie": "tendance", "valide": True,
        "incident": None, "reel_porte": True, "reel_categorie": "ironie", "reel_valide": True}
verifier("une ombre en incident (sens absent) est conforme",
         contrat.verifier({**base, "porte": None, "categorie": None, "valide": False,
                           "incident": "appel_echoue"})[0])
verifier("un masque inconnu est refuse", not contrat.verifier({**base, "masque": "x"})[0])
verifier("un sens hors liste est refuse", not contrat.verifier({**base, "categorie": "licorne"})[0])

print("\n3. Modele nul a persistance")
dist = {("suiveur", "llm_petit"): {"ironie": 2, "tendance": 1, "ringard": 1, "cercle_creatif": 1}}
classes = [("suiveur", "llm_petit")] * 10
indep = I.modele_nul(classes, dist, 20, tirages=400)
markov = I.modele_nul_markov(classes, dist, 20, 0.8, tirages=400)
verifier(f"la persistance releve le seuil ({indep['seuil']:.2f} -> {markov['seuil']:.2f})",
         markov["seuil"] > indep["seuil"])
rng = random.Random(5)
comptes = [dist[c] for c in classes]
faux = n = 0
for _ in range(300):
    etat = [I._tirer(rng, c) for c in comptes]
    serie = []
    for _ in range(20):
        etat = [s if rng.random() < 0.8 else I._tirer(rng, c) for s, c in zip(etat, comptes)]
        serie.append(I.accord_exprime(etat))
    g, _ = I.gain_soutenu(serie, markov["a0"])
    if g is not None:
        n += 1
        faux += g > markov["seuil"]
verifier(f"faux positifs sous persistance 0,8 avec le seuil a persistance : {faux / n:.0%}",
         faux / n <= 0.09)
verifier("persistance mesuree sur des etats",
         I.persistance([{"a": "x", "b": "y"}, {"a": "x", "b": "z"}]) == 0.5)

print("\n4. Ecart reel - ombre et sa permutation")
rng = random.Random(1)
sens = ["ironie", "tendance", "ringard", "cercle_creatif"]
agents_t = [f"a{i}" for i in range(10)]
# Le social pousse vers ironie : le reel converge, l'ombre reste au hasard.
fort = [(a, j, "ironie" if rng.random() < 0.8 else rng.choice(sens), rng.choice(sens))
        for j in range(1, 15) for a in agents_t]
r = I.ecart_ombres(fort, 15, permutations=200)
verifier(f"effet du social detecte : ecart {r['ecart']:+.2f}, p = {r['p']:.3f}",
         r["ecart"] > 0.2 and r["p"] < 0.05)
# Sans effet : reel et ombre tires de la meme distribution. Une p-valeur est
# alors uniforme : on verifie la calibration sur 40 jeux, pas un seul tirage.
detections = 0
for k in range(40):
    nul = [(a, j, rng.choice(sens), rng.choice(sens)) for j in range(1, 15) for a in agents_t]
    detections += I.ecart_ombres(nul, 15, permutations=100, graine=k)["p"] < 0.05
verifier(f"sans effet, detections a 5 % : {detections}/40", detections <= 6)
avec_incident = [("a0", 1, None, "ironie"), ("a1", 1, "ironie", "ironie"),
                 ("a2", 1, "ironie", "tendance"), ("a3", 1, "ironie", "ringard")]
reel, ombre = I._series(avec_incident, 2)
verifier("une decision en incident reste manquante", reel[1]["a0"] is None)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec.")
    sys.exit(1)
print("Toutes les verifications passent.")
