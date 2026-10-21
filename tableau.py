"""Tableau de bord des runs : metriques, vitesses et agents. Aucun appel LLM.

    python3 tableau.py                      # tous les runs termines de runs/
    python3 tableau.py --sortie rapport.html
    python3 tableau.py runs/exp_complet_*.jsonl

Produit une page HTML autonome (aucune dependance, aucun acces reseau) qui
complete la scene Godot : Godot montre un run en direct, ce tableau compare les
runs entre eux, apres coup.

  Metriques a evaluer  par configuration, dispersion run par run (B3, E2)
  Dynamique            adoption et accord jour par jour, chaque run et la moyenne
  Vitesses             latence de chaque taille de modele, temps simule par
                       seconde reelle, cadence des agents, vitesse de la mode
  Agents               pour un run : sens du ruban au fil du temps, etat de
                       chaque agent chaque jour, ses decisions et leurs raisons
  Incidents            sorties de role par nature et par moteur (A4, A5)

Les chiffres viennent des memes fonctions que experience.py (mesurer,
accord_partage) : le tableau et le protocole ne peuvent pas diverger. Un run
sans bilan.v1 est en cours ou interrompu : il est ignore et signale.
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from ephemere.contrat import SENS  # noqa: E402
from experience import CONFIGURATIONS, accord_partage, mesurer  # noqa: E402

ORDRE_SENS = list(SENS)
SEUIL_EMERGENCE = 0.30
_NOM_EXP = re.compile(r"^exp_([a-z0-9]+)_(.+)_(\d+)$")


def identifier(nom):
    """exp_complet_llm_synchrone_03 -> ("complet", "llm_synchrone")."""
    m = _NOM_EXP.match(nom)
    if m:
        return m.group(1), m.group(2)
    return "autres", nom


def lire_run(chemin):
    """Resume d'un run pour le tableau, ou None s'il n'est pas termine."""
    with open(chemin, encoding="utf-8") as f:
        evs = [json.loads(ligne) for ligne in f if ligne.strip()]
    meta = next((e for e in evs if e["schema"] == "run.v1"), None)
    bilan = next((e for e in evs if e["schema"] == "bilan.v1"), None)
    if meta is None or bilan is None:
        return None
    nom = os.path.basename(chemin)[:-len(".jsonl")]
    plan, config = identifier(nom)
    pop = next((e for e in evs if e["schema"] == "population.v1"), {"agents": []})
    releves = [e for e in evs if e["schema"] == "indicateurs.v1"]
    decisions = [e for e in evs if e["schema"] == "decision.v1"]
    incidents = [e for e in evs if e["schema"] == "incident.v1"]
    energie = next((e for e in evs if e["schema"] == "energie.v1"), {})
    coherence = next((e for e in evs if e["schema"] == "coherence.v1"), {})
    m = mesurer(chemin) or {}

    # Le moteur reel vient des decisions : --tout-grand change celui de la population.
    moteur_de = {a["id"]: a.get("moteur", "?") for a in pop["agents"]}
    moteur_de.update({d["agent"]: d["moteur"] for d in decisions})
    nature_de = {(i["agent"], i["t_sim"]): i["nature"] for i in incidents}

    # Releves : jour, adoption, accord partage, repartition dans l'ordre de SENS.
    serie = []
    for e in releves:
        n = sum(e["repartition_sens"].values()) or 1
        serie.append([round(e["t_sim"] / 1440, 3), e["taux_adoption"], accord_partage(e),
                      [e["repartition_sens"].get(s, 0) / n for s in ORDRE_SENS]])

    # Etat de chaque agent a chaque releve, rejoue depuis les decisions.
    etat = {a["id"]: (bool(a.get("porte")), 0 if a.get("porte") else ORDRE_SENS.index("aucun_sens"))
            for a in pop["agents"]}
    grille = {aid: [] for aid in etat}
    i = 0
    ordre = sorted(range(len(decisions)), key=lambda k: decisions[k]["t_sim"])
    for e in releves:
        while i < len(ordre) and decisions[ordre[i]]["t_sim"] <= e["t_sim"]:
            d = decisions[ordre[i]]
            if d["categorie"] in SENS:
                etat[d["agent"]] = (d["porte"], ORDRE_SENS.index(d["categorie"]))
            i += 1
        for aid, (porte, cat) in etat.items():
            grille[aid].append(chr(ord("a") + cat + (6 if porte else 0)))

    detail = defaultdict(list)
    for d in decisions:
        regles = d["moteur"] == "regles"
        detail[d["agent"]].append([
            round(d["t_sim"] / 1440, 2), int(d["porte"]),
            ORDRE_SENS.index(d["categorie"]) if d["categorie"] in SENS else -1,
            int(d["valide"]), nature_de.get((d["agent"], d["t_sim"]), ""),
            "" if regles else d["sens"][:200], d["raison"][:200]])

    jours = meta["jours"] or 1
    par_profil = defaultdict(list)
    for a in pop["agents"]:
        par_profil[a["profil"]].append(len(detail.get(a["id"], [])) / jours)

    decisions_llm = sum(1 for d in decisions if d["moteur"] != "regles")
    adoptions = [s[1] for s in serie]
    jour_pic = serie[adoptions.index(max(adoptions))][0] if serie else None
    emergence = next((s[0] for s in serie if s[2] >= SEUIL_EMERGENCE), None)
    duree = bilan.get("duree_run_s") or 0
    kwh = energie.get("kwh")
    return {
        "nom": nom, "plan": plan, "config": config, "mode": meta["mode"],
        "graine": meta["graine"], "jours": meta["jours"], "n": meta["nb_agents"],
        "metriques": {
            "accord_max": m.get("accord_max"), "adoption_pic": m.get("adoption_pic"),
            "adoption_finale": m.get("adoption_finale"), "declin": m.get("declin"),
            "jour_pic": jour_pic, "jour_emergence": emergence,
            "taux_incidents": (len(incidents) / decisions_llm) if decisions_llm else None,
            "appels": bilan["appels"], "appels_grand": m.get("appels_grand", 0),
            "tokens": bilan["tokens_entree"] + bilan["tokens_sortie"],
            "wh": None if kwh is None else kwh * 1000,
            "duree_s": duree,
            "vitesse_sim": (meta["jours"] * 1440 / duree) if duree else None,
            "violations": coherence.get("violations"), "controles": coherence.get("controles"),
            "decisions_llm": decisions_llm,
        },
        "latences": {t: {"moy": c.get("latence_moy_s"), "max": c.get("latence_max_s"),
                         "appels": c.get("appels", 0), "modele": c.get("modele", "")}
                     for t, c in bilan.get("par_taille", {}).items()},
        "cadence": {p: statistics.mean(v) for p, v in par_profil.items() if v},
        "incidents": Counter(f"{moteur_de.get(i['agent'], '?')}|{i['nature']}" for i in incidents),
        "decisions_par_moteur": Counter(d["moteur"] for d in decisions),
        "agents": [{"id": a["id"], "nom": a["nom"], "profil": a["profil"], "groupe": a["groupe"],
                    "moteur": moteur_de.get(a["id"], a.get("moteur", "?")),
                    "grille": "".join(grille.get(a["id"], [])),
                    "decisions": detail.get(a["id"], [])}
                   for a in pop["agents"]],
        "serie": serie,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="*", help="fichiers .jsonl (defaut : tout runs/)")
    p.add_argument("--sortie", default=os.path.join(RACINE, "runs", "tableau.html"))
    args = p.parse_args()

    chemins = args.runs or sorted(glob.glob(os.path.join(RACINE, "runs", "*.jsonl")))
    chemins = [c for c in chemins if not c.endswith((".rejets.jsonl", ".traitement.jsonl"))]
    runs, ignores = [], []
    for c in chemins:
        r = lire_run(c)
        (runs if r else ignores).append(r or os.path.basename(c))

    ordre = list(CONFIGURATIONS)
    donnees = {
        "genere": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sens": [{"cle": k, "texte": v} for k, v in SENS.items()],
        "seuil": SEUIL_EMERGENCE,
        "configs": {k: {"titre": v["titre"], "attendu": v["attendu"], "rang": ordre.index(k)}
                    for k, v in CONFIGURATIONS.items()},
        "ignores": ignores,
        "runs": runs,
    }
    charge = json.dumps(donnees, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    os.makedirs(os.path.dirname(os.path.abspath(args.sortie)), exist_ok=True)
    with open(args.sortie, "w", encoding="utf-8") as f:
        f.write(MODELE.replace("__DONNEES__", charge))
    print(f"{len(runs)} runs dans {args.sortie} ({os.path.getsize(args.sortie) // 1024} Ko)")
    if ignores:
        print(f"{len(ignores)} run(s) ignore(s), en cours ou interrompu(s) : {', '.join(ignores[:5])}"
              + (" ..." if len(ignores) > 5 else ""))


MODELE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tableau des runs</title>
<style>
:root{
  color-scheme:light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --mark:#52514e; --wash:rgba(11,11,11,.05);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#d6d5ce;
  --critical:#d03b3b;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --mark:#c3c2b7; --wash:rgba(255,255,255,.06);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#44443f;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --mark:#c3c2b7; --wash:rgba(255,255,255,.06);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#44443f;
}
*{box-sizing:border-box}
body{margin:0; background:var(--page); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; padding:0 16px 64px}
main{max-width:1180px; margin:0 auto}
header{padding:28px 0 8px}
h1{font-size:1.6rem; margin:0 0 4px}
h2{font-size:1.15rem; margin:0 0 4px}
h3{font-size:.95rem; margin:0 0 6px; font-weight:600}
p{margin:0}
.sub{color:var(--ink2); font-size:.9rem}
.muted{color:var(--muted); font-size:.82rem}
.filtres{position:sticky; top:0; z-index:5; background:var(--page); display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; padding:12px 0; border-bottom:1px solid var(--border)}
.filtres label{font-size:.85rem; color:var(--ink2)}
select{font:inherit; font-size:.88rem; color:var(--ink); background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:4px 8px; max-width:100%}
.puces{display:flex; flex-wrap:wrap; gap:6px}
.puce{font:inherit; font-size:.8rem; border:1px solid var(--border); background:var(--surface); color:var(--ink2); border-radius:999px; padding:3px 10px; cursor:pointer}
.puce[aria-pressed="true"]{background:var(--ink); color:var(--surface); border-color:var(--ink)}
section{margin-top:34px}
.carte{background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px; margin-top:12px; min-width:0}
.grille2{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr)); gap:12px}
.grille3{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr)); gap:12px}
svg{display:block; width:100%; height:auto; overflow:visible}
svg text{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.defil{overflow-x:auto}
table{border-collapse:collapse; width:100%; font-size:.84rem; font-variant-numeric:tabular-nums}
th,td{text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); vertical-align:top}
th{color:var(--ink2); font-weight:600; font-size:.78rem}
td.num,th.num{text-align:right; white-space:nowrap}
.legende{display:flex; flex-wrap:wrap; gap:6px 16px; margin:8px 0; font-size:.82rem; color:var(--ink2)}
.legende span{display:inline-flex; align-items:center; gap:6px}
.cle{width:12px; height:12px; border-radius:3px; display:inline-block}
.cle-ligne{width:16px; height:0; border-top:2px solid var(--ink); display:inline-block}
.cle-tiret{width:16px; height:0; border-top:2px dashed var(--ink); display:inline-block}
#info{position:fixed; pointer-events:none; z-index:20; background:var(--surface); color:var(--ink); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:.8rem; box-shadow:0 4px 18px rgba(0,0,0,.12); display:none; max-width:300px}
#info .ligne{display:flex; align-items:center; gap:8px; white-space:nowrap}
#info b{font-weight:650; font-variant-numeric:tabular-nums}
#info .trait{width:12px; border-top:2px solid; display:inline-block}
#info .tete{color:var(--ink2); margin-bottom:4px}
.agents-lignes text{cursor:pointer}
.choisi{fill:var(--wash)}
.decisions{max-height:420px; overflow:auto}
.decisions li{display:grid; grid-template-columns:62px minmax(0,1fr); gap:10px; padding:7px 0; border-bottom:1px solid var(--grid); font-size:.84rem}
.decisions ul{list-style:none; margin:0; padding:0}
.puce-sens{display:inline-flex; align-items:center; gap:6px; font-weight:600}
.alerte{color:var(--critical); font-weight:600}
.alerte::before{content:"⚠ "}
.vide{color:var(--muted); font-style:italic; padding:12px 0}
.bouton{font:inherit; font-size:.8rem; background:transparent; color:var(--ink); border:1px solid var(--border); border-radius:6px; padding:3px 10px; cursor:pointer}
.hyp{font-size:.82rem; color:var(--ink2); margin:2px 0 0}
#t-metriques td:first-child{min-width:240px; max-width:320px}
.hyp b{color:var(--ink)}
</style>
</head>
<body>
<main>
<header>
  <h1>Tableau des runs</h1>
  <p class="sub" id="soustitre"></p>
