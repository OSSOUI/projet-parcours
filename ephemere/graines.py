"""Graines separees du modele social v2 (reproductibilite, exigence E2).

Le modele v1 tire tout d'une seule graine : changer le reseau changerait
aussi la population. Ici, une graine de repetition r donne une graine par
flux, et chaque flux a son propre generateur :

  population  traits, affinites, groupes, horaires ;
  reseau      liens et poids ;
  evenements  qui est present a chaque evenement ;
  dynamique   bruit des regles, rencontres au hasard, graine envoyee au LLM ;
  moteurs     quels agents sont LLM : CONSTANTE pour toute l'etude, r n'y
              entre pas, si bien que les memes agents sont LLM a chaque graine.

La derivation passe par SHA-256 et non par hash(), que Python rend aleatoire
d'un processus a l'autre : la meme graine donne le meme monde partout.
"""
import hashlib

FLUX = ("population", "reseau", "evenements", "dynamique")


def deriver(r, flux):
    """Graine entiere du flux pour la repetition r (r ignore pour les moteurs)."""
    if flux != "moteurs" and flux not in FLUX:
        raise ValueError(f"flux inconnu : {flux!r}")
    cle = "moteurs" if flux == "moteurs" else f"{flux}:{r}"
    return int.from_bytes(hashlib.sha256(f"ephemere:{cle}".encode()).digest()[:8], "big")


def graines(r, **autres):
    """Les cinq graines de la repetition r.

    Un flux peut suivre une autre repetition que r, pour changer un seul
    facteur : graines(3, reseau=7) garde la population de r = 3 et prend le
    reseau de r = 7.
    """
    inconnus = set(autres) - set(FLUX)
    if inconnus:
        raise ValueError(f"flux inconnu(s) : {sorted(inconnus)}")
    g = {f: deriver(autres.get(f, r), f) for f in FLUX}
    g["moteurs"] = deriver(None, "moteurs")
    return g
