"""Pont Kafka vers WebSocket : alimente la scene Godot en direct.

Godot ne parle pas le protocole Kafka. Le pont lit le topic, reconstruit l'etat
du campus, horodate le traitement de chaque evenement (exigences C3 et C7), puis
diffuse a la scene par WebSocket sur ws://localhost:8765.

    python3 pont.py                            # en direct depuis Kafka
    python3 pont.py --depuis-debut             # relit tout le topic
    python3 pont.py --rejeu runs/xxx.jsonl     # sans Kafka ni LLM (filet de securite)

Le mode rejeu est le filet de la soutenance : si un quota tombe pendant la demo,
on rejoue un run enregistre et la scene se comporte exactement pareil.

Il remonte aussi les demandes d'injection de la scene vers le topic des
commandes, ce qui permet a l'observateur de bousculer le monde (exigence D3).
"""
import argparse
import asyncio
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ephemere.bus import TOPIC
from ephemere.campus import Campus

TOPIC_COMMANDES = "ephemere.commandes"


class Pont:
    def __init__(self, campus, serveur_kafka=None):
        self.campus = campus
        self.serveur_kafka = serveur_kafka
        self.clients = set()
        self.boucle = None
        self.producteur_commandes = None

    # ------------------------------------------------------------ sortie
    async def accueil(self, ws):
        self.clients.add(ws)
        print(f"[pont] scene connectee ({len(self.clients)} client(s))")
        try:
            await ws.send(json.dumps(self.campus.instantane(), ensure_ascii=False))
            async for message in ws:
                await self.recevoir(message)
        except Exception:
            pass
        finally:
            self.clients.discard(ws)
            print(f"[pont] scene deconnectee ({len(self.clients)} client(s))")

    async def diffuser(self, evt, cle=None):
        import websockets
        t0 = time.perf_counter()
        self.campus.appliquer(evt, cle)
        charge = json.dumps({"type": "evenement", "evenement": evt,
                             "etat": self.campus.instantane()}, ensure_ascii=False)
        self.campus.latences_ms.append((time.perf_counter() - t0) * 1000)
        if self.clients:
            websockets.broadcast(self.clients, charge)
        if evt.get("schema") == "indicateurs.v1":
            i = self.campus.indicateurs()
            print(f"[pont] {evt.get('t_sim_lisible', ''):10s} adoption "
                  f"{i['taux_adoption']:4.0%}  sens dominant {i['sens_dominant']:16s} "
                  f"{i['part_sens_dominant']:4.0%}")

    def depuis_thread(self, evt, cle=None):
        asyncio.run_coroutine_threadsafe(self.diffuser(evt, cle), self.boucle)

    # ------------------------------------------------------------ entree
    async def recevoir(self, message):
        """Une demande venue de la scene : injection d'un evenement (D3)."""
        try:
            demande = json.loads(message)
        except ValueError:
            return
        if demande.get("type") != "injection":
            return
        commande = {"nature": demande.get("nature", "inconnue"),
                    "details": demande.get("details", {}),
                    "source": "scene_godot"}
        print(f"[pont] injection demandee : {commande['nature']} {commande['details']}")
        if not self.serveur_kafka:
            print("[pont] sans Kafka, l'injection ne peut pas atteindre la simulation")
            return
        if self.producteur_commandes is None:
            from ephemere.bus import connecter
            self.producteur_commandes = connecter(self.serveur_kafka)
        self.producteur_commandes.send(TOPIC_COMMANDES, key="scene",
                                       value=commande)
        self.producteur_commandes.flush(timeout=5)


def lire_kafka(pont, serveur, depuis_debut):
    from kafka import KafkaConsumer
    conso = KafkaConsumer(TOPIC, bootstrap_servers=serveur,
                          auto_offset_reset="earliest" if depuis_debut else "latest",
                          enable_auto_commit=False, group_id=None)
    print(f"[pont] a l'ecoute du topic {TOPIC} sur {serveur}")
    for m in conso:
        cle = m.key.decode("utf-8") if m.key else None
        try:
            evt = json.loads(m.value.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        pont.depuis_thread(evt, cle)


async def rejouer(pont, chemin, vitesse, attendre_scene=True):
    while attendre_scene and not pont.clients:
        print("[pont] en attente de la scene Godot...", end="\r")
        await asyncio.sleep(0.5)
    cle = os.path.basename(chemin).rsplit(".", 1)[0]
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if ligne.strip():
                evt = json.loads(ligne)
                await pont.diffuser(evt, cle)
                await asyncio.sleep(vitesse * (6 if evt.get("schema") == "indicateurs.v1" else 1))
    lat = pont.campus.latences_ms
    if lat:
        print(f"\n[pont] rejeu termine. Traitement : "
              f"{sum(lat)/len(lat):.2f} ms en moyenne, {max(lat):.2f} ms au pire")


async def principal(args):
    import websockets
    campus = Campus()
    pont = Pont(campus, serveur_kafka=None if args.rejeu else args.kafka)
    pont.boucle = asyncio.get_running_loop()
    async with websockets.serve(pont.accueil, "localhost", args.port):
        print(f"[pont] WebSocket ouvert sur ws://localhost:{args.port}")
        if args.rejeu:
            await rejouer(pont, args.rejeu, args.vitesse)
            await asyncio.Future()
        else:
            threading.Thread(target=lire_kafka,
                             args=(pont, args.kafka, args.depuis_debut),
                             daemon=True).start()
            await asyncio.Future()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kafka", default="localhost:9092")
    p.add_argument("--depuis-debut", action="store_true", help="relire tout le topic")
    p.add_argument("--rejeu", help="rejouer un fichier runs/*.jsonl, sans Kafka")
    p.add_argument("--vitesse", type=float, default=0.12,
                   help="secondes reelles entre deux evenements rejoues")
    p.add_argument("--port", type=int, default=8765)
    try:
        asyncio.run(principal(p.parse_args()))
    except KeyboardInterrupt:
        print("\n[pont] arrete")
