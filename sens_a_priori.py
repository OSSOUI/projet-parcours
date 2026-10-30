"""Sens a priori du ruban : le point zero de la question Q2.

Q2 : quand les agents LLM s'accordent sur un sens, est-ce le fruit de leurs
echanges, ou de ce qu'ils ont en commun avant meme de se parler (le meme
modele, le meme prompt, le meme corpus) ? Pour trancher, il faut savoir ce
que chaque agent dit du ruban SANS AUCUNE information sociale.

Chaque personnage de la population recoit le prompt de sa premiere decision,
sans rien de social : ni qui le porte dans son groupe ou sur le campus, ni
message, ni souvenir. Quatre variantes (decidees le 28 octobre) ajoutent le
socle commun couche par couche :

  nu       le meme prompt systeme et le meme modele ; ni profil, ni
           personnalite, ni histoire du ruban, ni document
  profil   + son profil, sa personnalite et sa situation (une pionniere sait
           qu'elle a lance le ruban), sans document
  neutre   + les passages retrouves dans corpus_neutre/ (chartes et reglement
           tels quels, chroniques sans trajectoire ni morale)
  complet  + les passages retrouves dans corpus/, celui des runs deja faits

Un appel par personnage et par variante. Le meme personnage garde le meme
modele dans les quatre variantes : les ecarts se lisent agent par agent. Les
agents a regles n'ont pas de modele : ils repondent avec llm_petit. La
temperature est celle des runs (0,9) : c'est un tirage, pas une verite.

    python3 sens_a_priori.py                          # graine 100, les 4 variantes
    python3 sens_a_priori.py --variantes nu profil    # une partie seulement
    python3 sens_a_priori.py --graine 101

Ecrit resultats/sens_a_priori_g<graine>_<variante>.json (reponses, prompts, resume).

Frontiere entre tendance et suivre_la_foule (decidee le 29 octobre). Le meme
prompt est repose a chaque personnage (--repetitions), avec deux jeux de
definitions des six sens, en alternance appel par appel :

  courtes  celles des runs (contrat.SENS)
  nettes   agents_llm.DEFINITIONS_SENS, plus explicites sur la frontiere

Avec --sortie-structuree, le schema part dans l'appel avec les memes
definitions que le prompt : d'une condition a l'autre, seules les definitions
changent. La confusion se mesure chez un meme agent (mesures_llm.confusion) :
part des paires de ses tirages tendance / suivre_la_foule qui se contredisent.

    python3 sens_a_priori.py --variantes profil --repetitions 10 \\
        --definitions courtes nettes --sortie-structuree       # 2 x 200 appels
    python3 sens_a_priori.py --comparer AVANT.json APRES.json  # aucun appel

Resultat (30 octobre, graine 100, profil, 10 tirages, schema) : le critere est
rempli (21 % -> 4 %), mais le garde-fou montre que la baisse vient de
qwen2.5:3b, qui ne dit plus jamais tendance ni aucun_sens ; qwen2.5:7b passe
de 14 % a 33 %. Les definitions nettes ne sont pas retenues : les agents
gardent les courtes, et l'analyse regroupe tendance et suivre_la_foule.
"""
import argparse
import collections
import json
import math
import os
import sys
from datetime import datetime

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from ephemere import mesures_llm as M  # noqa: E402
from ephemere import population  # noqa: E402
from ephemere.agents_llm import (CONSIGNE, DEFINITIONS, SYSTEME, DecideurLLM,  # noqa: E402
                                 detecter_derive, lister_sens, schema_decision, valider)
from ephemere.contrat import SENS  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.llm import ClientLLM, charger_env  # noqa: E402
from ephemere.rag import Base  # noqa: E402

INCONNU = "tu ne sais pas encore qui le porte"
VARIANTES = ("nu", "profil", "neutre", "complet")
CORPUS = {"neutre": "corpus_neutre", "complet": "corpus"}
SITUATION_NUE = "Un ruban de couleur noue au poignet est apparu sur le campus."

# Critere fixe AVANT la mesure (29 octobre). La frontiere est jugee nette si le
# desaccord tendance / suivre_la_foule chez un meme agent baisse d'au moins
# moitie avec les definitions nettes, ET si l'intervalle a 95 % de la baisse
# (bootstrap sur les agents) reste au-dessus de zero. Sinon, le regroupement
# devient le choix officiel de l'analyse. Ni le critere ni les definitions ne
# se retouchent apres avoir vu le resultat.
BAISSE_RELATIVE_MIN = 0.5
PAIRES_MIN = 10      # en dessous, trop peu de paires pour que le verdict pese


