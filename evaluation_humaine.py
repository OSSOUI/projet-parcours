"""Evaluation humaine independante des constats publies par la narratrice.

  --preparer   construit le dossier a remettre a l'evaluateur : constats melanges
               et renumerotes, sans version ni verdict, evenements cites en brut,
               contexte utile, journaux complets, consignes. La cle (correspondance
               et verdicts precedents) est ecrite A COTE du dossier, pas dedans.
  --comparer   lit une ou plusieurs grilles remplies, les archive telles quelles,
               puis compte, calcule l'intervalle de Wilson et liste les desaccords
               avec les evaluateurs precedents (et entre humains s'il y en a deux).

    python3 evaluation_humaine.py --preparer runs/n7_complet_0[1-4].narration.jsonl
    python3 evaluation_humaine.py --comparer grille_remplie.csv --evaluateur tuteur

Le calcul est fixe avant tout retour : rien n'est ajuste au vu des verdicts.
"""
import argparse
import csv
import json
import math
import os
import random
import shutil
import sys
import time

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from ephemere import journal  # noqa: E402

DOSSIER = os.path.join(RACINE, "resultats", "evaluation_humaine")
KIT = os.path.join(DOSSIER, "dossier_evaluateur")
CLE = os.path.join(DOSSIER, "cle_ne_pas_transmettre.json")
RETOURS = os.path.join(DOSSIER, "retours")
VERDICTS_B = os.path.join(RACINE, "resultats", "audit_v4_evaluateur_b.json")
GRAINE_MELANGE = 20261104
VERDICTS = ("vrai", "faux", "insuffisamment_etaye")
COLONNES = ["numero", "fenetre", "constat", "evenements_cites", "verdict", "justification"]

CONSIGNES = """# Évaluation de constats sur des journaux de simulation

Merci d'avoir accepté cette évaluation. Elle demande environ deux heures.

## Ce qu'on vous demande

Un programme a lu quatre journaux de simulation (un campus de 20 étudiants, pendant 25 jours, qui adoptent ou non un ruban et lui donnent un sens). Il a écrit des **constats** : des phrases qui affirment des faits sur ce qui s'est passé.

Pour chacun des 133 constats de `grille.csv`, dites s'il est vrai **au vu des événements du journal**. Vous ne jugez ni le style ni l'intérêt de la phrase, seulement son exactitude.

## Les trois verdicts possibles (colonne `verdict`)

- `vrai` : tout ce que la phrase affirme (nombres, noms, sens, citations, moments) est confirmé par les événements.
- `faux` : au moins un élément est contredit par les événements.
- `insuffisamment_etaye` : les événements fournis ne permettent ni de confirmer ni de contredire un élément de la phrase, ou la phrase est ambiguë.

**Pour `faux` et `insuffisamment_etaye`, la colonne `justification` est obligatoire** : quel élément, et quel événement le contredit ou manque. Pour `vrai`, elle est facultative.

## Les pièces

- `grille.csv` : la grille à remplir (séparateur point-virgule ; s'ouvre dans Excel ou LibreOffice). Ne modifiez que les colonnes `verdict` et `justification`.
- `evenements.md` : pour chaque constat, les événements qu'il cite, en brut, et pour les constats sur des étudiants, leur décision précédente (marquée « contexte, non cité »).
- `journaux/` : les quatre journaux complets (un événement JSON par ligne), si vous voulez vérifier autre chose. Un identifiant `run#n` désigne la ligne n (comptée à partir de 0) du fichier `run.jsonl`.

## Comment lire les événements

- `indicateurs.v1` est un relevé quotidien :
  - `adoption` : la part des 20 étudiants qui portent le ruban ;
  - `porteurs` : leur nombre ;
  - `sens` : le nombre d'étudiants qui donnent chaque sens au ruban (agents « à règles » compris).
- `decision.v1` est la décision d'un étudiant :
  - `porte` : s'il porte le ruban ;
  - `categorie` : le sens qu'il lui donne ;
  - `valide` : faux si la réponse était inexploitable (l'étudiant garde alors son état précédent).
- `publication.v1` est un message publié sur le réseau du campus.
- **La fenêtre d'un constat** est la période qu'il couvre. Le relevé de fin de fenêtre en fait partie.

## Règles

- **Travaillez seul,** sans échanger avec quelqu'un qui a participé au développement du programme.
- **Ne cherchez pas d'autres verdicts :** vous n'en avez pas reçu, et c'est voulu.
- **En cas de doute, préférez `insuffisamment_etaye` et dites pourquoi.**
- Renvoyez `grille.csv` remplie, avec votre nom et la date dans le nom du fichier.
"""