</header>

<div class="filtres" role="group" aria-label="Filtres">
  <label>Série <select id="serie"></select></label>
  <div class="puces" id="configs" aria-label="Configurations"></div>
</div>

<section id="s-metriques">
  <h2>Métriques à évaluer</h2>
  <p class="sub">Une ligne par configuration, chaque point est un run. Le trait vertical marque la moyenne. Les configurations d'une même série partagent les mêmes graines.</p>
  <div class="carte defil"><table id="t-metriques"></table></div>
  <div class="grille2" id="strips"></div>
</section>

<section id="s-dynamique">
  <h2>Dynamique</h2>
  <p class="sub">Chaque run en trait fin, la moyenne des runs en trait épais. Survolez pour lire un jour.</p>
  <div class="grille2" id="dyn"></div>
</section>

<section id="s-vitesses">
  <h2>Vitesses</h2>
  <p class="sub">À quelle vitesse les agents pensent, à quelle vitesse le monde avance, à quelle vitesse la mode monte.</p>
  <div class="grille2" id="vit"></div>
  <div class="carte defil"><h3>Cadence des agents : décisions par agent et par jour simulé</h3><p class="muted">En synchrone, chacun décide une fois par jour (les pionnières une fois sur deux). En asynchrone, la cadence dépend du profil et du temps de réflexion.</p><table id="t-cadence"></table></div>
