"""Audit de la memoire individuelle des agents LLM, depuis les journaux. Aucun appel LLM.

Le journal n'enregistre pas la memoire d'un agent, seulement les souvenirs
INJECTES dans chaque prompt (perception.v1 : genre, t_sim, fait ; la raison,
pourtant affichee au modele, n'y est pas). On reconstruit donc la memoire
DISPONIBLE au moment de chaque decision, avec les fonctions memes du
simulateur (monde.memoriser, agents_llm.choisir_souvenirs) :

  souvenir de decision  un par decision.v1 (valide ou non), comme appliquer()
  souvenir d'echange    un par message prive recu (publication.v1 portee
                        "personne", replique.v1), comme monde.adresser()

En synchrone, une decision au pas T voit la memoire de la fin du pas
precedent : tout ce qui porte t_sim < T. La reconstruction est validee si
choisir_souvenirs() redonne exactement les souvenirs enregistres dans
perception.v1 ; sinon l'audit le dit.

    python3 audit_memoire.py runs/exp_reference_llm_reference_0[1-5].jsonl --json resultats/audit_memoire.json
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter

from ephemere import journal
from ephemere.agents_llm import choisir_souvenirs
from ephemere.monde import MAX_DECISIONS, MAX_ECHANGES, memoriser

LLM = ("llm_petit", "llm_grand")
# Mots qui disent un sens du ruban (liste fermee de contrat.SENS, en clair).
MOTS_SENS = re.compile(r"ironi|second degre|moqu|tendance|a la mode|dans le coup|foule|suiv|"
                       r"ringard|depasse|creati|atelier|cercle|ne veut rien|aucun sens|rien dire",
                       re.I)


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def auditer(chemin):
    evs = journal.lire(chemin)
    entete = evs[0]
    if entete.get("mode") != "synchrone":
        return {"run": entete["run"], "ignore": "audit valide pour le mode synchrone seulement"}
    pop = next(e for e in evs if e["schema"] in ("population.v1", "population.v2"))
    agents = {a["id"]: a for a in pop["agents"]}
    noms = {a["id"]: a.get("nom", a["id"]) for a in pop["agents"]}
    memoire = {a: [] for a in agents}
    instantane, t_courant = {}, None
    raisons = {}                 # (agent, t_sim) -> raison de la decision
    perceptions = []
    for e in evs:
        if e["t_sim"] != t_courant:
            # Debut d'un pas : ce que chaque agent a en memoire pour decider.
            t_courant = e["t_sim"]
            instantane = {a: list(m) for a, m in memoire.items()}
        s = e["schema"]
        if s == "perception.v1" and agents[e["agent"]]["moteur"] in LLM:
            perceptions.append((e, instantane[e["agent"]]))
        elif s == "decision.v1":
            raisons[(e["agent"], e["t_sim"])] = e["raison"]
            memoire[e["agent"]] = memoriser(memoire[e["agent"]], {
                "genre": "decision", "t_sim": e["t_sim"], "t_sim_lisible": e["t_sim_lisible"],
                "fait": f"j'ai decide de {'porter' if e['porte'] else 'ne pas porter'} le ruban",
                "raison": e["raison"]})
        elif ((s == "publication.v1" and e["portee"] == "personne" and e["destinataire"])
              or (s == "replique.v1" and e["valide"])):
            cible = e["destinataire"]
            memoire[cible] = memoriser(memoire[cible], {
                "genre": "echange", "t_sim": e["t_sim"], "t_sim_lisible": e["t_sim_lisible"],
                "fait": f"{noms[e['agent']]} m'a dit : \"{e['texte']}\"", "raison": ""})

    exactes = 0
    m_dec, m_ech, plein_dec, plein_ech = [], [], 0, 0
    inj_n, inj_genres, ages, avec_echange = [], Counter(), [], 0
    echanges_recus, echanges_injectes = set(), set()
    souvenirs_dec_injectes, avec_mot_sens = 0, 0
    for p, dispo in perceptions:
        choisis = choisir_souvenirs({"memoire": dispo})
        cle = [(m["genre"], m["t_sim"], m["fait"]) for m in choisis]
        if cle == [(m["genre"], m["t_sim"], m["fait"]) for m in p["souvenirs"]]:
            exactes += 1
        dec = [m for m in dispo if m["genre"] == "decision"]
        ech = [m for m in dispo if m["genre"] == "echange"]
        m_dec.append(len(dec))
        m_ech.append(len(ech))
        plein_dec += len(dec) >= MAX_DECISIONS
        plein_ech += len(ech) >= MAX_ECHANGES
        inj_n.append(len(choisis))
        avec_echange += any(m["genre"] == "echange" for m in choisis)
        for m in choisis:
            inj_genres[m["genre"]] += 1
            ages.append((p["t_sim"] - m["t_sim"]) / 1440)
            if m["genre"] == "echange":
                echanges_injectes.add((p["agent"], m["t_sim"], m["fait"]))
            else:
                souvenirs_dec_injectes += 1
                avec_mot_sens += bool(MOTS_SENS.search(_norm(m.get("raison") or "")))
        for m in ech:
            echanges_recus.add((p["agent"], m["t_sim"], m["fait"]))

    # Persistance du sens individuel d'une decision LLM valide a la suivante :
    # la base de comparaison de la variante "sens de la veille".
    prec, garde, paires = {}, 0, 0
    for e in evs:
        if e["schema"] == "decision.v1" and agents[e["agent"]]["moteur"] in LLM and e["valide"]:
            if e["agent"] in prec:
                paires += 1
                garde += prec[e["agent"]] == e["categorie"]
            prec[e["agent"]] = e["categorie"]

    n = len(perceptions) or 1
    return {
        "run": entete["run"], "decisions_llm": len(perceptions),
        "reconstruction_exacte": round(exactes / n, 4),
        "disponible": {
            "souvenirs_de_decision_moyen": round(statistics.mean(m_dec), 2) if m_dec else 0,
            "echanges_moyen": round(statistics.mean(m_ech), 2) if m_ech else 0,
            "part_au_plafond_decisions": round(plein_dec / n, 3),
            "part_au_plafond_echanges": round(plein_ech / n, 3)},
        "injecte": {
            "souvenirs_par_prompt_moyen": round(statistics.mean(inj_n), 2) if inj_n else 0,
            "par_genre": dict(inj_genres),
            "part_prompts_avec_un_echange": round(avec_echange / n, 3),
            "age_moyen_jours": round(statistics.mean(ages), 2) if ages else None,
            "age_max_jours": round(max(ages), 2) if ages else None,
            "raisons_de_decision_qui_nomment_un_sens": (round(avec_mot_sens / souvenirs_dec_injectes, 3)
                                                        if souvenirs_dec_injectes else None),
            "sens_explicite_de_la_veille": 0},
        "echanges": {"recus_distincts": len(echanges_recus),
                     "injectes_au_moins_une_fois": len(echanges_injectes & echanges_recus),
                     "jamais_injectes": len(echanges_recus - echanges_injectes)},
        "persistance_du_sens_individuel": round(garde / paires, 3) if paires else None,
        "paires_de_decisions": paires,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--json")
    args = p.parse_args()
    res = [auditer(c) for c in args.runs]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    return 0 if all(r.get("reconstruction_exacte", 1) == 1 for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
