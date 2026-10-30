"""Phase 1 relue avec l'indicateur d'emergence, en six sens puis regroupee.

Decide le 30 octobre, apres le point zero repete (sens_a_priori.py) : le
petit modele ne tient pas la frontiere entre tendance et suivre_la_foule,
donc l'analyse les compte comme un seul sens. Les runs ne sont pas relances
et le contrat ne change pas : seul le comptage regroupe.

L'indicateur est celui d'ephemere/indicateurs.py, sans second calcul :

  runs LLM     accord exprime des seuls agents LLM a chaque releve, Delta A =
               meilleure fenetre de 3 releves consecutifs (son minimum) moins
               A0, seuil = 95e centile de Delta A sous le modele nul. Le modele
               nul calcule la MEME statistique sur autant de releves, chaque
               agent tirant son sens dans la distribution du point zero de sa
               classe (profil, taille). Regroupe, il tire dans les six sens
               puis regroupe comme les runs.
  runs a regles  leur sens est ecrit d'apres l'adoption : l'indicateur ne s'y
               applique pas. B3 y est un resultat sur l'adoption ; l'accord est
               donne avec le hasard uniforme comme simple repere.

Controle du seuil : des runs tires du modele nul avec une autre graine doivent
etre declares emergents environ 5 % du temps.

Point zero de reference : variante complet (meme corpus que les runs),
definitions courtes, sans schema, 5 tirages, population de la graine 100.
Les runs des graines 101 a 104 prennent les distributions par classe de la
graine 100 : il reste a faire le point zero de leurs populations.

    python3 regroupement.py              # ecrit resultats/regroupement_phase1.json
"""
import collections
import glob
import json
import os
import random
import statistics

from ephemere import indicateurs as I
from ephemere.contrat import SENS

RACINE = os.path.dirname(os.path.abspath(__file__))
POINT_ZERO = os.path.join(RACINE, "resultats", "sens_a_priori_g100_complet_t5.json")
LECTURES = {"six_sens": None, "regroupe": I.REGROUPEMENT_FOULE}
LLM = ("llm_petit", "llm_grand")

RUNS_LLM = ["exp_complet_llm_synchrone", "exp_complet_llm_temoin_cloisonne",
            "exp_meneurs_llm_meneurs", "exp_phase1_llm_synchrone"]
RUNS_REGLES = ["exp_socle_baseline", "exp_socle_temoin_cloisonne",
               "exp_complet_baseline", "exp_complet_temoin_cloisonne"]


def lire(chemin):
    """Population, sens de chaque agent a chaque releve, adoptions."""
    pop, courant, releves, adoptions, graine = {}, {}, [], [], None
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            e = json.loads(ligne)
            if e["schema"] in ("run.v1", "run.v2"):
                graine = e["graine"]
            elif e["schema"] == "population.v1":
                pop = {a["id"]: a for a in e["agents"]}
            elif e["schema"].startswith("decision."):
                courant[e["agent"]] = e["categorie"]
            elif e["schema"] == "indicateurs.v1":
                releves.append(dict(courant))
                adoptions.append(e["taux_adoption"])
    return graine, pop, releves, adoptions


def distributions():
    with open(POINT_ZERO, encoding="utf-8") as f:
        return I.distributions_point_zero(json.load(f)["reponses"])


def controle(classes, dist, releves, nul, regroupement, n=500):
    """Part de runs tires du modele nul (autre graine) au-dessus du seuil."""
    rng = random.Random(99)
    comptes = [dist[c] for c in classes]
    emergents = mesures = 0
    for _ in range(n):
        serie = [I.accord_exprime([I._tirer(rng, c) for c in comptes], regroupement)
                 for _ in range(releves)]
        gain, _ = I.gain_soutenu(serie, nul["a0"])
        if gain is not None:
            mesures += 1
            emergents += gain > nul["seuil"]
    return emergents / mesures if mesures else None


