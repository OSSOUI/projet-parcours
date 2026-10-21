"""Construction de la population du campus (exigences C2, A5, A6).

Le nombre d'agents et la repartition des moteurs se fixent au LANCEMENT,
depuis config/tessaline.json et l'option --agents. Aucune ligne de code
a modifier pour passer de 8 a 60 agents.

Trois moteurs cohabitent dans la MEME simulation :
  - llm_grand : un modele plus gros, pour les agents qui fabriquent du sens
  - llm_petit : un modele plus petit, pour ceux qui suivent ou refusent
  - regles    : aucun appel LLM, une regle a seuil

Ne pas confondre avec la baseline de E1 : la baseline est un run entier
sans aucun LLM, alors qu'ici les agents a regles vivent au milieu des autres.
"""
import json
import random

PRENOMS = [
    "Ines", "Lea", "Karim", "Sofia", "Yanis", "Adam", "Nora", "Theo",
    "Imane", "Mehdi", "Salma", "Rayan", "Hiba", "Omar", "Lina", "Ayoub",
    "Maya", "Zakaria", "Aya", "Ilyas", "Ghita", "Anas", "Douae", "Bilal",
    "Kenza", "Walid", "Hajar", "Reda", "Sara", "Amine", "Nisrine", "Youssef",
    "Chaima", "Hamza", "Meryem", "Soufiane", "Asmae", "Othmane", "Rim", "Jad",
    "Nada", "Marouane", "Siham", "Taha", "Loubna", "Ismail", "Zineb", "Nabil",
    "Oumaima", "Hicham", "Fatima", "Said", "Houda", "Khalil", "Samira", "Driss",
    "Btissam", "Yassine", "Rania", "Soukaina",
]


def _tirer(rng, poids):
    """Tire une cle au hasard selon un dictionnaire {cle: poids}."""
    cles = sorted(poids)
    return rng.choices(cles, weights=[poids[c] for c in cles], k=1)[0]


def _effectifs(n, profils):
    """Repartit n agents entre les profils.

    Les parts seules ne suffisent pas : a 12 agents, 5 % de figures populaires
    arrondit a zero et la mode n'a plus personne pour l'entrainer. Chaque profil
    declare donc un minimum, servi en priorite (clef "minimum" de la config).
    """
    noms = sorted(profils, key=lambda p: -profils[p]["part"])
    minimums = {p: profils[p].get("minimum", 0) for p in noms}
    if sum(minimums.values()) > n:
        raise SystemExit(
            f"{n} agents demandes mais les minimums des profils en exigent "
            f"{sum(minimums.values())}. Augmentez --agents ou baissez les minimums.")
    compte = dict(minimums)
    restants = n - sum(compte.values())
    for p in noms:
        compte[p] += int(restants * profils[p]["part"])
    for i in range(n - sum(compte.values())):
        compte[noms[i % len(noms)]] += 1
    return compte


def construire(chemin_config="config/tessaline.json", n=12, graine=42):
    """Renvoie (agents, config). Deux appels avec la meme graine donnent la meme population."""
    with open(chemin_config, encoding="utf-8") as f:
        config = json.load(f)
    rng = random.Random(graine)
    profils = config["profils"]
    groupes = config["groupes"]
    horaires = config["horaires"]
    personnalites = config.get("personnalites", {})

    if n > len(PRENOMS):
        raise SystemExit(f"{n} agents demandes mais seulement {len(PRENOMS)} prenoms disponibles.")
    prenoms = PRENOMS[:n]

    agents = []
    i = 0
    for profil, nb in sorted(_effectifs(n, profils).items()):
        spec = profils[profil]
        for _ in range(nb):
            # Les pionniers naissent a l'atelier de design : c'est de la que part le ruban.
            groupe = "atelier_design" if profil == "pionnier" else rng.choice(groupes)
            agents.append({
                "id": prenoms[i].lower(),
                "nom": prenoms[i],
                "profil": profil,
                "personnalite": rng.choice(personnalites.get(profil, [""])),
                "groupe": groupe,
                "moteur": _tirer(rng, spec["moteurs"]),
                "cadence_min": spec["cadence_min"],
                # Chaque agent consulte le reseau a son heure : sans ca, le mode
                # asynchrone ne se distingue pas du synchrone.
                "decalage_min": rng.randint(0, horaires["dispersion_min"]),
                "heure_reveil": horaires["reveil_min"],
                "porte": bool(spec.get("porte_au_depart", False)),
                "categorie": "cercle_creatif" if spec.get("porte_au_depart") else "aucun_sens",
                "sens": "",
                "memoire": [],
                "minutes_porte": 0,
                "derniere_decision": 0,   # t_sim de la derniere decision appliquee
                "vu_jusqu_a": 0,          # position atteinte dans le fil du reseau
                "seuil": round(rng.uniform(*spec.get("seuil", [0.15, 0.55])), 3),
            })
            i += 1
    return agents, config


def resume(agents):
    """Comptage par profil et par moteur, a citer dans le rapport."""
    par_profil, par_moteur = {}, {}
    for a in agents:
        par_profil[a["profil"]] = par_profil.get(a["profil"], 0) + 1
        par_moteur[a["moteur"]] = par_moteur.get(a["moteur"], 0) + 1
    return {"total": len(agents), "par_profil": par_profil, "par_moteur": par_moteur}
