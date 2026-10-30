"""Indicateur d'emergence interpretable (decisions du 28 octobre, audit 2).

L'accord brut (part du campus sur le sens le plus repandu hors "aucun sens",
seuil 30 %) mesure ce qu'il definit, mais pas l'emergence : il ne retranche pas
le point de depart, n'exige aucune duree, et monte avec l'adoption puisque les
non-porteurs sont au denominateur. D'ou trois changements :

  accord exprime    part du sens le plus repandu PARMI LES AGENTS QUI EXPRIMENT
                    UN SENS (autre qu'"aucun sens"), et non parmi tout le campus.
                    Non defini sous MIN_EXPRIMES agents.
  gain soutenu      Delta A = meilleur, sur toute fenetre de FENETRE releves
                    consecutifs, du minimum de l'accord exprime dans la
                    fenetre, moins A0, l'accord attendu sans aucun echange.
  seuil             95e centile de Delta A sous un modele nul : chaque agent tire
                    son sens au hasard, a chaque releve, selon la distribution
                    du point zero de sa classe (profil, taille de modele), sur
                    TIRAGES_NULS runs. Fixe d'avance, sans reglage a la main.

Complementaire, pour B1 (le sens "pour chaque groupe du campus") :

  convergence entre groupes   1 - moyenne, sur les paires de groupes d'au moins
                    MIN_GROUPE agents qui expriment un sens, de la divergence de
                    Jensen-Shannon (base 2, bornee a [0, 1]) entre leurs
                    repartitions de sens. 1 : meme repartition partout ; 0 : un
                    sens propre a chaque groupe.

Ces indicateurs ne s'appliquent pas aux agents a regles v1 : leur sens est une
fonction ecrite de l'adoption percue, pas une croyance.

Regroupement (decide le 30 octobre) : tendance et suivre_la_foule comptent pour
un seul sens, le petit modele ne tenant pas la frontiere (sens_a_priori.py).
Le modele nul tire toujours dans les six sens du point zero, puis regroupe
comme les runs : le seuil monte avec l'accord attendu par hasard.
"""
import collections
import math
import random

AUCUN = "aucun_sens"
MIN_EXPRIMES = 3
FENETRE = 3
MIN_GROUPE = 3
TIRAGES_NULS = 1000
CENTILE = 0.95
REGROUPEMENT_FOULE = {"tendance": "tendance_ou_foule", "suivre_la_foule": "tendance_ou_foule"}


def accord_exprime(categories, regroupement=None):
    """Part du sens le plus repandu parmi les sens exprimes, ou None."""
    exprimes = [(regroupement or {}).get(c, c) for c in categories if c and c != AUCUN]
    if len(exprimes) < MIN_EXPRIMES:
        return None
    return collections.Counter(exprimes).most_common(1)[0][1] / len(exprimes)


def gain_soutenu(serie, a0, fenetre=FENETRE):
    """Delta A et le debut de la meilleure fenetre, ou (None, None).

    serie : accord exprime a chaque releve (None quand il n'est pas defini).
    Une fenetre qui contient un releve non defini ne compte pas.
    """
    meilleur, debut = None, None
    for i in range(len(serie) - fenetre + 1):
        bloc = serie[i:i + fenetre]
        if any(x is None for x in bloc):
            continue
        g = min(bloc) - a0
        if meilleur is None or g > meilleur:
            meilleur, debut = g, i
    return meilleur, debut


def distributions_point_zero(reponses):
    """(profil, taille) -> Counter des sens, d'apres les reponses valides du point zero."""
    d = collections.defaultdict(collections.Counter)
    for r in reponses:
        if r.get("incident") is None and r.get("categorie"):
            d[(r["profil"], r["taille"])][r["categorie"]] += 1
    return d


def _tirer(rng, compte):
    total = sum(compte.values())
    x = rng.random() * total
    for sens, n in sorted(compte.items()):
        x -= n
        if x < 0:
            return sens
    return sorted(compte)[-1]


def modele_nul(classes, distributions, releves, tirages=TIRAGES_NULS, graine=0,
               regroupement=None):
    """A0 et seuil de Delta A pour une population donnee.

    classes : la classe (profil, taille) de chaque agent dont on mesure le sens.
    Renvoie {"a0", "seuil", "gains"} ; une classe absente du point zero leve
    KeyError, plutot que d'etre tiree d'une autre distribution en silence.
    """
    rng = random.Random(graine)
    comptes = [distributions[c] for c in classes]
    def un_releve():
        return accord_exprime([_tirer(rng, c) for c in comptes], regroupement)
    # A0 : esperance de l'accord exprime sans echange, estimee sur autant de releves.
    echantillon = [x for x in (un_releve() for _ in range(tirages)) if x is not None]
    a0 = sum(echantillon) / len(echantillon)
    gains = []
    for _ in range(tirages):
        g, _ = gain_soutenu([un_releve() for _ in range(releves)], a0)
        if g is not None:
            gains.append(g)
    gains.sort()
    return {"a0": a0, "seuil": gains[min(len(gains) - 1, int(len(gains) * CENTILE))],
            "gains": gains}


def _jsd(p, q):
    """Divergence de Jensen-Shannon en base 2, entre deux Counter."""
    cles = set(p) | set(q)
    np_, nq = sum(p.values()), sum(q.values())
    def kl(a, na, m):
        return sum((a[k] / na) * math.log2((a[k] / na) / m[k]) for k in cles if a[k])
    m = {k: (p[k] / np_ + q[k] / nq) / 2 for k in cles}
    return (kl(p, np_, m) + kl(q, nq, m)) / 2


def convergence_groupes(sens_par_groupe):
    """1 - JSD moyenne entre groupes d'au moins MIN_GROUPE sens exprimes, ou None.

    sens_par_groupe : groupe -> liste des sens de ses agents.
    """
    reps = [collections.Counter(c for c in cats if c and c != AUCUN)
            for cats in sens_par_groupe.values()]
    reps = [r for r in reps if sum(r.values()) >= MIN_GROUPE]
    if len(reps) < 2:
        return None
    paires = [(a, b) for i, a in enumerate(reps) for b in reps[i + 1:]]
    return 1 - sum(_jsd(a, b) for a, b in paires) / len(paires)
