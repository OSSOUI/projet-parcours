"""Tableau de bord des runs : metriques, vitesses et agents. Aucun appel LLM.

    python3 tableau.py                      # tous les runs de runs/
    python3 tableau.py --sortie rapport.html
    python3 tableau.py runs/exp_complet_*.jsonl

Produit une page HTML autonome (aucune dependance, aucun acces reseau) qui
complete la scene Godot : Godot montre un run en direct, ce tableau compare les
runs entre eux, apres coup. C'est la meme page que direct.py (vues.py), donnees
figees : l'onglet Suivre un run montre chaque run comme direct.py le montre.

Onglet Comparer les runs :
  Metriques a evaluer  par configuration, dispersion run par run (B3, E2)
  Dynamique            adoption et accord jour par jour, chaque run et la moyenne
  Vitesses             latence de chaque taille de modele, temps simule par
                       seconde reelle, cadence des agents, vitesse de la mode
  Agents               pour un run : sens du ruban au fil du temps, etat de
                       chaque agent chaque jour, ses decisions et leurs raisons
  Incidents            sorties de role par nature et par moteur (A4, A5)

Les chiffres viennent des memes fonctions que experience.py (mesurer,
accord_partage) : le tableau et le protocole ne peuvent pas diverger. Un run
sans bilan.v1 est en cours ou interrompu : il est ignore et signale.
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from ephemere.contrat import SENS  # noqa: E402
from experience import CONFIGURATIONS, accord_partage, mesurer  # noqa: E402

ORDRE_SENS = list(SENS)
SEUIL_EMERGENCE = 0.30
_NOM_EXP = re.compile(r"^exp_([a-z0-9]+)_(.+)_(\d+)$")


def identifier(nom):
    """exp_complet_llm_synchrone_03 -> ("complet", "llm_synchrone")."""
    m = _NOM_EXP.match(nom)
    if m:
        return m.group(1), m.group(2)
    return "autres", nom


def lire_run(chemin):
    """Resume d'un run pour le tableau, ou None s'il n'est pas termine."""
    with open(chemin, encoding="utf-8") as f:
        evs = [json.loads(ligne) for ligne in f if ligne.strip()]
    meta = next((e for e in evs if e["schema"] in ("run.v1", "run.v2")), None)
    bilan = next((e for e in evs if e["schema"] == "bilan.v1"), None)
    if meta is None or bilan is None:
        return None
    nom = os.path.basename(chemin)[:-len(".jsonl")]
    plan, config = identifier(nom)
    pop = next((e for e in evs if e["schema"] == "population.v1"), {"agents": []})
    releves = [e for e in evs if e["schema"] == "indicateurs.v1"]
    decisions = [e for e in evs if e["schema"] == "decision.v1"]
    incidents = [e for e in evs if e["schema"] == "incident.v1"]
    energie = next((e for e in evs if e["schema"] == "energie.v1"), {})
    coherence = next((e for e in evs if e["schema"] == "coherence.v1"), {})
    m = mesurer(chemin) or {}

    # Le moteur reel vient des decisions : --tout-grand change celui de la population.
    moteur_de = {a["id"]: a.get("moteur", "?") for a in pop["agents"]}
    moteur_de.update({d["agent"]: d["moteur"] for d in decisions})
    nature_de = {(i["agent"], i["t_sim"]): i["nature"] for i in incidents}

    # Releves : jour, adoption, accord partage, repartition dans l'ordre de SENS.
    serie = []
    for e in releves:
        n = sum(e["repartition_sens"].values()) or 1
        serie.append([round(e["t_sim"] / 1440, 3), e["taux_adoption"], accord_partage(e),
                      [e["repartition_sens"].get(s, 0) / n for s in ORDRE_SENS]])

    # Etat de chaque agent a chaque releve, rejoue depuis les decisions.
    etat = {a["id"]: (bool(a.get("porte")), 0 if a.get("porte") else ORDRE_SENS.index("aucun_sens"))
            for a in pop["agents"]}
    grille = {aid: [] for aid in etat}
    i = 0
    ordre = sorted(range(len(decisions)), key=lambda k: decisions[k]["t_sim"])
    for e in releves:
        while i < len(ordre) and decisions[ordre[i]]["t_sim"] <= e["t_sim"]:
            d = decisions[ordre[i]]
            if d["categorie"] in SENS:
                etat[d["agent"]] = (d["porte"], ORDRE_SENS.index(d["categorie"]))
            i += 1
        for aid, (porte, cat) in etat.items():
            grille[aid].append(chr(ord("a") + cat + (6 if porte else 0)))

    detail = defaultdict(list)
    for d in decisions:
        regles = d["moteur"] == "regles"
        detail[d["agent"]].append([
            round(d["t_sim"] / 1440, 2), int(d["porte"]),
            ORDRE_SENS.index(d["categorie"]) if d["categorie"] in SENS else -1,
            int(d["valide"]), nature_de.get((d["agent"], d["t_sim"]), ""),
            "" if regles else d["sens"][:200], d["raison"][:200]])

    jours = meta["jours"] or 1
    par_profil = defaultdict(list)
    for a in pop["agents"]:
        par_profil[a["profil"]].append(len(detail.get(a["id"], [])) / jours)

    decisions_llm = sum(1 for d in decisions if d["moteur"] != "regles")
    adoptions = [s[1] for s in serie]
    jour_pic = serie[adoptions.index(max(adoptions))][0] if serie else None
    emergence = next((s[0] for s in serie if s[2] >= SEUIL_EMERGENCE), None)
    duree = bilan.get("duree_run_s") or 0
    kwh = energie.get("kwh")
    return {
        "nom": nom, "plan": plan, "config": config, "mode": meta["mode"],
        "graine": meta["graine"], "jours": meta["jours"], "n": meta["nb_agents"],
        "metriques": {
            "accord_max": m.get("accord_max"), "adoption_pic": m.get("adoption_pic"),
            "adoption_finale": m.get("adoption_finale"), "declin": m.get("declin"),
            "jour_pic": jour_pic, "jour_emergence": emergence,
            "taux_incidents": (len(incidents) / decisions_llm) if decisions_llm else None,
            "appels": bilan["appels"], "appels_grand": m.get("appels_grand", 0),
            "tokens": bilan["tokens_entree"] + bilan["tokens_sortie"],
            "wh": None if kwh is None else kwh * 1000,
            "duree_s": duree,
            "vitesse_sim": (meta["jours"] * 1440 / duree) if duree else None,
            "violations": coherence.get("violations"), "controles": coherence.get("controles"),
            "decisions_llm": decisions_llm,
        },
        "latences": {t: {"moy": c.get("latence_moy_s"), "max": c.get("latence_max_s"),
                         "appels": c.get("appels", 0), "modele": c.get("modele", "")}
                     for t, c in bilan.get("par_taille", {}).items()},
        "cadence": {p: statistics.mean(v) for p, v in par_profil.items() if v},
        "incidents": Counter(f"{moteur_de.get(i['agent'], '?')}|{i['nature']}" for i in incidents),
        "decisions_par_moteur": Counter(d["moteur"] for d in decisions),
        "agents": [{"id": a["id"], "nom": a["nom"], "profil": a["profil"], "groupe": a["groupe"],
                    "moteur": moteur_de.get(a["id"], a.get("moteur", "?")),
                    "grille": "".join(grille.get(a["id"], [])),
                    "decisions": detail.get(a["id"], [])}
                   for a in pop["agents"]],
        "serie": serie,
    }


