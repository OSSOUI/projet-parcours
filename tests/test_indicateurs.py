"""Tests synthetiques de l'indicateur d'emergence : le resultat attendu est connu
d'avance pour chaque cas.

    python3 tests/test_indicateurs.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ephemere import indicateurs as I  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    if condition:
        print(f"  ok   {nom}")
    else:
        print(f"  ECHEC {nom} {detail}")
        echecs.append(nom)


print("Accord exprime")
verifier("les non-porteurs sans sens ne comptent pas : 3 ironie sur 4 exprimes",
         I.accord_exprime(["ironie"] * 3 + ["tendance"] + ["aucun_sens"] * 16) == 0.75)
verifier("moins de 3 sens exprimes : non defini",
         I.accord_exprime(["ironie", "ironie", "aucun_sens"]) is None)

print("\nGain soutenu")
g, debut = I.gain_soutenu([0.4, 0.9, 0.5, 0.8, 0.8, 0.8, 0.4], a0=0.5)
verifier("un pic isole ne compte pas : la meilleure fenetre est 0,8 x 3, gain 0,3",
         abs(g - 0.3) < 1e-9 and debut == 3, (g, debut))
verifier("une fenetre avec un releve non defini est ignoree",
         I.gain_soutenu([0.9, None, 0.9, 0.9], a0=0.5)[1] is None)

print("\nModele nul")
# 20 agents d'une meme classe : moitie ironie, un quart tendance, un quart ringard.
dist = {("suiveur", "llm_petit"): {"ironie": 2, "tendance": 1, "ringard": 1}}
classes = [("suiveur", "llm_petit")] * 20
nul = I.modele_nul(classes, dist, releves=26, tirages=400, graine=1)
verifier(f"A0 proche de la part du sens majoritaire tire au hasard ({nul['a0']:.2f})",
         0.5 <= nul["a0"] <= 0.65, nul["a0"])
rng = random.Random(7)
def tirage():
    return I.accord_exprime([rng.choice(["ironie", "ironie", "tendance", "ringard"])
                             for _ in range(20)])
au_hasard = [I.gain_soutenu([tirage() for _ in range(26)], nul["a0"])[0] for _ in range(200)]
part = sum(g > nul["seuil"] for g in au_hasard) / len(au_hasard)
verifier(f"des runs tires du modele nul depassent le seuil environ 5 % du temps ({part:.0%})",
         part <= 0.10, part)
consensus = [0.55] * 5 + [0.95] * 21
verifier("un accord a 95 % tenu 21 releves depasse le seuil",
         I.gain_soutenu(consensus, nul["a0"])[0] > nul["seuil"])
try:
    I.modele_nul([("pionnier", "llm_grand")], dist, releves=5, tirages=10)
    verifier("une classe absente du point zero est refusee", False)
except KeyError:
    verifier("une classe absente du point zero est refusee", True)

print("\nConvergence entre groupes")
meme = {"a": ["ironie"] * 3 + ["tendance"], "b": ["ironie"] * 3 + ["tendance"]}
verifier("meme repartition dans chaque groupe : 1", abs(I.convergence_groupes(meme) - 1) < 1e-9)
disjoint = {"a": ["ironie"] * 4, "b": ["tendance"] * 4}
verifier("un sens propre a chaque groupe : 0", abs(I.convergence_groupes(disjoint)) < 1e-9)
petits = {"a": ["ironie"] * 4, "b": ["tendance"] * 2, "c": ["ringard"]}
verifier("les groupes de moins de 3 sens exprimes sont ignores : non defini",
         I.convergence_groupes(petits) is None)

print()
if echecs:
    print(f"{len(echecs)} verification(s) en echec : {echecs}")
    sys.exit(1)
print("Toutes les verifications passent.")
