"""Suivi en direct d'un run : agents, phenomene et performances. Aucun appel LLM.

    python3 direct.py                 # suit le run le plus recent de runs/
    python3 direct.py --port 8770
    puis ouvrir http://localhost:8770

La page (vues.py) est la meme que celle de tableau.py, avec deux onglets :
Suivre un run, et Comparer les runs, calcule en direct par tableau.py.

Le serveur relit, a chaque rafraichissement, le journal du run (runs/<run>.jsonl)
et sa telemetrie (runs/<run>.direct.jsonl, ecrite par simuler.py appel par
appel). Il ne parle ni a Kafka ni au LLM : il peut tourner a cote d'une
simulation, d'une serie experience.py, ou apres coup sur un run termine.

Ce que la page montre, en plus du phenomene (adoption, accord, sens) :

  latence          duree d'un appel LLM : mediane, p95, pire cas, par modele
  debit            tokens generes par seconde, tokens lus et ecrits par appel
  surcout          temps de decision hors LLM (recherche, prompt, controles)
  rythme           duree reelle d'un jour simule, appels par minute, fin estimee
  fiabilite        decisions exploitables, incidents par nature, nouvelles
                   tentatives, attente de quota, appels en echec
  comportement     changements d'avis, publications, messages adresses
  coherence        violations C6, passages retrouves, recherches sans resultat

Sans telemetrie (runs produits avant son ajout), la page se replie sur le
journal : etats des agents, rythme par jour simule, latences du bilan final.
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

RACINE = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(RACINE, "runs")
sys.path.insert(0, RACINE)

import tableau  # noqa: E402
import vues  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from experience import accord_partage  # noqa: E402

ORDRE_SENS = list(SENS)
INACTIF_S = 180          # sans ecriture depuis 3 min, un run sans bilan est dit interrompu
_cache = {}


def lire(chemin):
    """Evenements complets d'un fichier JSONL, relus seulement s'il a change."""
    try:
        st = os.stat(chemin)
    except OSError:
        return []
    cle = (st.st_mtime_ns, st.st_size)
    if _cache.get(chemin, (None,))[0] == cle:
        return _cache[chemin][1]
    evs = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if not ligne.endswith("\n"):
                break                     # ligne en cours d'ecriture
            try:
                evs.append(json.loads(ligne))
            except ValueError:
                continue
    _cache[chemin] = (cle, evs)
    return evs


def lister_runs():
    chemins = tableau.chemins_runs(DOSSIER)
    chemins.sort(key=os.path.getmtime, reverse=True)
    return [{"nom": os.path.basename(c)[:-6], "maj": os.path.getmtime(c)} for c in chemins]


def date(texte):
    try:
        return datetime.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


def centile(valeurs, q):
    if not valeurs:
        return None
    v = sorted(valeurs)
    return v[min(len(v) - 1, max(0, round(q * (len(v) - 1))))]


def resume_latences(appels):
    lat = [a["latence_s"] for a in appels if a.get("latence_s") is not None]
    sortie = sum(a.get("tokens_sortie") or 0 for a in appels if a.get("latence_s"))
    return {
        "n": len(appels), "reussis": len(lat),
        "moy": statistics.mean(lat) if lat else None,
        "p50": centile(lat, .5), "p95": centile(lat, .95), "max": max(lat) if lat else None,
        "tokens_s": (sortie / sum(lat)) if lat and sum(lat) else None,
        "entree_moy": statistics.mean([a.get("tokens_entree") or 0 for a in appels]) if appels else None,
        "sortie_moy": statistics.mean([a.get("tokens_sortie") or 0 for a in appels]) if appels else None,
        "relances": sum(1 for a in appels if (a.get("essais") or 1) > 1),
        "attente_s": sum(a.get("attente_s") or 0 for a in appels),
        "echecs": sum(1 for a in appels if a.get("echec")),
        "surcout_s": statistics.mean([a["duree_s"] - a["latence_s"] for a in appels
                                      if a.get("latence_s") is not None]) if lat else None,
    }


def etat(nom, dossier=None):
    dossier = dossier or DOSSIER
    chemin = os.path.join(dossier, f"{nom}.jsonl")
    evs = lire(chemin)
    tele = lire(os.path.join(dossier, f"{nom}.direct.jsonl"))
    if not evs:
        return {"erreur": f"run introuvable ou vide : {nom}"}
    par = defaultdict(list)
    for e in evs:
        par[e["schema"]].append(e)
    meta = (par["run.v2"] or par["run.v1"] or [{}])[0]
    bilan = (par["bilan.v1"] or [None])[0]
    pop = (par["population.v1"] or [{"agents": []}])[0]["agents"]
    jours = meta.get("jours") or 1
    maintenant = datetime.now()

    # ------------------------------------------------------------ avancement
    t_sim = max((e.get("t_sim") or 0) for e in evs)
    debut = date(evs[0].get("t_emission"))
    derniere = max(os.path.getmtime(chemin),
                   os.path.getmtime(os.path.join(dossier, f"{nom}.direct.jsonl")) if tele else 0)
    if bilan:
        statut, fin = "termine", date(bilan.get("t_emission"))
    elif maintenant.timestamp() - derniere > INACTIF_S:
        statut, fin = "interrompu", datetime.fromtimestamp(derniere)
    else:
        statut, fin = "en_cours", maintenant
    ecoule = (fin - debut).total_seconds() if debut and fin else None
    rythme = (t_sim / ecoule) if ecoule else None          # minutes simulees par seconde
    restant = ((jours * 1440 - t_sim) / rythme) if (rythme and statut == "en_cours") else None

    # Duree reelle de chaque jour simule : ecart entre deux releves.
    releves = par["indicateurs.v1"]
    jours_reels = []
    for a, b in zip(releves, releves[1:]):
        ta, tb = date(a["t_emission"]), date(b["t_emission"])
        if ta and tb:
            jours_reels.append([round(b["t_sim"] / 1440, 2), (tb - ta).total_seconds()])

    # ------------------------------------------------------------ agents
    moteur_de = {a["id"]: a.get("moteur", "?") for a in pop}
    dernier = {}
    nb_dec, nb_inc, flips = Counter(), Counter(), Counter()
    for d in par["decision.v1"]:
        moteur_de[d["agent"]] = d["moteur"]
        prec = dernier.get(d["agent"])
        if prec is not None and prec["porte"] != d["porte"]:
            flips[d["agent"]] += 1
        dernier[d["agent"]] = d
        nb_dec[d["agent"]] += 1
    for i in par["incident.v1"]:
        nb_inc[i.get("agent")] += 1
    publications = Counter(p["agent"] for p in par["publication.v1"])
    adresses = Counter(p["agent"] for p in par["publication.v1"] if p.get("portee") == "personne")

    appels = [a for a in tele if a.get("type") == "appel"]
    llm = [a for a in appels if a.get("moteur") != "regles"]
    lat_agent = defaultdict(list)
    for a in llm:
        if a.get("latence_s") is not None:
            lat_agent[a["agent"]].append(a["latence_s"])

    # Pas synchrone en cours : qui a deja repondu, qui reflechit, qui attend.
    en_cours = {}
    pas = [i for i, a in enumerate(tele) if a.get("type") == "debut_pas"]
    if pas and statut == "en_cours":
        dp = tele[pas[-1]]
        faits = {a["agent"]: a for a in tele[pas[-1] + 1:] if a.get("type") == "appel"}
        if len(faits) < len(dp["ordre"]):
            reste = [x for x in dp["ordre"] if x not in faits]
            depuis = max([date(a["t_reel"]) for a in faits.values()] + [date(dp["t_reel"])])
            en_cours = {"jour": round(dp["t_sim"] / 1440, 2), "faits": len(faits),
                        "total": len(dp["ordre"]), "reflechit": reste[0],
                        "depuis_s": (maintenant - depuis).total_seconds(),
                        "attente": reste[1:], "termines": list(faits)}

    agents = []
    for a in pop:
        d = dernier.get(a["id"])
        porte = d["porte"] if d else bool(a.get("porte"))
        cat = d["categorie"] if d else ("cercle_creatif" if a.get("porte") else "aucun_sens")
        lat = lat_agent.get(a["id"], [])
        if en_cours and a["id"] == en_cours["reflechit"]:
            etat_agent = "reflechit"
        elif en_cours and a["id"] in en_cours["attente"]:
            etat_agent = "attend"
        elif en_cours and a["id"] in en_cours["termines"]:
            etat_agent = "a_repondu"
        else:
            etat_agent = "repos"
        agents.append({
            "id": a["id"], "nom": a["nom"], "profil": a["profil"], "groupe": a["groupe"],
            "moteur": moteur_de.get(a["id"], "?"), "porte": porte,
            "sens": ORDRE_SENS.index(cat) if cat in SENS else -1,
            "texte": (d or {}).get("sens", "") if (d or {}).get("moteur") != "regles" else "",
            "raison": (d or {}).get("raison", ""), "valide": (d or {}).get("valide", True),
            "jour": round(d["t_sim"] / 1440, 2) if d else None,
            "decisions": nb_dec[a["id"]], "incidents": nb_inc[a["id"]], "flips": flips[a["id"]],
            "publications": publications[a["id"]], "adresses": adresses[a["id"]],
            "lat_der": lat[-1] if lat else None,
            "lat_moy": statistics.mean(lat) if lat else None,
            "etat": etat_agent,
        })

    # ------------------------------------------------------------ performances
    par_modele = {}
    for moteur in ("llm_grand", "llm_petit"):
        sel = [a for a in llm if a.get("moteur") == moteur]
        if sel:
            par_modele[moteur] = {"modele": sel[-1].get("modele") or "", **resume_latences(sel)}
    if not par_modele and bilan:
        # Repli : runs sans telemetrie, chiffres agreges du bilan.
        for t, c in bilan.get("par_taille", {}).items():
            par_modele[t] = {"modele": c.get("modele", ""), "n": c.get("appels", 0),
                             "moy": c.get("latence_moy_s"), "max": c.get("latence_max_s"),
                             "repli": True}
    t0 = date(tele[0]["t_reel"]) if tele else None
    points = [[round((date(a["t_reel"]) - t0).total_seconds(), 1), a["latence_s"], a["moteur"],
               a["agent"], int(bool(a.get("valide"))), round(a["t_sim"] / 1440, 2)]
              for a in llm if a.get("latence_s") is not None and t0][-600:]
    recents = [a for a in appels if date(a["t_reel"]) and
               (maintenant - date(a["t_reel"])).total_seconds() <= 300]
    decisions_llm = [d for d in par["decision.v1"] if d["moteur"] != "regles"]
    rec = par["recuperation.v1"]
    perceptions = par["perception.v1"]

    # ------------------------------------------------------------ phenomene
    serie = []
    for e in releves:
        n = sum(e["repartition_sens"].values()) or 1
        serie.append([round(e["t_sim"] / 1440, 2), e["taux_adoption"], accord_partage(e),
                      [e["repartition_sens"].get(s, 0) / n for s in ORDRE_SENS]])
    fil = [{"nom": next((a["nom"] for a in pop if a["id"] == p["agent"]), p["agent"]),
            "texte": p["texte"], "portee": p.get("portee"), "jour": round(p["t_sim"] / 1440, 2),
            "vers": p.get("destinataire")}
           for p in par["publication.v1"][-10:]][::-1]

    return {
        "nom": nom, "statut": statut, "mode": meta.get("mode"), "graine": meta.get("graine"),
        "jours": jours, "nb_agents": meta.get("nb_agents"), "telemetrie": bool(tele),
        "avancement": {"t_sim": t_sim, "jour": round(t_sim / 1440, 2), "ecoule_s": ecoule,
                       "rythme": rythme, "restant_s": restant,
                       "jour_reel_moy_s": statistics.mean([j[1] for j in jours_reels]) if jours_reels else None},
        "pas": en_cours or None,
        "agents": agents,
        "perf": {
            "par_modele": par_modele, "points": points, "jours_reels": jours_reels,
            "appels_llm": len(decisions_llm) if not llm else len(llm),
            "appels_par_min": len([a for a in recents if a.get("moteur") != "regles"]) / 5 if recents else None,
            "decision_regles_ms": (statistics.mean([a["duree_s"] for a in appels if a.get("moteur") == "regles"]) * 1000
                                   if any(a.get("moteur") == "regles" for a in appels) else None),
        },
        "qualite": {
            "decisions_llm": len(decisions_llm),
            "valides": sum(1 for d in decisions_llm if d["valide"]),
            "incidents": Counter(i["nature"] for i in par["incident.v1"]),
            "flips": sum(flips.values()), "decisions": len(par["decision.v1"]),
            "publications": len(par["publication.v1"]),
            "adresses": sum(adresses.values()),
            "c6_controles": len(perceptions),
            "c6_violations": sum(len(p.get("violations_c6", [])) for p in perceptions),
            "rag_recherches": len(rec),
            "rag_vides": sum(1 for r in rec if r["nb_resultats"] == 0),
            "rag_moy": statistics.mean([r["nb_resultats"] for r in rec]) if rec else None,
            "corrections": sum(1 for p in perceptions if p.get("categorie_corrigee")),
        },
        "bilan": None if not bilan else {
            "appels": bilan["appels"], "tokens": bilan["tokens_entree"] + bilan["tokens_sortie"],
            "duree_s": bilan["duree_run_s"],
            "wh": ((par["energie.v1"] or [{}])[0].get("kwh") or 0) * 1000 or None},
        "serie": serie, "fil": fil,
        "sens": [{"cle": k, "texte": v} for k, v in SENS.items()],
    }


class Gestion(BaseHTTPRequestHandler):
    def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        donnees = corps.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self._envoyer(200, vues.page(), "text/html; charset=utf-8")
        if url.path == "/api/runs":
            return self._envoyer(200, json.dumps(lister_runs()))
        if url.path == "/api/tableau":
            donnees = tableau.donnees_comparaison(tableau.chemins_runs(DOSSIER))
            return self._envoyer(200, json.dumps(donnees, ensure_ascii=False))
        if url.path == "/api/etat":
            nom = (parse_qs(url.query).get("run") or [""])[0]
            if not nom:
                runs = lister_runs()
                nom = runs[0]["nom"] if runs else ""
            if "/" in nom or "\\" in nom or nom.startswith("."):
                return self._envoyer(400, json.dumps({"erreur": "nom de run invalide"}))
            try:
                return self._envoyer(200, json.dumps(etat(nom), ensure_ascii=False))
            except Exception as e:      # une page doit survivre a un fichier en cours d'ecriture
                return self._envoyer(500, json.dumps({"erreur": f"{type(e).__name__} : {e}"}))
        self._envoyer(404, json.dumps({"erreur": "introuvable"}))

    def log_message(self, *_):
        pass


def main():
    global DOSSIER
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--hote", default="127.0.0.1",
                   help="0.0.0.0 pour l'ouvrir depuis une autre machine du reseau")
    p.add_argument("--dossier", default=DOSSIER, help="dossier des runs (defaut : runs/)")
    args = p.parse_args()
    DOSSIER = os.path.abspath(args.dossier)
    serveur = ThreadingHTTPServer((args.hote, args.port), Gestion)
    print(f"Suivi en direct sur http://localhost:{args.port}  (Ctrl+C pour arreter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\narrete")


if __name__ == "__main__":
    main()
