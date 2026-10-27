"""Lecture d'un ou plusieurs runs enregistres. Aucun appel LLM.

    python3 analyser.py runs/synchrone_xxx.jsonl
    python3 analyser.py runs/baseline.jsonl runs/synchrone_xxx.jsonl

Sort les chiffres a mettre dans le rapport : courbe d'adoption, part du sens
dominant, taux de sortie de role par moteur (A4 et A5), cout (E4).
"""
import collections
import json
import sys


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def analyser(chemin):
    evs = lire(chemin)
    meta = next((e for e in evs if e["schema"] == "run.v1"), {})
    dec = [e for e in evs if e["schema"] == "decision.v1"]
    inc = [e for e in evs if e["schema"] == "incident.v1"]
    ind = [e for e in evs if e["schema"] == "indicateurs.v1"]
    bilan = next((e for e in evs if e["schema"] == "bilan.v1"), {})
    coherence = next((e for e in evs if e["schema"] == "coherence.v1"), None)
    energie = next((e for e in evs if e["schema"] == "energie.v1"), None)

    print(f"\n=== {chemin}")
    print(f"{meta.get('mode', '?')}, {meta.get('nb_agents', '?')} agents, "
          f"{meta.get('jours', '?')} jours, graine {meta.get('graine', '?')}")

    if ind:
        pics = max(ind, key=lambda e: e["taux_adoption"])
        fin = ind[-1]
        print(f"\nADOPTION  depart {ind[0]['taux_adoption']:.0%}   "
              f"pic {pics['taux_adoption']:.0%} ({pics['t_sim_lisible']})   "
              f"fin {fin['taux_adoption']:.0%}")
        print(f"SENS DOMINANT  fin : {fin['sens_dominant']} a {fin['part_sens_dominant']:.0%}")
        # Accord sur un sens AUTRE que "aucun sens", meme quand celui-ci domine.
        def partage(e):
            rep = {s: c for s, c in e["repartition_sens"].items() if s != "aucun_sens"}
            sens = max(rep, key=rep.get) if rep else "aucun_sens"
            return rep.get(sens, 0) / (sum(e["repartition_sens"].values()) or 1), sens
        pic_sens = max(ind, key=lambda e: partage(e)[0])
        part, sens = partage(pic_sens)
        print(f"  accord maximal sur un sens partage : {part:.0%} "
              f"sur {sens} ({pic_sens['t_sim_lisible']})")
        # Un cycle complet suppose une montee PUIS une descente marquee.
        apres = [e for e in ind if e["t_sim"] > pics["t_sim"]]
        creux = min(apres, key=lambda e: e["taux_adoption"])["taux_adoption"] if apres else None
        if creux is not None and pics["taux_adoption"] - creux >= 0.2:
            print(f"  CYCLE COMPLET : montee a {pics['taux_adoption']:.0%} "
                  f"puis retombee a {creux:.0%}")
        elif creux is not None:
            print(f"  pas de cycle net : apres le pic, le creux reste a {creux:.0%}")

    if dec:
        print("\nSORTIES DE ROLE par moteur")
        moteur_de = {}
        for d in dec:
            moteur_de[d["agent"]] = d["moteur"]
        total = collections.Counter(d["moteur"] for d in dec)
        rates = collections.Counter()
        for i in inc:
            rates[moteur_de.get(i["agent"], "?")] += 1
        for m in sorted(total):
            print(f"  {m:12s} {rates[m]:4d} / {total[m]:4d} decisions = {rates[m]/total[m]:6.1%}")
        if inc:
            print("  par nature :")
            for n, c in collections.Counter(i["nature"] for i in inc).most_common():
                print(f"    {n:24s} {c}")

    rec = [e for e in evs if e["schema"] == "recuperation.v1"]
    if rec:
        vides = sum(1 for r in rec if r["nb_resultats"] == 0)
        moyenne = sum(r["nb_resultats"] for r in rec) / len(rec)
        print(f"\nRECUPERATION  {len(rec)} recherches, "
              f"{moyenne:.2f} passage(s) par decision, "
              f"{vides} recherche(s) sans resultat ({vides/len(rec):.1%})")
        tires = collections.Counter()
        scores = collections.defaultdict(list)
        for r in rec:
            for x in r["resultats"]:
                tires[x["id"]] += 1
                scores[x["id"]].append(x["score"])
        print("  documents les plus retrouves :")
        for doc, n in tires.most_common(6):
            moy = sum(scores[doc]) / len(scores[doc])
            print(f"    {doc:24s} {n:4d} fois, score moyen {moy:5.2f}")
        jamais = len({d for d in tires}) 
        print(f"  {jamais} document(s) different(s) effectivement utilise(s)")

    if coherence and coherence["controles"]:
        print(f"\nCOHERENCE TEMPORELLE (C6)  {coherence['violations']} violation(s) "
              f"sur {coherence['controles']} contextes controles")
    if energie:
        print("\nENERGIE  " + (f"{energie['kwh'] * 1000:.2f} Wh, {energie['co2_kg'] * 1000:.2f} g CO2"
                              if energie["kwh"] is not None else energie["note"])
              + f" ({energie['portee']})")

    if bilan.get("appels"):
        print(f"\nCOUT  {bilan['appels']} appels, "
              f"{bilan['tokens_entree']} tokens entree, "
              f"{bilan['tokens_sortie']} sortie, "
              f"{bilan['duree_run_s']:.0f}s")
        for t, c in sorted(bilan.get("par_taille", {}).items()):
            print(f"  {t:12s} {c['modele']:24s} {c['appels']:4d} appels, "
                  f"latence moyenne {c['latence_moy_s']}s")
    return ind


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    courbes = {}
    for chemin in sys.argv[1:]:
        # Les .direct.jsonl sont le suivi en direct (latences), pas des runs.
        if chemin.endswith(".direct.jsonl"):
            continue
        courbes[chemin] = analyser(chemin)
    if len(courbes) > 1:
        print("\n=== COMPARAISON, adoption par jour")
        noms = list(courbes)
        entete = "jour  " + "".join(f"{n.split('/')[-1][:18]:>20s}" for n in noms)
        print(entete)
        longueur = max(len(c) for c in courbes.values())
        for i in range(longueur):
            ligne = f"{i:4d}  "
            for n in noms:
                c = courbes[n]
                ligne += f"{c[i]['taux_adoption']:19.0%} " if i < len(c) else " " * 20
            print(ligne)
