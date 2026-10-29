"""Un run du modele social v2 : construction du monde et boucle synchrone.

Separe de simuler.py pour que les tests et le calibrage (etape 6) fassent
tourner des runs entiers en memoire, sans fichier ni sous-processus. Le
journal n'est qu'un objet qui a une methode ecrire(schema, **corps).

Un jour simule :
  1. chaque agent observe (monde.observer) et range ce qu'il a vu ;
  2. chaque agent decide sur l'etat de la veille ;
  3. toutes les decisions sont appliquees ensemble, puis les paroles partent.
Les messages d'un jour ne sont donc lus que le lendemain.
"""
import copy

from . import population_v2, regles_v2, reseau
from .graines import graines
from .horloge import MINUTES_PAR_JOUR
from .monde_v2 import MondeV2


def regler(config, reglages):
    """Applique des surcharges "cle.sous_cle=valeur" sur config["decision"] (copie)."""
    config = copy.deepcopy(config)
    for cle, valeur in (reglages or {}).items():
        noeud, *chemin = cle.split(".")
        cible, parties = config["decision"], [noeud] + chemin
        for p in parties[:-1]:
            cible = cible[p]
        if parties[-1] not in cible:
            raise KeyError(f"reglage inconnu : {cle}")
        cible[parties[-1]] = valeur
    return config


def construire(chemin_config, n, r, cloisonne=False, canal_public=True, complet=False,
               reglages=None, agregat_v1=False, **flux):
    """Renvoie (monde, config, graines, liens) pour la repetition r."""
    g = graines(r, **flux)
    agents, config = population_v2.construire(chemin_config, n, g)
    config = regler(config, reglages)
    observation = dict(config["observation"])
    if complet:
        liens = reseau.complet(agents, config["reseau"])
        observation["croises"] = [0, 0]
    else:
        liens = reseau.construire(agents, config["reseau"], g["reseau"], cloisonne=cloisonne)
    monde = MondeV2(agents, liens, observation, g["dynamique"],
                    cloisonne=cloisonne, canal_public=canal_public, agregat_v1=agregat_v1)
    for a in agents:
        regles_v2.initialiser(a, config["decision"])
    return monde, config, g, liens


def relever(monde, journal, horloge, afficher=None):
    ind = monde.indicateurs()
    monde.noter(horloge.minutes, ind)
    journal.ecrire("indicateurs.v1", **ind)
    if afficher:
        afficher(horloge, ind)
    return ind


def tourner(monde, config, decideurs, journal, horloge, jours, afficher=None):
    """Boucle synchrone v2, un pas par jour simule."""
    reglage = config["decision"]
    relever(monde, journal, horloge, afficher)
    while horloge.minutes < jours * MINUTES_PAR_JOUR:
        horloge.aller_a(horloge.minutes + MINUTES_PAR_JOUR)
        t = horloge.minutes
        decisions = []
        for agent in monde.agents.values():
            vu = monde.observer(agent, t)
            regles_v2.percevoir(agent, vu, t, reglage)
            journal.ecrire("perception.v2", agent=agent["id"], moteur=agent["moteur"],
                           **vu, souvenirs=[], documents=[])
            decisions.append((agent, decideurs[agent["id"]].decider(agent, monde, vu, t)))
        # Simultaneite : on n'applique qu'apres avoir interroge tout le monde.
        for agent, d in decisions:
            journal.ecrire("decision.v2", agent=agent["id"], porte=d["porte"],
                           categorie=d["categorie"], sens=d["sens"], sens_percu=d["sens_percu"],
                           confiance=d["confiance"], sources=d["sources"], raison=d["raison"],
                           moteur=agent["moteur"], valide=d["valide"], termes=d.get("termes"))
            regles_v2.appliquer(agent, d, reglage)
        for agent, d in decisions:
            parler(monde, journal, horloge, agent, d)
        relever(monde, journal, horloge, afficher)


def parler(monde, journal, horloge, agent, d):
    texte = d.get("publication") or ""
    if not texte:
        return
    cat = d.get("categorie_message")
    remis = (monde.adresser(agent["id"], d["destinataire"], texte, horloge.minutes,
                            horloge.lisible(), categorie=cat)
             if d.get("destinataire") else None)
    if remis:
        cible, mid = remis
        journal.ecrire("publication.v2", agent=agent["id"], id=mid, texte=texte,
                       portee="personne", destinataire=cible, categorie=cat)
        return
    pid = monde.publier(agent["id"], texte, horloge.minutes, categorie=cat)
    if pid:
        journal.ecrire("publication.v2", agent=agent["id"], id=pid, texte=texte,
                       portee="campus", destinataire=None, categorie=cat)


class JournalMemoire:
    """Journal minimal pour les tests et le calibrage : garde les evenements."""

    def __init__(self):
        self.evenements = []

    def ecrire(self, schema, **corps):
        self.evenements.append({"schema": schema, **corps})

    def courbe(self):
        return [e["taux_adoption"] for e in self.evenements if e["schema"] == "indicateurs.v1"]