def chemins_runs(dossier):
    """Journaux de runs d'un dossier, sans les fichiers annexes."""
    return sorted(c for c in glob.glob(os.path.join(dossier, "*.jsonl"))
                  if not c.endswith((".rejets.jsonl", ".traitement.jsonl", ".direct.jsonl")))


_lus = {}


def donnees_comparaison(chemins):
    """Donnees de l'onglet Comparer les runs. Un run deja lu n'est relu que s'il a change."""
    runs, ignores = [], []
    for c in chemins:
        st = os.stat(c)
        cle = (st.st_mtime_ns, st.st_size)
        if _lus.get(c, (None,))[0] != cle:
            try:
                _lus[c] = (cle, lire_run(c))
            except ValueError:            # derniere ligne en cours d'ecriture
                _lus[c] = (cle, None)
        r = _lus[c][1]
        (runs if r else ignores).append(r or os.path.basename(c))
    ordre = list(CONFIGURATIONS)
    return {
        "genere": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sens": [{"cle": k, "texte": v} for k, v in SENS.items()],
        "seuil": SEUIL_EMERGENCE,
        "configs": {k: {"titre": v["titre"], "attendu": v["attendu"], "rang": ordre.index(k)}
                    for k, v in CONFIGURATIONS.items()},
        "ignores": ignores,
        "runs": runs,
    }


def main():
    import direct
    import vues

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="*", help="fichiers .jsonl (defaut : tout runs/)")
    p.add_argument("--sortie", default=os.path.join(RACINE, "runs", "tableau.html"))
    args = p.parse_args()

    chemins = args.runs or chemins_runs(os.path.join(RACINE, "runs"))
    chemins = [c for c in chemins if not c.endswith((".rejets.jsonl", ".traitement.jsonl", ".direct.jsonl"))]
    donnees = donnees_comparaison(chemins)
    runs, ignores = donnees["runs"], donnees["ignores"]

    # Onglet Suivre un run : le meme etat que direct.py, fige pour chaque run, termine ou non.
    recents = sorted(chemins, key=os.path.getmtime, reverse=True)
    noms = [os.path.basename(c)[:-len(".jsonl")] for c in recents]
    statique = {
        "tableau": donnees,
        "runs": [{"nom": n, "maj": os.path.getmtime(c)} for n, c in zip(noms, recents)],
        "etats": {n: direct.etat(n, os.path.dirname(os.path.abspath(c))) for n, c in zip(noms, recents)},
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.sortie)), exist_ok=True)
    with open(args.sortie, "w", encoding="utf-8") as f:
        f.write(vues.page(statique))
    print(f"{len(runs)} runs dans {args.sortie} ({os.path.getsize(args.sortie) // 1024} Ko)")
    if ignores:
        print(f"{len(ignores)} run(s) ignore(s), en cours ou interrompu(s) : {', '.join(ignores[:5])}"
              + (" ..." if len(ignores) > 5 else ""))


if __name__ == "__main__":
    main()
