"""Second evaluateur des narrations : verifie les constats publies contre le journal.

Reimplementation separee : n'importe pas le calcul des faits de la narratrice
(ephemere/narration.py). Pour chaque constat verifie (observation ou mesure),
on reconnait le gabarit de sa phrase, on recalcule ce qu'elle affirme depuis
les evenements bruts du journal, et on compare nombre par nombre, nom par nom.

  vrai        tout ce que la phrase affirme est retrouve dans le journal
  faux        au moins une valeur, un nom ou une citation differe
  inconnu     gabarit non reconnu : a juger a la main

Il ecrit aussi un fichier d'audit a l'aveugle (CSV, sans verdict) pour un
evaluateur humain : phrase publiee + evenements sources resumes.

    python3 verifier_narrations.py runs/n6_*.narration.jsonl --csv resultats/audit_v3.csv
"""
import argparse
import csv
import json
import os
import random
import re
import sys

from ephemere import journal

RACINE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.join(RACINE, "resultats", "emergence_reference.json")


def _pc(x):
    return round(x * 100)


class Journal:
    def __init__(self, chemin):
        self.evs = journal.lire(chemin)
        self.par_id = {journal.identifiant(e): e for e in self.evs}
        pop = next(e for e in self.evs if e["schema"] in ("population.v1", "population.v2"))
        self.agents = {a["id"]: a for a in pop["agents"]}
        self.nom_vers_id = {a.get("nom", a["id"]).lower(): a["id"] for a in pop["agents"]}

    def releve(self, seq):
        return self.evs[seq]

    def avant(self, aid, seq):
        """Dernier etat valide (porte, categorie) de l'agent strictement avant seq."""
        porte, cat = bool(self.agents[aid].get("porte", False)), None
        for e in self.evs[:seq]:
            if e["schema"] in ("decision.v1", "decision.v2") and e["agent"] == aid and e["valide"]:
                porte, cat = e["porte"], e["categorie"]
        return porte, cat

    def fenetre(self, n):
        return self.evs[n["fenetre"]["seq_debut"] + 1:n["fenetre"]["seq_fin"] + 1]


def _noms(texte):
    return [x.strip() for x in re.split(r",", texte) if x.strip()]