</section>

<section id="s-agents">
  <h2>Agents</h2>
  <div class="filtres" style="position:static; border:0; padding:6px 0 0"><label>Run <select id="run"></select></label></div>
  <div class="carte">
    <h3>Ce que le ruban veut dire sur le campus, jour après jour</h3>
    <div class="legende" id="leg-sens"></div>
    <div id="aire"></div>
    <p style="margin-top:8px"><button class="bouton" id="voir-table" aria-expanded="false">Voir en tableau</button></p>
    <div class="defil" id="table-sens" hidden></div>
  </div>
  <div class="grille2">
    <div class="carte defil">
      <h3>État de chaque agent</h3>
      <p class="muted">Couleur : sens du ruban pour l'agent. Point : il porte le ruban. Cliquez sur un agent pour lire ses décisions.</p>
      <div id="grille-agents"></div>
    </div>
    <div class="carte">
      <h3 id="agent-titre">Décisions</h3>
      <p class="muted" id="agent-sous"></p>
      <div class="decisions" id="agent-decisions"><p class="vide">Choisissez un agent.</p></div>
    </div>
  </div>
</section>

<section id="s-incidents">
  <h2>Incidents</h2>
  <p class="sub">Sorties de rôle et réponses inexploitables, par nature et par moteur, sur les runs filtrés. Le taux rapporte au nombre de décisions du moteur.</p>
  <div class="carte defil"><table id="t-incidents"></table></div>
</section>
</main>
<div id="info" role="status" aria-live="polite"></div>

<script id="donnees" type="application/json">__DONNEES__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("donnees").textContent);
const NS = "http://www.w3.org/2000/svg";
const SENS = D.sens;
const coul = i => i < 0 ? "var(--muted)" : `var(--s${i + 1})`;
const LIB_SENS = {cercle_creatif:"cercle créatif", tendance:"tendance", suivre_la_foule:"suivre la foule",
                  ringard:"ringard", ironie:"ironie", aucun_sens:"aucun sens"};
const PROFILS = ["pionnier","figure_populaire","suiveur","refractaire","ironique"];
const MOTEURS = ["llm_grand","llm_petit","regles"];
const etat = {serie:null, configs:new Set(), run:null, agent:null};