def lire_narrations(chemins):
    constats = []
    for chemin in chemins:
        with open(chemin, encoding="utf-8") as f:
            evs = [json.loads(l) for l in f if l.strip()]
        entete, narrations = evs[0], evs[1:]
        for n in narrations:
            for i, a in enumerate(n["affirmations"]):
                if a["statut"] == "verifiee" and a["type"] in ("observation", "mesure"):
                    constats.append({"id": f"{entete['run']}/{n['narration']}/{i}",
                                     "source": entete["source"], "fichier": os.path.basename(chemin),
                                     "fenetre": f"{n['fenetre']['debut']} -> {n['fenetre']['fin']}",
                                     "texte": a["texte"], "sources": a["sources"]})
    return constats


def contexte(evs, evt):
    """Derniere decision valide de l'agent avant cet evenement, ou son etat initial."""
    for e in reversed(evs[:evt["seq"]]):
        if e["schema"] == "decision.v1" and e["agent"] == evt["agent"] and e["valide"]:
            return e, f"contexte, non cite : decision precedente de {evt['agent']}"
    pop = next(e for e in evs if e["schema"] == "population.v1")
    agent = next(a for a in pop["agents"] if a["id"] == evt["agent"])
    return ({"schema": "population.v1 (extrait)", "run": evt["run"], "seq": pop["seq"], "agent": agent},
            f"contexte, non cite : etat initial de {evt['agent']} (aucune decision valide avant)")


