"""Protocole experimental : runs repetes et dispersion (exigences B3 et E2).

E2 demande au moins 5 runs par configuration sur au moins 2 configurations,
avec la dispersion presentee et discutee. B3 demande de demontrer que
l'indicateur distingue un run ou un contexte commun emerge d'un run ou il
n'emerge pas.

Les deux se traitent ensemble : il suffit de construire une configuration ou
l'emergence est attendue et une configuration temoin ou elle ne l'est pas, puis
de montrer que l'indicateur les separe nettement, sur plusieurs repetitions.

    python3 experience.py --liste
    python3 experience.py --plan socle --repetitions 5
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
    "llm_asynchrone": {
        "titre": "Agents LLM, mode asynchrone",
        "options": ["--mode", "asynchrone"],
        "attendu": "emergence plus lente, ordre des prises de parole different",
    },
}

PLANS = {
    "socle": ["baseline", "temoin_cloisonne"],
    "llm": ["baseline", "llm_synchrone"],
    "temps": ["llm_synchrone", "llm_asynchrone"],
    "complet": ["baseline", "temoin_cloisonne", "llm_synchrone", "llm_asynchrone"],
}


def lancer(nom_run, options, args):
    """Lance un run et renvoie son chemin, ou None s'il a echoue."""
    commande = [sys.executable, os.path.join(RACINE, "simuler.py"),
                "--agents", str(args.agents), "--jours", str(args.jours),
                "--graine", str(args.graine), "--nom", nom_run] + list(options)
    if "--tout-regles" not in options:
        commande += ["--fournisseur", args.fournisseur, "--pause", str(args.pause)]
    t0 = time.perf_counter()
    r = subprocess.run(commande, capture_output=True, text=True)
    duree = time.perf_counter() - t0
    if r.returncode != 0:
        print(f"    echec : {(r.stderr or r.stdout).strip().splitlines()[-1][:120]}")
        return None, duree
    return os.path.join(RACINE, "runs", f"{nom_run}.jsonl"), duree


def mesurer(chemin):
    """Les quatre chiffres qui resument un run, pour la table de dispersion."""
    indicateurs, bilan = [], {}
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            e = json.loads(ligne)
            if e["schema"] == "indicateurs.v1":
                indicateurs.append(e)
            elif e["schema"] == "bilan.v1":
                bilan = e
    if not indicateurs:
        return None
    adoptions = [e["taux_adoption"] for e in indicateurs]
    accords = [e["part_sens_dominant"] for e in indicateurs
               if e["sens_dominant"] != "aucun_sens"]
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
        "incidents": bilan.get("incidents", 0),
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
    p.add_argument("--repetitions", type=int, default=5,
                   help="runs par configuration (le sujet en exige 5 au minimum)")
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
    print(f"Plan '{args.plan}' : {len(noms)} configuration(s) x {args.repetitions} "
          f"repetition(s) = {len(noms) * args.repetitions} runs")
    print(f"{args.agents} agents, {args.jours} jours simules\n")

    resultats = {}
    graine = args.graine
    for nom in noms:
        cfg = CONFIGURATIONS[nom]
        print(f"=== {nom} : {cfg['titre']}")
        print(f"    hypothese avant mesure : {cfg['attendu']}")
        mesures = []
        for i in range(args.repetitions):
            nom_run = f"exp_{args.plan}_{nom}_{i + 1:02d}"
            sys.stdout.write(f"    run {i + 1}/{args.repetitions} (graine {graine})... ")
            sys.stdout.flush()
            chemin, duree = lancer(nom_run, cfg["options"] + ["--graine", str(graine)], args)
            graine += 1
            if chemin is None:
                continue
            m = mesurer(chemin)
            if m:
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

    appels = sum(m["appels"] for ms in resultats.values() for m in ms)
    incidents = sum(m["incidents"] for ms in resultats.values() for m in ms)
    print(f"COUT TOTAL  {appels} appels LLM, {incidents} incidents d'agent")

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


if __name__ == "__main__":
    main()
