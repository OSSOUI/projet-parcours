"""Injection d'evenements en direct, depuis la scene (exigence D3).

La scene Godot envoie sa demande au pont, qui la publie dans le topic
ephemere.commandes. La simulation lit ce topic SANS BLOQUER entre deux pas de
temps : si rien n'est arrive, elle continue immediatement.

Les injections disponibles reprennent les leviers d'experimentation de la fiche
du sujet. Chacune agit sur le monde, pas sur les agents : on bouscule la
situation, on ne force la decision de personne.
"""
TOPIC_COMMANDES = "ephemere.commandes"


class Ecoute:
    """Lecteur non bloquant du topic des commandes."""

    def __init__(self, serveurs, topic=TOPIC_COMMANDES):
        from kafka import KafkaConsumer
        self.conso = KafkaConsumer(
            topic, bootstrap_servers=serveurs, auto_offset_reset="latest",
            enable_auto_commit=False, group_id=None, consumer_timeout_ms=1)

    def recuperer(self):
        """Renvoie les commandes arrivees depuis le dernier appel."""
        import json
        recues = []
        for lots in self.conso.poll(timeout_ms=10, max_records=20).values():
            for m in lots:
                try:
                    recues.append(json.loads(m.value.decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    continue
        return recues


def appliquer(commande, monde, horloge):
    """Applique une injection au monde. Renvoie (nature, details_effectifs)."""
    nature = commande.get("nature", "")
    details = dict(commande.get("details") or {})
    t = horloge.minutes

    if nature == "message":
        # Un message anonyme apparait sur le reseau interne.
        texte = details.get("texte") or "il parait que le ruban ne veut plus rien dire"
        monde.fil.append({"agent": "_injection", "nom_auteur": details.get("auteur", "Anonyme"),
                          "texte": texte, "t_sim": t, "portee": "campus"})
        details["texte"] = texte

    elif nature == "relais_massif":
        # Le levier "vitesse d'exposition" de la fiche : tout le campus voit
        # le ruban d'un coup, sans qu'aucune decision ne soit forcee.
        for a in monde.agents.values():
            a["vu_jusqu_a"] = 0        # tout le fil redevient a lire
        monde.fil.append({"agent": "_injection", "nom_auteur": "Le journal etudiant",
                          "texte": details.get("texte")
                          or "Le ruban au poignet, nouveau signe de ralliement du campus ?",
                          "t_sim": t, "portee": "campus"})
        details["agents_touches"] = len(monde.agents)

    elif nature == "tendance_rivale":
        # Le levier "tendance rivale a mi-parcours".
        monde.fil.append({"agent": "_injection", "nom_auteur": "Atelier serigraphie",
                          "texte": details.get("texte")
                          or "nouveaux badges emailles a l'atelier, serie limitee",
                          "t_sim": t, "portee": "campus"})

    elif nature == "cloisonnement":
        # Les groupes cessent de se voir : seul le groupe compte desormais.
        monde.poids_groupe, monde.poids_campus = 1.0, 0.0
        details["perception"] = "groupe seul"

    else:
        return nature, {"ignoree": True, **details}
    return nature, details