def consigne_neutre(decideur, agent, t_sim, documents, nu=False, definitions=SENS):
    """Le prompt de la premiere decision, sans aucune information sociale.

    nu : ni profil, ni personnalite, ni histoire du ruban ; le prenom et le
    groupe restent, parce que le prompt des runs les nomme toujours.
    """
    h = Horloge(0)
    h.aller_a(t_sim)
    return CONSIGNE.format(
        nom=agent["nom"], profil="etudiant" if nu else agent["profil"].replace("_", " "),
        groupe=agent["groupe"],
        personnalite="" if nu else agent.get("personnalite", ""), date=h.lisible(),
        situation=SITUATION_NUE if nu else decideur._situation(agent),
        nb_groupe=INCONNU, noms_groupe="", campus=INCONNU,
        messages="- (rien de nouveau)", souvenirs="- (rien pour l'instant)",
        documents="\n".join(f"- {d['titre']} ({d['source']}) : {d['passage'][:220]}"
                            for d in documents) or "- (rien qui te revienne)",
        etat="portes" if agent["porte"] else "ne portes pas",
        categories=lister_sens(definitions),
        voisins="",
    )


def entropie(compte):
    n = sum(compte.values())
    if not n:
        return None
    return -sum(k / n * math.log(k / n) for k in compte.values() if k) / math.log(len(SENS))


def resumer(reponses):
    valides = [r for r in reponses if r["incident"] is None]
    tout = collections.Counter(r["categorie"] for r in valides)
    dominant, nb = tout.most_common(1)[0] if tout else (None, 0)
    return {
        "appels": len(reponses), "valides": len(valides),
        "repartition": dict(tout.most_common()),
        "dominant": dominant, "part_dominant": round(nb / len(valides), 3) if valides else None,
        "entropie": round(entropie(tout), 3) if valides else None,
        "porte": sum(r["porte"] for r in valides),
        "par_modele": {m: dict(collections.Counter(r["categorie"] for r in valides
                                                   if r["modele"] == m).most_common())
                       for m in sorted({r["modele"] for r in valides})},
        "par_profil": {p: dict(collections.Counter(r["categorie"] for r in valides
                                                   if r["profil"] == p).most_common())
                       for p in sorted({r["profil"] for r in valides})},
        "incidents": dict(collections.Counter(r["incident"] for r in reponses if r["incident"])),
    }


def _taux(x):
    return "n/a" if x is None else f"{x:.0%}"


def comparer(avant, apres):
    """Confusion tendance / suivre_la_foule avant et apres, et le verdict.

    La confusion suivre_la_foule / aucun_sens est relevee a cote : si la
    frontiere se deplace au lieu de se nettoyer, on doit le voir.
    """
    comp = M.comparer_confusion(avant, apres)
    comp["foule_aucun"] = {"avant": M.confusion(avant, "suivre_la_foule", "aucun_sens"),
                           "apres": M.confusion(apres, "suivre_la_foule", "aucun_sens")}
    comp["critere"] = {"baisse_relative_min": BAISSE_RELATIVE_MIN, "paires_min": PAIRES_MIN}
    # Garde-fou (ajoute apres le 30 octobre, sans toucher au critere) : une
    # confusion nulle peut venir d'un modele qui n'emploie plus qu'un des deux sens.
    comp["garde_fou"] = {"avant": M.garde_fou(avant), "apres": M.garde_fou(apres)}
    comp["alertes"] = M.alertes_garde_fou(comp["garde_fou"]["avant"],
                                          comp["garde_fou"]["apres"])
    if comp["baisse"] is None:
        comp["verdict"] = ("non mesurable (aucune paire tendance / suivre_la_foule dans une "
                           "condition) : pas de baisse nette, le regroupement devient le choix "
                           "officiel de l'analyse")
        comp["nette"] = False
        return comp
    i95 = comp["intervalle_95"]
    comp["nette"] = (comp["baisse_relative"] is not None
                     and comp["baisse_relative"] >= BAISSE_RELATIVE_MIN
                     and i95 is not None and i95[0] > 0)
    comp["verdict"] = ("baisse nette : les definitions vont dans la version LLM de la v2"
                       if comp["nette"] else
                       "pas de baisse nette : le regroupement devient le choix officiel de l'analyse")
    if comp["avant"]["paires"] < PAIRES_MIN:
        comp["verdict"] += (f" (attention : {comp['avant']['paires']} paires avant, "
                            f"moins de {PAIRES_MIN} : verdict fragile)")
    return comp


