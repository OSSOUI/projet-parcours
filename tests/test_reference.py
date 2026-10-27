"""Non-regression du modele social v1, sans aucun appel LLM.

Les runs a regles du 21 octobre (tag v1-profils) doivent se reproduire a
l'identique : memes decisions, memes indicateurs, graine par graine. Tant que
ce test passe, le modele v2 peut etre construit sans perdre la reference.

    python3 tests/test_reference.py
"""
import json
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(RACINE, "runs")
sys.path.insert(0, RACINE)

from ephemere.contrat import modele_social, verifier as conforme  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


def trace(chemin):
    """Ce qui doit etre identique : decisions et indicateurs, dans l'ordre."""
    garder = {"decision.v1": ("t_sim", "agent", "porte", "categorie"),
              "indicateurs.v1": ("t_sim", "taux_adoption", "repartition_sens",
                                 "sens_dominant", "part_sens_dominant", "porteurs")}
    with open(chemin, encoding="utf-8") as f:
        evs = [json.loads(l) for l in f if l.strip()]
    return [(e["schema"], *(e[c] for c in garder[e["schema"]]))
            for e in evs if e.get("schema") in garder]


def entete(chemin):
    with open(chemin, encoding="utf-8") as f:
        return json.loads(f.readline())


def rejouer(graine, options):
    """Lance un run a regles et renvoie (en-tete, trace) ; ses fichiers sont supprimes."""
    nom = f"_test_reference_{graine}"
    subprocess.run([sys.executable, os.path.join(RACINE, "simuler.py"),
                    "--agents", "20", "--jours", "25", "--graine", str(graine),
                    "--tout-regles", "--energie", "non", "--nom", nom] + options,
                   check=True, capture_output=True)
    chemin = os.path.join(RUNS, f"{nom}.jsonl")
    try:
        return entete(chemin), trace(chemin)
    finally:
        for suffixe in (".jsonl", ".direct.jsonl", ".rejets.jsonl"):
            p = os.path.join(RUNS, nom + suffixe)
            if os.path.exists(p):
                os.remove(p)


print("\nEn-tetes de run")
base = {"run": "r", "t_sim": 0, "t_sim_lisible": "J01 00:00", "t_emission": "2026-10-27T00:00:00.000",
        "t_traitement": None, "mode": "synchrone", "nb_agents": 20, "graine": 1, "jours": 25,
        "config": "tessaline.json", "version_contrat": "1.3.0"}
verifier("run.v1 se lit comme v1", modele_social({"schema": "run.v1", **base}) == "v1")
verifier("run.v2 sans modele_social refuse", not conforme({"schema": "run.v2", **base})[0])
verifier("run.v2 avec un modele inconnu refuse",
         not conforme({"schema": "run.v2", **base, "modele_social": "v9"})[0])
verifier("run.v2 v1.1 accepte",
         conforme({"schema": "run.v2", **base, "modele_social": "v1.1"}) == (True, None))

# v1 : la baseline du plan complet. v1.1 : la baseline du plan meneurs, qui
# tournait avec la lassitude des suiveurs.
REFERENCES = [("v1", "exp_complet_baseline", []),
              ("v1.1", "exp_meneurs_baseline", ["--lassitude-suiveurs"])]

for version, prefixe, options in REFERENCES:
    print(f"\n{version} contre runs/{prefixe}_0*.jsonl")
    for i, graine in enumerate(range(100, 105), start=1):
        reference = os.path.join(RUNS, f"{prefixe}_{i:02d}.jsonl")
        # Une reference absente est un echec : un test qui saute en silence
        # passe au vert sans rien avoir verifie.
        if not os.path.exists(reference):
            verifier(f"graine {graine} : reference presente", False,
                     f"{os.path.basename(reference)} absent")
            continue
        verifier(f"graine {graine} : reference etiquetee {version}",
                 modele_social(entete(reference)) == version,
                 f"lu {modele_social(entete(reference))!r}")
        neuf, obtenu = rejouer(graine, options)
        verifier(f"graine {graine} : nouveau run etiquete {version} en run.v2",
                 neuf["schema"] == "run.v2" and modele_social(neuf) == version)
        attendu = trace(reference)
        verifier(f"graine {graine} identique ({len(attendu)} evenements)", obtenu == attendu,
                 f"{len(obtenu)} evenements obtenus")

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
