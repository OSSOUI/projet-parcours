"""Etape 1.5 du plan de performances : un run sans ombres contre le meme run avec ombres.

Compare evenement par evenement les evenements communs (ombre.v1 exclus, et les champs
d'enveloppe qui changent forcement : run, seq, horodatages), puis le bilan, l'indicateur
d'emergence et les faits de la narratrice recalcules depuis chaque journal. Chaque
divergence est listee ; rien n'est corrige. Aucun appel au modele.

    python3 comparer_sans_ombres.py runs/demo_fumee.jsonl runs/demo_sans_ombres_g200.jsonl
"""
import argparse
import contextlib
import io
import json
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import emergence  # noqa: E402
from ephemere import narration as N  # noqa: E402

ENVELOPPE = {"run", "seq", "t_emission", "t_traitement"}
FIN = {"energie.v1", "coherence.v1", "bilan.v1"}


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def communs(evs):
    return [{k: v for k, v in e.items() if k not in ENVELOPPE}
            for e in evs if e["schema"] not in FIN | {"ombre.v1", "run.v2"}]


def comparer_monde(a, b):
    ca, cb = communs(a), communs(b)
    par_schema, divergences = {}, []
    for i, (x, y) in enumerate(zip(ca, cb)):
        s = x["schema"]
        d = par_schema.setdefault(s, {"compares": 0, "identiques": 0})
        d["compares"] += 1
        if x == y:
            d["identiques"] += 1
        elif len(divergences) < 20:
            champs = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
            divergences.append({"rang": i, "schema": s, "schema_b": y["schema"],
                                "t_sim_lisible": x.get("t_sim_lisible"),
                                "agent": x.get("agent"), "champs": champs,
                                "avec_ombres": {k: x.get(k) for k in champs[:4]},
                                "sans_ombres": {k: y.get(k) for k in champs[:4]}})
    return {"evenements_communs": [len(ca), len(cb)], "meme_longueur": len(ca) == len(cb),
            "identiques": ca == cb, "par_schema": par_schema, "divergences": divergences}


def entetes(a, b):
    x = {k: v for k, v in a[0].items() if k not in ENVELOPPE}
    y = {k: v for k, v in b[0].items() if k not in ENVELOPPE}
    return {"champs_differents": {k: [x.get(k), y.get(k)] for k in sorted(set(x) | set(y))
                                  if x.get(k) != y.get(k)}}


def fin_du_run(evs):
    dernier = evs[-1]
    return {"trois_derniers": [e["schema"] for e in evs[-3:]],
            "bilan_naturel": dernier["schema"] == "bilan.v1" and not dernier.get("interrompu"),
            "appels": dernier.get("appels"), "appels_ombres": dernier.get("appels_ombres"),
            "duree_run_s": dernier.get("duree_run_s"), "incidents": dernier.get("incidents"),
            "seq_continus": [e["seq"] for e in evs] == list(range(len(evs)))}


def indicateur(chemin):
    with contextlib.redirect_stdout(io.StringIO()):
        r = emergence.analyser(chemin, emergence.distributions(), 1000)
    return r


def faits_textes(evs, em):
    """Les faits de chaque fenetre, texte et nature, sans les sources (leurs seq different)."""
    out = []
    for fen, av, ap, e in N.parcourir(evs, 1, em):
        table, paroles = N.faits(fen, av, ap, e)
        out.append(sorted((f["nature"], f["texte"]) for f in table.values()))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("avec_ombres")
    p.add_argument("sans_ombres")
    p.add_argument("--json")
    args = p.parse_args()
    a, b = lire(args.avec_ombres), lire(args.sans_ombres)
    ra, rb = indicateur(args.avec_ombres), indicateur(args.sans_ombres)
    fa, fb = faits_textes(a, ra), faits_textes(b, rb)
    emerg = [t for f in fb for n, t in f if n == "emergence"]
    sp = rb["seuil_persistance"]
    attendu = all(f"{l.replace('_', ' ')} : gain soutenu" in (emerg[0] if emerg else "")
                  and ("non emergent" in emerg[0]) == (not v["emergent"])
                  for l, v in sp.items() if v.get("delta_a") is not None)
    r = {"entetes": entetes(a, b),
         "monde": comparer_monde(a, b),
         "ombres": {"avec": sum(e["schema"] == "ombre.v1" for e in a),
                    "sans": sum(e["schema"] == "ombre.v1" for e in b)},
         "fin": {"avec_ombres": fin_du_run(a), "sans_ombres": fin_du_run(b)},
         "emergence": {"avec_ombres": ra["seuil_persistance"], "sans_ombres": sp,
                       "persistance": [ra["persistance"], rb["persistance"]],
                       "identique": ra["seuil_persistance"] == sp
                       and ra["persistance"] == rb["persistance"],
                       "temoins": [sorted(ra["ombres"]), sorted(rb["ombres"])]},
         "faits_narratrice": {"fenetres": [len(fa), len(fb)],
                              "textes_identiques_par_fenetre": [x == y for x, y in zip(fa, fb)],
                              "fait_emergence_sans_ombres": emerg,
                              "fait_emergence_conforme_a_emergence_py": bool(emerg) and attendu,
                              "faits_d_ombre": [sum(n == "ombre" for f in fa for n, _ in f),
                                                sum(n == "ombre" for f in fb for n, _ in f)]}}
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
