"""Conversations privees entre agents LLM (exigence A2), option --conversation N.

Sans cette option, un agent publie et un autre lit : il n'y a jamais de
reponse. Avec elle, un message prive entre deux agents LLM ouvre une
conversation : le destinataire repond, l'auteur repond a son tour, jusqu'a
--repliques repliques en tout (3 par defaut : le message, puis deux
reponses). Chaque replique est un evenement replique.v1, entre dans la
memoire de celui a qui elle s'adresse, et dit ce que le ruban veut dire
pour celui qui parle a ce moment de l'echange.

La croyance de l'agent ne change pas pendant la conversation : elle change
a sa decision suivante, qui lit l'echange dans sa memoire. On garde ainsi
une seule decision par agent et par jour, comme sans conversation, et la
mesure A2 compare le sens avant la conversation et apres la decision.

Au plus N conversations par jour simule, dans l'ordre des messages : chaque
conversation coute (repliques - 1) appels de plus. Un agent a regles ne
converse pas (il n'a pas de langage).
"""
from collections import Counter

from .horloge import MINUTES_PAR_JOUR


class Dialogue:
    def __init__(self, decideurs, max_par_jour, repliques=3):
        self.decideurs = decideurs
        self.max_par_jour = max_par_jour
        self.repliques = repliques
        self.en_attente = []          # (auteur, destinataire, texte, t_sim)
        self.par_jour = Counter()
        self.nombre = 0

    def noter(self, monde, auteur, destinataire, texte, t_sim):
        """Un message prive vient d'etre remis : il ouvrira peut-etre une conversation."""
        if self.max_par_jour <= 0 or self.repliques < 2:
            return
        if "regles" in (monde.agents[auteur]["moteur"], monde.agents[destinataire]["moteur"]):
            return
        self.en_attente.append((auteur, destinataire, texte, t_sim))

    def mener(self, journal, monde, horloge):
        """Tient les conversations en attente, apres les decisions du pas."""
        attente, self.en_attente = self.en_attente, []
        for auteur, destinataire, texte, t_sim in attente:
            jour = t_sim // MINUTES_PAR_JOUR
            if self.par_jour[jour] >= self.max_par_jour:
                continue
            self.par_jour[jour] += 1
            self.nombre += 1
            ident = f"c{self.nombre}"
            echanges = [(monde.agents[auteur]["nom"], texte)]
            parle, ecoute = destinataire, auteur
            for tour in range(2, self.repliques + 1):
                agent, autre = monde.agents[parle], monde.agents[ecoute]
                r = self.decideurs[parle].repondre(agent, autre, echanges, horloge.lisible())
                journal.ecrire("replique.v1", conversation=ident, tour=tour, agent=parle,
                               destinataire=ecoute, texte=r["texte"], categorie=r["categorie"],
                               moteur=agent["moteur"], valide=r["valide"])
                if not r["valide"]:
                    # La conversation s'arrete ; l'incident est compte (A4), a part
                    # des decisions grace au champ conversation.
                    journal.ecrire("incident.v1", agent=parle, nature=r["incident"]["nature"],
                                   details={**r["incident"]["details"], "conversation": ident,
                                            "tour": tour})
                    break
                monde.adresser(parle, autre["nom"], r["texte"], horloge.minutes,
                               horloge.lisible())
                print(f"{horloge.lisible()}   {agent['nom']:>10s} -> {autre['nom']:10s} "
                      f"[{r['categorie']}] {r['texte'][:60]}")
                echanges.append((agent["nom"], r["texte"]))
                parle, ecoute = ecoute, parle
