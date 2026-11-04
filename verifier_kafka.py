"""Validation de la chaine Kafka (exigence C1), sur un run lance pour l'occasion.

Un consommateur ecoute le topic AVANT que simuler.py ne demarre, recoit le run
en direct, puis le rapport confronte trois sources :

  le fichier du run       runs/<run>.jsonl, la reference (journal.lire)
  ce qu'a recu le topic   chaque message, avec son offset et l'heure de reception
  le bilan du producteur  runs/<run>.kafka.json (envoyes, confirmes, perdus)

et mesure : pertes, doublons, ordre, contenu identique au fichier, latence
emission -> reception, etat du campus reconstruit depuis Kafka egal a celui
reconstruit depuis le fichier (rejeu), et resultat d'un consommateur arrete
puis relance en cours de run (--coupure).

    .venv/bin/python verifier_kafka.py --run c1_regles -- --tout-regles --agents 20 --jours 25
    .venv/bin/python verifier_kafka.py --run c1_llm --coupure 120 -- --agents 20 --jours 3

Les runs de validation s'appellent c1_* : ils ne se confondent pas avec la
serie de reference (exp_reference_*). Rapport : resultats/c1_<run>.json.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime

from ephemere import journal
from ephemere.bus import TOPIC
from ephemere.campus import Campus

RACINE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(RACINE, "runs")


class Ecoute(threading.Thread):
    """Consommateur d'un groupe dedie, commit manuel tous les `lot` messages.

    Avec coupure=K, il s'arrete apres K messages du run SANS committer les
    derniers, puis un nouveau consommateur du meme groupe reprend : Kafka
    relivre ce qui n'etait pas committe. C'est le cas reel d'un consommateur
    qui tombe ; on verifie que les doublons sont reconnus et l'etat intact.

    Les commits nomment l'offset du dernier message TRAITE. Un commit() sans
    argument enregistre la position du client, qui a deja recupere tout un
    lot : un run a regles tient en un lot, et le commit sautait a sa fin.
    """

    def __init__(self, serveur, run, coupure=None, lot=50, silence_s=120):
        super().__init__(daemon=True)
        self.serveur, self.nom_run, self.coupure, self.lot = serveur, run, coupure, lot
        self.silence_s = silence_s
        self.groupe = f"verif-{run}-{int(time.time())}"
        self.recus = []          # (offset, recu_iso, evenement)
        self.reprises = 0
        self.pret = threading.Event()
        self.fini = False

    def _consommateur(self):
        from kafka import KafkaConsumer
        return KafkaConsumer(TOPIC, bootstrap_servers=self.serveur, group_id=self.groupe,
                             auto_offset_reset="latest" if not self.reprises else "earliest",
                             enable_auto_commit=False, consumer_timeout_ms=1000)

    def _committer(self, conso, offset):
        from kafka import TopicPartition
        from kafka.structs import OffsetAndMetadata
        if offset is not None:
            conso.commit({TopicPartition(TOPIC, 0): OffsetAndMetadata(offset + 1, "", -1)})

    def _attacher(self, conso):
        # Premier consommateur : attend la partition et fixe la position de
        # depart AVANT le lancement du run (offset "latest" a cet instant ; le
        # poll ne peut rien rendre, le run n'a pas commence). A la reprise, pas
        # de poll : il rendrait des messages que la boucle ne verrait jamais.
        if not self.reprises:
            while not conso.assignment():
                conso.poll(timeout_ms=200)
            p = next(iter(conso.assignment()))
            self._committer(conso, conso.position(p) - 1)
        self.pret.set()

    def run(self):
        conso = self._consommateur()
        self._attacher(conso)
        dernier = time.time()
        vus_depuis_commit, traite = 0, None
        while not self.fini:
            for m in conso:
                traite = m.offset
                cle = m.key.decode("utf-8") if m.key else None
                if cle != self.nom_run:
                    continue
                evt = json.loads(m.value.decode("utf-8"))
                self.recus.append((m.offset, datetime.now().isoformat(timespec="milliseconds"),
                                   evt))
                dernier = time.time()
                vus_depuis_commit += 1
                if vus_depuis_commit >= self.lot:
                    self._committer(conso, traite)
                    vus_depuis_commit = 0
                if self.coupure and not self.reprises and len(self.recus) == self.coupure:
                    conso.close(autocommit=False)
                    self.reprises = 1
                    conso = self._consommateur()
                    self._attacher(conso)
                    break
                if evt.get("schema") == "bilan.v1":
                    self.fini = True
                    break
            if time.time() - dernier > self.silence_s:
                break
        self._committer(conso, traite)
        conso.close(autocommit=False)


def _ms(a, b):
    return (datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds() * 1000


def _centile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * q))] if v else None


def _etat(evenements, cle):
    """L'etat que le pont montrerait, sans les horloges de traitement."""
    c = Campus(en_direct=False)
    for e in evenements:
        if not c.deja_vu(e, cle):
            c.appliquer(dict(e), cle)
    agents = {a: (x["porte"], x["categorie"], x["sens"]) for a, x in c.agents.items()}
    hist = [{k: h.get(k) for k in ("t_sim", "taux_adoption", "repartition_sens")}
            for h in c.historique]
    return {"agents": agents, "historique": hist, "fil": len(c.fil),
            "incidents": dict(c.incidents)}, c


