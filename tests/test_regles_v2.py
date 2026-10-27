"""Verifications des regles v2 (etape 5), terme par terme, sans appel LLM.

Chaque terme du score est teste seul, sur un monde de 3 agents construit a la
main, puis chaque interrupteur. Les runs entiers servent au contrat et a la
reproductibilite.

    python3 tests/test_regles_v2.py
"""
import copy
import math
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import boucle_v2, population_v2, regles_v2
from ephemere.contrat import verifier as conforme
from ephemere.horloge import Horloge
from ephemere.monde_v2 import MondeV2
from ephemere.regles_v2 import ReglesV2

CONFIG = os.path.join(RACINE, "config", "tessaline_v2.json")
CFG = population_v2.charger(CONFIG)
echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def reglage(**surcharges):
    return boucle_v2.regler(CFG, surcharges)["decision"]


def trio(porte_b=True, porte_c=False, groupe_c="club_humour", **traits):
    """a (atelier) est lie fortement a b (atelier) et faiblement a c."""
    t = {"appartenance": 0.5, "distinction": 0.5, "nouveaute": 0.5, "seuil": 0.2,
         "affinites": {g: 0.0 for g in CFG["groupes"]}, **traits}
    agents = []
    for aid, groupe, porte in (("a", "atelier_design", False), ("b", "atelier_design", porte_b),
                               ("c", groupe_c, porte_c)):
        agents.append({"id": aid, "nom": aid.upper(), "groupe": groupe, "porte": porte,
                       "categorie": "aucun_sens", "memoire": [], "vu_jusqu_a": 0,
                       "minutes_porte": 0, "moteur": "regles", "traits": copy.deepcopy(t)})
    liens = [{"a": "a", "b": "b", "type": "fort", "poids": 1.0},
             {"a": "a", "b": "c", "type": "faible", "poids": 0.3}]
    obs = {**CFG["observation"], "croises": [0, 0]}
    monde = MondeV2(agents, liens, obs, 1)
    r = reglage()
    for x in agents:
        regles_v2.initialiser(x, r)
    return monde, monde.agents["a"]


def termes(monde, a, t_sim=1440, **surcharges):
    r = reglage(bruit=0, **surcharges)
    vu = monde.observer(a, t_sim)
    regles_v2.percevoir(a, vu, t_sim, r)
    return ReglesV2(r, 0).termes(a, vu, t_sim), vu


print("Termes, un par un")
m, a = trio()
t, _ = termes(m, a, nouveaute_depuis="apparition", usure=True)
verifier(f"E pondere : b porte (1,0), c non (0,3) -> {t['E']:.3f}", abs(t["E"] - 1 / 1.3) < 1e-9)
verifier("appartenance = a x E", abs(t["appartenance"] - 0.5 * t["E"]) < 1e-9)
verifier("usure, depuis J1 : nouveaute = n x exp(-t / tau)",
         abs(t["nouveaute"] - 0.5 * math.exp(-1 / CFG["decision"]["tau_jours"])) < 1e-9)
verifier("sans usure : nouveaute = n, des la premiere vue",
         termes(*trio(), usure=False)[0]["nouveaute"] == 0.5)
mm, aa = trio()
termes(mm, aa, usure=True)
verifier("usure, depuis la premiere vue : le compteur part du jour ou il a vu",
         abs(termes(mm, aa, t_sim=2880, usure=True)[0]["nouveaute"]
             - 0.5 * math.exp(-1 / CFG["decision"]["tau_jours"])) < 1e-9)
m, a = trio(porte_b=False)
t, _ = termes(m, a, nouveaute_depuis="premiere_vue")
verifier("premiere_vue : nouveaute nulle tant que l'agent n'a vu personne porter", t["nouveaute"] == 0)
m, a = trio(porte_c=True)
a["traits"]["affinites"]["club_humour"] = -0.5
t, _ = termes(m, a)
verifier(f"R : 1 porteur sur 2 vient d'un groupe repoussoir -> {t['R']}", t["R"] == 0.5)
verifier("distinction = d x (alpha.R + beta.P)", abs(t["distinction"] - 0.5 * 0.5) < 1e-9)
a["sens_percu"] = "suivre_la_foule"
t, _ = termes(m, a)
verifier("P = 1 si le campus le lit comme suivre_la_foule", t["P"] == 1 and
         abs(t["distinction"] - 0.5 * (0.5 + 1)) < 1e-9)

print("\nInterrupteurs")
verifier("distinction = faux : terme nul", termes(m, a, distinction=False)[0]["distinction"] == 0)
verifier("alpha = 0 : seul P compte", abs(termes(m, a, alpha=0.0)[0]["distinction"] - 0.5) < 1e-9)
verifier("beta = 0 : seul R compte", abs(termes(m, a, beta=0.0)[0]["distinction"] - 0.25) < 1e-9)
verifier("nouveaute = faux : terme nul", termes(m, a, nouveaute=False)[0]["nouveaute"] == 0)
a["lassitude"] = 0.4
verifier("lassitude lue dans l'etat", termes(m, a, **{"lassitude.actif": True})[0]["lassitude"] == 0.4)
verifier("lassitude.actif = faux : terme nul", termes(m, a, **{"lassitude.actif": False})[0]["lassitude"] == 0)
verifier("bruit = 0 : terme nul", termes(m, a)[0]["bruit"] == 0)
x = {"porte": False, "lassitude": 0.3, "minutes_porte": 0}
d = {"porte": True, "categorie": "tendance", "sens": "", "sens_percu": "aucun_sens", "confiance": 0.3}
regles_v2.appliquer(x, d, reglage())
verifier("un jour porte : lassitude + 0,1", x["lassitude"] == 0.4)
regles_v2.appliquer(x, {**d, "porte": False}, reglage())
verifier("un jour sans : lassitude - 0,05", x["lassitude"] == 0.35)