def verifier_constat(texte, n, J, ref):
    """(verdict, detail) pour une phrase publiee."""
    r0, r1 = J.releve(n["fenetre"]["seq_debut"]), J.releve(n["fenetre"]["seq_fin"])
    total = len(J.agents)
    fen = J.fenetre(n)
    m = re.match(r"Taux d'adoption au releve de (\S+ \S+) : (\d+) % \((\d+) etudiants sur (\d+)", texte)
    if m:
        ok = (m[1] == r1["t_sim_lisible"] and int(m[2]) == _pc(r1["taux_adoption"])
              and int(m[3]) == len(r1["porteurs"]) and int(m[4]) == total)
        return ok, "adoption"
    m = re.match(r"Variation de l'adoption depuis le releve de (\S+ \S+) : ([+-])(\d+) points "
                 r"\((\d+) % puis (\d+) %\)", texte)
    if m:
        var = r1["taux_adoption"] - r0["taux_adoption"]
        ok = (m[1] == r0["t_sim_lisible"] and int(m[3]) == abs(_pc(var))
              and (m[2] == "+") == (var >= 0) and int(m[4]) == _pc(r0["taux_adoption"])
              and int(m[5]) == _pc(r1["taux_adoption"]))
        return ok, "variation"
    m = re.match(r"Sens le plus donne au ruban au releve de (\S+ \S+) : ([\w ]+?)(?: a egalite)? "
                 r"\((\d+) etudiants(?: chacun)? sur (\d+)", texte)
    if m:
        # Le ou les sens dits doivent etre EXACTEMENT ceux du sommet : un sens
        # annonce seul alors qu'un autre est a egalite est faux (trompeur).
        rep = r1["repartition_sens"]
        haut = max(rep.values())
        dits = set(m[2].split(" et "))
        ok = (dits == {s_ for s_, c in rep.items() if c == haut} and int(m[3]) == haut
              and int(m[4]) == total)
        return ok, "sens"
    if texte.startswith("Repartition des sens donnes au ruban : "):
        dit = dict((s, int(c)) for s, c in re.findall(r"(\w+) (\d+)", texte.split(" : ", 1)[1]))
        vrai = {s: c for s, c in r1["repartition_sens"].items() if c}
        return dit == vrai, "repartition"
    m = re.match(r"Le sens le plus donne au ruban change : (\w+) .*?, (\w+) au releve", texte)
    if m:
        def seul(r):
            h = max(r["repartition_sens"].values())
            t = [s_ for s_, c in r["repartition_sens"].items() if c == h]
            return t[0] if len(t) == 1 else None
        return (m[1] == seul(r0) and m[2] == seul(r1) and m[1] != m[2]), "bascule"
    m = re.match(r"Groupe (\w+) : (\d+) membres sur (\d+) portent", texte)
    if m:
        membres = [a for a, x in J.agents.items() if x.get("groupe") == m[1]]
        ok = int(m[3]) == len(membres) and int(m[2]) == sum(1 for a in membres
                                                           if a in r1["porteurs"])
        return ok, "groupe"
    m = re.match(r"Ont (noue|retire) le ruban pendant la fenetre : (.*) \((\d+)\)\.$", texte)
    if m:
        cible = m[1] == "noue"
        vrai = []
        for e in fen:
            if e["schema"] in ("decision.v1", "decision.v2") and e["valide"]:
                avant, _ = J.avant(e["agent"], e["seq"])
                if avant != e["porte"] and e["porte"] == cible:
                    vrai.append(J.agents[e["agent"]].get("nom", e["agent"]))
        dit = _noms(m[2])
        return sorted(dit) == sorted(vrai) and int(m[3]) == len(vrai), m[1]
    m = re.match(r"Ont change de lecture du ruban : (.*) \((\d+)\)\.$", texte)
    if m:
        dit = re.findall(r"(\w+) \((\w+) puis (\w+)\)", m[1])
        vrai = []
        for e in fen:
            if e["schema"] in ("decision.v1", "decision.v2") and e["valide"]:
                _, avant = J.avant(e["agent"], e["seq"])
                if avant is not None and avant != e["categorie"]:
                    vrai.append((J.agents[e["agent"]].get("nom"), avant, e["categorie"]))
        return sorted(dit) == sorted(vrai) and int(m[2]) == len(vrai), "change"
    if texte.startswith("Aucun etudiant n'a noue, retire ou relu"):
        for e in fen:
            if e["schema"] in ("decision.v1", "decision.v2") and e["valide"]:
                p, c = J.avant(e["agent"], e["seq"])
                if p != e["porte"] or (c is not None and c != e["categorie"]):
                    return False, "calme"
        return any(e["schema"].startswith("decision") for e in fen), "calme"
    m = re.match(r"Messages pendant la fenetre : (\d+) publics sur le reseau, (\d+) adresses", texte)
    if m:
        pubs = [e for e in fen if e["schema"].startswith("publication")]
        prives = sum(1 for e in pubs if e["portee"] == "personne")
        return (int(m[1]) == len(pubs) - prives and int(m[2]) == prives), "messages"
    m = re.match(r"(\d+) repliques dans des conversations privees", texte)
    if m:
        return int(m[1]) == sum(1 for e in fen if e["schema"] == "replique.v1"), "repliques"
    m = re.match(r"(\d+) incidents de decision", texte)
    if m:
        return int(m[1]) == sum(1 for e in fen if e["schema"] == "incident.v1"), "incidents"
    m = re.match(r"(\w+) a ecrit sur le reseau : \"(.*)\"$", texte)
    if m:
        aid = J.nom_vers_id.get(m[1].lower())
        ok = any(e["schema"].startswith("publication") and e["agent"] == aid
                 and m[2] in e["texte"].replace("\n", " ") for e in fen)
        return ok, "parole"
    if texte.startswith("Indicateur d'emergence corrige") and ref is not None:
        # Version 4 : les deux lectures dans la meme phrase (versions 1 a 3 : une seule).
        dits = re.findall(r"(six sens|regroupe)[ ,(].*?gain soutenu (\d+) points pour un seuil de "
                          r"(\d+) points[ ;,]+(?:verdict : )?(emergent|non emergent)", texte)
        ok = bool(dits)
        for lecture, g, seuil, verdict in dits:
            v = ref["seuil_persistance"]["six_sens" if lecture == "six sens" else "regroupe"]
            ok = ok and (int(g) == abs(_pc(v["delta_a"])) and int(seuil) == _pc(v["seuil"])
                         and (verdict == "emergent") == v["emergent"])
        return ok, "emergence"
    m = re.match(r"Ecart d'accord entre les decisions reelles et l'ombre (\w+) sur le run : "
                 r"([+-])(\d+) points, p = ([\d.]+)", texte)
    if m and ref is not None:
        o = ref["ombres"][m[1]]["six_sens"]
        ok = int(m[3]) == abs(_pc(o["ecart"])) and abs(float(m[4]) - o["p"]) < 0.0015
        return ok, "ombre"
    return None, "gabarit inconnu"


