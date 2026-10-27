"""Population du modele social v2 : des traits, plus des comportements ecrits.

Le profil ne decide plus de ce que fait l'agent. Il fixe deux choses :
  - la distribution de ses traits (exigence A5 : la taille du modele suit le
    profil, donc le profil reste) ;
  - son moteur, attribue par quota et avec une graine constante, si bien que
    les memes agents sont LLM a chaque repetition.

Chaque tirage vient de son propre flux (ephemere/graines.py) : changer la
graine du reseau ou des evenements ne touche pas la population.

    python3 -m ephemere.population_v2 --graine 0
"""
import json
import os
import random

from .population import PRENOMS, _effectifs

TRAITS = ("appartenance", "distinction", "nouveaute")


def charger(chemin_config):
    """Lit une config v2 ; les sections absentes viennent de sa config de base."""
    with open(chemin_config, encoding="utf-8") as f:
        config = json.load(f)
    if config.get("base"):
        with open(os.path.join(os.path.dirname(chemin_config), config["base"]),
                  encoding="utf-8") as f:
            base = json.load(f)
        # Les personnalites v1 decrivent un comportement ("tu laisses tomber
        # tout ce qui devient banal") : elles ne passent pas en v2.
        base.pop("personnalites", None)
        config = {**base, **config}
    return config


def _quotas(nb, parts):
    """Repartit nb agents entre moteurs au plus fort reste, sans hasard."""
    exacts = {m: nb * p / sum(parts.values()) for m, p in parts.items()}
    compte = {m: int(v) for m, v in exacts.items()}
    restes = sorted(exacts, key=lambda m: (-(exacts[m] - compte[m]), m))
    for m in restes[:nb - sum(compte.values())]:
        compte[m] += 1
    return compte


def _beta(rng, moyenne, concentration):
    return rng.betavariate(moyenne * concentration, (1 - moyenne) * concentration)


def _borne(x, bas=-1.0, haut=1.0):
    return max(bas, min(haut, x))


def construire(chemin_config, n, graines):
    """Renvoie (agents, config). graines : le dictionnaire de graines.graines(r)."""
    config = charger(chemin_config)
    profils, groupes, horaires = config["profils"], config["groupes"], config["horaires"]
    reglage = config["traits"]
    k = reglage["concentration"]
    aff = reglage["affinites"]
    rng_pop = random.Random(graines["population"])
    rng_mot = random.Random(graines["moteurs"])

    # Au-dela de 60 agents (tailles 50 et 100 du plan), les prenoms reviennent
    # avec un numero : Ines, ..., Soukaina, Ines 2, ...
    noms = [p if k == 0 else f"{p} {k + 1}"
            for k in range(-(-n // len(PRENOMS))) for p in PRENOMS][:n]

    agents, i = [], 0
    for profil, nb in sorted(_effectifs(n, profils).items()):
        spec = profils[profil]
        # Le moteur de chaque place du profil est fixe une fois pour toutes :
        # ni r ni les traits tires n'y entrent.
        moteurs = [m for m, c in sorted(_quotas(nb, spec["moteurs"]).items()) for _ in range(c)]
        rng_mot.shuffle(moteurs)
        a_aff = {**aff, **spec.get("affinites", {})}
        for j in range(nb):
            groupe = spec.get("groupe") or rng_pop.choice(groupes)
            traits = {t: round(_beta(rng_pop, spec[t], k), 3) for t in TRAITS}
            seuil = round(rng_pop.uniform(*spec["seuil"]), 3)
            affinites = {
                g: round(_borne(rng_pop.gauss(a_aff["propre_groupe"] if g == groupe else
                                              a_aff["autres"], a_aff["dispersion"])), 3)
                for g in groupes}
            porte = bool(spec.get("porte_au_depart", False))
            agents.append({
                "id": noms[i].lower().replace(" ", "_"),
                "nom": noms[i],
                "profil": profil,
                "personnalite": "",
                "groupe": groupe,
                "moteur": moteurs[j],
                "traits": {**traits, "seuil": seuil, "affinites": affinites},
                # seuil reste aussi a la racine : monde.py et les regles v1 l'y lisent.
                "seuil": seuil,
                "cadence_min": config["cadence_min"],
                "decalage_min": rng_pop.randint(0, horaires["dispersion_min"]),
                "heure_reveil": horaires["reveil_min"],
                "porte": porte,
                "categorie": "cercle_creatif" if porte else "aucun_sens",
                "sens": "",
                "memoire": [],
                "minutes_porte": 0,
                "derniere_decision": 0,
                "vu_jusqu_a": 0,
            })
            i += 1
    return agents, config


def decrire(agents):
    """Ce que population.v2 publie de chaque agent : identite, moteur, traits."""
    return [{"id": a["id"], "nom": a["nom"], "profil": a["profil"], "groupe": a["groupe"],
             "moteur": a["moteur"], "porte": a["porte"], "traits": a["traits"]}
            for a in agents]


if __name__ == "__main__":
    import argparse
    from .graines import graines as deriver_graines
    from .population import resume

    p = argparse.ArgumentParser(description="Affiche la population v2 d'une repetition.")
    p.add_argument("--graine", type=int, default=0, help="repetition r")
    p.add_argument("--agents", type=int, default=20)
    p.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "config", "tessaline_v2.json"))
    args = p.parse_args()
    agents, _ = construire(args.config, args.agents, deriver_graines(args.graine))
    print(f"{'agent':10s} {'profil':17s} {'groupe':15s} {'moteur':10s} appart distin nouv  seuil")
    for a in agents:
        t = a["traits"]
        print(f"{a['id']:10s} {a['profil']:17s} {a['groupe']:15s} {a['moteur']:10s} "
              f"{t['appartenance']:6.2f} {t['distinction']:6.2f} {t['nouveaute']:5.2f} {t['seuil']:6.2f}")
    print(resume(agents))
