"""Reseau social du modele v2 : liens forts dans le groupe, ponts faibles entre groupes.

Les six groupes restent des lieux. Les relations entre personnes forment un
reseau pondere a une couche, tire de la graine "reseau" (ephemere/graines.py) :
le changer ne touche ni la population ni les moteurs.

  fort    deux membres d'un meme groupe ; poids 1,0
  faible  un pont vers un autre groupe ; poids 0,3

La probabilite d'un lien fort vaut degre_fort / (taille du groupe - 1), et non
une constante : avec une constante (0,6), le degre fort passait de 2,1 a 20
agents a 10,5 a 100, et la taille de population aurait change la densite du
reseau en meme temps que le nombre d'agents. Ici le degre moyen reste le meme
a toutes les tailles.

La variante cloisonnee n'a aucun pont : c'est l'idee de tessaline_cloisonne.json
en v1, portee par le reseau.
"""
import random
from collections import defaultdict


def construire(agents, reglage, graine, cloisonne=False):
    """Renvoie la liste des liens [{"a", "b", "type", "poids"}], a < b par ordre des agents."""
    rng = random.Random(graine)
    rang = {a["id"]: i for i, a in enumerate(agents)}
    par_groupe = defaultdict(list)
    for a in agents:
        par_groupe[a["groupe"]].append(a["id"])

    liens = {}

    def lier(x, y, nature):
        a, b = sorted((x, y), key=rang.get)
        liens[(a, b)] = {"a": a, "b": b, "type": nature, "poids": reglage[f"poids_{nature}"]}

    for groupe in sorted(par_groupe):
        membres = par_groupe[groupe]
        if len(membres) < 2:
            continue
        p = min(1.0, reglage["degre_fort"] / (len(membres) - 1))
        for i, x in enumerate(membres):
            for y in membres[i + 1:]:
                if rng.random() < p:
                    lier(x, y, "fort")

    if not cloisonne:
        # Chaque agent vise 1 a 2 ponts AU TOTAL : il n'ajoute que ce qui lui
        # manque apres les ponts recus des agents precedents. Sinon chacun en
        # creerait 1 a 2 et en recevrait autant, soit environ 3.
        bas, haut = reglage["ponts"]
        ponts = defaultdict(int)
        for a in agents:
            manque = rng.randint(bas, haut) - ponts[a["id"]]
            dehors = [b["id"] for b in agents if b["groupe"] != a["groupe"]
                      and tuple(sorted((a["id"], b["id"]), key=rang.get)) not in liens]
            for b in rng.sample(dehors, max(0, min(len(dehors), manque))):
                lier(a["id"], b, "faible")
                ponts[a["id"]] += 1
                ponts[b] += 1

    return sorted(liens.values(), key=lambda l: (rang[l["a"]], rang[l["b"]]))


def complet(agents, reglage):
    """Tout le monde relie a tout le monde par un lien fort : sert au modele v2
    reduit, qui doit retrouver le monde v1 ou chacun voyait tout le campus."""
    return [{"a": x["id"], "b": y["id"], "type": "fort", "poids": reglage["poids_fort"]}
            for i, x in enumerate(agents) for y in agents[i + 1:]]


def voisins(liens):
    """{agent: {voisin: poids}}, dans les deux sens."""
    v = defaultdict(dict)
    for l in liens:
        v[l["a"]][l["b"]] = l["poids"]
        v[l["b"]][l["a"]] = l["poids"]
    return v


def composantes(agents, liens):
    """Nombre de composantes connexes : 1 = tout le monde peut se joindre."""
    v, vus, n = voisins(liens), set(), 0
    for a in agents:
        if a["id"] in vus:
            continue
        n += 1
        pile = [a["id"]]
        while pile:
            x = pile.pop()
            if x not in vus:
                vus.add(x)
                pile.extend(v[x])
    return n


def resume(agents, liens):
    """Ce que reseau.v1 publie a cote des liens, et ce que le rapport cite."""
    n = len(agents) or 1
    forts = sum(l["type"] == "fort" for l in liens)
    faibles = len(liens) - forts
    v = voisins(liens)
    return {"liens": len(liens), "forts": forts, "faibles": faibles,
            "degre_fort_moyen": round(2 * forts / n, 2),
            "degre_faible_moyen": round(2 * faibles / n, 2),
            "isoles": sum(1 for a in agents if not v[a["id"]]),
            "composantes": composantes(agents, liens)}