def afficher_comparaison(comp):
    print("\nCONFUSION tendance / suivre_la_foule chez un meme agent, prompt identique")
    for cle in ("avant", "apres"):
        c = comp[cle]
        print(f"  {cle:6s} {c['discordantes']:3d}/{c['paires']:<3d} paires discordantes "
              f"= {_taux(c['taux']):>4s}   agents qui melangent les deux : "
              f"{c['agents_mixtes']}/{c['agents_concernes']}   instabilite generale "
              f"{_taux(c['instabilite'])}")
    if comp["baisse"] is not None:
        i95 = comp["intervalle_95"]
        print(f"  baisse {comp['baisse']:+.0%} (relative {_taux(comp['baisse_relative'])}), "
              f"intervalle a 95 % " + (f"[{i95[0]:+.0%} ; {i95[1]:+.0%}]" if i95 else "n/a")
              + f", bootstrap sur les agents, {comp['tirages']} tirages")
    fa = comp["foule_aucun"]
    print(f"  a cote : suivre_la_foule / aucun_sens {_taux(fa['avant']['taux'])} avant, "
          f"{_taux(fa['apres']['taux'])} apres")
    print(f"  critere fixe avant la mesure : baisse relative >= {BAISSE_RELATIVE_MIN:.0%} "
          f"et intervalle au-dessus de zero")
    print(f"  => {comp['verdict']}")
    print("\nGARDE-FOU  repartition par modele et sens employes")
    for cle in ("avant", "apres"):
        for m, g in comp["garde_fou"][cle].items():
            print(f"  {cle:6s} {m:12s} {g['sens_utilises']} sens, confusion "
                  f"{_taux(g['confusion']):>4s} ({g['paires']} paires)  "
                  + ", ".join(f"{k} {v}" for k, v in g["repartition"].items()))
    for alerte in comp["alertes"]:
        print(f"  ! {alerte}")
    if comp["alertes"]:
        print("  => le verdict reste celui du critere, mais il ne se lit pas sans ces alertes.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--graine", type=int, default=100)
    p.add_argument("--agents", type=int, default=20)
    p.add_argument("--config", default=os.path.join(RACINE, "config", "tessaline.json"))
    p.add_argument("--variantes", nargs="+", choices=VARIANTES, default=list(VARIANTES))
    p.add_argument("--fournisseur", default="ollama")
    p.add_argument("--passages", type=int, default=3)
    p.add_argument("--repetitions", type=int, default=1,
                   help="tirages par personnage et par jeu de definitions")
    p.add_argument("--definitions", nargs="+", choices=list(DEFINITIONS), default=["courtes"],
                   help="courtes : celles des runs ; nettes : celles de la sortie structuree")
    p.add_argument("--sortie-structuree", action="store_true",
                   help="envoie le schema, avec les memes definitions que le prompt")
    p.add_argument("--comparer", nargs=2, metavar=("AVANT", "APRES"),
                   help="compare deux fichiers deja ecrits, sans aucun appel")
    p.add_argument("--ecrire", metavar="JSON", help="avec --comparer : ecrit la comparaison")
    args = p.parse_args()

    if args.comparer:
        lus = []
        for chemin in args.comparer:
            with open(chemin, encoding="utf-8") as f:
                lus.append(json.load(f)["reponses"])
        comp = comparer(*lus)
        afficher_comparaison(comp)
        if args.ecrire:
            with open(args.ecrire, "w", encoding="utf-8") as f:
                json.dump({"date": datetime.now().isoformat(timespec="seconds"),
                           "fichiers": args.comparer, **comp}, f, ensure_ascii=False, indent=1)
            print(f"  ecrit dans {args.ecrire}")
        return

    repete = (args.repetitions > 1 or args.definitions != ["courtes"]
              or args.sortie_structuree)
    agents, config = population.construire(args.config, args.agents, args.graine)
    charger_env(os.path.join(RACINE, ".env"))
    modeles = config["modeles"][args.fournisseur]
    client = ClientLLM(args.fournisseur, modeles)
    t_sim = 1440   # moment de la premiere decision dans un run synchrone
    print(f"Sens a priori, graine {args.graine}, {len(agents)} personnages, "
          f"temperature {client.temperature}, variantes {' '.join(args.variantes)}")
    if repete:
        print(f"  {args.repetitions} tirage(s) par personnage, definitions "
              f"{' et '.join(args.definitions)}"
              + (", schema envoye" if args.sortie_structuree else "")
              + f" : {args.repetitions * len(agents) * len(args.definitions)} appels par variante")
    os.makedirs(os.path.join(RACINE, "resultats"), exist_ok=True)
    for variante in args.variantes:
        base = Base(os.path.join(RACINE, CORPUS[variante])) if variante in CORPUS else None
        print(f"\n== {variante}")
        reponses = {d: [] for d in args.definitions}
        # Les conditions alternent appel par appel : une derive de la machine
        # ou du modele en cours de serie touche les deux de la meme facon.
        for tirage in range(args.repetitions):
            for a in agents:
                taille = a["moteur"] if a["moteur"] != "regles" else "llm_petit"
                decideur = DecideurLLM(client, taille, base=base, k=args.passages)
                requete, documents = decideur._recuperer(a, t_sim)
                for d in args.definitions:
                    consigne = consigne_neutre(decideur, a, t_sim, documents,
                                               nu=variante == "nu", definitions=DEFINITIONS[d])
                    schema = schema_decision(DEFINITIONS[d]) if args.sortie_structuree else None
                    rep = client.json(SYSTEME, consigne, taille,
                                      **({"schema": schema} if schema else {}))
                    nature, _ = detecter_derive(rep)
                    if nature is None and schema and valider(rep, schema):
                        nature = "schema_non_respecte"
                    ok = nature is None
                    r = {"agent": a["id"], "profil": a["profil"], "groupe": a["groupe"],
                         "moteur_du_run": a["moteur"], "taille": taille, "modele": modeles[taille],
                         "porte_avant": a["porte"], "incident": nature,
                         "porte": bool(rep["porte"]) if ok else None,
                         "categorie": rep["categorie"] if ok else None,
                         "sens": str(rep.get("sens", ""))[:300] if ok else "",
                         "raison": str(rep.get("raison", ""))[:300] if ok else "",
                         "documents": [f"{x['id']}#{x['numero']}" for x in documents],
                         "requete": requete, "consigne": consigne}
                    if repete:
                        r.update(tirage=tirage, definitions=d)
                    reponses[d].append(r)
                    print(f"  {a['nom']:9s} {a['profil']:17s} {modeles[taille]:12s} "
                          + (f"t{tirage + 1} {d:7s} " if repete else "")
                          + (f"{r['categorie']:16s} {'porte' if r['porte'] else '-':6s} "
                             f"{r['sens'][:60]}" if ok else f"INCIDENT {nature}"), flush=True)
        for d in args.definitions:
            resume = resumer(reponses[d])
            if repete:
                resume["confusion"] = M.confusion(reponses[d])
                resume["confusion_foule_aucun"] = M.confusion(reponses[d], "suivre_la_foule",
                                                              "aucun_sens")
            print(f"  {d} : repartition {resume['repartition']}")
            print(f"  sens dominant : {resume['dominant']} a {_taux(resume['part_dominant'])}, "
                  f"entropie {resume['entropie']}")
            for m, c in resume["par_modele"].items():
                print(f"    {m:12s} {c}")
            suffixe = (f"_r{args.repetitions}_{d}" + ("_schema" if args.sortie_structuree else "")
                       if repete else "")
            sortie = os.path.join(RACINE, "resultats",
                                  f"sens_a_priori_g{args.graine}_{variante}{suffixe}.json")
            with open(sortie, "w", encoding="utf-8") as f:
                json.dump({"date": datetime.now().isoformat(timespec="seconds"),
                           "graine": args.graine, "variante": variante,
                           "corpus": CORPUS.get(variante), "agents": len(agents),
                           "fournisseur": args.fournisseur, "modeles": modeles,
                           "temperature": client.temperature, "t_sim": t_sim, "systeme": SYSTEME,
                           **({"repetitions": args.repetitions, "definitions": d,
                               "texte_definitions": DEFINITIONS[d],
                               "schema": args.sortie_structuree} if repete else {}),
                           "resume": resume, "reponses": reponses[d]},
                          f, ensure_ascii=False, indent=1)
            print(f"  ecrit dans {sortie}")
        if set(args.definitions) == set(DEFINITIONS):
            comp = comparer(reponses["courtes"], reponses["nettes"])
            afficher_comparaison(comp)
            sortie = os.path.join(RACINE, "resultats", f"frontiere_g{args.graine}_{variante}"
                                  f"_r{args.repetitions}"
                                  + ("_schema" if args.sortie_structuree else "") + ".json")
            with open(sortie, "w", encoding="utf-8") as f:
                json.dump({"date": datetime.now().isoformat(timespec="seconds"),
                           "graine": args.graine, "variante": variante,
                           "repetitions": args.repetitions, "schema": args.sortie_structuree,
                           **comp}, f, ensure_ascii=False, indent=1)
            print(f"  ecrit dans {sortie}")


if __name__ == "__main__":
    main()
