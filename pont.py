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

En rejeu, la scene pilote la lecture : pause, reprise, et saut a un jour. Pour
sauter, le pont reconstruit l'etat depuis le debut du fichier jusqu'a ce jour :
l'etat ne vient toujours que des evenements, jamais d'un calcul a part.
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
from ephemere.campus import Campus, resumer_delais
from ephemere.horloge import MINUTES_PAR_JOUR

RACINE = os.path.dirname(os.path.abspath(__file__))

TOPIC_COMMANDES = "ephemere.commandes"


class Pont:
    def __init__(self, campus, serveur_kafka=None):
        self.campus = campus
        self.serveur_kafka = serveur_kafka
        self.clients = set()
        self.boucle = None
        self.producteur_commandes = None
        self.mesures = None       # runs/<run>.traitement.jsonl, exigence C7
        self.run_mesure = None
        self.rejeu = None         # en rejeu : evenements, position, pause

    # ------------------------------------------------------------ sortie
    async def accueil(self, ws):
        self.clients.add(ws)
        print(f"[pont] scene connectee ({len(self.clients)} client(s))")
        try:
            await ws.send(json.dumps(self.etat(), ensure_ascii=False))
            async for message in ws:
                await self.recevoir(message, ws)
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
                             "etat": self.etat()}, ensure_ascii=False)
        self.campus.latences_ms.append((time.perf_counter() - t0) * 1000)
        self.noter_delai(evt)
        if self.clients:
            websockets.broadcast(self.clients, charge)
        if evt.get("schema") == "indicateurs.v1":
            i = self.campus.indicateurs()
            print(f"[pont] {evt.get('t_sim_lisible', ''):10s} adoption "
                  f"{i['taux_adoption']:4.0%}  sens dominant {i['sens_dominant']:16s} "
                  f"{i['part_sens_dominant']:4.0%}")

    def etat(self):
        """L'instantane du campus, plus la position de lecture en rejeu."""
        etat = self.campus.instantane()
        if self.rejeu:
            etat["rejeu"] = {"jour": self.campus.t_sim // MINUTES_PAR_JOUR,
                             "jours": self.rejeu["jours"], "pause": self.rejeu["pause"]}
        return etat

    async def positionner(self, jour):
        """Saut a la fin d'un jour : l'etat est reconstruit depuis le debut."""
        import websockets
        r = self.rejeu
        jour = max(0, min(int(jour), r["jours"]))
        limite = jour * MINUTES_PAR_JOUR
        self.campus = Campus(en_direct=False)
        i = 0
        while i < len(r["evenements"]) and r["evenements"][i].get("t_sim", 0) <= limite:
            self.campus.appliquer(dict(r["evenements"][i]), r["cle"])
            i += 1
        r["i"] = i
        if self.clients:
            websockets.broadcast(self.clients, json.dumps(self.etat(), ensure_ascii=False))

    def noter_delai(self, evt):
        """Enregistre le delai emission -> traitement de chaque evenement (C7).

        Un fichier par run, a cote du run lui-meme : la mesure survit au pont
        et se compare au journal du producteur sans rien recalculer.
        """
        if evt.get("delai_ms") is None:
            return
        if self.campus.run != self.run_mesure:
            self.fermer_mesures()
            self.run_mesure = self.campus.run
            chemin = os.path.join(RACINE, "runs", f"{self.run_mesure}.traitement.jsonl")
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            self.mesures = open(chemin, "a", encoding="utf-8")
            print(f"[pont] delais de traitement enregistres dans {chemin}")
        self.mesures.write(json.dumps({
            "schema": evt.get("schema"), "t_sim": evt.get("t_sim"),
            "t_emission": evt.get("t_emission"), "t_traitement": evt["t_traitement"],
            "delai_ms": evt["delai_ms"]}, ensure_ascii=False) + "\n")
        self.mesures.flush()
        if evt.get("schema") == "bilan.v1":
            d = resumer_delais(self.campus.delais_ms)
            print(f"[pont] fin du run {self.run_mesure} : delai emission -> traitement "
                  f"{d['moyen']} ms en moyenne, mediane {d['median']}, "
                  f"p95 {d['p95']}, pire {d['max']} ms (n={d['n']})")

    def fermer_mesures(self):
        if self.mesures:
            self.mesures.close()
            self.mesures = None

    def depuis_thread(self, evt, cle=None):
        asyncio.run_coroutine_threadsafe(self.diffuser(evt, cle), self.boucle)

    # ------------------------------------------------------------ entree
    async def accuser(self, ws, nature, ok, texte):
        """Dit a la scene ce qu'il est advenu de sa demande, pour qu'elle l'affiche."""
        try:
            await ws.send(json.dumps({"type": "accuse", "nature": nature, "ok": ok,
                                      "texte": texte}, ensure_ascii=False))
        except Exception:
            pass

    async def recevoir(self, message, ws=None):
        """Une demande venue de la scene : injection d'un evenement (D3)."""
        try:
            demande = json.loads(message)
        except ValueError:
            return
        if demande.get("type") == "rejeu" and self.rejeu:
            action = demande.get("action")
            if action == "pause":
                self.rejeu["pause"] = True
            elif action == "lecture":
                self.rejeu["pause"] = False
            elif action == "aller_a":
                self.rejeu["pause"] = True
                await self.positionner(demande.get("jour", 0))
                return
            await self.accuser(ws, "rejeu", True, "en pause" if self.rejeu["pause"] else "lecture")
            return
        if demande.get("type") != "injection":
            return
        commande = {"nature": demande.get("nature", "inconnue"),
                    "details": demande.get("details", {}),
                    "source": "scene_godot"}
        print(f"[pont] injection demandee : {commande['nature']} {commande['details']}")
        nature = commande["nature"]
        if not self.serveur_kafka:
            print("[pont] sans Kafka, l'injection ne peut pas atteindre la simulation")
            await self.accuser(ws, nature, False, "rejeu : un run enregistre ne se bouscule pas")
            return
        if self.campus.modele_social == "v2":
            # Les evenements du modele v2 arrivent a l'etape 7 de la migration.
            print("[pont] injection ignoree : le modele v2 ne lit pas encore les commandes")
            await self.accuser(ws, nature, False, "modele v2 : injections prevues a l'etape 7")
            return
        try:
            if self.producteur_commandes is None:
                from ephemere.bus import connecter
                self.producteur_commandes = connecter(self.serveur_kafka)
            self.producteur_commandes.send(TOPIC_COMMANDES, key="scene",
                                           value=commande)
            self.producteur_commandes.flush(timeout=5)
        except Exception as e:
            print(f"[pont] injection non publiee : {e}")
            await self.accuser(ws, nature, False, "Kafka injoignable")
            return
        await self.accuser(ws, nature, True, f"envoyee a {self.campus.t_sim_lisible}")


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
        evenements = [json.loads(l) for l in f if l.strip()]
    r = pont.rejeu = {"cle": cle, "evenements": evenements, "i": 0, "pause": False,
                      "jours": max(e.get("t_sim", 0) for e in evenements) // MINUTES_PAR_JOUR}
    fini = False
    while True:
        if r["pause"] or r["i"] >= len(evenements):
            if r["i"] >= len(evenements) and not fini:
                fini = True
                lat = pont.campus.latences_ms
                if lat:
                    print(f"\n[pont] rejeu termine. Traitement : "
                          f"{sum(lat)/len(lat):.2f} ms en moyenne, {max(lat):.2f} ms au pire")
            await asyncio.sleep(0.05)
            continue
        fini = False
        evt = dict(evenements[r["i"]])
        r["i"] += 1
        await pont.diffuser(evt, cle)
        await asyncio.sleep(vitesse * (6 if evt.get("schema") == "indicateurs.v1" else 1))


async def principal(args):
    import websockets
    campus = Campus(en_direct=not args.rejeu)
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
