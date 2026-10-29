"""Protocole experimental : runs repetes et dispersion (exigences B3 et E2).

E2 demande au moins 5 runs par configuration sur au moins 2 configurations,
avec la dispersion presentee et discutee. B3 demande de demontrer que
l'indicateur distingue un run ou un contexte commun emerge d'un run ou il
n'emerge pas.

Les deux se traitent ensemble : il suffit de construire une configuration ou
l'emergence est attendue et une configuration temoin ou elle ne l'est pas, puis
de montrer que l'indicateur les separe nettement, sur plusieurs repetitions.

    python3 experience.py --liste
    python3 experience.py --plan socle                  # 30 graines communes
    python3 experience.py --plan temps --repetitions 5 --fournisseur ollama

Chaque run est enregistre normalement dans runs/, donc rejouable et analysable
un par un avec analyser.py.
"""
import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time

RACINE = os.path.dirname(os.path.abspath(__file__))

# Une configuration = un jeu d'options passe a simuler.py.
# "attendu" dit si l'on s'attend a voir emerger un contexte commun : c'est
# l'hypothese formulee AVANT de mesurer, comme l'exige le sujet.
CONFIGURATIONS = {
    "baseline": {
        "titre": "Baseline a regles, sans aucun LLM",
        "options": ["--tout-regles"],
        "attendu": "emergence partielle, sans declin",
    },
    "temoin_cloisonne": {
        "titre": "Temoin : groupes cloisonnes des le depart",
        "options": ["--tout-regles", "--config",
                    os.path.join(RACINE, "config", "tessaline_cloisonne.json")],
        "attendu": "pas d'emergence a l'echelle du campus",
    },
    "llm_synchrone": {
        "titre": "Agents LLM, mode synchrone",
        "options": ["--mode", "synchrone"],
        "attendu": "emergence puis declin",
    },
    "llm_meneurs": {
        "titre": "Seuls les meneurs en LLM, le reste en regles",
        "options": ["--mode", "synchrone", "--meneurs-llm", "--lassitude-suiveurs"],
        "attendu": ("si l'emergence egale celle de llm_synchrone, ce sont les "
                    "meneurs LLM qui la portent, et non les LLM de la population"),
    },
    "llm_asynchrone": {
        "titre": "Agents LLM, mode asynchrone",
        "options": ["--mode", "asynchrone"],
        "attendu": ("emergence plus lente qu'en synchrone : le grand modele, plus lent, "
                    "fait parler les pionnieres et la figure populaire apres les autres"),
    },
    "llm_temoin_cloisonne": {
        "titre": "Temoin LLM : groupes cloisonnes des le depart",
        "options": ["--mode", "synchrone", "--config",
                    os.path.join(RACINE, "config", "tessaline_cloisonne.json")],
        "attendu": ("pas d'emergence a l'echelle du campus. Si l'accord depasse "
                    "quand meme le seuil, il vient de la ressemblance des reponses "
                    "d'un meme modele et non d'un contexte commun (question Q2)"),
    },
    "tout_grand": {
        "titre": "Tous les agents sur le grand modele (reference E5)",
        "options": ["--mode", "synchrone", "--tout-grand"],
        "attendu": ("phenomene comparable a llm_synchrone (memes graines), mais "
                    "chaque agent appelle le grand modele : plus d'appels au total, "
                    "environ cinq fois plus au grand modele, plus de tokens"),
    },
}

PLANS = {
    "socle": ["baseline", "temoin_cloisonne"],
    "llm": ["baseline", "llm_synchrone"],                  # E1 : apport du LLM
    "b3_llm": ["llm_synchrone", "llm_temoin_cloisonne"],   # B3 et Q2 cote LLM
    "meneurs": ["baseline", "llm_meneurs", "llm_synchrone"],  # effet des meneurs LLM
    "temps": ["llm_synchrone", "llm_asynchrone"],          # C5
    "sobriete": ["llm_synchrone", "tout_grand"],           # E5
    "complet": ["baseline", "temoin_cloisonne", "llm_synchrone", "llm_temoin_cloisonne",
                "llm_asynchrone", "tout_grand"],
}


def lancer(nom_run, options, args):
    """Lance un run et renvoie son chemin, ou None s'il a echoue."""
    commande = [sys.executable, os.path.join(RACINE, "simuler.py"),
                "--agents", str(args.agents), "--jours", str(args.jours),
                "--nom", nom_run] + list(options)
    if "--tout-regles" not in options:
        commande += ["--fournisseur", args.fournisseur, "--pause", str(args.pause)]
    t0 = time.perf_counter()
    r = subprocess.run(commande, capture_output=True, text=True)
    duree = time.perf_counter() - t0
    if r.returncode != 0:
        print(f"    echec : {(r.stderr or r.stdout).strip().splitlines()[-1][:120]}")
        return None, duree
    return os.path.join(RACINE, "runs", f"{nom_run}.jsonl"), duree