def preparer(chemins):
    constats = lire_narrations(chemins)
    random.Random(GRAINE_MELANGE).shuffle(constats)
    if os.path.exists(KIT):
        raise SystemExit(f"{KIT} existe deja : on ne reecrit pas un dossier peut-etre transmis.")
    os.makedirs(os.path.join(KIT, "journaux"))
    journaux = {}
    for c in constats:
        if c["source"] not in journaux:
            journaux[c["source"]] = journal.lire(os.path.join(RACINE, c["source"]))
            shutil.copy(os.path.join(RACINE, c["source"]), os.path.join(KIT, "journaux"))
    b = {x["id"]: x["verdict"] for x in json.load(open(VERDICTS_B, encoding="utf-8"))}
    cle, blocs = [], ["# Événements cités par chaque constat\n"]
    with open(os.path.join(KIT, "grille.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        for k, c in enumerate(constats, 1):
            numero = f"C{k:03d}"
            w.writerow({"numero": numero, "fenetre": c["fenetre"], "constat": c["texte"],
                        "evenements_cites": " ".join(c["sources"]), "verdict": "",
                        "justification": ""})
            evs = journaux[c["source"]]
            blocs.append(f"\n## {numero}  (fenêtre {c['fenetre'].replace('->', '→')})\n\n"
                         f"**Constat :** {c['texte']}\n")
            vus = set()
            for sid in c["sources"]:
                evt = evs[int(sid.split("#")[1])]
                blocs.append(f"\n`{sid}` (cité)\n\n```json\n"
                             f"{json.dumps(evt, ensure_ascii=False, indent=1)}\n```\n")
                if evt["schema"] == "decision.v1" and evt["agent"] not in vus:
                    vus.add(evt["agent"])
                    ctx, titre = contexte(evs, evt)
                    blocs.append(f"\n`{ctx['run']}#{ctx['seq']}` ({titre})\n\n```json\n"
                                 f"{json.dumps(ctx, ensure_ascii=False, indent=1)}\n```\n")
            cle.append({"numero": numero, "id": c["id"], "narrations": c["fichier"],
                        "evaluateur_a": "vrai", "evaluateur_b": b.get(c["id"])})
    with open(os.path.join(KIT, "evenements.md"), "w", encoding="utf-8") as f:
        f.write("".join(blocs))
    with open(os.path.join(KIT, "CONSIGNES.md"), "w", encoding="utf-8") as f:
        f.write(CONSIGNES)
    with open(CLE, "w", encoding="utf-8") as f:
        json.dump({"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "graine_melange": GRAINE_MELANGE,
                   "narrations": [os.path.relpath(c, RACINE) for c in chemins],
                   "note": "evaluateur_a : relecture du 4 novembre (133 vrais, NARRATRICE.md) ; "
                           "evaluateur_b : verifier_narrations.py",
                   "constats": cle}, f, ensure_ascii=False, indent=1)
    print(f"{len(constats)} constats -> {KIT}\ncle (a garder) -> {CLE}")


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    demi = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [centre - demi, centre + demi]


def kappa(x, y):
    """Kappa de Cohen entre deux listes de verdicts. None si un evaluateur est constant."""
    n = len(x)
    cats = sorted(set(x) | set(y))
    po = sum(a == b for a, b in zip(x, y)) / n
    pe = sum((x.count(c) / n) * (y.count(c) / n) for c in cats)
    return None if pe == 1 else (po - pe) / (1 - pe)


def lire_grille(chemin):
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        echantillon = f.read(2048)
        f.seek(0)
        lignes = list(csv.DictReader(f, delimiter=";" if ";" in echantillon else ","))
    out = {}
    for l in lignes:
        v = (l.get("verdict") or "").strip().lower().replace(" ", "_").replace("é", "e")
        out[l["numero"].strip()] = {"verdict": v, "justification": (l.get("justification") or "").strip()}
    return out


def comparer(grilles, evaluateurs):
    cle = {c["numero"]: c for c in json.load(open(CLE, encoding="utf-8"))["constats"]}
    os.makedirs(RETOURS, exist_ok=True)
    bilan = {"evaluateurs": {}, "desaccords": [], "accord_entre_humains": None}
    lus = {}
    for chemin, nom in zip(grilles, evaluateurs):
        # Le retour brut est archive tel quel, avant toute lecture.
        shutil.copy(chemin, os.path.join(RETOURS, f"{nom}_{os.path.basename(chemin)}"))
        g = lire_grille(chemin)
        lus[nom] = g
        manquants = sorted(set(cle) - set(g))
        hors = {k: v["verdict"] for k, v in g.items() if v["verdict"] not in VERDICTS}
        sans_justif = sorted(k for k, v in g.items()
                             if v["verdict"] in VERDICTS[1:] and not v["justification"])
        n = len(cle)
        compte = {v: sum(1 for k in cle if g.get(k, {}).get("verdict") == v) for v in VERDICTS}
        bilan["evaluateurs"][nom] = {
            "constats": n, **compte, "manquants": manquants, "verdicts_hors_liste": hors,
            "contestes_sans_justification": sans_justif,
            "part_vrais": compte["vrai"] / n, "ic95_vrais": wilson(compte["vrai"], n),
            "part_faux": compte["faux"] / n, "ic95_faux": wilson(compte["faux"], n),
            "accord_avec_b": sum(1 for k in cle if g.get(k, {}).get("verdict") == cle[k]["evaluateur_b"]) / n,
            "kappa_avec_b": kappa([g.get(k, {}).get("verdict", "") for k in sorted(cle)],
                                  [cle[k]["evaluateur_b"] for k in sorted(cle)])}
        for k in sorted(cle):
            v = g.get(k, {})
            if v.get("verdict") != cle[k]["evaluateur_b"] or v.get("verdict") != cle[k]["evaluateur_a"]:
                bilan["desaccords"].append({"numero": k, "id": cle[k]["id"], "evaluateur": nom,
                                            "verdict": v.get("verdict"),
                                            "justification": v.get("justification"),
                                            "evaluateur_a": cle[k]["evaluateur_a"],
                                            "evaluateur_b": cle[k]["evaluateur_b"]})
    if len(lus) >= 2:
        (n1, g1), (n2, g2) = list(lus.items())[:2]
        x = [g1.get(k, {}).get("verdict", "") for k in sorted(cle)]
        y = [g2.get(k, {}).get("verdict", "") for k in sorted(cle)]
        bilan["accord_entre_humains"] = {"evaluateurs": [n1, n2],
                                         "accord": sum(a == b for a, b in zip(x, y)) / len(x),
                                         "kappa": kappa(x, y),
                                         "divergences": [k for k, a, b in zip(sorted(cle), x, y) if a != b]}
    sortie = os.path.join(DOSSIER, "bilan.json")
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(bilan, f, ensure_ascii=False, indent=1)
    for nom, r in bilan["evaluateurs"].items():
        print(f"{nom} : {r['vrai']} vrais, {r['faux']} faux, {r['insuffisamment_etaye']} insuffisamment "
              f"etayes sur {r['constats']} ; part de vrais {r['part_vrais']:.1%} "
              f"(IC 95 % {r['ic95_vrais'][0]:.1%} a {r['ic95_vrais'][1]:.1%})")
        if r["manquants"] or r["verdicts_hors_liste"] or r["contestes_sans_justification"]:
            print(f"  a reprendre avec l'evaluateur : manquants {r['manquants']}, hors liste "
                  f"{r['verdicts_hors_liste']}, sans justification {r['contestes_sans_justification']}")
    for d in bilan["desaccords"]:
        print(f"  {d['numero']} {d['evaluateur']} : {d['verdict']} (A {d['evaluateur_a']}, "
              f"B {d['evaluateur_b']}) {d['justification'][:120]}")
    print(f"ecrit dans {sortie}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preparer", nargs="+", metavar="NARRATIONS")
    p.add_argument("--comparer", nargs="+", metavar="GRILLE")
    p.add_argument("--evaluateur", nargs="+", help="un nom par grille, dans le meme ordre")
    args = p.parse_args()
    if args.preparer:
        return preparer(args.preparer)
    if args.comparer:
        noms = args.evaluateur or [f"evaluateur{i + 1}" for i in range(len(args.comparer))]
        if len(noms) != len(args.comparer):
            raise SystemExit("un nom d'evaluateur par grille")
        return comparer(args.comparer, noms)
    p.print_help()


if __name__ == "__main__":
    sys.exit(main())