/* ---------- outils ---------- */
const $ = id => document.getElementById(id);
function el(tag, attrs, parent, texte){
  const n = tag.startsWith("svg:") ? document.createElementNS(NS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null) n.setAttribute(k, v);
  if (texte !== undefined) n.textContent = texte;
  if (parent) parent.appendChild(n);
  return n;
}
const pct = v => v == null ? "–" : Math.round(v * 100) + " %";
const nb = (v, d = 0) => v == null ? "–" : Number(v).toLocaleString("fr-FR", {maximumFractionDigits:d, minimumFractionDigits:d});
const moy = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
const et = a => { if (a.length < 2) return null; const m = moy(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
function echelle(d0, d1, r0, r1){ const k = (r1 - r0) / ((d1 - d0) || 1); return v => r0 + (v - d0) * k; }
function graduations(max, n = 4){
  if (max <= 0) return [0];
  const brut = max / n, p = 10 ** Math.floor(Math.log10(brut)), r = brut / p;
  const pas = (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * p;
  // La derniere graduation couvre toujours le maximum.
  const out = []; for (let v = 0; ; v += pas){ out.push(+v.toFixed(10)); if (v >= max - pas * 1e-9) break; } return out;
}
function libConfig(c){ return D.configs[c] ? c.replace(/_/g, " ") : c; }

/* ---------- info-bulle ---------- */
const info = $("info");
function montrer(evt, tete, lignes){
  info.textContent = "";
  if (tete) el("div", {class:"tete"}, info, tete);
  for (const l of lignes){
    const r = el("div", {class:"ligne"}, info);
    if (l.couleur) el("span", {class:"trait", style:`border-color:${l.couleur}`}, r);
    el("b", {}, r, l.valeur);
    el("span", {}, r, l.label);
  }
  info.style.display = "block";
  const x = evt.clientX ?? (evt.target.getBoundingClientRect().left + 10);
  const y = evt.clientY ?? (evt.target.getBoundingClientRect().top);
  const w = info.offsetWidth, h = info.offsetHeight;
  info.style.left = Math.min(window.innerWidth - w - 8, x + 14) + "px";
  info.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, y - h - 10)) + "px";
}
function cacher(){ info.style.display = "none"; }

/* ---------- selection ---------- */
function runsFiltres(){ return D.runs.filter(r => r.plan === etat.serie && etat.configs.has(r.config)); }
function configsDe(serie){
  const cs = [...new Set(D.runs.filter(r => r.plan === serie).map(r => r.config))];
  return cs.sort((a, b) => (D.configs[a]?.rang ?? 99) - (D.configs[b]?.rang ?? 99) || a.localeCompare(b));
}
function parConfig(runs){
  const m = new Map();
  for (const c of configsDe(etat.serie)) if (etat.configs.has(c)) m.set(c, []);
  for (const r of runs) m.get(r.config)?.push(r);
  for (const [c, rs] of m) if (!rs.length) m.delete(c);
  return m;
}

function initFiltres(){
  const series = [...new Set(D.runs.map(r => r.plan))];
  series.sort((a, b) => (b === "complet") - (a === "complet") || a.localeCompare(b));
  const sel = $("serie");
  for (const s of series){
    const n = D.runs.filter(r => r.plan === s).length;
    el("option", {value:s}, sel, `${s} (${n} runs)`);
  }
  sel.addEventListener("change", () => choisirSerie(sel.value));
  if (series.length) choisirSerie(series[0]);
}
function choisirSerie(s){
  etat.serie = s; $("serie").value = s;
  etat.configs = new Set(configsDe(s));
  const box = $("configs"); box.textContent = "";
  for (const c of configsDe(s)){
    const b = el("button", {class:"puce", type:"button", "aria-pressed":"true"}, box, libConfig(c));
    b.addEventListener("click", () => {
      if (etat.configs.has(c) && etat.configs.size > 1) etat.configs.delete(c); else etat.configs.add(c);
      b.setAttribute("aria-pressed", String(etat.configs.has(c)));
      rendre();
    });
  }
  rendre();
}

/* ---------- metriques ---------- */
const METRIQUES = [
  {cle:"accord_max", lib:"Accord max. sur un sens", f:pct, dom:[0,1], seuil:true},
  {cle:"adoption_pic", lib:"Adoption au pic", f:pct, dom:[0,1]},
  {cle:"adoption_finale", lib:"Adoption finale", f:pct, dom:[0,1]},
  {cle:"declin", lib:"Déclin après le pic", f:pct, dom:[0,1]},
  {cle:"jour_pic", lib:"Jour du pic", f:v => v == null ? "–" : "J" + nb(v, 1)},
  {cle:"jour_emergence", lib:"Jour où l'accord passe le seuil", f:v => v == null ? "–" : "J" + nb(v, 1)},
  {cle:"taux_incidents", lib:"Incidents / décision LLM", f:v => v == null ? "–" : nb(v * 100, 1) + " %", dom:[0,null]},
  {cle:"appels", lib:"Appels LLM", f:v => nb(v)},
  {cle:"tokens", lib:"Tokens", f:v => nb(v)},
  {cle:"wh", lib:"Énergie (Wh)", f:v => nb(v, 2)},
  {cle:"duree_s", lib:"Durée réelle (min)", f:v => nb(v / 60, 1)},
];
const STRIPS = ["accord_max", "adoption_pic", "declin", "jour_pic", "taux_incidents", "appels"];

function tableMetriques(groupes){
  const t = $("t-metriques"); t.textContent = "";
  const th = el("tr", {}, el("thead", {}, t));
  el("th", {}, th, "Configuration");
  el("th", {class:"num"}, th, "Runs");
  el("th", {class:"num"}, th, `Émergents (≥ ${Math.round(D.seuil * 100)} %)`);
  for (const m of METRIQUES) el("th", {class:"num"}, th, m.lib);
  el("th", {class:"num"}, th, "C6 : violations / contrôles");
  const tb = el("tbody", {}, t);
  for (const [c, rs] of groupes){
    const tr = el("tr", {}, tb);
    const td = el("td", {}, tr);
    el("div", {}, td, libConfig(c)).style.fontWeight = "600";
    if (D.configs[c]) { const h = el("p", {class:"hyp"}, td); el("b", {}, h, "Hypothèse : "); h.append(D.configs[c].attendu); }
    el("td", {class:"num"}, tr, rs.length);
    const em = rs.filter(r => (r.metriques.accord_max ?? 0) >= D.seuil).length;
    el("td", {class:"num"}, tr, `${em} / ${rs.length}`);
    for (const m of METRIQUES){
      const v = rs.map(r => r.metriques[m.cle]).filter(x => x != null);
      const cell = el("td", {class:"num"}, tr);
      if (!v.length){ cell.textContent = "–"; continue; }
      el("div", {}, cell, m.f(moy(v)));
      const s = et(v);
      el("div", {class:"muted"}, cell, (s != null ? "± " + m.f(s) + " · " : "") + `${m.f(Math.min(...v))} à ${m.f(Math.max(...v))}`);
    }
    const viol = rs.reduce((s, r) => s + (r.metriques.violations || 0), 0);
    const ctrl = rs.reduce((s, r) => s + (r.metriques.controles || 0), 0);
    el("td", {class:"num"}, tr, ctrl ? `${viol} / ${nb(ctrl)}` : "–");
  }
}

function strip(parent, m, groupes){
  const carte = el("div", {class:"carte"}, parent);
  el("h3", {}, carte, m.lib);
  const lignes = [...groupes].filter(([, rs]) => rs.some(r => r.metriques[m.cle] != null));
  if (!lignes.length){ el("p", {class:"vide"}, carte, "Pas de donnée pour ces runs."); return; }
  const W = 520, G = 132, D0 = 20, H = lignes.length * 34 + 30;
  const vals = lignes.flatMap(([, rs]) => rs.map(r => r.metriques[m.cle]).filter(v => v != null));
  let d1 = m.dom && m.dom[1] != null ? m.dom[1] : Math.max(...vals) * 1.08 || 1;
  if (m.dom && m.dom[1] == null) d1 = Math.max(...vals) * 1.15 || 0.01;
  let ticks, x;
  if (m.log){
    // Echelle logarithmique : les regles decident des milliers de fois plus vite qu'un LLM.
    const lo = Math.floor(Math.log10(Math.min(...vals.filter(v => v > 0)))), hi = Math.ceil(Math.log10(Math.max(...vals)));
    ticks = []; for (let e = lo; e <= hi; e++) ticks.push(10 ** e);
    const lx = echelle(lo, Math.max(hi, lo + 1), G, W - 12); x = v => lx(Math.log10(Math.max(v, 10 ** lo)));
  } else {
    ticks = m.dom && m.dom[1] === 1 ? [0, .25, .5, .75, 1] : graduations(d1);
    d1 = Math.max(d1, ticks[ticks.length - 1]);
    x = echelle(0, d1, G, W - 12);
  }
  const s = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":m.lib}, carte);
  for (const t of ticks){
    el("svg:line", {x1:x(t), x2:x(t), y1:6, y2:H - 22, stroke:"var(--grid)", "stroke-width":1}, s);
    el("svg:text", {x:x(t), y:H - 6, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, s, m.f(t));
  }
  if (m.seuil){
    el("svg:line", {x1:x(D.seuil), x2:x(D.seuil), y1:4, y2:H - 22, stroke:"var(--ink2)", "stroke-width":1.5, "stroke-dasharray":"4 3"}, s);
    el("svg:text", {x:x(D.seuil) + 4, y:12, "font-size":11, fill:"var(--ink2)"}, s, "seuil");
  }
  lignes.forEach(([c, rs], i) => {
    const y = D0 + i * 34;
    el("svg:text", {x:G - 10, y:y + 4, "text-anchor":"end", "font-size":12, fill:"var(--ink)"}, s, libConfig(c));
    const v = rs.filter(r => r.metriques[m.cle] != null);
    const mm = moy(v.map(r => r.metriques[m.cle]));
    el("svg:line", {x1:x(mm), x2:x(mm), y1:y - 10, y2:y + 10, stroke:"var(--ink)", "stroke-width":2.5, "stroke-linecap":"round"}, s);
    // Petit decalage vertical deterministe : les runs egaux restent visibles.
    const vus = new Map();
    for (const r of v){
      const val = r.metriques[m.cle], k = Math.round(x(val));
      const rang = vus.get(k) || 0; vus.set(k, rang + 1);
      const dy = (rang % 2 ? 1 : -1) * Math.ceil(rang / 2) * 4;
      el("svg:circle", {cx:x(val), cy:y + dy, r:4.5, fill:"var(--mark)", "fill-opacity":.8, stroke:"var(--surface)", "stroke-width":1.5}, s);
      const hit = el("svg:circle", {cx:x(val), cy:y + dy, r:12, fill:"transparent", tabindex:0}, s);
      const voir = e => montrer(e, `${libConfig(c)} · graine ${r.graine}`, [{valeur:m.f(val), label:m.lib}]);
      hit.addEventListener("pointermove", voir); hit.addEventListener("focus", voir);
      hit.addEventListener("pointerleave", cacher); hit.addEventListener("blur", cacher);
      hit.addEventListener("click", () => { choisirRun(r.nom); $("s-agents").scrollIntoView({behavior:"smooth"}); });
      hit.style.cursor = "pointer";
    }
  });
}

/* ---------- dynamique ---------- */
function courbes(parent, titre, indice, groupes, seuil){
  const carte = el("div", {class:"carte"}, parent);
  el("h3", {}, carte, titre);
  const leg = el("div", {class:"legende"}, carte);
  const a = el("span", {}, leg); el("span", {class:"cle-ligne"}, a); a.append("moyenne des runs");
  const b = el("span", {}, leg); el("span", {class:"cle-ligne", style:"border-top:1px solid var(--mark);opacity:.5"}, b); b.append("un run");
  for (const [c, rs] of groupes){
    const W = 520, H = 170, G = 40, B = 22, T = 18;
    const jmax = Math.max(...rs.flatMap(r => r.serie.map(p => p[0])), 1);
    const x = echelle(0, jmax, G, W - 8), y = echelle(0, 1, H - B, T);
    const s = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":`${titre}, ${libConfig(c)}`}, carte);
    el("svg:text", {x:G, y:12, "font-size":12, "font-weight":600, fill:"var(--ink)"}, s, `${libConfig(c)} · ${rs.length} run${rs.length > 1 ? "s" : ""}`);
    for (const t of [0, .5, 1]){
      el("svg:line", {x1:G, x2:W - 8, y1:y(t), y2:y(t), stroke:t ? "var(--grid)" : "var(--axis)", "stroke-width":1}, s);
      el("svg:text", {x:G - 6, y:y(t) + 4, "text-anchor":"end", "font-size":11, fill:"var(--muted)"}, s, pct(t));
    }
    for (const t of graduations(jmax, 5)) el("svg:text", {x:x(t), y:H - 6, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, s, "J" + t);
    if (seuil) el("svg:line", {x1:G, x2:W - 8, y1:y(D.seuil), y2:y(D.seuil), stroke:"var(--ink2)", "stroke-width":1, "stroke-dasharray":"4 3"}, s);
    for (const r of rs){
      const d = r.serie.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[indice]).toFixed(1)}`).join("");
      el("svg:path", {d, fill:"none", stroke:"var(--mark)", "stroke-opacity":.35, "stroke-width":1}, s);
    }
    // Moyenne par releve (memes jours d'une config a l'autre : meme grille de releves).
    const n = Math.max(...rs.map(r => r.serie.length));
    const pts = [];
    for (let i = 0; i < n; i++){
      const v = rs.filter(r => r.serie[i]).map(r => r.serie[i][indice]);
      const j = rs.find(r => r.serie[i]).serie[i][0];
      pts.push([j, moy(v), Math.min(...v), Math.max(...v), v.length]);
    }
    el("svg:path", {d:pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(""),
                    fill:"none", stroke:"var(--ink)", "stroke-width":2, "stroke-linejoin":"round"}, s);
    const reticule = el("svg:line", {y1:T, y2:H - B, stroke:"var(--ink2)", "stroke-width":1, visibility:"hidden"}, s);
    const zone = el("svg:rect", {x:G, y:T, width:W - 8 - G, height:H - B - T, fill:"transparent"}, s);
    zone.addEventListener("pointermove", e => {
      const box = s.getBoundingClientRect(), px = (e.clientX - box.left) * W / box.width;
      let best = pts[0]; for (const p of pts) if (Math.abs(x(p[0]) - px) < Math.abs(x(best[0]) - px)) best = p;
      reticule.setAttribute("x1", x(best[0])); reticule.setAttribute("x2", x(best[0])); reticule.setAttribute("visibility", "visible");
      montrer(e, `${libConfig(c)} · J${nb(best[0], 1)}`, [
        {valeur:pct(best[1]), label:"moyenne", couleur:"var(--ink)"},
        {valeur:`${pct(best[2])} à ${pct(best[3])}`, label:`étendue sur ${best[4]} runs`}]);
    });
    zone.addEventListener("pointerleave", () => { reticule.setAttribute("visibility", "hidden"); cacher(); });
  }
}

/* ---------- vitesses ---------- */
function barresLatence(parent, groupes){
  const tailles = MOTEURS.filter(t => t !== "regles" && [...groupes.values()].flat().some(r => r.latences[t]?.moy != null));
  for (const t of tailles){
    const carte = el("div", {class:"carte"}, parent);
    const modeles = [...new Set([...groupes.values()].flat().map(r => r.latences[t]?.modele).filter(Boolean))];
    el("h3", {}, carte, `Temps de réflexion · ${t.replace("llm_", "modèle ")}`);
    el("p", {class:"muted"}, carte, `${modeles.join(", ")}. Barre : latence moyenne par appel. Trait : pire appel observé.`);
    const lignes = [...groupes].filter(([, rs]) => rs.some(r => r.latences[t]?.moy != null));
    const W = 520, G = 132, H = lignes.length * 30 + 28;
    const vmax = Math.max(...lignes.flatMap(([, rs]) => rs.map(r => r.latences[t]?.max || 0)), 1);
    const ticks = graduations(vmax), x = echelle(0, ticks[ticks.length - 1], G, W - 70);
    const s = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":`Latence ${t}`}, carte);
    for (const v of ticks){
      el("svg:line", {x1:x(v), x2:x(v), y1:4, y2:H - 22, stroke:v ? "var(--grid)" : "var(--axis)"}, s);
      el("svg:text", {x:x(v), y:H - 6, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, s, nb(v) + " s");
    }
    lignes.forEach(([c, rs], i) => {
      const y = 10 + i * 30;
      const m = moy(rs.map(r => r.latences[t]?.moy).filter(v => v != null));
      const pire = Math.max(...rs.map(r => r.latences[t]?.max || 0));
      const appels = rs.reduce((a, r) => a + (r.latences[t]?.appels || 0), 0);
      el("svg:text", {x:G - 10, y:y + 12, "text-anchor":"end", "font-size":12, fill:"var(--ink)"}, s, libConfig(c));
      el("svg:line", {x1:x(m), x2:x(pire), y1:y + 8, y2:y + 8, stroke:"var(--mark)", "stroke-width":1.5}, s);
      el("svg:line", {x1:x(pire), x2:x(pire), y1:y + 3, y2:y + 13, stroke:"var(--mark)", "stroke-width":1.5}, s);
      el("svg:rect", {x:G, y:y + 1, width:Math.max(1, x(m) - G), height:14, rx:3, fill:"var(--mark)"}, s);
      el("svg:text", {x:x(pire) + 6, y:y + 12, "font-size":11, fill:"var(--ink2)"}, s, `${nb(m, 1)} s`);
      const hit = el("svg:rect", {x:G, y, width:W - G, height:18, fill:"transparent", tabindex:0}, s);
      const voir = e => montrer(e, `${libConfig(c)} · ${t}`, [
        {valeur:`${nb(m, 2)} s`, label:"latence moyenne"}, {valeur:`${nb(pire, 2)} s`, label:"pire appel"},
        {valeur:nb(appels), label:`appels sur ${rs.length} runs`}]);
      hit.addEventListener("pointermove", voir); hit.addEventListener("focus", voir);
      hit.addEventListener("pointerleave", cacher); hit.addEventListener("blur", cacher);
    });
  }
  if (!tailles.length){
    const carte = el("div", {class:"carte"}, parent);
    el("h3", {}, carte, "Temps de réflexion des modèles");
    el("p", {class:"vide"}, carte, "Aucun agent LLM dans ces runs : tout est décidé par des règles, instantanément.");
  }
}

function tableCadence(groupes){
  const t = $("t-cadence"); t.textContent = "";
  const profils = PROFILS.filter(p => [...groupes.values()].flat().some(r => r.cadence[p] != null));
  const th = el("tr", {}, el("thead", {}, t));
  el("th", {}, th, "Configuration"); el("th", {}, th, "Mode");
  for (const p of profils) el("th", {class:"num"}, th, p.replace("_", " "));
  const tb = el("tbody", {}, t);
  for (const [c, rs] of groupes){
    const tr = el("tr", {}, tb);
    el("td", {}, tr, libConfig(c)); el("td", {}, tr, rs[0].mode);
    for (const p of profils) el("td", {class:"num"}, tr, nb(moy(rs.map(r => r.cadence[p]).filter(v => v != null)), 2));
  }
}

/* ---------- agents ---------- */
function choisirRun(nom){
  etat.run = nom; etat.agent = null;
  const sel = $("run"); if (sel.value !== nom) sel.value = nom;
  rendreRun();
}
function listeRuns(runs){
  const sel = $("run"); sel.textContent = "";
  for (const r of runs) el("option", {value:r.nom}, sel, `${libConfig(r.config)} · graine ${r.graine} · ${r.mode}`);
  if (!runs.some(r => r.nom === etat.run)) etat.run = runs[0]?.nom ?? null;
  if (etat.run) sel.value = etat.run;
}
function legendeSens(){
  const leg = $("leg-sens"); leg.textContent = "";
  SENS.forEach((s, i) => { const sp = el("span", {title:s.texte}, leg); el("span", {class:"cle", style:`background:${coul(i)}`}, sp); sp.append(LIB_SENS[s.cle]); });
  const sp = el("span", {}, leg); el("span", {class:"cle-tiret"}, sp); sp.append("part des porteurs");
}
function rendreRun(){
  const r = D.runs.find(x => x.nom === etat.run);
  const aire = $("aire"), grille = $("grille-agents"); aire.textContent = ""; grille.textContent = "";
  $("agent-decisions").textContent = ""; $("agent-titre").textContent = "Décisions"; $("agent-sous").textContent = "";
  if (!r){ el("p", {class:"vide"}, aire, "Aucun run pour ce filtre."); return; }
  el("p", {class:"vide"}, $("agent-decisions"), "Choisissez un agent.");

  // Aire empilee : repartition des sens, et la part des porteurs en tirets.
  const W = 900, H = 240, G = 40, B = 22, T = 8;
  const jmax = Math.max(...r.serie.map(p => p[0]), 1);
  const x = echelle(0, jmax, G, W - 8), y = echelle(0, 1, H - B, T);
  const s = el("svg:svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":"Répartition des sens du ruban"}, aire);
  const cumul = r.serie.map(() => 0);
  SENS.forEach((_, k) => {
    const bas = r.serie.map((p, i) => cumul[i]);
    const haut = r.serie.map((p, i) => (cumul[i] += p[3][k]));
    const d = r.serie.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(haut[i]).toFixed(1)}`).join("")
      + r.serie.map((p, i) => i).reverse().map(i => `L${x(r.serie[i][0]).toFixed(1)},${y(bas[i]).toFixed(1)}`).join("") + "Z";
    el("svg:path", {d, fill:coul(k), stroke:"var(--surface)", "stroke-width":1}, s);
  });
  for (const t of [0, .5, 1]) el("svg:text", {x:G - 6, y:y(t) + 4, "text-anchor":"end", "font-size":11, fill:"var(--muted)"}, s, pct(t));
  for (const t of graduations(jmax, 6)) el("svg:text", {x:x(t), y:H - 6, "text-anchor":"middle", "font-size":11, fill:"var(--muted)"}, s, "J" + t);
  el("svg:path", {d:r.serie.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(""),
                  fill:"none", stroke:"var(--ink)", "stroke-width":2, "stroke-dasharray":"6 4"}, s);
  const ret = el("svg:line", {y1:T, y2:H - B, stroke:"var(--ink)", "stroke-width":1, visibility:"hidden"}, s);
  const zone = el("svg:rect", {x:G, y:T, width:W - 8 - G, height:H - B - T, fill:"transparent"}, s);
  zone.addEventListener("pointermove", e => {
    const box = s.getBoundingClientRect(), px = (e.clientX - box.left) * W / box.width;
    let bi = 0; r.serie.forEach((p, i) => { if (Math.abs(x(p[0]) - px) < Math.abs(x(r.serie[bi][0]) - px)) bi = i; });
    const p = r.serie[bi];
    ret.setAttribute("x1", x(p[0])); ret.setAttribute("x2", x(p[0])); ret.setAttribute("visibility", "visible");
    montrer(e, `J${nb(p[0], 1)}`, [{valeur:pct(p[1]), label:"portent le ruban", couleur:"var(--ink)"},
      ...SENS.map((sn, k) => ({valeur:pct(p[3][k]), label:LIB_SENS[sn.cle], couleur:coul(k)})).reverse()]);
  });
  zone.addEventListener("pointerleave", () => { ret.setAttribute("visibility", "hidden"); cacher(); });

  // Vue tableau, pour lire sans survol.
  const tab = $("table-sens"); tab.textContent = "";
  const t = el("table", {}, tab), th = el("tr", {}, el("thead", {}, t));
  el("th", {}, th, "Jour"); el("th", {class:"num"}, th, "Porteurs");
  for (const sn of SENS) el("th", {class:"num"}, th, LIB_SENS[sn.cle]);
  const tb = el("tbody", {}, t);
  for (const p of r.serie){
    const tr = el("tr", {}, tb);
    el("td", {}, tr, "J" + nb(p[0], 1)); el("td", {class:"num"}, tr, pct(p[1]));
    for (const v of p[3]) el("td", {class:"num"}, tr, pct(v));
  }

  // Grille agents x releves.
  const agents = [...r.agents].sort((a, b) => PROFILS.indexOf(a.profil) - PROFILS.indexOf(b.profil) || a.nom.localeCompare(b.nom));
  const nc = Math.max(...agents.map(a => a.grille.length), 1);
  const GL = 230, C = Math.max(9, Math.min(22, Math.floor((900 - GL) / nc))), L = 20;
  const WG = GL + nc * C + 8, HG = agents.length * L + 24;
  const g = el("svg:svg", {viewBox:`0 0 ${WG} ${HG}`, role:"img", "aria-label":"État de chaque agent, jour par jour", class:"agents-lignes", style:`min-width:${Math.min(WG, 560)}px`}, grille);
  for (let j = 0; j < nc; j += Math.max(1, Math.round(nc / 8)))
    el("svg:text", {x:GL + j * C + C / 2, y:HG - 6, "text-anchor":"middle", "font-size":10, fill:"var(--muted)"}, g, "J" + nb(r.serie[j]?.[0] ?? j, 0));
  agents.forEach((a, i) => {
    const y0 = i * L;
    const fond = el("svg:rect", {x:0, y:y0, width:WG, height:L, fill:"transparent"}, g);
    const lib = el("svg:text", {x:4, y:y0 + 14, "font-size":11.5, fill:"var(--ink)", tabindex:0, role:"button"}, g);
    el("svg:tspan", {"font-weight":600}, lib, a.nom);
    el("svg:tspan", {fill:"var(--ink2)"}, lib, `  ${a.profil.replace("_", " ")} · ${a.moteur.replace("llm_", "")}`);
    [...a.grille].forEach((ch, j) => {
      const code = ch.charCodeAt(0) - 97, porte = code >= 6, k = code % 6;
      const cx = GL + j * C;
      const cell = el("svg:rect", {x:cx + 1, y:y0 + 2, width:C - 2, height:L - 4, rx:2, fill:coul(k)}, g);
      if (porte) el("svg:circle", {cx:cx + C / 2, cy:y0 + L / 2, r:Math.min(3.2, C / 4), fill:"var(--ink)", stroke:"var(--surface)", "stroke-width":1}, g);
      cell.addEventListener("pointermove", e => montrer(e, `${a.nom} · J${nb(r.serie[j]?.[0] ?? j, 1)}`,
        [{valeur:LIB_SENS[SENS[k].cle], label:porte ? "porte le ruban" : "ne le porte pas", couleur:coul(k)}]));
      cell.addEventListener("pointerleave", cacher);
      cell.addEventListener("click", () => choisirAgent(r, a, fond));
      cell.style.cursor = "pointer";
    });
    lib.addEventListener("click", () => choisirAgent(r, a, fond));
    lib.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choisirAgent(r, a, fond); } });
  });
}
function choisirAgent(r, a, fond){
  document.querySelectorAll(".agents-lignes .choisi").forEach(n => n.classList.remove("choisi"));
  fond.classList.add("choisi");
  $("agent-titre").textContent = a.nom;
  $("agent-sous").textContent = `${a.profil.replace("_", " ")} · ${a.groupe.replace("_", " ")} · moteur ${a.moteur} · ${a.decisions.length} décisions`;
  const box = $("agent-decisions"); box.textContent = "";
  if (!a.decisions.length){ el("p", {class:"vide"}, box, "Aucune décision enregistrée."); return; }
  const ul = el("ul", {}, box);
  for (const [jour, porte, k, valide, nature, sens, raison] of a.decisions){
    const li = el("li", {}, ul);
    el("span", {class:"muted"}, li, "J" + nb(jour, 2));
    const d = el("div", {}, li);
    const tete = el("div", {}, d);
    const ps = el("span", {class:"puce-sens"}, tete);
    el("span", {class:"cle", style:`background:${coul(k)}`}, ps);
    ps.append(k >= 0 ? LIB_SENS[SENS[k].cle] : "hors liste");
    tete.append(porte ? " · porte le ruban" : " · ne le porte pas");
    if (!valide) el("div", {class:"alerte"}, d, `décision inexploitable : ${nature || "?"}`);
    if (sens) el("div", {}, d, `« ${sens} »`);
    if (raison) el("div", {class:"muted"}, d, raison);
  }
}