def accord_partage(releve):
    """Part du campus sur le sens le plus repandu AUTRE que "aucun sens".

    On ne peut pas se contenter de part_sens_dominant : quand "aucun sens"
    domine, un releve ou 40 % du campus s'accorde sur "tendance" etait jete
    tout entier. Les non-porteurs restent au denominateur.
    """
    rep = releve["repartition_sens"]
    n = sum(rep.values()) or 1
    return max((c for s, c in rep.items() if s != "aucun_sens"), default=0) / n


def mesurer(chemin):
    """Les chiffres qui resument un run, pour la table de dispersion."""
    indicateurs, bilan, energie, coherence = [], {}, {}, {}
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            e = json.loads(ligne)
            if e["schema"] == "indicateurs.v1":
                indicateurs.append(e)
            elif e["schema"] == "bilan.v1":
                bilan = e
            elif e["schema"] == "energie.v1":
                energie = e
            elif e["schema"] == "coherence.v1":
                coherence = e
    if not indicateurs:
        return None
    adoptions = [e["taux_adoption"] for e in indicateurs]
    accords = [accord_partage(e) for e in indicateurs]
    pic = max(adoptions)
    index_pic = adoptions.index(pic)
    apres = adoptions[index_pic + 1:]
    return {
        "adoption_pic": pic,
        "adoption_finale": adoptions[-1],
        # Amplitude du cycle : de combien la mode retombe apres son pic.
        "declin": pic - min(apres) if apres else 0.0,
        # Accord maximal sur un sens AUTRE que "aucun sens" : c'est lui qui
        # mesure vraiment l'emergence d'un contexte commun (exigence B1).
        "accord_max": max(accords) if accords else 0.0,
        "appels": bilan.get("appels", 0),
        "appels_grand": bilan.get("par_taille", {}).get("llm_grand", {}).get("appels", 0),
        "tokens": bilan.get("tokens_entree", 0) + bilan.get("tokens_sortie", 0),
        "incidents": bilan.get("incidents", 0),
        "kwh": energie.get("kwh"),
        "violations_c6": coherence.get("violations", 0),
        "controles_c6": coherence.get("controles", 0),
    }


