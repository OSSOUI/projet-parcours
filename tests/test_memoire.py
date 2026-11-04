"""Memoire individuelle : reference inchangee, variante --memoire-sens, ombre sans_souvenirs,
audit hors ligne. Aucun appel reseau : le modele est simule.

    python3 tests/test_memoire.py
"""
import hashlib
import os
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import audit_memoire  # noqa: E402
import simuler  # noqa: E402
from ephemere import contrat, population  # noqa: E402
from ephemere.agents_llm import DecideurLLM  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.journal import Journal  # noqa: E402
from ephemere.monde import Monde  # noqa: E402
from ephemere.rag import Base  # noqa: E402
from ephemere.regles_v1 import Regles  # noqa: E402

echecs = []
# Empreinte des prompts reels de ce scenario, relevee le 4 novembre AVANT l'ajout
# de la memoire du sens : sans --memoire-sens, les prompts doivent rester ceux-la.
EMPREINTE_REFERENCE = {(): (34, "d70dbf1a0b15eb32ac4f5fd943d0d1dadd0d3ea46103d21f82f89bcbd96c6543"),
                       ("sans_discours", "sans_social"):
                       (102, "ed792ae2338f27861b22a24bb5774aa4a88528f9960e7713504ec17b72479acc")}


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


class Client:
    """Modele simule, deterministe : varie le sens, publie, ecrit parfois a Lea."""

    def __init__(self):
        self.consignes, self.derniere_mesure, self.dernier_brut = [], {}, None

    def json(self, systeme, consigne, taille="llm_petit", **_):
        self.consignes.append(systeme + consigne)
        self.derniere_mesure = {"latence_s": 0.1}
        n = len(self.consignes)
        return {"porte": n % 3 != 0, "categorie": ["tendance", "ironie", "suivre_la_foule"][n % 3],
                "sens": f"s{n}", "publication": f"message {n}" if n % 2 else "",
                "destinataire": "Lea" if n % 5 == 0 else "", "raison": f"raison {n} ironie"}


