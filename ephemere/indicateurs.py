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


# ------------------------------------------------- base experimentale (3 novembre)
#
# Deux corrections, decidees apres l'audit :
#
#   persistance   le modele nul ci-dessus tire chaque releve independamment. Or
#                 un agent garde son sens d'un releve a l'autre (72 a 88 % dans
#                 les runs) : le minimum d'une fenetre est alors plus haut, et le
#                 seuil independant declare emergents 31 a 38 % des runs nuls.
#                 modele_nul_markov garde le sens avec la probabilite p.
#   ombres        le temoin de reference est le temoin asservi (simuler.py
#                 --ombres) : la meme decision reposee sans le social. L'ecart
#                 d'accord reel - ombre est apparie agent par decision, et son
#                 seuil vient d'une permutation de ces paires, pas d'un modele.


def persistance(etats):
    """Part des agents qui gardent leur sens d'un releve au suivant.

    etats : un dict agent -> sens par releve (None = non defini, ignore).
    """
    gardes = paires = 0
    for avant, apres in zip(etats, etats[1:]):
        for a, s in avant.items():
            if s is not None and apres.get(a) is not None:
                paires += 1
                gardes += apres[a] == s
    return gardes / paires if paires else None


def modele_nul_markov(classes, distributions, releves, p, tirages=TIRAGES_NULS, graine=0,
                      regroupement=None):
    """Comme modele_nul, mais chaque agent garde son sens d'un releve au suivant avec
    la probabilite p, sinon il retire dans la distribution de sa classe.

    A0 reste l'accord attendu a un releve (p ne le change pas) ; seule la
    distribution du gain soutenu, donc le seuil, depend de p.
    """
    rng = random.Random(graine)
    comptes = [distributions[c] for c in classes]
    nul = modele_nul(classes, distributions, releves, tirages, graine, regroupement)
    gains = []
    for _ in range(tirages):
        etat = [_tirer(rng, c) for c in comptes]
        serie = []
        for _ in range(releves):
            etat = [s if rng.random() < p else _tirer(rng, c) for s, c in zip(etat, comptes)]
            serie.append(accord_exprime(etat, regroupement))
        g, _ = gain_soutenu(serie, nul["a0"])
        if g is not None:
            gains.append(g)
    gains.sort()
    return {"a0": nul["a0"], "persistance": p,
            "seuil": gains[min(len(gains) - 1, int(len(gains) * CENTILE))], "gains": gains}


def _series(decisions, releves, permutees=None):
    """Sens de chaque agent a chaque releve, cote reel et cote ombre.

    decisions : liste de (agent, releve, reel, ombre), releve = premier releve
    que la decision touche ; une decision remplace la precedente du meme agent.
    permutees : indices des decisions dont reel et ombre sont echanges.
    """
    reel, ombre = [{} for _ in range(releves)], [{} for _ in range(releves)]
    courant_r, courant_o = {}, {}
    par_releve = collections.defaultdict(list)
    for i, d in enumerate(decisions):
        par_releve[d[1]].append(i)
    for j in range(releves):
        for i in par_releve.get(j, []):
            agent, _, r, o = decisions[i]
            if permutees and i in permutees:
                r, o = o, r
            courant_r[agent], courant_o[agent] = r, o
        reel[j], ombre[j] = dict(courant_r), dict(courant_o)
    return reel, ombre


def _ecart_moyen(reel, ombre, regroupement):
    ecarts = []
    for r, o in zip(reel, ombre):
        agents = [a for a in r if r[a] is not None and o.get(a) is not None]
        ar = accord_exprime([r[a] for a in agents], regroupement)
        ao = accord_exprime([o[a] for a in agents], regroupement)
        if ar is not None and ao is not None:
            ecarts.append(ar - ao)
    return (sum(ecarts) / len(ecarts), len(ecarts)) if ecarts else (None, 0)


def ecart_ombres(decisions, releves, regroupement=None, permutations=1000, graine=0):
    """Ecart moyen d'accord reel - ombre, et sa p-valeur par permutation des paires.

    Sans effet du social, la decision reelle et son ombre sont echangeables :
    chaque permutation echange au hasard la moitie des paires (le sens persiste
    des deux cotes de la meme facon). Une paire ou l'un des deux cotes est en
    incident (None) est retiree des deux cotes. p unilaterale : le social
    augmente-t-il l'accord ?
    """
    reel, ombre = _series(decisions, releves)
    observe, n = _ecart_moyen(reel, ombre, regroupement)
    if observe is None:
        return {"ecart": None, "p": None, "releves": 0, "decisions": len(decisions)}
    rng = random.Random(graine)
    au_moins = 0
    for _ in range(permutations):
        echanges = {i for i in range(len(decisions)) if rng.random() < 0.5}
        e, _ = _ecart_moyen(*_series(decisions, releves, echanges), regroupement)
        au_moins += e is not None and e >= observe
    return {"ecart": observe, "p": (1 + au_moins) / (1 + permutations), "releves": n,
            "decisions": len(decisions)}