def resume_source(J, sid):
    e = J.par_id.get(sid)
    if e is None:
        return f"{sid} INTROUVABLE"
    s = e["schema"]
    if s == "indicateurs.v1":
        return (f"{sid} releve {e['t_sim_lisible']} adoption {e['taux_adoption']:.2f} "
                f"porteurs {len(e['porteurs'])} sens {e['repartition_sens']}")
    if s.startswith("decision"):
        return (f"{sid} decision {e['agent']} porte={e['porte']} sens={e['categorie']} "
                f"valide={e['valide']}")
    if s.startswith("publication"):
        return f"{sid} publication {e['agent']} ({e['portee']}) : {e['texte'][:160]}"
    return f"{sid} {s}"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("narrations", nargs="+")
    p.add_argument("--csv", help="fichier d'audit a l'aveugle pour un evaluateur humain")
    p.add_argument("--json", help="verdicts de cet evaluateur")
    p.add_argument("--emergence", nargs="*", default=[REFERENCE],
                   help="sorties --json d'emergence.py ou chercher l'indicateur des runs narres")
    args = p.parse_args()
    refs = {}
    for chemin in args.emergence:
        if os.path.exists(chemin):
            for r in json.load(open(chemin, encoding="utf-8"))["runs"]:
                refs[r["run"]] = r
    lignes, compte = [], {}
    for chemin in args.narrations:
        evs = [json.loads(l) for l in open(chemin, encoding="utf-8")]
        entete, narrations = evs[0], evs[1:]
        J = Journal(os.path.join(RACINE, entete["source"]))
        ref = refs.get(entete["run"])
        for n in narrations:
            for i, a in enumerate(n["affirmations"]):
                if a["statut"] != "verifiee" or a["type"] not in ("observation", "mesure"):
                    continue
                ok, nature = verifier_constat(a["texte"], n, J, ref)
                verdict = {True: "vrai", False: "faux", None: "inconnu"}[ok]
                compte[verdict] = compte.get(verdict, 0) + 1
                lignes.append({"id": f"{entete['run']}/{n['narration']}/{i}",
                               "fenetre": f"{n['fenetre']['debut']} -> {n['fenetre']['fin']}",
                               "texte": a["texte"], "nature": nature, "verdict": verdict,
                               "sources": " | ".join(resume_source(J, s) for s in a["sources"][:12])})
    print(json.dumps({"constats": len(lignes), **compte}, ensure_ascii=False))
    for l in lignes:
        if l["verdict"] != "vrai":
            print(f"  {l['verdict']:8s} {l['id']} [{l['nature']}] {l['texte'][:110]}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(lignes, f, ensure_ascii=False, indent=1)
    if args.csv:
        aveugle = [{k: l[k] for k in ("id", "fenetre", "texte", "sources")} for l in lignes]
        random.Random(0).shuffle(aveugle)
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "fenetre", "texte", "sources", "jugement",
                                              "commentaire"])
            w.writeheader()
            for l in aveugle:
                w.writerow({**l, "jugement": "", "commentaire": ""})
    return 0 if not compte.get("faux") else 1


if __name__ == "__main__":
    sys.exit(main())
