"""Verifications des mesures LLM (ephemere/mesures_llm.py) sur un run fabrique a
la main : chaque chiffre attendu se calcule de tete.

    python3 tests/test_mesures_llm.py
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import mesures_llm as M  # noqa: E402

J = 1440
echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def agent(i, profil, moteur, porte=False):
    return {"id": i, "nom": i.capitalize(), "profil": profil, "groupe": "g", "moteur": moteur,
            "porte": porte}


def decision(i, t, porte, cat, moteur="llm_petit", valide=True):
    return {"schema": "decision.v1", "agent": i, "t_sim": t, "porte": porte, "categorie": cat,
            "sens": "", "raison": "", "moteur": moteur, "valide": valide}


def perception(i, t, campus, souvenirs=(), messages=()):
    return {"schema": "perception.v1", "agent": i, "t_sim": t, "moteur": "llm_petit",
            "messages": list(messages), "souvenirs": list(souvenirs), "documents": [],
            "vue": {"campus": f"{campus} etudiants sur 10 le portent"}}


pop = {"schema": "population.v1", "agents": [
    agent("pia", "pionnier", "llm_grand", porte=True),
    agent("sam", "suiveur", "llm_petit", porte=True),
    agent("ira", "ironique", "llm_petit"),
    agent("reg", "suiveur", "regles"),
]}
evs = [pop,
       # J1 : 8 sur 10 portent. Le pionnier abandonne, le suiveur garde.
       perception("pia", J, 8), decision("pia", J, False, "ringard", "llm_grand"),
       perception("sam", J, 8, souvenirs=[{"t_sim": 0}]), decision("sam", J, True, "tendance"),
       perception("ira", J, 8), decision("ira", J, True, "ironie"),
       decision("reg", J, True, "tendance", "regles"),
       {"schema": "incident.v1", "agent": "sam", "nature": "incoherence_texte_etat", "details": {}},
       # Message prive de pia a sam, lu a J2 ; sam change alors de sens.
       {"schema": "publication.v1", "agent": "pia", "t_sim": J, "texte": "c'est depasse",
        "portee": "personne", "destinataire": "Sam"},
       {"schema": "publication.v1", "agent": "ira", "t_sim": J, "texte": "c'est depasse !",
        "portee": "campus", "destinataire": None},
       perception("sam", 2 * J, 9), decision("sam", 2 * J, True, "ringard"),
       # J5 : un souvenir de J1, vieux de 4 jours ; ira change de sens sans message.
       perception("ira", 5 * J, 9, souvenirs=[{"t_sim": J}]), decision("ira", 5 * J, True, "tendance"),
       ]

print("Fiabilite (A4)")
f = M.fiabilite(evs)
verifier("un incident sur 2 decisions du suiveur LLM",
         f[("llm_petit", "suiveur")]["incidents"] == 1 and f[("llm_petit", "suiveur")]["decisions"] == 2)
verifier("les agents a regles ne sont pas comptes", all(k[0] != "regles" for k in f))

print("\nFidelite (A3)")
fid = M.fidelite(evs)
haut = len(M.TRANCHES)
verifier("pionnier : 1 abandon sur 1 porteur a 80 %", fid[("llm_grand", "pionnier", haut)]["taux"] == 1.0)
verifier("suiveur : 0 abandon sur 2 decisions de porteur a 80 et 90 %",
         fid[("llm_petit", "suiveur", haut)] == {"abandons": 0, "porteurs": 2, "taux": 0.0})
verifier("un non-porteur n'entre pas dans le taux d'abandon",
         ("llm_petit", "ironique", haut) in fid and fid[("llm_petit", "ironique", haut)]["porteurs"] == 1)

print("\nMemoire et echanges (A1, A2)")
mem = M.memoire(evs)
verifier("1 decision LLM sur 5 avait un souvenir de plus de 3 jours",
         (mem["avec_souvenir_ancien"], mem["decisions"]) == (1, 5), mem)
ech = M.echanges(evs)
verifier("le message prive a Sam est suivi d'un changement de sens",
         ech["avec_message"] == {"changements": 1, "decisions": 1, "taux": 1.0}, ech)
verifier("passer d'aucun sens a un premier sens ne compte pas comme un changement",
         ech["sans_message"]["decisions"] == 3, ech)

print("\nSens (B1, B3)")
div = M.diversite(evs)
verifier("a la fin, Pia et Sam ringard, Ira tendance : 2 sens distincts",
         div["sens_distincts_fin"] == 2, div)
dup = M.quasi_identiques(evs)
verifier("\"c'est depasse\" et \"c'est depasse !\" sont quasi identiques",
         dup["quasi_identiques"] == 2 and dup["messages"] == 2, dup)
v2 = [{"schema": "population.v2", "agents": [{**agent("x", "suiveur", "regles"),
                                              "categorie": "aucun_sens"}]},
      {"schema": "perception.v2", "agent": "x", "t_sim": J, "observations": [{"id": "o1"}],
       "messages": [], "publications": []},
      {"schema": "decision.v2", "agent": "x", "t_sim": J, "porte": True, "categorie": "tendance",
       "sources": ["o1"], "moteur": "regles"},
      {"schema": "decision.v2", "agent": "x", "t_sim": 2 * J, "porte": True, "categorie": "ringard",
       "sources": ["o9"], "moteur": "regles"}]
src = M.sources_valides(v2)
verifier("v2 : 1 changement sur 2 cite une source vraiment vue",
         (src["justifies"], src["changements"]) == (1, 2), src)

print("\nTemps (C5)")
tel = [{"type": "appel", "modele": "m", "latence_s": x, "attente_s": 1.0} for x in (1, 2, 3, 4)]
t = M.temps(evs, tel)
verifier("latence moyenne et attente cumulee",
         t["latences"]["m"]["moyenne"] == 2.5 and t["latences"]["m"]["attente_s"] == 4.0)

print("\nEchantillon F2")
rec = [{"schema": "recuperation.v1", "agent": "sam", "t_sim": J, "requete": "q",
        "resultats": [{"id": "inconnu", "score": 1.0, "numero": 0}], "nb_resultats": 1}]
lignes = M.echantillon_f2(evs + rec, os.path.join(RACINE, "corpus"))
verifier("une ligne par decision tiree, colonne de jugement vide",
         len(lignes) == 1 and lignes[0]["pertinent (oui / en partie / non)"] == "")

print("\nConfusion et garde-fou (point zero repete)")
t, f = "tendance", "suivre_la_foule"
avant = ([{"agent": "a", "modele": "petit", "categorie": c} for c in (t, f, t, f)]
         + [{"agent": "b", "modele": "petit", "categorie": c} for c in (t, "ironie")])
apres = ([{"agent": "a", "modele": "petit", "categorie": c} for c in (f, f, f, f)]
         + [{"agent": "b", "modele": "petit", "categorie": c} for c in (f, "ironie")])
c = M.confusion(avant)
verifier("a : 6 paires dont 4 discordantes ; b : aucune paire",
         c["paires"] == 6 and c["discordantes"] == 4 and c["agents_mixtes"] == 1, c)
verifier("tout sous suivre_la_foule : confusion nulle", M.confusion(apres)["taux"] == 0)
g_av, g_ap = M.garde_fou(avant), M.garde_fou(apres)
verifier("le garde-fou compte les sens employes",
         g_av["petit"]["sens_utilises"] == 3 and g_ap["petit"]["sens_utilises"] == 2)
verifier("plus aucun tendance : effondrement signale",
         g_ap["petit"]["effondrement"] == [t] and g_av["petit"]["effondrement"] == [])
alertes = M.alertes_garde_fou(g_av, g_ap)
verifier("l'alerte accompagne une confusion nulle",
         any("plus aucun tendance" in a for a in alertes), alertes)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
