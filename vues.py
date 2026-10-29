"""Page commune a direct.py et tableau.py : deux onglets, les memes informations.

  Suivre un run      un run, en direct ou apres coup : avancement, agents,
                     performances des modeles appel par appel, phenomene,
                     fiabilite, comportement, coherence, messages
  Comparer les runs  les runs entre eux : metriques a evaluer, dynamique,
                     vitesses, etat de chaque agent jour par jour, incidents

direct.py sert la page et la nourrit en direct (/api/etat, /api/runs,
/api/tableau). tableau.py l'ecrit en HTML autonome, les memes donnees figees
dedans : aucune dependance, aucun acces reseau.
"""
import json


def page(statique=None):
    """La page HTML. statique : donnees figees (tableau.py), ou None (direct.py)."""
    charge = "null" if statique is None else json.dumps(
        statique, ensure_ascii=False, separators=(",", ":"))
    return PAGE.replace("__STATIQUE__", charge.replace("</", "<\\/"))


PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Runs d'Éphémère</title>
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
body{margin:0; background:var(--page); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; padding:0 16px 64px}
main{max-width:1280px; margin:0 auto}
h1{font-size:1.45rem; margin:0}
h2{font-size:1.1rem; margin:0 0 6px}
h3{font-size:.92rem; margin:0 0 6px; font-weight:600}
p{margin:0}
.sub{color:var(--ink2); font-size:.88rem}
.muted{color:var(--muted); font-size:.8rem}
select{font:inherit; font-size:.86rem; color:var(--ink); background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:4px 8px; max-width:100%}
section{margin-top:30px}
.carte{background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; min-width:0}
svg{display:block; width:100%; height:auto; overflow:visible}
svg text{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.defil{overflow-x:auto}
table{border-collapse:collapse; width:100%; font-size:.83rem; font-variant-numeric:tabular-nums}
th,td{text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); vertical-align:top}
th{color:var(--ink2); font-weight:600; font-size:.76rem}
.legende{display:flex; flex-wrap:wrap; gap:6px 16px; margin:8px 0; font-size:.8rem; color:var(--ink2)}
.legende span{display:inline-flex; align-items:center; gap:6px}
.cle{width:12px; height:12px; border-radius:3px; display:inline-block}
.cle-ligne{width:16px; height:0; border-top:2px solid var(--ink); display:inline-block}
.cle-tiret{width:16px; height:0; border-top:2px dashed var(--ink); display:inline-block}
.alerte{color:var(--critical); font-weight:600}
.vide{color:var(--muted); font-style:italic; font-size:.84rem; padding:10px 0}
#info{position:fixed; pointer-events:none; z-index:20; background:var(--surface); color:var(--ink); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:.8rem; box-shadow:0 4px 18px rgba(0,0,0,.12); display:none; max-width:320px}
#info .ligne{display:flex; align-items:center; gap:8px; white-space:nowrap}
#info b{font-weight:650; font-variant-numeric:tabular-nums}
#info .trait{width:12px; border-top:2px solid; display:inline-block}
#info .tete{color:var(--ink2); margin-bottom:4px}
@keyframes pouls{50%{opacity:.25}}

/* onglets */
.onglets{max-width:1280px; margin:0 auto; display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:14px 0 4px}
.onglets .marque{font-weight:700; margin-right:8px}
.onglets button{font:inherit; font-size:.88rem; background:transparent; color:var(--ink2); border:1px solid var(--border); border-radius:999px; padding:4px 14px; cursor:pointer}
.onglets button[aria-selected="true"]{background:var(--ink); color:var(--surface); border-color:var(--ink)}