/* ---------- incidents ---------- */
function tableIncidents(runs){
  const t = $("t-incidents"); t.textContent = "";
  const comptes = {}, dec = {};
  for (const r of runs){
    for (const [k, n] of Object.entries(r.incidents)) comptes[k] = (comptes[k] || 0) + n;
    for (const [m, n] of Object.entries(r.decisions_par_moteur)) dec[m] = (dec[m] || 0) + n;
  }
  const moteurs = MOTEURS.filter(m => dec[m]);
  const natures = [...new Set(Object.keys(comptes).map(k => k.split("|")[1]))].sort();
  const th = el("tr", {}, el("thead", {}, t));
  el("th", {}, th, "Nature");
  for (const m of moteurs) el("th", {class:"num"}, th, `${m} (${nb(dec[m])} déc.)`);
  const tb = el("tbody", {}, t);
  if (!natures.length){ const tr = el("tr", {}, tb); el("td", {colspan:moteurs.length + 1, class:"vide"}, tr, "Aucun incident sur ces runs."); return; }
  for (const n of [...natures, "total"]){
    const tr = el("tr", {}, tb);
    el("td", {}, tr, n === "total" ? "Total" : n).style.fontWeight = n === "total" ? "600" : "";
    for (const m of moteurs){
      const c = n === "total" ? natures.reduce((s, x) => s + (comptes[`${m}|${x}`] || 0), 0) : (comptes[`${m}|${n}`] || 0);
      el("td", {class:"num"}, tr, c ? `${c} · ${nb(100 * c / dec[m], 1)} %` : "–");
    }
  }
}

