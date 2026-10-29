"""Test de coherence scientifique : le modele v2 reduit doit retrouver v1.

Critere fixe AVANT la mesure (plan de migration, etape 5) : sur 50 graines,
le pic d'adoption moyen du v2 reduit est a 10 points au plus de celui de v1.
La tolerance ne se change pas apres coup, et les parametres ne se retouchent
jamais pour faire passer le test.

La reduction donne a v2 les MEMES ENTREES que v1, lues dans le code de v1
(regles_v1.py, Monde.adoption_percue) et non dans les courbes :
  information  0,4 x taux du groupe + 0,6 x taux du campus, l'agent compris
               (entree agregat_v1, au lieu des observations) ;
  seuil        percu compare directement au seuil : appartenance = 1 ;
  nouveaute    aucune en v1 : coupee ;
  lassitude    v1 (et non v1.1) : aucune lassitude generique, coupee ;
  bruit        v1 est deterministe : coupe ;
  distinction  coupee, par definition de la reduction.

Ce que v2 ne peut pas recevoir sans distinction, et qui reste donc different :
le pionnier v1 porte TANT QUE l'adoption est sous son seuil (seuil inverse),
le refractaire v1 ne porte jamais, l'ironique porte des 50 %, le suiveur v1
garde le ruban au-dessus de 20 % (hysteresis), la figure v1 se lasse au bout
de 4 jours, et les pionnieres v1 reevaluent un jour sur deux.

    python3 tests/test_coherence_v2.py      (environ 20 s : 50 runs v1)
"""
import json
import os
import statistics
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from ephemere import boucle_v2  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.regles_v2 import ReglesV2  # noqa: E402

TOLERANCE = 0.10
GRAINES = range(50)
REDUCTION = {"distinction": False, "nouveaute": False, "lassitude.actif": False,
             "bruit": 0, "exposition": "agregat_v1"}


def courbe_v1(graine):
    nom = f"_coherence_{graine}"
    subprocess.run([sys.executable, os.path.join(RACINE, "simuler.py"), "--agents", "20",
                    "--jours", "25", "--graine", str(graine), "--tout-regles",
                    "--energie", "non", "--nom", nom], check=True, capture_output=True)
    try:
        with open(os.path.join(RACINE, "runs", f"{nom}.jsonl"), encoding="utf-8") as f:
            return [e["taux_adoption"] for e in map(json.loads, f) if e["schema"] == "indicateurs.v1"]
    finally:
        for s in (".jsonl", ".direct.jsonl", ".rejets.jsonl"):
            p = os.path.join(RACINE, "runs", nom + s)
            if os.path.exists(p):
                os.remove(p)


def courbe_v2_reduit(r):
    monde, config, g, _ = boucle_v2.construire(
        os.path.join(RACINE, "config", "tessaline_v2.json"), 20, r,
        reglages=REDUCTION, agregat_v1=True)
    for a in monde.agents.values():
        a["traits"]["appartenance"] = 1.0
    regles = ReglesV2(config["decision"], g["dynamique"])
    journal = boucle_v2.JournalMemoire()
    boucle_v2.tourner(monde, config, {a: regles for a in monde.agents}, journal, Horloge(0), 25)
    return journal.courbe()


v1 = [courbe_v1(g) for g in GRAINES]
v2 = [courbe_v2_reduit(r) for r in GRAINES]
pic_v1 = statistics.mean(max(c) for c in v1)
pic_v2 = statistics.mean(max(c) for c in v2)
ecart = pic_v2 - pic_v1
print(f"pic moyen v1 {pic_v1:.0%}, v2 reduit {pic_v2:.0%}, ecart {ecart * 100:+.0f} points "
      f"(tolerance {TOLERANCE * 100:.0f})")
print(f"  J1 moyen : v1 {statistics.mean(c[1] for c in v1):.0%}, v2 {statistics.mean(c[1] for c in v2):.0%} ; "
      f"fin moyenne : v1 {statistics.mean(c[-1] for c in v1):.0%}, v2 {statistics.mean(c[-1] for c in v2):.0%}")
# ECHEC ATTENDU, mode strict (decision du 27 octobre, document de conception,
# etape 5). Mesure unique apres correction de la reduction : v1 58 %, v2 reduit
# 23 %, ecart -36 points. Les trois pionniers lachent le ruban des le J1 : en
# v1, ils portent tant que l'adoption est SOUS leur seuil, un comportement que
# v2 n'exprime que par la distinction, coupee ici. L'ecart est un resultat :
# v2 n'est pas une extension de v1, le lancement de v1 etait ecrit dans le
# profil du pionnier. Si le test se met a passer, quelque chose a change dans
# v1, v2 ou la reduction : il faut comprendre quoi avant de retirer ce marqueur.
ECHEC_ATTENDU = True
if abs(ecart) > TOLERANCE:
    print("ECHEC ATTENDU : le v2 reduit ne retrouve pas v1 (voir le commentaire du test).")
    sys.exit(0 if ECHEC_ATTENDU else 1)
if ECHEC_ATTENDU:
    print("ATTENTION : le test passe alors qu'un echec etait attendu. Comprendre pourquoi "
          "avant de retirer le marqueur ECHEC_ATTENDU.")
    sys.exit(1)
print("Toutes les verifications passent.")