def runs_llm(dist):
    sortie = {}
    for prefixe in RUNS_LLM:
        lignes = []
        for chemin in sorted(glob.glob(os.path.join(RACINE, "runs", f"{prefixe}_[0-9][0-9].jsonl"))):
            graine, pop, releves, _ = lire(chemin)
            ids = [i for i, a in pop.items() if a["moteur"] in LLM]
            classes = [(pop[i]["profil"], pop[i]["moteur"]) for i in ids]
            ligne = {"run": os.path.basename(chemin)[:-6], "graine": graine,
                     "agents_llm": len(ids), "releves": len(releves)}
            for lecture, reg in LECTURES.items():
                serie = [I.accord_exprime([r.get(i) for i in ids], reg) for r in releves]
                try:
                    nul = I.modele_nul(classes, dist, len(releves), graine=0, regroupement=reg)
                except KeyError as manque:
                    ligne[lecture] = {"erreur": f"classe absente du point zero : {manque}"}
                    continue
                gain, debut = I.gain_soutenu(serie, nul["a0"])
                ligne[lecture] = {
                    "a0": nul["a0"], "seuil": nul["seuil"], "delta_a": gain,
                    "fenetre_debut": debut,
                    "emergent": gain is not None and gain > nul["seuil"],
                    "accord_max": max((x for x in serie if x is not None), default=None),
                    "controle_5pc": controle(classes, dist, len(releves), nul, reg),
                }
            lignes.append(ligne)
        sortie[prefixe] = lignes
    return sortie


def runs_regles():
    sortie = {}
    for prefixe in RUNS_REGLES:
        lignes = []
        for chemin in sorted(glob.glob(os.path.join(RACINE, "runs", f"{prefixe}_[0-9][0-9].jsonl"))):
            graine, pop, releves, adoptions = lire(chemin)
            ids = list(pop)
            ligne = {"run": os.path.basename(chemin)[:-6], "graine": graine,
                     "adoption_pic": max(adoptions), "adoption_finale": adoptions[-1]}
            uni = {("tous", "uniforme"): {s: 1 for s in SENS}}
            for lecture, reg in LECTURES.items():
                serie = [I.accord_exprime([r.get(i) for i in ids], reg) for r in releves]
                nul = I.modele_nul([("tous", "uniforme")] * len(ids), uni, len(releves),
                                   tirages=300, regroupement=reg)
                gain, _ = I.gain_soutenu(serie, nul["a0"])
                ligne[lecture] = {"a0_uniforme": nul["a0"], "seuil_uniforme": nul["seuil"],
                                  "delta_a": gain}
            lignes.append(ligne)
        sortie[prefixe] = lignes
    return sortie


def _pc(x):
    return "  n/a" if x is None else f"{x:+.0%}" if x < 0 else f"{x:.0%}"


def main():
    dist = distributions()
    llm = runs_llm(dist)
    print("RUNS LLM  indicateur d'emergence, agents LLM seulement, point zero complet t5")
    print(f"  {'run':38s} {'lecture':9s} {'A0':>4s} {'seuil':>6s} {'dA':>5s}  emergent  controle")
    for lignes in llm.values():
        for ligne in lignes:
            for lecture in LECTURES:
                v = ligne[lecture]
                if "erreur" in v:
                    print(f"  {ligne['run']:38s} {lecture:9s} {v['erreur']}")
                    continue
                print(f"  {ligne['run']:38s} {lecture:9s} {v['a0']:4.0%} {v['seuil']:6.0%} "
                      f"{_pc(v['delta_a']):>5s}  {'oui' if v['emergent'] else 'non':8s}  "
                      f"{v['controle_5pc']:.0%}   ({ligne['agents_llm']} agents LLM, "
                      f"{ligne['releves']} releves)")
    regles = runs_regles()
    print("\nRUNS A REGLES  B3 sur l'adoption ; accord avec le hasard uniforme comme repere")
    for prefixe, lignes in regles.items():
        pics = [x["adoption_pic"] for x in lignes]
        au_dessus = {lec: sum(1 for x in lignes if x[lec]["delta_a"] is not None
                              and x[lec]["delta_a"] > x[lec]["seuil_uniforme"])
                     for lec in LECTURES}
        print(f"  {prefixe:30s} {len(lignes):2d} runs  adoption au pic mediane "
              f"{statistics.median(pics):.0%} [{min(pics):.0%} a {max(pics):.0%}]  "
              f"au-dessus du repere : six sens {au_dessus['six_sens']}/{len(lignes)}, "
              f"regroupe {au_dessus['regroupe']}/{len(lignes)}")
    chemin = os.path.join(RACINE, "resultats", "regroupement_phase1.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({"point_zero": os.path.relpath(POINT_ZERO, RACINE),
                   "tirages_nuls": I.TIRAGES_NULS, "fenetre": I.FENETRE,
                   "runs_llm": llm, "runs_regles": regles}, f, ensure_ascii=False, indent=1)
    print(f"\necrit dans {os.path.relpath(chemin, RACINE)}")


if __name__ == "__main__":
    main()
