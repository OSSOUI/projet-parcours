"""Indicateur d'emergence corrige, run par run. Aucun appel LLM.

Base experimentale du 3 novembre (matrice de validation, section Validation
du protocole). Deux lectures, sur les seuls agents LLM :

  seuil a persistance  Delta A contre A0 du point zero, comme regroupement.py,
                       mais les decisions en incident sont des valeurs
                       manquantes (l'agent garde son etat de la veille, ce n'est
                       pas un sens qu'il donne) et le seuil vient du modele nul
                       de Markov, a la persistance mesuree dans le run.
                       Controle analytique : A0 vient d'un prompt sans adoption.
  ombres               si le run a tourne avec --ombres : ecart moyen d'accord
                       entre chaque decision reelle et son ombre, au meme instant
                       et dans le meme etat, avec sa p-valeur par permutation des
                       paires. C'est le temoin de reference.

    python3 emergence.py runs/exp_complet_llm_synchrone_0[1-5].jsonl
    python3 emergence.py --json resultats/emergence_reference.json runs/exp_reference_*.jsonl
"""
import argparse
import json
import os
import sys

from ephemere import indicateurs as I

RACINE = os.path.dirname(os.path.abspath(__file__))
POINT_ZERO = os.path.join(RACINE, "resultats", "sens_a_priori_g100_complet_t5.json")
LECTURES = {"six_sens": None, "regroupe": I.REGROUPEMENT_FOULE}
LLM = ("llm_petit", "llm_grand")


def lire(chemin):
    """Agents LLM, sens reels par releve (incidents = None) et paires reel / ombre."""
    pop, courant, etats, ombres, entete = {}, {}, [], {}, {"incidents": 0}
    for ligne in open(chemin, encoding="utf-8"):
        e = json.loads(ligne)
        s = e["schema"]
        if s in ("run.v1", "run.v2"):
            entete = {**e, "incidents": 0}
        elif s == "population.v1":
            pop = {a["id"]: a for a in e["agents"] if a["moteur"] in LLM}
        elif s == "decision.v1" and e["agent"] in pop:
            courant[e["agent"]] = e["categorie"] if e["valide"] else None
            entete["incidents"] += not e["valide"]
        elif s == "ombre.v1" and e["agent"] in pop:
            ombres.setdefault(e["masque"], []).append((
                e["agent"], len(etats),
                e["reel_categorie"] if e["reel_valide"] else None,
                e["categorie"] if e["valide"] else None))
        elif s == "indicateurs.v1":
            etats.append({a: courant.get(a) for a in pop})
    return entete, pop, etats, ombres


def distributions():
    with open(POINT_ZERO, encoding="utf-8") as f:
        return I.distributions_point_zero(json.load(f)["reponses"])


def analyser(chemin, dist, permutations):
    entete, pop, etats, ombres = lire(chemin)
    classes = [(pop[a]["profil"], pop[a]["moteur"]) for a in pop]
    p = I.persistance(etats)
    sortie = {"run": os.path.basename(chemin)[:-6], "graine": entete.get("graine"),
              "agents_llm": len(pop), "releves": len(etats),
              "incidents": entete["incidents"],
              "persistance": p, "seuil_persistance": {}, "ombres": {}}
    for lecture, reg in LECTURES.items():
        serie = [I.accord_exprime(list(x.values()), reg) for x in etats]
        ligne = {"accord_max": max((x for x in serie if x is not None), default=None),
                 "exprimes_min": min((sum(1 for v in x.values() if v and v != I.AUCUN)
                                      for x in etats[1:]), default=0)}
        try:
            nul = I.modele_nul_markov(classes, dist, len(etats), p or 0.0, regroupement=reg)
            gain, debut = I.gain_soutenu(serie, nul["a0"])
            ligne.update({"a0": nul["a0"], "seuil": nul["seuil"], "delta_a": gain,
                          "fenetre_debut": debut,
                          "emergent": gain is not None and gain > nul["seuil"]})
        except KeyError as manque:
            ligne["erreur"] = f"classe absente du point zero : {manque}"
        sortie["seuil_persistance"][lecture] = ligne
        for masque, paires in ombres.items():
            sortie["ombres"].setdefault(masque, {})[lecture] = I.ecart_ombres(
                paires, len(etats), reg, permutations=permutations)
    return sortie


def _pc(x, signe=False):
    if x is None:
        return "  n/a"
    return f"{x:+.0%}" if signe else f"{x:.0%}"


def afficher(r):
    print(f"\n{r['run']}  graine {r['graine']}, {r['agents_llm']} agents LLM, "
          f"{r['releves']} releves, persistance {_pc(r['persistance'])}, "
          f"{r['incidents']} decisions en incident (manquantes)")
    for lecture, v in r["seuil_persistance"].items():
        if "erreur" in v:
            print(f"  {lecture:9s} {v['erreur']}")
            continue
        print(f"  {lecture:9s} seuil a persistance : A0 {_pc(v['a0'])}, seuil {_pc(v['seuil'])}, "
              f"dA {_pc(v['delta_a'], True)} -> {'emergent' if v['emergent'] else 'non emergent'}"
              f"   (au moins {v['exprimes_min']} agents expriment un sens)")
    for masque, lectures in r["ombres"].items():
        for lecture, o in lectures.items():
            print(f"  {lecture:9s} ombre {masque:13s} : ecart reel - ombre "
                  f"{_pc(o['ecart'], True)} sur {o['releves']} releves, p = "
                  + ("n/a" if o["p"] is None else f"{o['p']:.3f}")
                  + f"  ({o['decisions']} paires)")
    if not r["ombres"]:
        print("  pas d'ombres dans ce run : seul le controle analytique s'applique")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--permutations", type=int, default=1000)
    p.add_argument("--json", help="ecrit aussi les resultats dans ce fichier")
    args = p.parse_args()
    dist = distributions()
    resultats = [analyser(c, dist, args.permutations) for c in args.runs]
    for r in resultats:
        afficher(r)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"point_zero": os.path.relpath(POINT_ZERO, RACINE), "runs": resultats},
                      f, ensure_ascii=False, indent=1)
        print(f"\necrit dans {args.json}")


if __name__ == "__main__":
    sys.exit(main())