def scenario(ombres=(), memoire_sens=False, jours=4, dossier=None):
    """Le scenario des empreintes : 20 agents, graine 100, boucle du simulateur."""
    c = Client()
    base = Base(os.path.join(RACINE, "corpus"))
    agents, config = population.construire(os.path.join(RACINE, "config", "tessaline.json"),
                                           20, 100)
    monde = Monde(agents, config.get("perception"))
    r = Regles()
    dec = {a["id"]: DecideurLLM(c, a["moteur"], base=base, memoire_sens=memoire_sens)
           if a["moteur"] != "regles" else r for a in agents}
    args = types.SimpleNamespace(jours=jours, pas_min=1440, releve_min=1440, ombres=list(ombres),
                                 telemetrie=None, dialogue=None, pionnieres_simultanees=False)
    with tempfile.TemporaryDirectory() as d:
        with Journal(dossier or d, "m", Horloge(0)) as j:
            j.ecrire("run.v2", mode="synchrone", nb_agents=20, graine=100, jours=jours,
                     config="tessaline.json", version_contrat=contrat.VERSION_CONTRAT,
                     modele_social="v1")
            j.ecrire("population.v1", resume={}, agents=[
                {k: a[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")}
                for a in agents])
            simuler.tourner_synchrone(monde, dec, j, j.horloge, args)
            chemin = j.chemin
        audit = audit_memoire.auditer(chemin) if dossier is None else None
    return c, agents, audit


print("1. La reference ne change pas")
for ombres, (n, empreinte) in EMPREINTE_REFERENCE.items():
    c, _, _ = scenario(ombres)
    h = hashlib.sha256("\n\0".join(c.consignes).encode()).hexdigest()
    verifier(f"prompts {'+'.join(ombres) or 'sans ombre'} identiques a l'empreinte du 4 novembre "
             f"({n} prompts)", (len(c.consignes), h) == (n, empreinte), (len(c.consignes), h))
c, agents, audit = scenario()
verifier("aucun prompt de reference ne montre le sens de la veille",
         not any("voulait alors dire" in x for x in c.consignes))
llm = [a for a in agents if a["moteur"] != "regles"]
verifier("la memoire garde le sens de chaque decision (pour la variante)",
         all(m.get("categorie") in SENS for a in llm for m in a["memoire"]
             if m["genre"] == "decision"))

print("\n2. Variante --memoire-sens")
cv, agents_v, _ = scenario(memoire_sens=True)
verifier("meme nombre d'appels que la reference", len(cv.consignes) == len(c.consignes))
avec = [x for x in cv.consignes if "voulait alors dire" in x]
verifier(f"le sens de la veille apparait dans les prompts ({len(avec)} sur {len(cv.consignes)})",
         len(avec) > 0)
premier_jour = [x for x in cv.consignes[:5]]
verifier("pas de sens affiche avant toute decision (jour 1)",
         not any("voulait alors dire" in x for x in premier_jour))

print("\n3. Ombre sans_souvenirs : seule la memoire est retiree")
from ephemere.monde import memoriser  # noqa: E402
agents_o, config = population.construire(os.path.join(RACINE, "config", "tessaline.json"), 12, 1)
monde = Monde(agents_o, config.get("perception"))
ag = next(x for x in agents_o if x["moteur"] != "regles")
autre = next(x for x in agents_o if x["id"] != ag["id"])
monde.publier(autre["id"], "message public du jour", 600)
ag["memoire"] = memoriser(ag["memoire"], {"genre": "decision", "t_sim": 400,
                                          "t_sim_lisible": "J01 06:40", "categorie": "ironie",
                                          "fait": "j'ai decide de porter le ruban",
                                          "raison": "souvenir de decision"})
d = DecideurLLM(Client(), ag["moteur"])
complet, _ = d._consigne(ag, monde, 700, "J01 11:40")
sans, perception = d._consigne(ag, monde, 700, "J01 11:40", masque="sans_souvenirs")
verifier("le souvenir disparait", "souvenir de decision" in complet
         and "souvenir de decision" not in sans and "(rien pour l'instant)" in sans)
verifier("le fil et l'adoption vue restent", "message public du jour" in sans and "le portent" in sans)
verifier("la perception de l'ombre n'a aucun souvenir", perception["souvenirs"] == [])
verifier("le contrat accepte une ombre sans_souvenirs", contrat.verifier({
    "schema": "ombre.v1", "run": "r", "t_sim": 0, "t_sim_lisible": "J01 00:00", "t_emission": "x",
    "t_traitement": None, "agent": "a", "masque": "sans_souvenirs", "t_decision": 0,
    "porte": True, "categorie": "ironie", "valide": True, "incident": None,
    "reel_porte": True, "reel_categorie": "ironie", "reel_valide": True})[0])
dv = DecideurLLM(Client(), ag["moteur"], memoire_sens=True)
variante, pv = dv._consigne(ag, monde, 700, "J01 11:40")
verifier("variante : la ligne du souvenir dit le sens de CETTE decision (ironie)",
         "J01 06:40 : j'ai decide de porter le ruban (souvenir de decision) ; pour toi, le ruban "
         f"voulait alors dire : {SENS['ironie']}" in variante)
_, pr = d._consigne(ag, monde, 700, "J01 11:40")
verifier("perception : sens_affiche seulement dans la variante",
         pv["souvenirs"][0].get("sens_affiche") == "ironie" and "sens_affiche" not in pr["souvenirs"][0])

print("\n4. Audit hors ligne : la memoire reconstruite redonne les souvenirs injectes")
verifier(f"reconstruction exacte sur {audit['decisions_llm']} decisions LLM simulees",
         audit["reconstruction_exacte"] == 1.0, audit["reconstruction_exacte"])
verifier("des echanges recus sont comptes", audit["echanges"]["recus_distincts"] > 0, audit["echanges"])
verifier("la reference n'affiche jamais le sens de la veille",
         audit["injecte"]["sens_explicite_de_la_veille"] == 0)

print("\n5. Experience A/E : comparabilite et statistiques fixees d'avance")
import experience_memoire as X  # noqa: E402
import verifier_comparabilite  # noqa: E402
gele = os.path.join(RACINE, "runs", "exp_reference_llm_reference_01.jsonl")
if os.path.exists(gele):
    r = verifier_comparabilite.verifier_run(gele)
    verifier("le code actuel refait le run gele (ombres, + sans_souvenirs, variante)",
             all(v for v in r.values() if isinstance(v, bool)), r)
    verifier("persistance du sens = celle de l'audit (0,745 pour la graine 100)",
             round(X.taux(X.gardes_par_agent(X.decisions(X.lire(gele))[1])), 3) == 0.745)
verifier("E = A + sans_souvenirs + --memoire-sens, rien d'autre",
         X.OPTIONS_E == X.OPTIONS_A + ["sans_souvenirs", "--memoire-sens"]
         and X.OPTIONS_A == ["--mode", "synchrone", "--ombres", "sans_discours", "sans_social"])
verifier("test des signes : 9 sur 10 -> p = 11/1024", X.test_signes(9, 10) == 11 / 1024)
verifier("Wilcoxon exact unilateral", X.wilcoxon([1, 2, 3, -0.5])["p"] == 2 / 16)
verifier("permutation par agent exacte", X.permutation_agents(
    [((1, 2), (2, 2))] * 3, X.ecart_taux) == {"observe": 0.5, "p": 0.125, "methode": "exacte",
                                              "agents": 3})

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec.")
    sys.exit(1)
print("Toutes les verifications passent.")
