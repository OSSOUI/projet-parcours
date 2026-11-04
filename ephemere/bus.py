"""Publication des evenements dans Kafka (exigence C1).

Granularite choisie : UN evenement Kafka par evenement metier, exactement
les memes que ceux du fichier de run. Pas d'agregation, pas de lot. La raison
est l'exigence F6 : tout indicateur affiche doit pouvoir etre remonte jusqu'aux
evenements bruts qui l'ont produit, donc les evenements bruts doivent circuler.

La cle du message est le nom du run. Tous les evenements d'un meme run partent
ainsi sur la meme partition, et arrivent dans l'ordre ou ils ont ete produits.
Sans cela, une decision pourrait etre traitee avant la publication qui l'a
provoquee, et le pont reconstruirait un monde incoherent.

Un envoi Kafka est asynchrone : send() rend la main avant que le broker ait
repondu. Un echec a ce moment-la ne leve rien. Chaque envoi recoit donc un
rappel, et le bilan distingue envoyes, confirmes par le broker et echoues :
une perte n'est jamais silencieuse. acks="all" attend l'ecriture effective ;
une seule requete en vol par connexion garde l'ordre meme quand le client
renvoie un message apres une erreur passagere. Un renvoi peut en revanche
dupliquer un message : le consommateur les reconnait a (run, seq).
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
            acks="all",
            retries=5,
            max_in_flight_requests_per_connection=1,
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
        self.publies = 0      # remis au client Kafka
        self.confirmes = 0    # ecrits par le broker
        self.perdus = 0       # refuses tout de suite ou en echec apres coup
        self.seq_perdus = []  # seq des evenements perdus, pour le rapport C1
        self.refus_immediats = 0

    def publier(self, evt):
        seq = evt.get("seq")
        try:
            futur = self.producteur.send(self.topic, key=self.nom_run, value=evt)
            self.publies += 1
        except Exception as e:
            self.refus_immediats += 1
            self._perte(seq, e)
            return
        futur.add_callback(self._confirme)
        futur.add_errback(lambda e: self._perte(seq, e))

    def _confirme(self, _metadonnees):
        self.confirmes += 1

    def _perte(self, seq, erreur):
        self.perdus += 1
        self.seq_perdus.append(seq)
        if self.perdus == 1:
            print(f"  [Kafka : publication impossible ({erreur}), le fichier continue]")

    def bilan(self):
        return {"topic": self.topic, "cle": self.nom_run, "publies": self.publies,
                "confirmes": self.confirmes, "perdus": self.perdus,
                # Envoyes sans reponse du broker a la fermeture : ni confirmes
                # ni declares perdus. Ils doivent valoir 0 pour un run sain.
                "sans_reponse": (self.publies - self.confirmes
                                 - (self.perdus - self.refus_immediats)),
                "seq_perdus": self.seq_perdus[:50]}

    def fermer(self):
        try:
            self.producteur.flush(timeout=10)
            self.producteur.close(timeout=5)
        except Exception as e:
            print(f"  [Kafka : envoi final incomplet ({e})]")
        print(f"Kafka : {self.publies} evenements envoyes, {self.confirmes} confirmes, "
              f"{self.perdus} perdus (topic {self.topic}, cle {self.nom_run})")
        return self.bilan()