def resumer(valeurs):
    if not valeurs:
        return "n/a"
    moyenne = statistics.mean(valeurs)
    if len(valeurs) < 2:
        return f"{moyenne:.0%}"
    ecart = statistics.stdev(valeurs)
    return f"{moyenne:5.0%} +/- {ecart:4.0%}  [{min(valeurs):.0%} a {max(valeurs):.0%}]"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", default="socle", choices=sorted(PLANS))
    p.add_argument("--repetitions", type=int, default=None,
                   help="runs par configuration : 30 par defaut sans LLM, 5 avec "
                        "(le sujet en exige 5 au minimum)")
    p.add_argument("--agents", type=int, default=20)
    p.add_argument("--jours", type=int, default=20)
    p.add_argument("--graine", type=int, default=100, help="graine du premier run")
    p.add_argument("--fournisseur", default="ollama")
    p.add_argument("--pause", type=float, default=0.0)
    p.add_argument("--seuil", type=float, default=0.30,
                   help="accord minimal pour qu'un run compte comme emergent")
    p.add_argument("--liste", action="store_true", help="affiche les plans et sort")
    args = p.parse_args()

    if args.liste:
        for nom, cfgs in sorted(PLANS.items()):
            print(f"{nom:10s} {' + '.join(cfgs)}")
        print()
        for nom, c in CONFIGURATIONS.items():
            print(f"  {nom:18s} {c['titre']}\n{'':21s}attendu : {c['attendu']}")
        return

    noms = PLANS[args.plan]
    if args.repetitions is None:
        sans_llm = all("--tout-regles" in CONFIGURATIONS[n]["options"] for n in noms)
        args.repetitions = 30 if sans_llm else 5
    # Les MEMES graines pour chaque configuration : run i de la baseline et
    # run i du temoin partent de la meme population, seule la configuration
    # change. La comparaison se fait alors graine par graine.
    graines = [args.graine + i for i in range(args.repetitions)]
    print(f"Plan '{args.plan}' : {len(noms)} configuration(s) x {args.repetitions} "
          f"repetition(s) = {len(noms) * args.repetitions} runs")
    print(f"{args.agents} agents, {args.jours} jours simules, "
          f"graines {graines[0]} a {graines[-1]} communes aux configurations\n")

    resultats = {}
    for nom in noms:
        cfg = CONFIGURATIONS[nom]
        print(f"=== {nom} : {cfg['titre']}")
        print(f"    hypothese avant mesure : {cfg['attendu']}")
        mesures = []
        for i, graine in enumerate(graines):
            nom_run = f"exp_{args.plan}_{nom}_{i + 1:02d}"
            sys.stdout.write(f"    run {i + 1}/{args.repetitions} (graine {graine})... ")
            sys.stdout.flush()
            chemin, duree = lancer(nom_run, cfg["options"] + ["--graine", str(graine)], args)
            if chemin is None:
                continue
            m = mesurer(chemin)
            if m:
                m["graine"] = graine
                mesures.append(m)
                print(f"pic {m['adoption_pic']:.0%}, accord {m['accord_max']:.0%}, "
                      f"{duree:.0f}s")
        resultats[nom] = mesures
        print()

    print("=" * 78)
    print("DISPERSION  (moyenne +/- ecart type  [minimum a maximum])\n")
    cles = [("adoption_pic", "adoption au pic"), ("adoption_finale", "adoption finale"),
            ("declin", "declin apres le pic"), ("accord_max", "accord maximal sur un sens")]
    for cle, libelle in cles:
        print(f"{libelle}")
        for nom in noms:
            v = [m[cle] for m in resultats.get(nom, [])]
            print(f"  {nom:20s} {resumer(v)}  (n={len(v)})")
        print()

    print("COUT PAR RUN, moyenne par configuration (E4, E5)")
    for nom in noms:
        ms = resultats.get(nom, [])
        if not ms:
            continue
        kwh = [m["kwh"] for m in ms if m["kwh"] is not None]
        print(f"  {nom:20s} {statistics.mean(m['appels'] for m in ms):7.0f} appels "
              f"(dont {statistics.mean(m['appels_grand'] for m in ms):.0f} au grand modele), "
              f"{statistics.mean(m['tokens'] for m in ms):8.0f} tokens, "
              + (f"{statistics.mean(kwh) * 1000:.1f} Wh" if kwh else "energie non mesuree"))
    appels = sum(m["appels"] for ms in resultats.values() for m in ms)
    incidents = sum(m["incidents"] for ms in resultats.values() for m in ms)
    controles = sum(m["controles_c6"] for ms in resultats.values() for m in ms)
    violations = sum(m["violations_c6"] for ms in resultats.values() for m in ms)
    print(f"\nCOUT TOTAL  {appels} appels LLM, {incidents} incidents d'agent")
    if controles:
        print(f"COHERENCE TEMPORELLE (C6)  {violations} violation(s) sur "
              f"{controles} contextes controles")

    # Conclusion B3 : l'indicateur separe-t-il les configurations ?
    #
    # Comparer deux moyennes avec un ecart type n'a pas de sens ici : le temoin
    # vaut toujours exactement zero, alors que l'autre configuration s'etale.
    # On compte donc des RUNS, pas des moyennes : combien, dans chaque
    # configuration, atteignent un accord qu'on puisse appeler une emergence.
    if len(noms) >= 2:
        print("\nSEPARATION (exigence B3)")
        print(f"  seuil d'emergence retenu : accord maximal >= {int(args.seuil * 100)} % "
              f"sur un sens autre que \"aucun sens\"")
        comptes = {}
        for nom in noms:
            v = [m["accord_max"] for m in resultats.get(nom, [])]
            emergents = sum(1 for x in v if x >= args.seuil)
            comptes[nom] = (emergents, len(v))
            mediane = statistics.median(v) if v else 0.0
            print(f"  {nom:20s} {emergents}/{len(v)} runs emergents, "
                  f"mediane {mediane:.0%}")
        hauts = max(comptes, key=lambda k: comptes[k][0] / max(1, comptes[k][1]))
        bas = min(comptes, key=lambda k: comptes[k][0] / max(1, comptes[k][1]))
        e_haut, n_haut = comptes[hauts]
        e_bas, n_bas = comptes[bas]
        if n_haut and n_bas and e_haut > e_bas and e_bas == 0:
            print(f"  => l'indicateur separe : {e_haut}/{n_haut} pour {hauts} "
                  f"contre {e_bas}/{n_bas} pour {bas}.")
            print("     Aucun run du temoin n'atteint le seuil, ce qui est "
                  "exactement ce que B3 demande de demontrer.")
        elif e_haut > e_bas:
            print(f"  => separation partielle : {e_haut}/{n_haut} contre "
                  f"{e_bas}/{n_bas}. A presenter telle quelle, sans l'arrondir.")
        else:
            print("  => aucune separation. Le resultat est negatif et doit etre "
                  "ecrit tel quel dans le rapport.")

        # Graines communes : on peut comparer run a run, a population egale.
        a, b = noms[0], noms[1]
        par_graine = {m["graine"]: m["accord_max"] for m in resultats.get(b, [])}
        paires = [(m["accord_max"], par_graine[m["graine"]])
                  for m in resultats.get(a, []) if m["graine"] in par_graine]
        if paires:
            plus = sum(1 for x, y in paires if x > y)
            egal = sum(1 for x, y in paires if x == y)
            print(f"  graine par graine : accord {a} > {b} dans {plus}/{len(paires)} "
                  f"paires, egal dans {egal}")


if __name__ == "__main__":
    main()
