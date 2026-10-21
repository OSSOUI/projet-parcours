"""Suivi en direct d'un run : agents, phenomene et performances. Aucun appel LLM.

    python3 direct.py                 # suit le run le plus recent de runs/
    python3 direct.py --port 8770
    puis ouvrir http://localhost:8770

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
import glob
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
    chemins = [c for c in glob.glob(os.path.join(DOSSIER, "*.jsonl"))
               if not c.endswith((".rejets.jsonl", ".traitement.jsonl", ".direct.jsonl"))]
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


def etat(nom):
    chemin = os.path.join(DOSSIER, f"{nom}.jsonl")
    evs = lire(chemin)
    tele = lire(os.path.join(DOSSIER, f"{nom}.direct.jsonl"))
    if not evs:
        return {"erreur": f"run introuvable ou vide : {nom}"}
    par = defaultdict(list)
    for e in evs:
        par[e["schema"]].append(e)
    meta = (par["run.v1"] or [{}])[0]
    bilan = (par["bilan.v1"] or [None])[0]
    pop = (par["population.v1"] or [{"agents": []}])[0]["agents"]
    jours = meta.get("jours") or 1
    maintenant = datetime.now()

    # ------------------------------------------------------------ avancement
    t_sim = max((e.get("t_sim") or 0) for e in evs)
    debut = date(evs[0].get("t_emission"))
    derniere = max(os.path.getmtime(chemin),
                   os.path.getmtime(os.path.join(DOSSIER, f"{nom}.direct.jsonl")) if tele else 0)
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
            return self._envoyer(200, PAGE, "text/html; charset=utf-8")
        if url.path == "/api/runs":
            return self._envoyer(200, json.dumps(lister_runs()))
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


PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Éphémère en direct</title>
<style>
:root{
  color-scheme:light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --mark:#52514e; --wash:rgba(11,11,11,.05);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#d6d5ce;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b; --good-text:#006300;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --mark:#c3c2b7; --wash:rgba(255,255,255,.06);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#44443f; --good-text:#0ca30c;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --mark:#c3c2b7; --wash:rgba(255,255,255,.06);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#44443f; --good-text:#0ca30c;
}
*{box-sizing:border-box}
body{margin:0; background:var(--page); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; padding:0 16px 48px}
main{max-width:1280px; margin:0 auto}
h1{font-size:1.45rem; margin:0}
h2{font-size:1.05rem; margin:0 0 8px}
h3{font-size:.9rem; margin:0 0 6px; font-weight:600}
p{margin:0}
.muted{color:var(--muted); font-size:.8rem}
.sub{color:var(--ink2); font-size:.88rem}
.barre{position:sticky; top:0; z-index:5; background:var(--page); padding:14px 0 10px; border-bottom:1px solid var(--border)}
.ligne-titre{display:flex; flex-wrap:wrap; align-items:center; gap:8px 16px}
select{font:inherit; font-size:.85rem; color:var(--ink); background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:3px 8px; max-width:100%}
.statut{display:inline-flex; align-items:center; gap:6px; font-size:.82rem; font-weight:600; padding:2px 10px; border-radius:999px; border:1px solid var(--border)}
.statut i{width:8px; height:8px; border-radius:50%; display:inline-block}
.en_cours i{background:var(--good); animation:pouls 1.4s infinite}
.termine i{background:var(--muted)}
.interrompu i{background:var(--critical)}
@keyframes pouls{50%{opacity:.25}}
.progres{height:6px; background:var(--grid); border-radius:999px; margin-top:10px; overflow:hidden}
.progres div{height:100%; background:var(--ink); border-radius:999px; transition:width .6s}
.infos{display:flex; flex-wrap:wrap; gap:4px 18px; margin-top:6px; font-size:.8rem; color:var(--ink2); font-variant-numeric:tabular-nums}
.infos b{color:var(--ink); font-weight:600}
.tuiles{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr)); gap:10px; margin-top:16px}
.tuile{background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:10px 12px; min-width:0}
.tuile .v{font-size:1.45rem; font-weight:650; line-height:1.2}
.tuile .l{font-size:.76rem; color:var(--ink2)}
.tuile .d{font-size:.74rem; color:var(--muted)}
section{margin-top:26px}
.carte{background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; min-width:0}
.g2{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr)); gap:12px}
.g3{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr)); gap:12px}
svg{display:block; width:100%; height:auto; overflow:visible}
svg text{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.defil{overflow-x:auto}
table{border-collapse:collapse; width:100%; font-size:.82rem; font-variant-numeric:tabular-nums}
th,td{text-align:left; padding:5px 7px; border-bottom:1px solid var(--grid); vertical-align:middle}
th{color:var(--ink2); font-weight:600; font-size:.74rem; white-space:nowrap}
td.n,th.n{text-align:right; white-space:nowrap}
td{white-space:nowrap}
td.raison{white-space:nowrap}
tr.reflechit{background:var(--wash)}
.etat{display:inline-flex; align-items:center; gap:5px; white-space:nowrap; font-size:.78rem}
.etat i{width:8px; height:8px; border-radius:50%; display:inline-block; border:1.5px solid var(--muted)}
.etat.reflechit i{border-color:var(--warning); background:var(--warning); animation:pouls 1s infinite}
.etat.a_repondu i{border-color:var(--good); background:var(--good)}
.etat.attend i{border-style:dotted}
.cle{width:11px; height:11px; border-radius:3px; display:inline-block; vertical-align:-1px; margin-right:5px}
.ruban{font-size:.95rem}
.raison{color:var(--ink2); max-width:340px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.alerte{color:var(--critical); font-weight:600}
.legende{display:flex; flex-wrap:wrap; gap:4px 14px; margin:6px 0; font-size:.78rem; color:var(--ink2)}
.legende span{display:inline-flex; align-items:center; gap:5px}
.cle-ligne{width:16px; border-top:2px solid var(--ink); display:inline-block}
.cle-tiret{width:16px; border-top:2px dashed var(--ink); display:inline-block}
.cle-rond{width:9px; height:9px; border-radius:50%; display:inline-block; background:var(--mark)}
.cle-rond.ko{background:transparent; border:2px solid var(--critical)}
#info{position:fixed; pointer-events:none; z-index:20; background:var(--surface); color:var(--ink); border:1px solid var(--border); border-radius:8px; padding:7px 10px; font-size:.78rem; box-shadow:0 4px 18px rgba(0,0,0,.12); display:none; max-width:320px}
#info b{font-variant-numeric:tabular-nums}
.fil li{padding:6px 0; border-bottom:1px solid var(--grid); font-size:.82rem}
.fil ul{list-style:none; margin:0; padding:0}
.vide{color:var(--muted); font-style:italic; font-size:.84rem; padding:8px 0}
.kv{display:grid; grid-template-columns:auto auto; gap:3px 14px; font-size:.82rem; font-variant-numeric:tabular-nums}
.kv span:nth-child(odd){color:var(--ink2)}
.kv span:nth-child(even){text-align:right; font-weight:600}
.note{font-size:.78rem; color:var(--ink2); background:var(--wash); border-radius:6px; padding:6px 10px; margin-top:10px}
</style>
</head>
<body>
<main>
<div class="barre">
  <div class="ligne-titre">
    <h1>Éphémère en direct</h1>
    <span class="statut" id="statut"><i></i><span>–</span></span>
    <label class="sub">Run <select id="run"><option value="">le plus récent</option></select></label>
  </div>
  <div class="progres" role="progressbar" aria-label="Avancement du run" id="progres"><div style="width:0"></div></div>
  <div class="infos" id="infos"></div>
</div>

<div class="tuiles" id="tuiles"></div>
<p class="note" id="note" hidden></p>

<section>
  <h2>Agents</h2>
  <p class="sub" id="pas-info"></p>
  <div class="carte defil" style="margin-top:8px"><table id="agents"></table></div>
</section>

<section>
  <h2>Performances des agents LLM</h2>
  <div class="g3" id="modeles"></div>
  <div class="g2" style="margin-top:12px">
    <div class="carte"><h3>Temps de réponse, appel par appel</h3>
      <div class="legende"><span><i class="cle-rond"></i>appel exploitable</span><span><i class="cle-rond ko"></i>décision inexploitable</span></div>
      <div id="nuage"></div></div>
    <div class="carte"><h3>Durée réelle de chaque jour simulé</h3>
      <p class="muted">Écart entre deux relevés d'indicateurs : en synchrone, le temps que mettent tous les agents à répondre.</p>
      <div id="jours"></div></div>
  </div>
</section>

<section>
  <h2>Phénomène</h2>
  <div class="g2">
    <div class="carte"><h3>Adoption et accord</h3>
      <div class="legende"><span><i class="cle-ligne"></i>portent le ruban</span><span><i class="cle-tiret"></i>accord sur un sens partagé</span></div>
      <div id="courbes"></div></div>
    <div class="carte"><h3>Ce que le ruban veut dire sur le campus</h3>
      <div class="legende" id="leg-sens"></div>
      <div id="aire"></div></div>
  </div>
</section>

<section>
  <h2>Fiabilité, comportement et cohérence</h2>
  <div class="g3">
    <div class="carte"><h3>Fiabilité</h3><div id="fiab"></div></div>
    <div class="carte"><h3>Comportement</h3><div id="compo"></div></div>
    <div class="carte"><h3>Cohérence et recherche</h3><div id="coher"></div></div>
  </div>
  <div class="carte fil" style="margin-top:12px"><h3>Derniers messages sur le réseau</h3><div id="fil"></div></div>
</section>
</main>
<div id="info"></div>

<script>
"use strict";
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const LIB = {cercle_creatif:"cercle créatif", tendance:"tendance", suivre_la_foule:"suivre la foule", ringard:"ringard", ironie:"ironie", aucun_sens:"aucun sens"};
const coul = i => i < 0 ? "var(--muted)" : `var(--s${i + 1})`;
const ETATS = {reflechit:"réfléchit", attend:"en attente", a_repondu:"a répondu", repos:"–", pause:"pas ce jour"};
let choix = "", minuterie = null, dernier = null;

function el(tag, a, parent, texte){
  const n = tag.startsWith("svg:") ? document.createElementNS(NS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(a || {})) if (v != null) n.setAttribute(k, v);
  if (texte !== undefined) n.textContent = texte;
  if (parent) parent.appendChild(n);
  return n;
}
const nb = (v, d = 0) => v == null ? "–" : Number(v).toLocaleString("fr-FR", {maximumFractionDigits:d, minimumFractionDigits:d});
const pct = v => v == null ? "–" : Math.round(v * 100) + " %";
const sec = v => v == null ? "–" : v < 10 ? nb(v, 2) + " s" : nb(v, 1) + " s";
function duree(s){
  if (s == null) return "–";
  s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), r = s % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")}` : m ? `${m} min ${String(r).padStart(2, "0")}` : `${r} s`;
}
function echelle(d0, d1, r0, r1){ const k = (r1 - r0) / ((d1 - d0) || 1); return v => r0 + (v - d0) * k; }
function grad(max, n = 4){
  if (max <= 0) return [0];
  const b = max / n, p = 10 ** Math.floor(Math.log10(b)), r = b / p;
  const pas = (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * p;
  const o = []; for (let v = 0; ; v += pas){ o.push(+v.toFixed(10)); if (v >= max - pas * 1e-9) break; } return o;
}
const info = $("info");
function montrer(e, tete, lignes){
  info.textContent = ""; if (tete) el("div", {style:"color:var(--ink2);margin-bottom:3px"}, info, tete);
  for (const [v, l] of lignes){ const d = el("div", {}, info); el("b", {}, d, v); d.append(" " + l); }
  info.style.display = "block";
  info.style.left = Math.min(innerWidth - info.offsetWidth - 8, e.clientX + 14) + "px";
  info.style.top = Math.max(8, e.clientY - info.offsetHeight - 10) + "px";
}
const cacher = () => info.style.display = "none";

/* ---------- en-tete ---------- */
function entete(s){
  const st = $("statut"); st.className = "statut " + s.statut;
  st.lastChild.textContent = {en_cours:"en cours", termine:"terminé", interrompu:"interrompu"}[s.statut];
  const a = s.avancement, part = Math.min(1, a.t_sim / (s.jours * 1440));
  $("progres").firstChild.style.width = (part * 100).toFixed(1) + "%";
  $("progres").setAttribute("aria-valuenow", Math.round(part * 100));
  const inf = $("infos"); inf.textContent = "";
  const champ = (l, v) => { const sp = el("span", {}, inf); sp.append(l + " "); el("b", {}, sp, v); };
  champ("", s.nom); champ("mode", s.mode); champ("graine", s.graine); champ("agents", s.nb_agents);
  champ("jour simulé", `${nb(a.jour, 1)} / ${s.jours}`); champ("temps écoulé", duree(a.ecoule_s));
  champ("rythme", a.rythme == null ? "–" : `${nb(a.rythme, a.rythme < 10 ? 1 : 0)} min simulées / s`);
  if (s.statut === "en_cours") champ("fin estimée dans", duree(a.restant_s));
}

/* ---------- tuiles ---------- */
function tuiles(s){
  const t = $("tuiles"); t.textContent = "";
  const der = s.serie[s.serie.length - 1] || [0, 0, 0, []];
  let dom = 0; (der[3] || []).forEach((v, i) => { if (i < 5 && v > (der[3][dom] || 0)) dom = i; });
  const q = s.perf, m = Object.values(q.par_modele);
  const p50 = m.length ? Math.max(...m.map(x => x.p50 ?? x.moy ?? 0)) : null;
  const p95 = m.length ? Math.max(...m.map(x => x.p95 ?? x.max ?? 0)) : null;
  const sortie = m.filter(x => x.tokens_s != null);
  const ql = s.qualite;
  const items = [
    ["Portent le ruban", pct(der[1]), `jour ${nb(der[0], 1)}`],
    ["Accord sur un sens", pct(der[2]), LIB[s.sens[dom]?.cle] ?? ""],
    ["Appels LLM", nb(q.appels_llm), q.appels_par_min == null ? "" : `${nb(q.appels_par_min, 1)} / min sur 5 min`],
    ["Temps de réponse médian", sec(p50), "pire modèle"],
    ["Temps de réponse p95", sec(p95), "95 % des appels en dessous"],
    ["Débit de génération", sortie.length ? nb(Math.min(...sortie.map(x => x.tokens_s)), 1) + " tok/s" : "–", "modèle le plus lent"],
    ["Décisions exploitables", ql.decisions_llm ? pct(ql.valides / ql.decisions_llm) : "–", `${nb(ql.decisions_llm - ql.valides)} incidents`],
    ["Un jour simulé", duree(s.avancement.jour_reel_moy_s), "en temps réel, en moyenne"],
  ];
  for (const [l, v, d] of items){ const c = el("div", {class:"tuile"}, t); el("div", {class:"l"}, c, l); el("div", {class:"v"}, c, v); el("div", {class:"d"}, c, d); }
  const note = $("note");
  note.hidden = s.telemetrie;
  note.textContent = "Ce run a été lancé sans télémétrie : les temps de réponse appel par appel ne sont pas disponibles. La page se replie sur le journal (états, rythme par jour, latences du bilan final).";
}

/* ---------- agents ---------- */
function agents(s){
  const p = s.pas;
  $("pas-info").textContent = p
    ? `Jour ${nb(p.jour, 0)} en cours : ${p.faits} agents sur ${p.total} ont répondu. ${s.agents.find(a => a.id === p.reflechit)?.nom ?? "?"} réfléchit depuis ${duree(p.depuis_s)}.`
    : (s.statut === "en_cours" ? "Entre deux pas, ou run asynchrone : l'état affiché est la dernière décision de chaque agent." : "État final de chaque agent.");
  const t = $("agents"); t.textContent = "";
  const h = el("tr", {}, el("thead", {}, t));
  for (const [l, c] of [["État"],["Agent"],["Profil"],["Moteur"],["Ruban"],["Sens du ruban"],["Dernière réponse","n"],["Réponse moy.","n"],["Décisions","n"],["Incidents","n"],["Changements d'avis","n"],["Messages","n"],["Dernière raison"]])
    el("th", {class:c}, h, l);
  const b = el("tbody", {}, t);
  const ordre = ["pionnier","figure_populaire","suiveur","refractaire","ironique"];
  for (const a of [...s.agents].sort((x, y) => ordre.indexOf(x.profil) - ordre.indexOf(y.profil) || x.nom.localeCompare(y.nom))){
    const tr = el("tr", {class:a.etat === "reflechit" ? "reflechit" : null}, b);
    const etat = p && a.etat === "repos" ? "pause" : a.etat;
    const e = el("span", {class:"etat " + etat, title:etat === "pause" ? "les pionnières se relaient : une sur deux réévalue à chaque pas" : null}, el("td", {}, tr)); el("i", {}, e); e.append(ETATS[etat]);
    el("td", {style:"font-weight:600"}, tr, a.nom);
    el("td", {}, tr, a.profil.replace("_", " "));
    el("td", {}, tr, a.moteur.replace("llm_", ""));
    el("td", {class:"ruban", title:a.porte ? "porte le ruban" : "ne le porte pas"}, tr, a.porte ? "● porte" : "○");
    const sc = el("td", {title:a.texte || ""}, tr); el("span", {class:"cle", style:`background:${coul(a.sens)}`}, sc); sc.append(a.sens >= 0 ? LIB[s.sens[a.sens].cle] : "hors liste");
    el("td", {class:"n"}, tr, sec(a.lat_der));
    el("td", {class:"n"}, tr, sec(a.lat_moy));
    el("td", {class:"n"}, tr, a.decisions);
    const inc = el("td", {class:"n" + (a.incidents ? " alerte" : "")}, tr, a.incidents ? "⚠ " + a.incidents : "0");
    el("td", {class:"n"}, tr, a.flips);
    el("td", {class:"n"}, tr, a.publications ? `${a.publications} (${a.adresses} adressés)` : "0");
    el("td", {class:"raison", title:a.raison}, tr, (a.valide ? "" : "⚠ ") + a.raison);
  }
}

/* ---------- performances ---------- */
function modeles(s){
  const box = $("modeles"); box.textContent = "";
  const entrees = Object.entries(s.perf.par_modele);
  if (!entrees.length){ el("p", {class:"vide"}, box, "Aucun agent LLM dans ce run : tout est décidé par des règles."); }
  for (const [taille, m] of entrees){
    const c = el("div", {class:"carte"}, box);
    el("h3", {}, c, `${taille.replace("llm_", "modèle ")} · ${m.modele}`);
    const kv = el("div", {class:"kv"}, c);
    const ligne = (l, v) => { el("span", {}, kv, l); el("span", {}, kv, v); };
    ligne("appels", nb(m.n));
    if (m.repli){ ligne("latence moyenne", sec(m.moy)); ligne("pire appel", sec(m.max)); el("p", {class:"muted", style:"margin-top:6px"}, c, "Chiffres du bilan final (pas de télémétrie)."); continue; }
    ligne("médiane", sec(m.p50)); ligne("p95", sec(m.p95)); ligne("pire appel", sec(m.max));
    ligne("débit de génération", m.tokens_s == null ? "–" : nb(m.tokens_s, 1) + " tok/s");
    ligne("tokens lus / écrits par appel", `${nb(m.entree_moy)} / ${nb(m.sortie_moy)}`);
    ligne("surcoût hors LLM (recherche, prompt)", m.surcout_s == null ? "–" : nb(m.surcout_s * 1000) + " ms");
    ligne("appels relancés", nb(m.relances)); ligne("attente de quota", sec(m.attente_s)); ligne("appels en échec", nb(m.echecs));
  }
  if (s.perf.decision_regles_ms != null){
    const c = el("div", {class:"carte"}, box); el("h3", {}, c, "agents à règles");
    const kv = el("div", {class:"kv"}, c); el("span", {}, kv, "temps de décision moyen"); el("span", {}, kv, s.perf.decision_regles_ms < 0.01 ? "< 0,01 ms" : nb(s.perf.decision_regles_ms, 2) + " ms");
  }
}

function nuage(s){
  const box = $("nuage"); box.textContent = "";
  const pts = s.perf.points;
  if (!pts.length){ el("p", {class:"vide"}, box, s.telemetrie ? "Pas encore d'appel LLM." : "Disponible pour les runs lancés avec la télémétrie."); return; }
  const tailles = [...new Set(pts.map(p => p[2]))].sort();
  const xmax = Math.max(...pts.map(p => p[0]), 1), ymax = Math.max(...pts.map(p => p[1]), .1);
  for (const t of tailles){
    const W = 560, H = 150, G = 44, B = 22, T = 16;
    const x = echelle(0, xmax, G, W - 8), yt = grad(ymax, 3), y = echelle(0, yt[yt.length - 1], H - B, T);
    const sv = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":`Temps de réponse ${t}`}, box);
    el("svg:text", {x:G, y:10, "font-size":12, "font-weight":600, fill:"var(--ink)"}, sv, t.replace("llm_", "modèle "));
    for (const v of yt){ el("svg:line", {x1:G, x2:W - 8, y1:y(v), y2:y(v), stroke:v ? "var(--grid)" : "var(--axis)"}, sv);
      el("svg:text", {x:G - 6, y:y(v) + 4, "text-anchor":"end", "font-size":11, fill:"var(--muted)"}, sv, nb(v) + " s"); }
    for (const v of grad(xmax, 5)) el("svg:text", {x:x(v), y:H - 5, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, sv, duree(v));
    for (const p of pts.filter(p => p[2] === t)){
      const c = el("svg:circle", {cx:x(p[0]), cy:y(p[1]), r:3.5, fill:p[4] ? "var(--mark)" : "transparent",
        "fill-opacity":.7, stroke:p[4] ? "var(--surface)" : "var(--critical)", "stroke-width":p[4] ? 1 : 2}, sv);
      const hit = el("svg:circle", {cx:x(p[0]), cy:y(p[1]), r:9, fill:"transparent"}, sv);
      hit.addEventListener("pointermove", e => montrer(e, `${p[3]} · J${nb(p[5], 0)}`, [[sec(p[1]), "de réponse"], [p[4] ? "exploitable" : "⚠ inexploitable", ""]]));
      hit.addEventListener("pointerleave", cacher);
    }
  }
  el("p", {class:"muted"}, box, "Axe horizontal : temps réel depuis le début du run (600 derniers appels).");
}

function barresJours(s){
  const box = $("jours"); box.textContent = "";
  const j = s.perf.jours_reels;
  if (!j.length){ el("p", {class:"vide"}, box, "Pas encore de jour complet."); return; }
  const W = 560, H = 170, G = 50, B = 22, T = 10;
  const ym = grad(Math.max(...j.map(v => v[1])), 3), y = echelle(0, ym[ym.length - 1], H - B, T);
  const bw = Math.max(2, (W - 8 - G) / j.length - 2), x = i => G + i * (bw + 2);
  const sv = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":"Durée réelle de chaque jour simulé"}, box);
  for (const v of ym){ el("svg:line", {x1:G, x2:W - 8, y1:y(v), y2:y(v), stroke:v ? "var(--grid)" : "var(--axis)"}, sv);
    el("svg:text", {x:G - 6, y:y(v) + 4, "text-anchor":"end", "font-size":11, fill:"var(--muted)"}, sv, duree(v)); }
  j.forEach(([jour, d], i) => {
    const r = el("svg:rect", {x:x(i), y:y(d), width:bw, height:Math.max(1, y(0) - y(d)), rx:Math.min(3, bw / 2), fill:"var(--mark)"}, sv);
    r.addEventListener("pointermove", e => montrer(e, `jour ${nb(jour, 0)}`, [[duree(d), "en temps réel"]]));
    r.addEventListener("pointerleave", cacher);
    if (j.length <= 12 || i % Math.ceil(j.length / 8) === 0) el("svg:text", {x:x(i) + bw / 2, y:H - 5, "text-anchor":"middle", "font-size":10, fill:"var(--muted)"}, sv, "J" + nb(jour, 0));
  });
}

/* ---------- phenomene ---------- */
function courbes(s){
  const box = $("courbes"); box.textContent = "";
  const W = 560, H = 200, G = 40, B = 22, T = 10, jm = Math.max(s.jours, 1);
  const x = echelle(0, jm, G, W - 8), y = echelle(0, 1, H - B, T);
  const sv = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":"Adoption et accord"}, box);
  for (const v of [0, .5, 1]){ el("svg:line", {x1:G, x2:W - 8, y1:y(v), y2:y(v), stroke:v ? "var(--grid)" : "var(--axis)"}, sv);
    el("svg:text", {x:G - 6, y:y(v) + 4, "text-anchor":"end", "font-size":11, fill:"var(--muted)"}, sv, pct(v)); }
  for (const v of grad(jm, 5)) el("svg:text", {x:x(v), y:H - 5, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, sv, "J" + v);
  el("svg:line", {x1:G, x2:W - 8, y1:y(.3), y2:y(.3), stroke:"var(--ink2)", "stroke-dasharray":"2 4"}, sv);
  const ch = k => s.serie.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[k]).toFixed(1)}`).join("");
  if (s.serie.length){
    el("svg:path", {d:ch(1), fill:"none", stroke:"var(--ink)", "stroke-width":2}, sv);
    el("svg:path", {d:ch(2), fill:"none", stroke:"var(--ink)", "stroke-width":2, "stroke-dasharray":"6 4"}, sv);
  }
  survol(sv, W, G, T, H - B, x, s.serie, p => [[pct(p[1]), "portent le ruban"], [pct(p[2]), "accord sur un sens"]]);
}
function aire(s){
  const box = $("aire"); box.textContent = "";
  if (!s.serie.length) return;
  const W = 560, H = 200, G = 40, B = 22, T = 10, jm = Math.max(s.jours, 1);
  const x = echelle(0, jm, G, W - 8), y = echelle(0, 1, H - B, T);
  const sv = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":"Répartition des sens"}, box);
  const cumul = s.serie.map(() => 0);
  s.sens.forEach((_, k) => {
    const bas = cumul.slice(), haut = s.serie.map((p, i) => (cumul[i] += p[3][k]));
    const d = s.serie.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(haut[i]).toFixed(1)}`).join("")
      + s.serie.map((_, i) => i).reverse().map(i => `L${x(s.serie[i][0]).toFixed(1)},${y(bas[i]).toFixed(1)}`).join("") + "Z";
    el("svg:path", {d, fill:coul(k), stroke:"var(--surface)", "stroke-width":1}, sv);
  });
  for (const v of [0, .5, 1]) el("svg:text", {x:G - 6, y:y(v) + 4, "text-anchor":"end", "font-size":11, fill:"var(--muted)"}, sv, pct(v));
  for (const v of grad(jm, 5)) el("svg:text", {x:x(v), y:H - 5, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, sv, "J" + v);
  survol(sv, W, G, T, H - B, x, s.serie, p => s.sens.map((sn, k) => [pct(p[3][k]), LIB[sn.cle]]).reverse());
}
function survol(sv, W, G, T, bas, x, serie, lignes){
  const ret = el("svg:line", {y1:T, y2:bas, stroke:"var(--ink2)", visibility:"hidden"}, sv);
  const z = el("svg:rect", {x:G, y:T, width:W - 8 - G, height:bas - T, fill:"transparent"}, sv);
  z.addEventListener("pointermove", e => {
    if (!serie.length) return;
    const bx = sv.getBoundingClientRect(), px = (e.clientX - bx.left) * W / bx.width;
    let b = serie[0]; for (const p of serie) if (Math.abs(x(p[0]) - px) < Math.abs(x(b[0]) - px)) b = p;
    ret.setAttribute("x1", x(b[0])); ret.setAttribute("x2", x(b[0])); ret.setAttribute("visibility", "visible");
    montrer(e, `jour ${nb(b[0], 1)}`, lignes(b));
  });
  z.addEventListener("pointerleave", () => { ret.setAttribute("visibility", "hidden"); cacher(); });
}

/* ---------- qualite ---------- */
function kv(box, lignes){ box.textContent = ""; const k = el("div", {class:"kv"}, box); for (const [l, v] of lignes){ el("span", {}, k, l); el("span", {}, k, v); } return k; }
function qualite(s){
  const q = s.qualite;
  const inc = Object.entries(q.incidents).sort((a, b) => b[1] - a[1]);
  const f = kv($("fiab"), [
    ["décisions LLM exploitables", q.decisions_llm ? `${nb(q.valides)} / ${nb(q.decisions_llm)} · ${pct(q.valides / q.decisions_llm)}` : "–"],
    ...inc.map(([n, c]) => ["⚠ " + n, nb(c)]),
    ["catégories ramenées (fautes de frappe)", nb(q.corrections)],
  ]);
  if (!inc.length) el("p", {class:"muted", style:"margin-top:6px"}, $("fiab"), "Aucun incident.");
  kv($("compo"), [
    ["changements d'avis (porte ↔ ne porte pas)", q.decisions ? `${nb(q.flips)} · ${pct(q.flips / q.decisions)} des décisions` : "–"],
    ["messages publiés", nb(q.publications)],
    ["dont adressés à une personne", nb(q.adresses)],
  ]);
  kv($("coher"), [
    ["contextes contrôlés (C6)", nb(q.c6_controles)],
    ["informations venues du futur", q.c6_violations ? "⚠ " + nb(q.c6_violations) : "0"],
    ["recherches dans la base", nb(q.rag_recherches)],
    ["passages retrouvés par décision", nb(q.rag_moy, 2)],
    ["recherches sans résultat", q.rag_recherches ? pct(q.rag_vides / q.rag_recherches) : "–"],
  ]);
  const fil = $("fil"); fil.textContent = "";
  if (!s.fil.length){ el("p", {class:"vide"}, fil, "Aucun message pour l'instant."); return; }
  const ul = el("ul", {}, fil);
  for (const m of s.fil){
    const li = el("li", {}, ul);
    el("b", {}, li, m.nom); li.append(m.portee === "personne" ? ` → ${m.vers} ` : " ");
    el("span", {class:"muted"}, li, `J${nb(m.jour, 1)} `);
    li.append(m.texte);
  }
}

/* ---------- boucle ---------- */
function legende(sens){
  const l = $("leg-sens"); if (l.childElementCount) return;
  sens.forEach((s, i) => { const sp = el("span", {title:s.texte}, l); el("span", {class:"cle", style:`background:${coul(i)}`}, sp); sp.append(LIB[s.cle]); });
}
async function rafraichir(){
  clearTimeout(minuterie);
  let s;
  try {
    const r = await fetch("/api/etat" + (choix ? "?run=" + encodeURIComponent(choix) : ""));
    s = await r.json();
  } catch (e) { s = {erreur: "serveur injoignable"}; }
  if (s.erreur){ $("infos").textContent = s.erreur; minuterie = setTimeout(rafraichir, 4000); return; }
  dernier = s; legende(s.sens);
  entete(s); tuiles(s); agents(s); modeles(s); nuage(s); barresJours(s); courbes(s); aire(s); qualite(s);
  minuterie = setTimeout(rafraichir, s.statut === "en_cours" ? 1500 : 10000);
}
async function listerRuns(){
  try {
    const runs = await (await fetch("/api/runs")).json();
    const sel = $("run"), garde = sel.value;
    while (sel.options.length > 1) sel.remove(1);
    for (const r of runs.slice(0, 80)) el("option", {value:r.nom}, sel, r.nom);
    sel.value = garde;
  } catch (e) {}
}
$("run").addEventListener("change", e => { choix = e.target.value; rafraichir(); });
listerRuns(); setInterval(listerRuns, 30000);
rafraichir();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