/* vue « Suivre un run » */
#vue-run .barre{position:sticky; top:0; z-index:5; background:var(--page); padding:10px 0; border-bottom:1px solid var(--border)}
#vue-run .ligne-titre{display:flex; flex-wrap:wrap; align-items:center; gap:8px 16px}
#vue-run .statut{display:inline-flex; align-items:center; gap:6px; font-size:.82rem; font-weight:600; padding:2px 10px; border-radius:999px; border:1px solid var(--border)}
#vue-run .statut i{width:8px; height:8px; border-radius:50%; display:inline-block}
#vue-run .en_cours i{background:var(--good); animation:pouls 1.4s infinite}
#vue-run .termine i{background:var(--muted)}
#vue-run .interrompu i{background:var(--critical)}
#vue-run .progres{height:6px; background:var(--grid); border-radius:999px; margin-top:10px; overflow:hidden}
#vue-run .progres div{height:100%; background:var(--ink); border-radius:999px; transition:width .6s}
#vue-run .infos{display:flex; flex-wrap:wrap; gap:4px 18px; margin-top:6px; font-size:.8rem; color:var(--ink2); font-variant-numeric:tabular-nums}
#vue-run .infos b{color:var(--ink); font-weight:600}
#vue-run .tuiles{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr)); gap:10px; margin-top:16px}
#vue-run .tuile{background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:10px 12px; min-width:0}
#vue-run .tuile .v{font-size:1.45rem; font-weight:650; line-height:1.2}
#vue-run .tuile .l{font-size:.76rem; color:var(--ink2)}
#vue-run .tuile .d{font-size:.74rem; color:var(--muted)}
#vue-run section{margin-top:26px}
#vue-run .g2{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr)); gap:12px}
#vue-run .g3{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr)); gap:12px}
#vue-run th{white-space:nowrap}
#vue-run td{white-space:nowrap; vertical-align:middle}
#vue-run td.n,#vue-run th.n{text-align:right}
#vue-run tr.reflechit{background:var(--wash)}
#vue-run .etat{display:inline-flex; align-items:center; gap:5px; white-space:nowrap; font-size:.78rem}
#vue-run .etat i{width:8px; height:8px; border-radius:50%; display:inline-block; border:1.5px solid var(--muted)}
#vue-run .etat.reflechit i{border-color:var(--warning); background:var(--warning); animation:pouls 1s infinite}
#vue-run .etat.a_repondu i{border-color:var(--good); background:var(--good)}
#vue-run .etat.attend i{border-style:dotted}
#vue-run .cle{width:11px; height:11px; vertical-align:-1px; margin-right:5px}
#vue-run .ruban{font-size:.95rem}
#vue-run .raison{color:var(--ink2); max-width:340px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
#vue-run .cle-rond{width:9px; height:9px; border-radius:50%; display:inline-block; background:var(--mark)}
#vue-run .cle-rond.ko{background:transparent; border:2px solid var(--critical)}
#vue-run .fil li{padding:6px 0; border-bottom:1px solid var(--grid); font-size:.82rem}
#vue-run .fil ul{list-style:none; margin:0; padding:0}
#vue-run .kv{display:grid; grid-template-columns:auto auto; gap:3px 14px; font-size:.82rem; font-variant-numeric:tabular-nums}
#vue-run .kv span:nth-child(odd){color:var(--ink2)}
#vue-run .kv span:nth-child(even){text-align:right; font-weight:600}
#vue-run .note{font-size:.78rem; color:var(--ink2); background:var(--wash); border-radius:6px; padding:6px 10px; margin-top:10px}

/* vue « Comparer les runs » */
#vue-comparaison header{padding:10px 0 8px}
#vue-comparaison .filtres{position:sticky; top:0; z-index:5; background:var(--page); display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; padding:12px 0; border-bottom:1px solid var(--border)}
#vue-comparaison .filtres label{font-size:.85rem; color:var(--ink2)}
#vue-comparaison .puces{display:flex; flex-wrap:wrap; gap:6px}
#vue-comparaison .puce{font:inherit; font-size:.8rem; border:1px solid var(--border); background:var(--surface); color:var(--ink2); border-radius:999px; padding:3px 10px; cursor:pointer}
#vue-comparaison .puce[aria-pressed="true"]{background:var(--ink); color:var(--surface); border-color:var(--ink)}
#vue-comparaison section{margin-top:34px}
#vue-comparaison .carte{margin-top:12px}
#vue-comparaison .grille2{display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr)); gap:12px}
#vue-comparaison td.num,#vue-comparaison th.num{text-align:right; white-space:nowrap}
#vue-comparaison .agents-lignes text{cursor:pointer}
#vue-comparaison .choisi{fill:var(--wash)}
#vue-comparaison .decisions{max-height:420px; overflow:auto}
#vue-comparaison .decisions li{display:grid; grid-template-columns:62px minmax(0,1fr); gap:10px; padding:7px 0; border-bottom:1px solid var(--grid); font-size:.84rem}
#vue-comparaison .decisions ul{list-style:none; margin:0; padding:0}
#vue-comparaison .puce-sens{display:inline-flex; align-items:center; gap:6px; font-weight:600}
#vue-comparaison .alerte::before{content:"⚠ "}
#vue-comparaison .bouton{font:inherit; font-size:.8rem; background:transparent; color:var(--ink); border:1px solid var(--border); border-radius:6px; padding:3px 10px; cursor:pointer}
#vue-comparaison .hyp{font-size:.82rem; color:var(--ink2); margin:2px 0 0}
#vue-comparaison .hyp b{color:var(--ink)}
#t-metriques td:first-child{min-width:240px; max-width:320px}
</style>
</head>
<body>
<nav class="onglets" role="tablist" aria-label="Vues">
  <span class="marque">Éphémère</span>
  <button type="button" role="tab" id="onglet-run" aria-controls="vue-run" aria-selected="false">Suivre un run</button>
  <button type="button" role="tab" id="onglet-comparaison" aria-controls="vue-comparaison" aria-selected="false">Comparer les runs</button>
