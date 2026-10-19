"""Publication des evenements dans Kafka (exigence C1).

Granularite choisie : UN evenement Kafka par evenement metier, exactement
les memes que ceux du fichier de run. Pas d'agregation, pas de lot. La raison
est l'exigence F6 : tout indicateur affiche doit pouvoir etre remonte jusqu'aux
evenements bruts qui l'ont produit, donc les evenements bruts doivent circuler.

La cle du message est le nom du run. Tous les evenements d'un meme run partent
ainsi sur la meme partition, et arrivent dans l'ordre ou ils ont ete produits.
Sans cela, une decision pourrait etre traitee avant la publication qui l'a
provoquee, et le pont reconstruirait un monde incoherent.
"""
import json

TOPIC = "ephemere.evenements"


def connecter(serveurs, timeout_ms=5000):
    """Cree le producteur, ou arrete le programme avec un message clair.

    On echoue AVANT le premier appel LLM : un run interrompu apres cinquante
    appels pour cause de Kafka absent, c'est du quota gratuit jete.
    """
    try:
        from kafka import KafkaProducer
    except ImportError:
        raise SystemExit("Module kafka absent. Lancez : pip install -r requirements.txt")
    try:
        return KafkaProducer(
            bootstrap_servers=serveurs,
            key_serializer=lambda k: k.encode("utf-8"),
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            api_version_auto_timeout_ms=timeout_ms,
            max_block_ms=timeout_ms,
        )
    except Exception as e:
        raise SystemExit(f"Kafka injoignable sur {serveurs} ({e}).\n"
                         "Demarrez-le avec : docker compose up -d")


class Bus:
    """Enveloppe du producteur. Si Kafka tombe en cours de run, le fichier continue."""

    def __init__(self, serveurs, topic=TOPIC, nom_run=""):
        self.topic = topic
        self.nom_run = nom_run
        self.producteur = connecter(serveurs)
        self.publies = 0
        self.perdus = 0

    def publier(self, evt):
        try:
            self.producteur.send(self.topic, key=self.nom_run, value=evt)
            self.publies += 1
        except Exception as e:
            self.perdus += 1
            if self.perdus == 1:
                print(f"  [Kafka : publication impossible ({e}), le fichier continue]")

    def fermer(self):
        try:
            self.producteur.flush(timeout=10)
            self.producteur.close(timeout=5)
        except Exception as e:
            print(f"  [Kafka : envoi final incomplet ({e})]")
        if self.perdus:
            print(f"Kafka : {self.publies} evenements publies, {self.perdus} perdus")
        else:
            print(f"Kafka : {self.publies} evenements publies "
                  f"(topic {self.topic}, cle {self.nom_run})")
