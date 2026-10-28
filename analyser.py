"""Lecture d'un ou plusieurs runs enregistres. Aucun appel LLM.

    python3 analyser.py runs/synchrone_xxx.jsonl
    python3 analyser.py runs/baseline.jsonl runs/synchrone_xxx.jsonl
    python3 analyser.py --echantillon-f2 runs/synchrone_xxx.jsonl

Sort les chiffres a mettre dans le rapport : courbe d'adoption, part du sens
dominant, taux de sortie de role par moteur (A4 et A5), cout (E4), puis les
mesures sur les agents LLM (ephemere/mesures_llm.py) : fiabilite par profil
(A4), fidelite au profil (A3), memoire et echanges (A1, A2), sens (B1, B3),
temps (C5, C7). --echantillon-f2 ecrit en plus runs/<run>.f2.csv : 30
decisions avec ce que la recherche a retrouve, a juger a la main (F2).
"""
import collections
import json
import os
import sys

from ephemere import mesures_llm as M

RACINE = os.path.dirname(os.path.abspath(__file__))


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def analyser(chemin):
    evs = lire(chemin)
    meta = next((e for e in evs if e["schema"] in ("run.v1", "run.v2")), {})
    dec = [e for e in evs if e["schema"] == "decision.v1"]
    inc = [e for e in evs if e["schema"] == "incident.v1"]
    ind = [e for e in evs if e["schema"] == "indicateurs.v1"]
    bilan = next((e for e in evs if e["schema"] == "bilan.v1"), {})
    coherence = next((e for e in evs if e["schema"] == "coherence.v1"), None)
    energie = next((e for e in evs if e["schema"] == "energie.v1"), None)

    print(f"\n=== {chemin}")
    print(f"{meta.get('mode', '?')}, {meta.get('nb_agents', '?')} agents, "
          f"{meta.get('jours', '?')} jours, graine {meta.get('graine', '?')}, "
          f"modele social {meta.get('modele_social', 'v1')}")

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
    mesures(chemin, evs)
    return ind


def _pct(x):
    return "  n/a" if x is None else f"{x:5.1%}"


def mesures(chemin, evs):
    """Les mesures sur les agents LLM, et la tracabilite des sources en v2."""
    llm = any(d.get("moteur") in M.MOTEURS_LLM for d in evs if d["schema"].startswith("decision."))
    src = M.sources_valides(evs)
    if src["changements"]:
        print(f"\nSOURCES (B1, v2)  {src['justifies']} / {src['changements']} changements de sens "
              f"citent une source vue ({_pct(src['part'])})")
    if not llm:
        return
    print("\nFIABILITE PAR PROFIL (A4)")
    for (moteur, profil), f in M.fiabilite(evs).items():
        natures = ", ".join(f"{n} {c}" for n, c in sorted(f["natures"].items()))
        print(f"  {moteur:10s} {profil:17s} {f['incidents']:3d} / {f['decisions']:4d} = "
              f"{_pct(f['taux'])}  {natures}")

    print("\nFIDELITE AU PROFIL (A3)  abandons parmi les porteurs, par adoption percue")
    fid = M.fidelite(evs)
    tranches = sorted({k[2] for k in fid})
    print("  " + " " * 29 + "".join(f"{M.libelle_tranche(t):>14s}" for t in tranches))
    for moteur, profil in sorted({(k[0], k[1]) for k in fid}):
        cases = []
        for t in tranches:
            f = fid.get((moteur, profil, t))
            cases.append(f"{f['abandons']:>4d}/{f['porteurs']:<4d}{f['taux']:4.0%}" if f else " " * 14)
        print(f"  {moteur:10s} {profil:17s}  " + "".join(f"{c:>14s}" for c in cases))

    mem = M.memoire(evs)
    print(f"\nMEMOIRE (A1)  {mem['avec_souvenir_ancien']} / {mem['decisions']} decisions LLM "
          f"avaient un souvenir de plus de {M.VIEUX_JOURS} jours dans leur prompt "
          f"({_pct(mem['part'])}). Disponible, pas cite : la v1 ne cite pas ses souvenirs.")
    ech = M.echanges(evs)
    a, s = ech["avec_message"], ech["sans_message"]
    print(f"ECHANGES (A2)  change de sens apres un message prive : {a['changements']}/{a['decisions']} "
          f"({_pct(a['taux'])}) ; sans message prive : {s['changements']}/{s['decisions']} "
          f"({_pct(s['taux'])})")

    div = M.diversite(evs)
    dup = M.quasi_identiques(evs)
    rec = M.recouvrement_corpus(evs, os.path.join(RACINE, "corpus"))
    print("\nSENS (B1, B3)")
    if div:
        print(f"  diversite des sens chez les LLM (entropie, 0 = tous pareils, 1 = six sens egaux) : "
              f"moyenne {div['moyenne']:.2f}, fin {div['fin']:.2f}, "
              f"{div['sens_distincts_fin']} sens distincts a la fin")
    print(f"  messages quasi identiques a celui d'un autre agent : {dup['quasi_identiques']} / "
          f"{dup['messages']} ({_pct(dup['part'])})")
    if rec["textes"]:
        print(f"  recouvrement avec le corpus (4-grammes) : moyenne {rec['moyenne']:.1%}, "
              f"max {rec['max']:.0%}, {rec['recites']} texte(s) recite(s) a plus de "
              f"{M.SEUIL_RECITE:.0%}")

    tel_chemin = chemin[:-len(".jsonl")] + ".direct.jsonl"
    tel = M.lire_jsonl(tel_chemin) if os.path.exists(tel_chemin) else []
    t = M.temps(evs, tel)
    print("\nTEMPS (C5, E4)")
    for modele, l in t["latences"].items():
        print(f"  {modele:16s} {l['appels']:4d} appels, latence moyenne {l['moyenne']:.2f}s, "
              f"p95 {l['p95']:.2f}s, attente de quota {l['attente_s']}s")
    if not t["latences"]:
        print("  pas de telemetrie (.direct.jsonl) : latences du bilan seulement")
    if t["decisions_par_agent_jour"]:
        print(f"  decisions par agent LLM et par jour simule : {t['decisions_par_agent_jour']:.2f} "
              f"en moyenne, {t['decisions_par_agent_jour_max']} au plus")
    trait = chemin[:-len(".jsonl")] + ".traitement.jsonl"
    if os.path.exists(trait):
        d = sorted(x["delai_ms"] for x in M.lire_jsonl(trait) if x.get("delai_ms") is not None)
        if d:
            print(f"  delai emission -> traitement (C7) : moyenne {sum(d) / len(d):.1f} ms, "
                  f"p95 {d[min(len(d) - 1, int(len(d) * 0.95))]} ms, pire {d[-1]} ms (n={len(d)})")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--echantillon-f2"]
    if not args:
        raise SystemExit(__doc__)
    courbes = {}
    for chemin in args:
        # Les .direct.jsonl (suivi en direct) et .traitement.jsonl (delais du
        # pont) accompagnent un run, ce ne sont pas des runs.
        if chemin.endswith((".direct.jsonl", ".traitement.jsonl", ".rejets.jsonl")):
            continue
        courbes[chemin] = analyser(chemin)
        if "--echantillon-f2" in sys.argv:
            lignes = M.echantillon_f2(lire(chemin), os.path.join(RACINE, "corpus"))
            sortie = chemin[:-len(".jsonl")] + ".f2.csv"
            M.ecrire_csv(lignes, sortie)
            print(f"\nECHANTILLON F2  {len(lignes)} decisions a juger a la main : {sortie}")
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