/* ---------- rendu ---------- */
function rendre(){
  const runs = runsFiltres(), groupes = parConfig(runs);
  $("soustitre").textContent = `${D.runs.length} runs terminés lus le ${D.genere}`
    + (D.ignores.length ? ` · ${D.ignores.length} run(s) en cours ou interrompu(s), ignoré(s)` : "")
    + ` · série « ${etat.serie} » : ${runs.length} runs affichés`;
  tableMetriques(groupes);
  const st = $("strips"); st.textContent = "";
  for (const k of STRIPS) strip(st, METRIQUES.find(m => m.cle === k), groupes);
  const dyn = $("dyn"); dyn.textContent = "";
  courbes(dyn, "Part des agents qui portent le ruban", 1, groupes, false);
  courbes(dyn, "Accord sur un sens partagé (hors « aucun sens »)", 2, groupes, true);
  const vit = $("vit"); vit.textContent = "";
  barresLatence(vit, groupes);
  const carte = el("div", {class:"carte"}, vit);
  strip(carte, {cle:"vitesse_sim", lib:"Temps simulé par seconde réelle (minutes, échelle log.)", log:true, f:v => nb(v, v > 0 && v < 10 ? 1 : 0)}, groupes);
  strip(carte, {cle:"jour_emergence", lib:"Vitesse de la mode : jour où l'accord passe le seuil", f:v => v == null ? "–" : "J" + nb(v, 1)}, groupes);
  carte.querySelectorAll(":scope > .carte").forEach(c => { c.style.border = "0"; c.style.padding = "0"; c.style.marginTop = "14px"; });
  tableCadence(groupes);
  listeRuns(runs);
  rendreRun();
  tableIncidents(runs);
}

$("run").addEventListener("change", e => choisirRun(e.target.value));
$("voir-table").addEventListener("click", e => {
  const tab = $("table-sens"), ouvert = tab.hidden;
  tab.hidden = !ouvert; e.target.setAttribute("aria-expanded", String(ouvert));
  e.target.textContent = ouvert ? "Masquer le tableau" : "Voir en tableau";
});
legendeSens();
if (D.runs.length) initFiltres();
else $("soustitre").textContent = "Aucun run terminé dans runs/.";
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