def rapporter(run, ecoute, duree_run_s):
    chemin = os.path.join(RUNS, f"{run}.jsonl")
    fichier = journal.lire(chemin)
    attendus = {e["seq"]: e for e in fichier}
    recus = ecoute.recus
    seqs = [e["seq"] for _, _, e in recus]
    uniques = set(seqs)
    pertes = sorted(set(attendus) - uniques)
    inconnus = sorted(uniques - set(attendus))
    doublons = len(seqs) - len(uniques)
    # Ordre : au premier passage de chaque seq, les seq doivent croitre avec l'offset.
    vus, premiers = set(), []
    for off, _, e in sorted(recus, key=lambda r: r[0]):
        if e["seq"] not in vus:
            vus.add(e["seq"])
            premiers.append(e["seq"])
    desordres = sum(1 for a, b in zip(premiers, premiers[1:]) if b < a)
    differents = [e["seq"] for _, _, e in recus
                  if e["seq"] in attendus and e != attendus[e["seq"]]]
    # Latence a la premiere reception : une relivraison apres la coupure mesure
    # la reprise du consommateur, pas le trajet d'un evenement.
    latences, deja = [], set()
    for _, recu, e in recus:
        if e["seq"] not in deja:
            deja.add(e["seq"])
            latences.append(_ms(recu, e["t_emission"]))
    etat_fichier, _ = _etat(fichier, run)
    flux = [e for _, _, e in recus]   # doublons compris, dans l'ordre de reception
    etat_kafka, campus_kafka = _etat(flux, run)
    producteur = {}
    p = os.path.join(RUNS, f"{run}.kafka.json")
    if os.path.exists(p):
        producteur = json.load(open(p, encoding="utf-8"))
    rejets = os.path.join(RUNS, f"{run}.rejets.jsonl")
    rapport = {
        "run": run, "date": datetime.now().isoformat(timespec="seconds"),
        "duree_run_s": round(duree_run_s, 1),
        "evenements_fichier": len(fichier),
        "rejets_contrat": (sum(1 for _ in open(rejets, encoding="utf-8"))
                           if os.path.exists(rejets) else 0),
        "producteur": producteur,
        "messages_recus": len(recus), "seq_uniques_recus": len(uniques),
        "pertes": len(pertes), "seq_perdus": pertes[:50],
        "pertes_annoncees_par_le_producteur": producteur.get("perdus"),
        "inconnus": len(inconnus), "doublons": doublons, "desordres": desordres,
        "contenu_different": len(differents),
        "coupure_consommateur": ({"apres": ecoute.coupure, "reprises": ecoute.reprises,
                                  "doublons_ecartes_par_le_campus": campus_kafka.doublons}
                                 if ecoute.coupure else None),
        "latence_ms": {"n": len(latences),
                       "mediane": round(statistics.median(latences), 1) if latences else None,
                       "p95": round(_centile(latences, 0.95), 1) if latences else None,
                       "max": round(max(latences), 1) if latences else None},
        "etat_kafka_egal_etat_fichier": etat_kafka == etat_fichier,
    }
    # Panne du broker : des pertes sont attendues, mais aucune ne doit etre
    # silencieuse. Chaque evenement absent du topic doit figurer dans le bilan
    # du producteur, comme perdu ou comme reste sans reponse a la fermeture.
    annoncees = (producteur.get("perdus") or 0) + (producteur.get("sans_reponse") or 0)
    rapport["pertes_silencieuses"] = max(0, len(pertes) - annoncees)
    rapport["c1_ok"] = (not pertes and not inconnus and not desordres and not differents
                        and rapport["etat_kafka_egal_etat_fichier"]
                        and producteur.get("perdus") == 0
                        and producteur.get("sans_reponse") == 0)
    return rapport


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True, help="nom du run, commence par c1_")
    p.add_argument("--kafka", default="localhost:9092")
    p.add_argument("--coupure", type=int, help="arreter le consommateur apres N messages")
    p.add_argument("options", nargs=argparse.REMAINDER, help="options de simuler.py, apres --")
    args = p.parse_args()
    if not args.run.startswith("c1_"):
        raise SystemExit("Un run de validation C1 s'appelle c1_* (jamais exp_*).")
    options = [o for o in args.options if o != "--"]
    ecoute = Ecoute(args.kafka, args.run, args.coupure)
    ecoute.start()
    if not ecoute.pret.wait(30):
        raise SystemExit("Le consommateur n'a pas obtenu sa partition en 30 s.")
    t0 = time.time()
    code = subprocess.run([sys.executable, os.path.join(RACINE, "simuler.py"),
                           "--nom", args.run, "--kafka", args.kafka, "--energie", "non"]
                          + options).returncode
    duree = time.time() - t0
    ecoute.join(timeout=180)
    if code:
        print(f"simuler.py s'est termine avec le code {code}")
    rapport = rapporter(args.run, ecoute, duree)
    os.makedirs(os.path.join(RACINE, "resultats"), exist_ok=True)
    sortie = os.path.join(RACINE, "resultats", f"{args.run}.json")
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rapport.items() if k != "seq_perdus"},
                     ensure_ascii=False, indent=1))
    print(f"\nrapport ecrit dans {sortie}")
    return 0 if rapport["c1_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