print("\nDecision")
m, a = trio()
r = reglage(bruit=0)
vu = m.observer(a, 1440)
regles_v2.percevoir(a, vu, 1440, r)
d = ReglesV2(r, 0).decider(a, m, vu, 1440)
t = d["termes"]
S = t["appartenance"] + t["nouveaute"] - t["distinction"] - t["lassitude"] - t["seuil"] + t["bruit"]
verifier("porte si et seulement si S > 0", abs(t["S"] - S) < 1e-3 and d["porte"] == (S > 0))
m, a = trio(appartenance=0.0, nouveaute=0.0)
vu = m.observer(a, 1440)
regles_v2.percevoir(a, vu, 1440, r)
verifier("sans appartenance ni nouveaute, le seuil l'emporte",
         ReglesV2(r, 0).decider(a, m, vu, 1440)["porte"] is False)

print("\nCroyances")
m, a = trio()
m.adresser("b", "A", "c'est dans le coup", 1400, "J01 23:20", categorie="tendance")
m.publier("c", "c'est dans le coup", 1400, categorie="tendance")
vu = m.observer(a, 1440)
regles_v2.percevoir(a, vu, 1440, r)
a["confiance"] = 0.0
d = ReglesV2(r, 0).decider(a, m, vu, 1440)
verifier("sens_percu = le plus entendu", d["sens_percu"] == "tendance")
verifier("confiance 0 : adopte le sens entendu chez un lien fort", d["categorie"] == "tendance")
verifier("les sources citent le message et la publication",
         {x["id"] for x in vu["messages"] + vu["publications"]} <= set(d["sources"]))
a["confiance"] = 1.0
verifier("confiance 1 : ne change jamais de sens",
         ReglesV2(r, 0).decider(a, m, vu, 1440)["categorie"] == a["sens_perso"])
m, a = trio(porte_b=False, porte_c=True)
vu = m.observer(a, 1440)
regles_v2.percevoir(a, vu, 1440, r)
d = ReglesV2(r, 0).decider(a, m, vu, 1440)
verifier("rien entendu, porteurs surtout hors atelier : suivre_la_foule, source = l'observation",
         d["sens_percu"] == "suivre_la_foule"
         and d["sources"] == [o["id"] for o in vu["observations"] if o["qui"] == "c"])
m2, a2 = trio(porte_b=False, porte_c=True)
vu2 = m2.observer(a2, 1440)
regles_v2.percevoir(a2, vu2, 1440, r)
verifier("deduction_foule = faux : sens_percu inchange",
         ReglesV2(reglage(bruit=0, deduction_foule=False), 0).decider(a2, m2, vu2, 1440)["sens_percu"]
         == "aucun_sens")
debut = a["vus_recents"][0]["t_sim"]
regles_v2.percevoir(a, {"observations": [], "messages": [], "publications": []},
                    debut + (CFG["decision"]["fenetre_jours"] + 1) * 1440, r)
verifier("au-dela de la fenetre, les observations sont oubliees", a["vus_recents"] == [])

print("\nRegle 3")


def abandon(regle3):
    # S sans distinction = 1 - 0,6 = +0,4 ; avec distinction (R = 0,5) = -0,1.
    m, a = trio(porte_c=True, appartenance=1.0, nouveaute=0.0, seuil=0.6, distinction=1.0)
    a["traits"]["affinites"]["club_humour"] = -1.0
    a["porte"] = True
    rr = reglage(bruit=0, regle3=regle3, **{"lassitude.actif": False})
    vu = m.observer(a, 1440)
    regles_v2.percevoir(a, vu, 1440, rr)
    return ReglesV2(rr, 0).decider(a, m, vu, 1440), vu


d, vu = abandon(True)
verifier("abandon cause par la distinction : passe a ringard", not d["porte"] and d["categorie"] == "ringard")
verifier("la source est le porteur repoussoir vu",
         d["sources"] == [o["id"] for o in vu["observations"] if o["qui"] == "c"])
verifier("regle3 = faux : le sens ne change pas", abandon(False)[0]["categorie"] == "aucun_sens")

print("\nRuns entiers")


def run(r_, **kw):
    m, c, g, _ = boucle_v2.construire(CONFIG, 20, r_, **kw)
    d = ReglesV2(c["decision"], g["dynamique"])
    j = boucle_v2.JournalMemoire()
    boucle_v2.tourner(m, c, {a: d for a in m.agents}, j, Horloge(0), 25)
    return j


j = run(3)
verifier("meme r, meme run", run(3).evenements == j.evenements)
verifier("autre graine dynamique, autre run", run(3, dynamique=4).evenements != j.evenements)
enveloppe = {"run": "t", "t_sim": 0, "t_sim_lisible": "J01 00:00",
             "t_emission": "2026-10-27T00:00:00.000", "t_traitement": None}
refus = [(e["schema"], conforme({**enveloppe, **e})[1]) for e in j.evenements
         if not conforme({**enveloppe, **e})[0]]
verifier(f"{len(j.evenements)} evenements, tous conformes au contrat", not refus, refus[:3])
ids_vus = {x["id"] for e in j.evenements if e["schema"] == "perception.v2"
           for canal in ("observations", "messages", "publications") for x in e[canal]}
sources = [s for e in j.evenements if e["schema"] == "decision.v2" for s in e["sources"]]
verifier(f"chaque source citee ({len(sources)}) a bien ete vue", set(sources) <= ids_vus)
verifier("les regles publient leur sens",
         any(e["schema"] == "publication.v2" and e["categorie"] for e in j.evenements))

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
