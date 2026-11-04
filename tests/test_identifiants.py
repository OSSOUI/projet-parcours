"""Identifiants d'evenements (seq), lecture des anciens runs, doublons Kafka.
Aucun appel reseau : le producteur Kafka est simule.

    python3 tests/test_identifiants.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ephemere import contrat, journal  # noqa: E402
from ephemere.bus import Bus  # noqa: E402
from ephemere.campus import Campus  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


ENTETE = {"mode": "synchrone", "nb_agents": 1, "graine": 1, "jours": 1, "config": "t.json",
          "version_contrat": contrat.VERSION_CONTRAT, "modele_social": "v1"}
DECISION = {"agent": "a", "porte": True, "categorie": "tendance", "sens": "s", "raison": "r",
            "moteur": "regles", "valide": True}


class Futur:
    def __init__(self):
        self.ok, self.ko = [], []

    def add_callback(self, f):
        self.ok.append(f)

    def add_errback(self, f):
        self.ko.append(f)


class ProducteurFactice:
    """Garde chaque envoi ; le test decide ensuite qui reussit et qui echoue."""

    def __init__(self):
        self.envois = []

    def send(self, topic, key, value):
        f = Futur()
        self.envois.append((value, f))
        return f

    def flush(self, timeout=None):
        pass

    def close(self, timeout=None):
        pass


print("1. seq : rang parmi les evenements conformes, egal au numero de ligne")
with tempfile.TemporaryDirectory() as dossier:
    h = Horloge(0)
    with journal.Journal(dossier, "r", h) as j:
        j.ecrire("run.v2", **ENTETE)
        j.ecrire("decision.v1", **{**DECISION, "categorie": "licorne"})   # rejete
        j.ecrire("decision.v1", **DECISION)
        h.aller_a(10)
        j.ecrire("decision.v1", **DECISION)
        chemin, rejets = j.chemin, j.chemin_rejets
    lignes = [json.loads(l) for l in open(chemin, encoding="utf-8")]
    verifier("seq 0, 1, 2 sans trou malgre le rejet", [e["seq"] for e in lignes] == [0, 1, 2])
    rejet = json.loads(open(rejets, encoding="utf-8").readline())["evenement"]
    verifier("un evenement rejete ne porte pas de seq", "seq" not in rejet)
    lus = journal.lire(chemin)
    verifier("journal.lire garde le seq ecrit", [e["seq"] for e in lus] == [0, 1, 2])
    verifier("identifiant run#seq", journal.identifiant(lus[2]) == "r#2")

print("\n2. Anciens runs (sans seq) : migration verifiee, jamais supposee")


def ecrire(dossier, nom, evenements, brut=None):
    p = os.path.join(dossier, nom)
    with open(p, "w", encoding="utf-8") as f:
        for e in evenements:
            f.write(json.dumps(e) + "\n")
        if brut:
            f.write(brut)
    return p


def evt(schema, t, run="vieux", **corps):
    return {"schema": schema, "run": run, "t_sim": t, "t_sim_lisible": "", "t_emission": "x",
            "t_traitement": None, **corps}


with tempfile.TemporaryDirectory() as d:
    sain = [evt("run.v2", 0, **ENTETE), evt("decision.v1", 0, **DECISION),
            evt("decision.v1", 5, **DECISION)]
    verifier("ancien run sain : seq = numero de ligne",
             [e["seq"] for e in journal.lire(ecrire(d, "a.jsonl", sain))] == [0, 1, 2])
    cas = {
        "sans en-tete en tete": sain[1:],
        "deux runs dans un fichier": sain + [evt("decision.v1", 9, run="autre", **DECISION)],
        "temps simule qui recule": sain + [evt("decision.v1", 1, **DECISION)],
        "seq different de la ligne": sain[:1] + [{**sain[1], "seq": 7}],
    }
    for nom, evs in cas.items():
        try:
            journal.lire(ecrire(d, "b.jsonl", evs))
            verifier(f"refuse : {nom}", False)
        except journal.JournalIllisible:
            verifier(f"refuse : {nom}", True)
    try:
        journal.lire(ecrire(d, "c.jsonl", sain, brut='{"schema": "deci'))
        verifier("refuse : derniere ligne tronquee", False)
    except journal.JournalIllisible:
        verifier("refuse : derniere ligne tronquee", True)

print("\n3. Contrat : seq facultatif, verifie s'il est present")
base = evt("decision.v1", 0, **DECISION)
verifier("sans seq : conforme (runs anterieurs)", contrat.verifier(dict(base))[0])
verifier("seq entier : conforme", contrat.verifier({**base, "seq": 3})[0])
verifier("seq booleen : refuse", not contrat.verifier({**base, "seq": True})[0])
verifier("seq texte : refuse", not contrat.verifier({**base, "seq": "3"})[0])
verifier("seq negatif : refuse", not contrat.verifier({**base, "seq": -1})[0])

print("\n4. Le pont ecarte les doublons Kafka et compte les trous")
flux = [{**evt("run.v2", 0, run="k", **ENTETE), "seq": 0},
        {**evt("decision.v1", 0, run="k", **DECISION), "seq": 1},
        {**evt("decision.v1", 0, run="k", **DECISION), "seq": 1},      # renvoi
        {**evt("run.v2", 0, run="k", **ENTETE), "seq": 0},             # en-tete renvoye
        {**evt("decision.v1", 5, run="k", **{**DECISION, "agent": "b"}), "seq": 4}]
c = Campus(en_direct=False)
for e in flux:
    if not c.deja_vu(e, "k"):
        c.appliquer(dict(e), "k")
verifier("deux doublons ecartes", c.doublons == 2)
verifier("l'en-tete renvoye ne remet pas le campus a zero", set(c.agents) == {"a", "b"})
verifier("deux evenements manquants comptes (seq 2 et 3)", c.trous == 2)
ancien = Campus(en_direct=False)
for e in sain + sain[1:]:
    if not ancien.deja_vu(e, "vieux"):
        ancien.appliquer(dict(e), "vieux")
verifier("sans seq (ancien run) rien n'est ecarte", ancien.doublons == 0 and ancien.vus == 5)

print("\n5. Le producteur ne perd rien en silence")
bus = Bus.__new__(Bus)
bus.topic, bus.nom_run = "t", "r"
bus.producteur = ProducteurFactice()
bus.publies = bus.confirmes = bus.perdus = bus.refus_immediats = 0
bus.seq_perdus = []
for i in range(4):
    bus.publier({"seq": i})
(_, f0), (_, f1), (_, f2), _ = bus.producteur.envois
f0.ok[0](None)
f1.ok[0](None)
f2.ko[0](RuntimeError("broker parti"))
b = bus.bilan()
verifier("2 confirmes, 1 perdu apres coup, 1 sans reponse",
         (b["confirmes"], b["perdus"], b["sans_reponse"]) == (2, 1, 1), b)
verifier("le seq perdu est nomme", b["seq_perdus"] == [2])

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec.")
    sys.exit(1)
print("Toutes les verifications passent.")