</nav>

<main id="vue-run" role="tabpanel" aria-labelledby="onglet-run" hidden>
<div class="barre">
  <div class="ligne-titre">
    <h1>Suivre un run</h1>
    <span class="statut" id="statut"><i></i><span>–</span></span>
    <label class="sub">Run <select id="d-run"><option value="">le plus récent</option></select></label>
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
      <div class="legende" id="d-leg-sens"></div>
      <div id="d-aire"></div></div>
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

<main id="vue-comparaison" role="tabpanel" aria-labelledby="onglet-comparaison" hidden>
<header>
  <h1>Comparer les runs</h1>
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
  <div class="filtres" style="position:static; border:0; padding:6px 0 0">
    <label>Run <select id="run"></select></label>
    <button class="bouton" type="button" id="vers-suivi">Ouvrir dans « Suivre un run »</button>
  </div>
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

<script id="statique" type="application/json">__STATIQUE__</script>
<script>
"use strict";
// null quand direct.py sert la page ; donnees figees quand tableau.py l'a ecrite.
const STATIQUE = JSON.parse(document.getElementById("statique").textContent);
</script>

<script>
/* ==================== Suivre un run ==================== */
(() => {
"use strict";
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const LIB = {cercle_creatif:"cercle créatif", tendance:"tendance", suivre_la_foule:"suivre la foule", ringard:"ringard", ironie:"ironie", aucun_sens:"aucun sens"};
const coul = i => i < 0 ? "var(--muted)" : `var(--s${i + 1})`;
const ETATS = {reflechit:"réfléchit", attend:"en attente", a_repondu:"a répondu", repos:"–", pause:"pas ce jour"};
let choix = "", minuterie = null;

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
  info.textContent = ""; if (tete) el("div", {class:"tete"}, info, tete);
  for (const [v, l] of lignes){ const d = el("div", {}, info); el("b", {}, d, v); d.append(" " + l); }
  info.style.display = "block";
  info.style.left = Math.min(innerWidth - info.offsetWidth - 8, e.clientX + 14) + "px";
  info.style.top = Math.max(8, e.clientY - info.offsetHeight - 10) + "px";
}
const cacher = () => info.style.display = "none";

/* ---------- en-tete ---------- */
function entete(s){
  const st = $("statut"); st.className = "statut " + s.statut;
  st.lastChild.textContent = {en_cours:STATIQUE ? "en cours à l'export" : "en cours", termine:"terminé", interrompu:"interrompu"}[s.statut];
  const a = s.avancement, part = Math.min(1, a.t_sim / (s.jours * 1440));
  $("progres").firstChild.style.width = (part * 100).toFixed(1) + "%";
  $("progres").setAttribute("aria-valuenow", Math.round(part * 100));
  const inf = $("infos"); inf.textContent = "";
  const champ = (l, v) => { const sp = el("span", {}, inf); sp.append(l + " "); el("b", {}, sp, v); };
  champ("", s.nom); champ("mode", s.mode); champ("graine", s.graine); champ("agents", s.nb_agents);
  champ("jour simulé", `${nb(a.jour, 1)} / ${s.jours}`); champ("temps écoulé", duree(a.ecoule_s));
  champ("rythme", a.rythme == null ? "–" : `${nb(a.rythme, a.rythme < 10 ? 1 : 0)} min simulées / s`);
  if (s.statut === "en_cours" && !STATIQUE) champ("fin estimée dans", duree(a.restant_s));
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
    el("td", {class:"n" + (a.incidents ? " alerte" : "")}, tr, a.incidents ? "⚠ " + a.incidents : "0");
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
      el("svg:circle", {cx:x(p[0]), cy:y(p[1]), r:3.5, fill:p[4] ? "var(--mark)" : "transparent",
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
  const box = $("d-aire"); box.textContent = "";
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
  kv($("fiab"), [
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
  const l = $("d-leg-sens"); if (l.childElementCount) return;
  sens.forEach((s, i) => { const sp = el("span", {title:s.texte}, l); el("span", {class:"cle", style:`background:${coul(i)}`}, sp); sp.append(LIB[s.cle]); });
}
async function charger(){
  if (STATIQUE) return STATIQUE.etats[choix || STATIQUE.runs[0]?.nom] || {erreur: "aucun run"};
  const r = await fetch("/api/etat" + (choix ? "?run=" + encodeURIComponent(choix) : ""));
  return r.json();
}
async function rafraichir(){
  clearTimeout(minuterie);
  let s;
  try { s = await charger(); } catch (e) { s = {erreur: "serveur injoignable"}; }
  if (s.erreur){ $("infos").textContent = s.erreur; if (!STATIQUE) minuterie = setTimeout(rafraichir, 4000); return; }
  legende(s.sens);
  entete(s); tuiles(s); agents(s); modeles(s); nuage(s); barresJours(s); courbes(s); aire(s); qualite(s);
  if (!STATIQUE) minuterie = setTimeout(rafraichir, s.statut === "en_cours" ? 1500 : 10000);
}
async function listerRuns(){
  try {
    const runs = STATIQUE ? STATIQUE.runs : await (await fetch("/api/runs")).json();
    const sel = $("d-run");
    while (sel.options.length > 1) sel.remove(1);
    for (const r of runs) el("option", {value:r.nom}, sel, r.nom);
    sel.value = choix;
  } catch (e) {}
}
$("d-run").addEventListener("change", e => { choix = e.target.value; rafraichir(); });
// Appelee depuis « Comparer les runs » pour ouvrir un run ici.
window.ouvrirRun = nom => { choix = nom || ""; $("d-run").value = choix; rafraichir(); };
listerRuns(); if (!STATIQUE) setInterval(listerRuns, 30000);
rafraichir();
})();
</script>

<script>
/* ==================== Comparer les runs ==================== */
(() => {
"use strict";
let D = null, SENS = [];
const NS = "http://www.w3.org/2000/svg";
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
  const sel = $("serie"); sel.textContent = "";
  for (const s of series){
    const n = D.runs.filter(r => r.plan === s).length;
    el("option", {value:s}, sel, `${s} (${n} runs)`);
  }
  sel.onchange = () => choisirSerie(sel.value);
  if (series.length) choisirSerie(series.includes(etat.serie) ? etat.serie : series[0]);
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
$("vers-suivi").addEventListener("click", () => { if (etat.run){ window.ouvrirRun(etat.run); window.montrerVue("run"); } });

// Chargee a la premiere ouverture de l'onglet : en direct, lire tous les runs prend un moment.
let charge = null;
window.chargerComparaison = () => charge ??= (async () => {
  $("soustitre").textContent = "Lecture des runs…";
  try { D = STATIQUE ? STATIQUE.tableau : await (await fetch("/api/tableau")).json(); }
  catch (e) { $("soustitre").textContent = "Impossible de lire les runs."; charge = null; return; }
  SENS = D.sens;
  legendeSens();
  if (D.runs.length) initFiltres();
  else $("soustitre").textContent = "Aucun run terminé dans runs/.";
})();
})();
</script>

<script>
/* ==================== Onglets ==================== */
(() => {
"use strict";
const VUES = ["run", "comparaison"];
function montrerVue(v){
  if (!VUES.includes(v)) v = STATIQUE ? "comparaison" : "run";
  for (const id of VUES){
    document.getElementById("vue-" + id).hidden = id !== v;
    document.getElementById("onglet-" + id).setAttribute("aria-selected", String(id === v));
  }
  if (v === "comparaison") window.chargerComparaison();
  try { history.replaceState(null, "", "#" + v); } catch (e) {}
}
window.montrerVue = montrerVue;
for (const id of VUES) document.getElementById("onglet-" + id).addEventListener("click", () => montrerVue(id));
montrerVue(location.hash.slice(1));
})();
</script>
</body>
</html>
"""
