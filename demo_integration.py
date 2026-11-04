"""Demonstration integree de bout en bout, et son rapport.

Chaine lancee, dans cet ordre :
  pont.py --run <nom> --sans-injections    Kafka -> etat du campus -> WebSocket
  scene(s)                                 Godot (--godot CHEMIN) et/ou scene_temoin.py
  narratrice.py --suivre runs/<nom>.jsonl  observe le journal, ecrit <nom>.narration.jsonl
  simuler.py ... --kafka --nom <nom>       produit les evenements (journal = source de verite)

Configuration du monde : celle de la condition E de l'experience memoire
(--memoire-sens, ombres sans_discours, sans_social, sans_souvenirs). Un run de
demonstration n'est PAS une mesure : une seule graine, des pannes provoquees.

Avec --pannes (test de fumee), le script provoque pendant le run :
  pont arrete puis relance     il relit le run depuis le debut du topic
  scene fermee puis rouverte   elle recoit l'instantane a la reconnexion
  narratrice arretee, relancee elle renarre tout dans un fichier neuf
  broker Kafka coupe ~20 s     les evenements perdus sont rattrapes par le pont dans le journal

Puis il audite : topic Kafka contre fichier, bilan du producteur, bilan du pont,
traces des scenes, narrations (et evaluateur B), rejeu complet sans modele.

    .venv/bin/python demo_integration.py --nom demo_fumee --jours 4 --pannes
    .venv/bin/python demo_integration.py --nom demo_complete --jours 25 --godot <Godot>
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

RACINE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(RACINE, "runs")
PY = os.path.join(RACINE, ".venv", "bin", "python")
OPTIONS_E = ["--mode", "synchrone", "--ombres", "sans_discours", "sans_social", "sans_souvenirs",
             "--memoire-sens"]
CONTENEUR_KAFKA = "ephemere-kafka"


class Chaine:
    def __init__(self, args):
        self.args, self.nom = args, args.nom
        self.procs, self.journal_demo = {}, []
        self.base = os.path.join(RUNS, self.nom)

    def noter(self, quoi, **x):
        ligne = {"t": time.strftime("%H:%M:%S"), "quoi": quoi, **x}
        self.journal_demo.append(ligne)
        print(f"[demo {ligne['t']}] {quoi} {x if x else ''}", flush=True)

    def lancer(self, cle, commande, env=None, suffixe=""):
        log = open(f"{self.base}.{cle}{suffixe}.log", "w", encoding="utf-8")
        p = subprocess.Popen(commande, cwd=RACINE, stdout=log, stderr=subprocess.STDOUT,
                             env={**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})})
        self.procs[cle] = p
        self.noter(f"lance {cle}", pid=p.pid)
        return p

    def arreter(self, cle, delai=15):
        p = self.procs.get(cle)
        if p and p.poll() is None:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(delai)
            except subprocess.TimeoutExpired:
                p.kill()
            self.noter(f"arrete {cle}", code=p.returncode)

    # -------------------------------------------------------------- composants
    def pont(self, suffixe=""):
        return self.lancer("pont", [PY, "pont.py", "--run", self.nom, "--sans-injections"],
                           suffixe=suffixe)

    def scenes(self, suffixe=""):
        if self.args.scene_temoin:
            self.lancer("scene_temoin", [PY, "scene_temoin.py",
                                         f"{self.base}.scene_temoin{suffixe}.jsonl"], suffixe=suffixe)
        if self.args.godot:
            self.lancer("godot", [self.args.godot, "--path", os.path.join(RACINE, "godot")]
                        + (["--headless"] if self.args.godot_headless else []),
                        env={"EPHEMERE_TRACE": f"{self.base}.godot{suffixe}.jsonl",
                             "EPHEMERE_CAPTURES": f"{self.base}.captures"}, suffixe=suffixe)

    def narratrice(self, suffixe=""):
        return self.lancer("narratrice", [PY, "narratrice.py", "--suivre", f"{self.base}.jsonl"],
                           suffixe=suffixe)

    def simulateur(self):
        return self.lancer("simulateur", [PY, "simuler.py", "--agents", "20", "--jours",
                                          str(self.args.jours), "--graine", str(self.args.graine),
                                          "--fournisseur", "ollama", "--pause", "0",
                                          "--kafka", self.args.kafka, "--nom", self.nom]
                           + (["--tout-regles"] if self.args.regles else OPTIONS_E))

    # -------------------------------------------------------------- attentes
    def releve(self, t_sim, delai=7200):
        """Attend que le journal contienne le releve de cet instant."""
        fin = time.time() + delai
        while time.time() < fin:
            try:
                with open(f"{self.base}.jsonl", encoding="utf-8") as f:
                    for l in f:
                        if '"indicateurs.v1"' in l and json.loads(l)["t_sim"] >= t_sim:
                            return True
            except (OSError, ValueError):
                pass
            if self.procs["simulateur"].poll() is not None:
                return False
            time.sleep(2)
        return False

    def kafka_coupe(self, secondes):
        self.noter("coupure du broker Kafka", conteneur=CONTENEUR_KAFKA, secondes=secondes)
        subprocess.run(["docker", "stop", CONTENEUR_KAFKA], capture_output=True, timeout=60)
        time.sleep(secondes)
        subprocess.run(["docker", "start", CONTENEUR_KAFKA], capture_output=True, timeout=60)
        for _ in range(60):
            if port_ouvert(self.args.kafka):
                break
            time.sleep(1)
        self.noter("broker Kafka relance", joignable=port_ouvert(self.args.kafka))

    # -------------------------------------------------------------- deroulement
    def derouler(self):
        J = 1440
        self.pont()
        time.sleep(2)
        self.scenes()
        if self.args.narratrice:
            self.narratrice()
        time.sleep(1)
        self.simulateur()
        if self.args.pannes:
            if self.releve(1 * J):
                self.arreter("pont")
                time.sleep(5)
                self.pont(suffixe="_2")
            if self.releve(2 * J):
                self.arreter("scene_temoin")
                time.sleep(3)
                if self.args.scene_temoin:
                    self.lancer("scene_temoin", [PY, "scene_temoin.py",
                                                 f"{self.base}.scene_temoin_2.jsonl"], suffixe="_2")
                if self.args.narratrice:
                    self.arreter("narratrice")
                    time.sleep(2)
                    self.narratrice(suffixe="_2")
            if self.releve(3 * J):
                self.kafka_coupe(20)
        code = self.procs["simulateur"].wait()
        self.noter("simulateur termine", code=code)
        if self.args.narratrice:
            try:
                self.procs["narratrice"].wait(900)
            except subprocess.TimeoutExpired:
                self.noter("narratrice encore active apres 15 min : arretee")
            self.noter("narratrice terminee", code=self.procs["narratrice"].poll())
        dernier = sum(1 for _ in open(f"{self.base}.jsonl", encoding="utf-8")) - 1
        for _ in range(60):     # le pont a-t-il tout applique ?
            b = lire_json(f"{self.base}.pont.json") or {}
            if b.get("dernier_seq") == dernier and (b.get("narrations_lues", 0) >= 1
                                                    or not self.args.narratrice):
                break
            time.sleep(2)
        time.sleep(5)            # la scene recoit les derniers messages
        if self.args.godot:      # image finale de Godot : 20 s apres le bilan
            for _ in range(45):
                if os.path.exists(f"{self.base}.captures/final.png"):
                    break
                time.sleep(2)
        for cle in ("scene_temoin", "godot", "pont"):
            self.arreter(cle)


# ------------------------------------------------------------------ audit
def port_ouvert(adresse):
    hote, port = adresse.split(":")
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((hote, int(port))) == 0


def lire_json(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def lire_jsonl(chemin):
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def audit_kafka(nom, serveur, journal):
    """Le topic, relu depuis le debut, confronte au fichier du run."""
    from kafka import KafkaConsumer
    from ephemere.bus import TOPIC
    conso = KafkaConsumer(TOPIC, bootstrap_servers=serveur, auto_offset_reset="earliest",
                          enable_auto_commit=False, group_id=None, consumer_timeout_ms=15000)
    recus = []
    for m in conso:
        if m.key and m.key.decode("utf-8") == nom:
            recus.append(json.loads(m.value.decode("utf-8")))
    conso.close()
    seqs = [e["seq"] for e in recus]
    uniques = set(seqs)
    par_seq = {e["seq"]: e for e in journal}
    return {"messages_du_run": len(recus), "seq_distincts": len(uniques),
            "doublons": len(seqs) - len(uniques),
            "absents_du_topic": len(set(par_seq) - uniques),
            "seq_absents": sorted(set(par_seq) - uniques)[:30],
            "hors_ordre": sum(1 for a, b in zip(seqs, seqs[1:]) if b < a),
            "contenu_identique_au_fichier": all(par_seq.get(e["seq"]) == e for e in recus),
            "evenements_observateur_dans_le_topic": sum(1 for e in recus if e["schema"] in
                                                        ("narratrice.v1", "narration.v1"))}


def audit_scene(traces, journal):
    if not traces:
        return None
    evs = [x for t in traces for x in t if x["type"] == "evenement"]
    seqs = {x["seq"] for x in evs if x["seq"] is not None}
    fin = [x for x in traces[-1] if x["type"] == "fin"]
    recit = fin[-1]["recit_affiche"] if fin else []
    return {"traces": len(traces), "connexions": sum(1 for t in traces for x in t
                                                     if x["type"] == "connexion"),
            "messages_evenement": len(evs), "seq_distincts_recus": len(seqs),
            "seq_du_journal_jamais_recus": len({e["seq"] for e in journal} - seqs),
            "evenements_vus_au_final": (fin[-1]["indicateurs"] or {}).get("evenements_vus")
            if fin else None,
            "narrations_affichees": len(recit),
            "constats_affiches": sum(len(n["constats"]) for n in recit),
            "hypotheses_et_incertitudes_masquees": sum(n["masquees"] for n in recit),
            "exemple_recit": recit[-2:]}


def auditer(nom, serveur, journal_demo, godot_rejeu=None):
    base = os.path.join(RUNS, nom)
    journal = lire_jsonl(f"{base}.jsonl")
    narr = lire_jsonl(f"{base}.narration.jsonl")
    schemas = {}
    for e in journal:
        schemas[e["schema"]] = schemas.get(e["schema"], 0) + 1
    rapport = {"run": nom, "deroulement": journal_demo,
               "journal": {"evenements": len(journal), "par_schema": schemas,
                           "seq_continus": [e["seq"] for e in journal] == list(range(len(journal))),
                           "evenements_observateur": sum(1 for e in journal if e["schema"] in
                                                         ("narratrice.v1", "narration.v1")),
                           "entete": {k: journal[0].get(k) for k in
                                      ("graine", "jours", "ombres", "memoire_sens",
                                       "empreinte_prompt")} if journal else None,
                           "bilan": journal[-1] if journal and journal[-1]["schema"] == "bilan.v1"
                           else None},
               "producteur_kafka": lire_json(f"{base}.kafka.json"),
               "pont": lire_json(f"{base}.pont.json")}
    try:
        rapport["topic_kafka"] = audit_kafka(nom, serveur, journal)
    except Exception as e:
        rapport["topic_kafka"] = {"erreur": str(e)}
    temoins = [lire_jsonl(f"{base}.scene_temoin{s}.jsonl") for s in ("", "_2")]
    rapport["scene_temoin"] = audit_scene([t for t in temoins if t], journal)
    godot = [lire_jsonl(f"{base}.godot{s}.jsonl") for s in ("", "_2")]
    rapport["godot"] = audit_scene_godot([x for t in godot for x in t], journal) if any(godot) \
        else {"lance": False, "raison": "Godot non lance ou sans trace"}
    if os.path.isdir(f"{base}.captures"):
        rapport["godot_captures"] = sorted(os.listdir(f"{base}.captures"))
    if narr:
        aff = [a for n in narr[1:] for a in n["affirmations"]]
        rapport["narrations"] = {
            "narrations": len(narr) - 1, "mode": narr[0].get("mode"),
            "constats_verifies": sum(1 for a in aff if a["type"] in ("observation", "mesure")
                                     and a["statut"] == "verifiee"),
            "hypotheses_verifiees": sum(1 for a in aff if a["type"] == "interpretation"
                                        and a["statut"] == "verifiee"),
            "incertitudes_verifiees": sum(1 for a in aff if a["type"] == "incertitude"
                                          and a["statut"] == "verifiee"),
            "rejetees": sum(1 for a in aff if a["statut"] == "rejetee")}
        b = subprocess.run([PY, "verifier_narrations.py", f"{base}.narration.jsonl", "--json",
                            f"{base}.evaluateur_b.json"], cwd=RACINE, capture_output=True,
                           text=True)
        rapport["narrations"]["evaluateur_b"] = (b.stdout.strip().splitlines() or [""])[0]
    avant = requetes_ollama()
    r = subprocess.run([PY, "rejeu_integration.py", f"{base}.jsonl", "--json",
                        f"{base}.rejeu.json"], cwd=RACINE, capture_output=True, text=True)
    rapport["rejeu"] = lire_json(f"{base}.rejeu.json")
    rapport["rejeu_code"] = r.returncode
    rapport["rejeu_requetes_ollama"] = None if avant is None else requetes_ollama() - avant
    if godot_rejeu:
        rapport["rejeu_godot"] = rejeu_godot(nom, godot_rejeu)
    with open(f"{base}.integration.json", "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=1)
    return rapport


def godot_actif():
    return bool(subprocess.run(["pgrep", "-f", "Godot.app/Contents/MacOS/Godot"],
                               capture_output=True, text=True).stdout.strip())


def requetes_ollama():
    """Nombre de requetes servies par Ollama, lu dans son journal (preuve d'absence d'appel)."""
    chemin = os.path.expanduser("~/.ollama/logs/server.log")
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            return sum(1 for l in f if "| POST" in l)
    except OSError:
        return None


def rejeu_godot(nom, godot, attente=180):
    """Le run rejoue dans Godot depuis son seul fichier : trace, images, et zero appel au modele."""
    base = os.path.join(RUNS, nom)
    if godot_actif():
        return {"erreur": "un Godot tournait deja : rejeu non lance"}
    dossier = f"{base}.rejeu_godot"
    os.makedirs(dossier, exist_ok=True)
    avant = requetes_ollama()
    pont = subprocess.Popen([PY, "pont.py", "--rejeu", f"{base}.jsonl", "--vitesse", "0.02"],
                            cwd=RACINE, stdout=open(f"{dossier}/pont.log", "w"),
                            stderr=subprocess.STDOUT)
    time.sleep(1)
    scene = subprocess.Popen([godot, "--path", os.path.join(RACINE, "godot")], cwd=RACINE,
                             stdout=open(f"{dossier}/godot.log", "w"), stderr=subprocess.STDOUT,
                             env={**os.environ, "EPHEMERE_TRACE": f"{dossier}/trace.jsonl",
                                  "EPHEMERE_CAPTURES": f"{dossier}/captures"})
    fin = time.time() + attente
    while time.time() < fin and not os.path.exists(f"{dossier}/captures/final.png"):
        time.sleep(2)
    time.sleep(2)
    for p in (scene, pont):
        p.terminate()
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            p.kill()
    journal = lire_jsonl(f"{base}.jsonl")
    trace = lire_jsonl(f"{dossier}/trace.jsonl")
    r = audit_scene_godot(trace, journal)
    r.update({"requetes_ollama_pendant_le_rejeu": (None if avant is None
                                                   else requetes_ollama() - avant),
              "captures": sorted(os.listdir(f"{dossier}/captures"))
              if os.path.isdir(f"{dossier}/captures") else []})
    return r


def audit_scene_godot(trace, journal):
    """Trace EPHEMERE_TRACE de main.gd confrontee au journal et au fichier de narration."""
    evs = [x for x in trace if x["type"] == "evenement"]
    seqs = [int(x["seq"]) for x in evs if x.get("seq") is not None]
    narr = {x["narration"]: x for x in trace if x["type"] == "narration"}
    dernier = [e for e in journal if e["schema"] == "indicateurs.v1"]
    return {"evenements_recus": len(evs), "seq_distincts": len(set(seqs)),
            "seq_du_journal_jamais_recus": len({e["seq"] for e in journal} - set(seqs)),
            "dans_l_ordre": seqs == sorted(seqs),
            "evenements_vus_au_final": evs[-1]["vus"] if evs else None,
            "narrations_recues": len(narr),
            "constats_recus": sum(x["constats"] for x in narr.values()),
            "hypotheses_recues": sum(x["hypotheses"] for x in narr.values()),
            "incertitudes_recues": sum(x["incertitudes"] for x in narr.values()),
            "dernier_releve_journal": {k: dernier[-1][k] for k in
                                       ("t_sim_lisible", "taux_adoption", "sens_dominant",
                                        "part_sens_dominant", "repartition_sens")}
            if dernier else None}


def verifier_prealables(args):
    if not args.nom.startswith("demo_"):
        raise SystemExit("Le nom d'un run de demonstration commence par demo_.")
    if os.path.exists(os.path.join(RUNS, f"{args.nom}.jsonl")):
        raise SystemExit(f"runs/{args.nom}.jsonl existe deja : choisir un autre nom.")
    if not port_ouvert(args.kafka):
        raise SystemExit(f"Kafka injoignable sur {args.kafka} (docker start {CONTENEUR_KAFKA}).")
    if port_ouvert("localhost:8765"):
        raise SystemExit("Le port 8765 est deja pris (un autre pont tourne ?).")
    if args.regles and not args.narratrice:
        return      # ni agent LLM ni narratrice : Ollama n'est pas utilise
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
        noms = {m["name"] for m in json.load(r)["models"]}
    if not {"qwen2.5:7b", "qwen2.5:3b"} <= noms:
        raise SystemExit("Modeles Ollama absents.")
    if godot_actif():
        raise SystemExit("Un Godot tourne deja : il se connecterait au pont et fausserait les traces.")
    occupe = subprocess.run(["pgrep", "-f", "experience_memoire.py --lancer"],
                            capture_output=True, text=True).stdout.strip()
    if occupe:
        raise SystemExit("L'experience memoire tourne : la demo partagerait Ollama avec elle.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nom", required=True)
    p.add_argument("--jours", type=int, default=4)
    p.add_argument("--graine", type=int, default=200)
    p.add_argument("--kafka", default="localhost:9092")
    p.add_argument("--pannes", action="store_true", help="test de fumee : pannes provoquees")
    p.add_argument("--godot", help="executable Godot (version standard, sans .NET)")
    p.add_argument("--godot-headless", action="store_true")
    p.add_argument("--sans-scene-temoin", dest="scene_temoin", action="store_false")
    p.add_argument("--regles", action="store_true",
                   help="agents a regles seulement (essai de la chaine sans modele)")
    p.add_argument("--sans-narratrice", dest="narratrice", action="store_false")
    p.add_argument("--audit-seul", action="store_true", help="ne relance rien, refait l'audit")
    args = p.parse_args()
    if args.audit_seul:
        r = auditer(args.nom, args.kafka, [], args.godot)
    else:
        verifier_prealables(args)
        c = Chaine(args)
        try:
            c.derouler()
        finally:
            for cle in list(c.procs):
                c.arreter(cle)
        r = auditer(args.nom, args.kafka, c.journal_demo, args.godot)
    print(json.dumps({k: v for k, v in r.items() if k != "deroulement"}, ensure_ascii=False,
                     indent=1)[:6000])
    print(f"\nrapport : runs/{args.nom}.integration.json")


if __name__ == "__main__":
    main()
