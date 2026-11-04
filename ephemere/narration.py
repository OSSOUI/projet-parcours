"""Narratrice externe : faits, consigne, validation et rejeu (etape 4).

Ce module n'est importe que par narratrice.py et par les tests. Le simulateur
ne l'importe pas (tests/test_narratrice.py le verifie sur tout son graphe
d'imports) : la narratrice lit le journal du monde, le monde ne lit jamais
la narratrice.

Chaine d'une narration, une par fenetre de releves :

  1. faits()      table de faits calculee SANS LLM depuis les evenements :
                  chaque fait a une etiquette [F3], un texte, les nombres qu'il
                  autorise, ses sources run#seq et les agents qu'il nomme.
  2. consigne()   le modele recoit ces faits et quelques paroles d'agents
                  [P1]. Depuis la version 3, il n'ecrit plus les constats : il
                  CHOISIT les faits a publier par leur etiquette, et le texte
                  publie est celui du fait. Il n'ecrit librement que des
                  interpretations et des incertitudes, etiquetees comme telles.
  3. valider()    controle independant, sans LLM. Constat : etiquette connue,
                  non repetee. Interpretation ou incertitude : sources connues
                  et pertinentes, aucun nombre, conditionnel, personnes et
                  quantificateurs ("tous", "la plupart"...) conformes aux faits
                  cites, pas d'action deduite d'une parole, pas de cause ni
                  d'emergence non etayees. Une affirmation qui echoue est
                  rejetee et sort du texte ; elle reste dans l'evenement.
  4. rejouer()    relit les narrations, recalcule les faits depuis le journal
                  et revalide les reponses enregistrees : aucun appel au modele.
"""
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime

from . import contrat, journal

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIERS_AGENTS = ("corpus", "corpus_neutre", "config")   # ce que les agents lisent
# Version du validateur et de la consigne : une narration validee par une autre
# version ne se compare pas champ a champ au rejeu (rejouer() le signale).
# 1 : 4 novembre, premiere mesure. 2 : nombres en lettres, paroles rapportees,
# consigne plus stricte sur les intentions et les calculs. 3 : les constats
# reprennent le texte des faits (plus de paraphrase) ; interpretations sans
# nombre, au conditionnel, controle des quantificateurs et du sujet des sources ;
# sens initial inconnu tant que l'agent n'a pas decide. 4 : ex aequo dits (sens
# le plus donne, pas de bascule sur une egalite), les deux lectures de
# l'indicateur d'emergence dans un seul fait, "stabiliser" et "influence"
# controles dans les lectures.
VERSION_VALIDATEUR = 4
MAX_AFFIRMATIONS = 6
PAROLES_MAX = 4
SEUIL_STABLE = 0.05      # comme Monde.tendance : moins de 5 points = stable

SYSTEME = """Tu es la narratrice d'une simulation sociale. Tu observes le campus
de Tessaline de l'exterieur : personne dans la simulation ne lit ce que tu ecris,
et tu ne t'adresses a aucun etudiant. Tu racontes a une personne qui regarde la
simulation ce qui s'est passe, sans rien inventer.
Tu reponds uniquement par un objet JSON, sans aucun texte autour."""

CONSIGNE = """Fenetre observee : de {debut} a {fin} (temps simule).

Faits etablis, calcules depuis le journal de la simulation :
{faits}

Paroles d'etudiants pendant la fenetre :
{paroles}

Compose la narration de cette fenetre en deux parties.

1. Les constats. Choisis de 2 a 4 faits ou paroles qui racontent le mieux ce
   qui s'est passe, dans l'ordre ou tu veux les presenter. Pour chacun :
   "type" vaut "observation", "fait" vaut son etiquette (par exemple "F3" ou
   "P1"), "texte" vaut "" et "sources" vaut []. Tu n'ecris pas le constat :
   c'est le texte du fait qui sera publie.

2. Au plus 2 lectures, facultatives. "type" vaut "interpretation" (ce que les
   faits suggerent) ou "incertitude" (ce qu'on ne peut pas savoir), "fait"
   vaut "", "texte" est ta phrase, "sources" liste les etiquettes F ou P qui la
   fondent. Regles :
   - au conditionnel ("semble", "pourrait") ;
   - aucun nombre, ecrit en chiffres ou en lettres ;
   - ne nomme que des personnes presentes dans les faits ou paroles cites ;
   - n'utilise "tous", "aucun", "la plupart" ou "la moitie" que si un fait
     cite le dit ;
   - ne deduis pas d'une parole ce que quelqu'un a fait ;
   - ne parle d'emergence que si tu cites le fait sur l'indicateur d'emergence.

S'il ne se passe rien de notable, choisis le fait qui le dit.

Reponds par un objet JSON :
{{"affirmations": [{{"type": "observation", "fait": "F1", "texte": "", "sources": []}},
{{"type": "interpretation", "fait": "", "texte": "...", "sources": ["F2"]}}]}}"""

EMPREINTE_PROMPT = hashlib.sha256((SYSTEME + CONSIGNE).encode("utf-8")).hexdigest()[:12]

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["affirmations"],
    "properties": {"affirmations": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["type", "fait", "texte", "sources"],
        "properties": {"type": {"type": "string", "enum": list(contrat.TYPES_AFFIRMATION)},
                       "fait": {"type": "string"},
                       "texte": {"type": "string"},
                       "sources": {"type": "array", "items": {"type": "string"}}}}}},
}


# ------------------------------------------------------------------ faits
def _norm(texte):
    t = unicodedata.normalize("NFD", str(texte).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _pct(x):
    return round(x * 100)


def _pcts(x):
    """Les ecritures entieres acceptees d'une proportion : arrondi, plancher, plafond."""
    v = x * 100
    return sorted({round(v), int(v), int(v) + (v != int(v))})


UNITES = {"zero": 0, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
          "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13,
          "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30,
          "quarante": 40, "cinquante": 50, "soixante": 60, "cent": 100}
# "un" et "une" sont aussi des articles : ils ne comptent pas comme nombres.
NOMBRE_EN_LETTRES = re.compile(r"\b(?:" + "|".join(sorted(UNITES, key=len, reverse=True))
                               + r")(?:[- ](?:et[- ])?(?:un|" + "|".join(UNITES) + r"))*\b")


def _en_lettres(mot):
    total = 0
    for m in re.split(r"[- ]", mot):
        if m == "et":
            continue
        v = 1 if m == "un" else UNITES[m]
        total = total * v if v == 100 and total else total + v
    return float(total)


def _nombres_du_texte(texte):
    chiffres = [float(m.replace(",", ".")) for m in re.findall(r"\d+(?:[.,]\d+)?", texte)]
    return chiffres + [_en_lettres(m) for m in NOMBRE_EN_LETTRES.findall(_norm(texte))]


class Etat:
    """Ce que le journal dit du monde a un instant : qui porte, quel sens."""

    def __init__(self):
        self.pop = {}          # id -> {nom, groupe, moteur}
        self.id_pop = None
        self.porte, self.sens = {}, {}

    def appliquer(self, e):
        s = e["schema"]
        if s in ("population.v1", "population.v2"):
            self.id_pop = journal.identifiant(e)
            for a in e["agents"]:
                self.pop[a["id"]] = {"nom": a.get("nom", a["id"]), "groupe": a.get("groupe", "?"),
                                     "moteur": a.get("moteur", "?")}
                self.porte[a["id"]] = bool(a.get("porte", False))
                # Le sens de depart n'est pas dans population.v1 : inconnu
                # tant que l'agent n'a pas decide (jamais compte comme un changement).
                self.sens.setdefault(a["id"], a.get("categorie"))
        elif s in ("decision.v1", "decision.v2") and e.get("valide", True):
            self.porte[e["agent"]] = e["porte"]
            self.sens[e["agent"]] = e["categorie"]

    def nom(self, aid):
        return self.pop.get(aid, {}).get("nom", aid)


def fenetres(evenements, periode=1):
    """Decoupe le run entre releves : (indice, evenements, releve_avant, releve_fin)."""
    releves = [i for i, e in enumerate(evenements) if e["schema"] == "indicateurs.v1"]
    bornes = releves[::periode]
    if releves and bornes[-1] != releves[-1]:
        bornes.append(releves[-1])
    for k in range(1, len(bornes)):
        a, b = bornes[k - 1], bornes[k]
        yield k, evenements[a + 1:b + 1], evenements[a], evenements[b]


def faits(fenetre, etat_avant, etat_apres, emergence=None):
    """Table des faits d'une fenetre. Aucun nombre ne vient du modele.

    fenetre : (k, evenements, releve_avant, releve_fin) ; etat_avant et
    etat_apres : Etat au debut et a la fin de la fenetre ; emergence : le
    resultat d'emergence.analyser pour un run termine, ou None.
    """
    k, evs, r0, r1 = fenetre
    ident = journal.identifiant
    table, n = {}, [0]

    def ajouter(texte, nombres=(), sources=(), agents=(), **attrs):
        n[0] += 1
        tag = f"F{n[0]}"
        table[tag] = {"tag": tag, "texte": texte, "nombres": sorted(set(float(x) for x in nombres)),
                      "sources": list(sources), "agents": sorted(set(agents)), **attrs}

    total = len(etat_apres.pop) or 1
    porteurs = len(r1["porteurs"])
    ajouter(f"Taux d'adoption au releve de {r1['t_sim_lisible']} : {_pct(r1['taux_adoption'])} % "
            f"({porteurs} etudiants sur {total} portent le ruban).",
            _pcts(r1["taux_adoption"]) + [porteurs, total], [ident(r1)],
            nature="adoption", proportion=porteurs / total)
    var = r1["taux_adoption"] - r0["taux_adoption"]
    ajouter(f"Variation de l'adoption depuis le releve de {r0['t_sim_lisible']} : "
            f"{'+' if var >= 0 else '-'}{abs(_pct(var))} points "
            f"({_pct(r0['taux_adoption'])} % puis {_pct(r1['taux_adoption'])} %).",
            _pcts(abs(var)) + _pcts(r0["taux_adoption"]) + _pcts(r1["taux_adoption"]),
            [ident(r0), ident(r1)], variation=var, nature="variation")
    rep = {s: c for s, c in r1["repartition_sens"].items() if c}
    # Le sens dominant d'indicateurs.v1 est le premier des ex aequo : on dit l'egalite.
    haut = max(rep.values())
    tete = [s for s, c in rep.items() if c == haut]
    ajouter(f"Sens le plus donne au ruban au releve de {r1['t_sim_lisible']} : "
            + (f"{tete[0]} ({haut} etudiants sur {total}" if len(tete) == 1 else
               f"{' et '.join(tete)} a egalite ({haut} etudiants chacun sur {total}")
            + ", agents a regles compris).",
            [haut, total] + _pcts(haut / total), [ident(r1)],
            nature="sens", proportion=haut / total)
    ajouter("Repartition des sens donnes au ruban : "
            + ", ".join(f"{s} {c}" for s, c in sorted(rep.items(), key=lambda x: -x[1])) + ".",
            list(rep.values()), [ident(r1)], nature="repartition")
    haut0 = max(r0["repartition_sens"].values())
    seul0 = [s for s, c in r0["repartition_sens"].items() if c == haut0]
    if len(seul0) == 1 and len(tete) == 1 and seul0[0] != tete[0]:
        ajouter(f"Le sens le plus donne au ruban change : {seul0[0]} au releve de "
                f"{r0['t_sim_lisible']}, {tete[0]} au releve de {r1['t_sim_lisible']}.",
                [], [ident(r0), ident(r1)], nature="bascule")
    groupes = {}
    for aid, p in etat_apres.pop.items():
        groupes.setdefault(p["groupe"], []).append(aid)
    porteurs_fin = set(r1["porteurs"])
    for g, membres in sorted(groupes.items()):
        a = sum(1 for m in membres if m in porteurs_fin)
        ajouter(f"Groupe {g} : {a} membres sur {len(membres)} portent le ruban.",
                [a, len(membres)], [ident(r1)] + ([etat_apres.id_pop] if etat_apres.id_pop else []),
                nature="groupe", proportion=a / len(membres))

    decisions = [e for e in evs if e["schema"] in ("decision.v1", "decision.v2")]
    noues, retires, changes = [], [], []
    vu = {}
    for e in decisions:
        if not e.get("valide", True):
            continue
        aid = e["agent"]
        avant_p = vu.get(aid, (etat_avant.porte.get(aid), None))[0]
        avant_s = vu.get(aid, (None, etat_avant.sens.get(aid)))[1]
        if avant_p is False and e["porte"]:
            noues.append(e)
        if avant_p and not e["porte"]:
            retires.append(e)
        if avant_s is not None and e["categorie"] != avant_s:
            changes.append((e, avant_s))
        vu[aid] = (e["porte"], e["categorie"])
    if noues:
        ajouter(f"Ont noue le ruban pendant la fenetre : "
                f"{', '.join(etat_apres.nom(e['agent']) for e in noues)} ({len(noues)}).",
                [len(noues)], [ident(e) for e in noues], [etat_apres.nom(e["agent"]) for e in noues],
                role="noue", nature="noue")
    if retires:
        ajouter(f"Ont retire le ruban pendant la fenetre : "
                f"{', '.join(etat_apres.nom(e['agent']) for e in retires)} ({len(retires)}).",
                [len(retires)], [ident(e) for e in retires],
                [etat_apres.nom(e["agent"]) for e in retires], role="retire", nature="retire")
    if changes:
        ajouter("Ont change de lecture du ruban : " + ", ".join(
            f"{etat_apres.nom(e['agent'])} ({avant} puis {e['categorie']})" for e, avant in changes)
            + f" ({len(changes)}).",
            [len(changes)], [ident(e) for e, _ in changes],
            [etat_apres.nom(e["agent"]) for e, _ in changes], nature="change")
    if decisions and not (noues or retires or changes):
        ajouter("Aucun etudiant n'a noue, retire ou relu le ruban pendant la fenetre.",
                [], [ident(e) for e in decisions], nature="calme", proportion=0.0)

    pubs = [e for e in evs if e["schema"] in ("publication.v1", "publication.v2")]
    publics = [e for e in pubs if e["portee"] != "personne"]
    prives = [e for e in pubs if e["portee"] == "personne"]
    if pubs:
        ajouter(f"Messages pendant la fenetre : {len(publics)} publics sur le reseau, "
                f"{len(prives)} adresses a une personne.",
                [len(publics), len(prives)], [ident(e) for e in pubs], nature="messages")
    repliques = [e for e in evs if e["schema"] == "replique.v1"]
    if repliques:
        ajouter(f"{len(repliques)} repliques dans des conversations privees.",
                [len(repliques)], [ident(e) for e in repliques],
                [etat_apres.nom(e["agent"]) for e in repliques], nature="repliques")
    incidents = [e for e in evs if e["schema"] == "incident.v1"]
    if incidents:
        natures = sorted({e["nature"] for e in incidents})
        ajouter(f"{len(incidents)} incidents de decision ({', '.join(natures)}) : "
                f"ces decisions ne comptent pas.",
                [len(incidents)], [ident(e) for e in incidents], nature="incidents")

    if emergence:
        _faits_emergence(emergence, evs, ajouter)

    paroles = {}
    for i, e in enumerate(publics[-PAROLES_MAX:], start=1):
        texte = e["texte"].strip().replace("\n", " ")[:200]
        nom = etat_apres.nom(e["agent"])
        paroles[f"P{i}"] = {"tag": f"P{i}", "texte": f"{nom} a ecrit sur le reseau : \"{texte}\"",
                            "nombres": sorted(set(_nombres_du_texte(texte))),
                            "sources": [ident(e)], "agents": [nom], "role": "parole",
                            "nature": "parole"}
    return table, paroles


def _faits_emergence(r, evs, ajouter):
    """L'indicateur corrige en UN fait, ses deux lectures ensemble : on ne peut pas
    en publier une sans l'autre. La lecture en six sens est la lecture principale
    du protocole : c'est son verdict que les lectures du modele doivent suivre."""
    fin = [journal.identifiant(e) for e in evs if e["schema"] == "bilan.v1"]
    lectures = [(l, v) for l, v in r.get("seuil_persistance", {}).items()
                if v.get("delta_a") is not None and "erreur" not in v]
    if lectures:
        ajouter("Indicateur d'emergence corrige (seuil a persistance, run complet) : " + " ; ".join(
            f"{l.replace('_', ' ')} : gain soutenu {_pct(v['delta_a'])} points pour un seuil de "
            f"{_pct(v['seuil'])} points, {'emergent' if v['emergent'] else 'non emergent'}"
            for l, v in lectures) + ".",
            [x for _, v in lectures for x in _pcts(abs(v["delta_a"])) + _pcts(v["seuil"])], fin,
            emergence=dict(lectures).get("six_sens", lectures[0][1])["emergent"],
            nature="emergence")
    for masque, lectures_o in r.get("ombres", {}).items():
        o = lectures_o.get("six_sens")
        if not o or o.get("p") is None:
            continue
        ajouter(f"Ecart d'accord entre les decisions reelles et l'ombre {masque} sur le run : "
                f"{'+' if o['ecart'] >= 0 else '-'}{abs(_pct(o['ecart']))} points, "
                f"p = {o['p']:.3f}.",
                _pcts(abs(o["ecart"])) + [round(o["p"], 3)], fin, nature="ombre")


def empreinte_faits(table, paroles):
    brut = json.dumps([table, paroles], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


def consigne(table, paroles, debut, fin):
    return CONSIGNE.format(
        debut=debut, fin=fin,
        faits="\n".join(f"[{t}] {f['texte']}" for t, f in table.items()),
        paroles="\n".join(f"[{t}] {p['texte']}" for t, p in paroles.items()) or "(aucune)")


# -------------------------------------------------------------- validation
CAUSES = ("parce qu", "a cause", "grace a", "provoqu", "entrain", "en raison", "du fait",
          " car ", "donc", "cause", "influenc", "sous l'effet", "pousse")
PRUDENCE = ("semble", "peut-etre", "peut etre", "pourrait", "possible", "sans doute",
            "probable", "suggere")
HAUSSE = ("hausse", "augment", "progress", "monte", "grimpe", "croissan", "gagne")
BAISSE = ("baisse", "diminu", "recul", "chute", "descend", "decroiss", "perd")
STABLE = ("stable", "stabilis", "inchang", "stagn", "plateau")
NEGATION = ("pas ", "aucun", "non ", "n'", "ni ")
NOUER = ("noue", "adopt", "a mis le ruban", "ont mis le ruban")
RETIRER = ("retir", "enlev", "abandonn", "ote le ruban", "a ote", "ont ote")
CITATION = re.compile(r"[«\"“]\s*([^»\"”]{6,})\s*[»\"”]")


QUANT_TOUS = ("tous", "toutes", "chacun", "chacune", "l'ensemble", "tout le monde",
              "tout le campus", "unanim")
QUANT_AUCUN = ("aucun", "aucune", "personne ne", "personne n'", "nul ", "nulle ")
QUANT_MAJORITE = ("majorite", "la plupart", "majoritaire", "plus de la moitie")
QUANT_MINORITE = ("minorite", "minoritaire", "peu d", "quelques", "rares")
QUANT_MOITIE = ("la moitie",)
# Sujet d'une lecture -> natures de faits qui peuvent la fonder.
THEMES = (
    (re.compile(r"\bport(?:e|ent|er|eurs?|ant)\b|adopt|\bnou|retir|poignet"),
     {"adoption", "variation", "groupe", "noue", "retire", "calme", "parole"}, "port du ruban"),
    (re.compile(r"\bsens\b|lecture|signif|ironi|tendance|foule|ringard|creati|percu|percoi"),
     {"sens", "repartition", "change", "bascule", "calme", "parole"}, "sens du ruban"),
    (re.compile(r"emerg"), {"emergence"}, "emergence"),
    (re.compile(r"\bombre|accord"), {"ombre", "emergence", "sens", "repartition"}, "accord"),
)


def valider(brutes, table, paroles, noms, jours=()):
    """Verifie chaque affirmation brute. Renvoie la liste validee, dans l'ordre.

    Constat ("fait" renseigne) : le texte publie est celui du fait ou de la
    parole choisie, son type vient du fait (mesure s'il porte des nombres).
    Lecture (interpretation, incertitude) : le texte du modele, controle.
    Chaque element : type, texte, etiquettes, sources (run#seq), statut
    ("verifiee" ou "rejetee") et raison. Tout ce qui n'est pas verifiable ici
    est rejete.
    """
    connus = {**table, **paroles}
    sortie, deja = [], set()
    for i, b in enumerate(brutes if isinstance(brutes, list) else []):
        b = b if isinstance(b, dict) else {}
        fait = str(b.get("fait") or "").strip("[] ")
        etiquettes = ([fait] if fait else
                      [str(x).strip("[] ") for x in b.get("sources") or []]
                      if isinstance(b.get("sources"), list) else [])
        a = {"type": b.get("type"), "texte": str(b.get("texte") or "").strip(),
             "etiquettes": etiquettes}
        if fait:
            a["type_modele"], a["texte_modele"] = a["type"], a["texte"]
            raison = _rejet_constat(fait, i, connus, deja)
            if fait in connus:
                f = connus[fait]
                a["texte"] = f["texte"]
                a["type"] = "mesure" if f["nombres"] and f.get("role") != "parole" else "observation"
            deja.add(fait)
        else:
            raison = _rejet_lecture(a, i, connus, noms)
        cites = [connus[t] for t in a["etiquettes"] if t in connus]
        a["sources"] = sorted({x for f in cites for x in f["sources"]},
                              key=lambda x: int(x.rsplit("#", 1)[1]))
        if a["type"] not in contrat.TYPES_AFFIRMATION:
            a["type"] = "incertitude"
            raison = raison or "type inconnu"
        a["statut"] = "rejetee" if raison else "verifiee"
        a["raison"] = raison
        sortie.append(a)
    return sortie


def _rejet_constat(fait, i, connus, deja):
    if i >= MAX_AFFIRMATIONS:
        return f"au-dela de {MAX_AFFIRMATIONS} affirmations"
    if fait not in connus:
        return f"source inconnue : {fait}"
    if fait in deja:
        return f"fait deja cite : {fait}"
    return None


def _proportions(cites):
    return [f["proportion"] for f in cites if f.get("proportion") is not None]


def _rejet_lecture(a, i, connus, noms):
    if i >= MAX_AFFIRMATIONS:
        return f"au-dela de {MAX_AFFIRMATIONS} affirmations"
    if a["type"] not in ("interpretation", "incertitude"):
        return "constat sans fait choisi"
    if not a["texte"]:
        return "texte vide"
    inconnues = [t for t in a["etiquettes"] if t not in connus]
    if inconnues:
        return f"source inconnue : {', '.join(inconnues)}"
    cites = [connus[t] for t in a["etiquettes"]]
    if a["type"] == "interpretation" and not cites:
        return "affirmation sans source"
    t = " " + _norm(a["texte"]) + " "
    # Une lecture ne porte aucun nombre : les nombres sont dans les constats.
    if _nombres_du_texte(re.sub(r"\b\d{1,2}:\d{2}\b", " ", a["texte"])):
        return "nombre dans une lecture"
    if a["type"] == "interpretation" and not any(p in t for p in PRUDENCE):
        return "interpretation sans conditionnel"
    # Cause : les faits ne la montrent jamais ; seule une incertitude peut l'evoquer.
    if a["type"] == "interpretation" and any(c in t for c in CAUSES):
        return "cause suggeree dans une interpretation"
    # Personnes : chaque nom ecrit doit figurer dans un fait ou une parole cite.
    sources_noms = {_norm(n) for f in cites for n in f["agents"]}
    nommes = [n for n in noms if re.search(rf"\b{re.escape(_norm(n))}\b", t)]
    for nom in nommes:
        if _norm(nom) not in sources_noms:
            return f"personne non sourcee : {nom}"
    # Action d'une personne connue seulement par sa parole : deduite, pas observee.
    for nom in nommes:
        roles = {f.get("role") for f in cites if _norm(nom) in {_norm(n) for n in f["agents"]}}
        if roles <= {"parole"} and (any(m in t for m in NOUER + RETIRER)
                                    or re.search(r"\bport(?:e|ent|ait|er)\b", t)):
            return f"action de {nom} deduite d'une parole"
        if any(m in t for m in RETIRER) and not roles & {"retire"}:
            return f"retrait de {nom} non sourcee"
        if any(m in t for m in NOUER) and not roles & {"noue"}:
            return f"adoption de {nom} non sourcee"
    # Quantificateurs : conformes a une proportion d'un fait cite.
    q = re.sub(r"aucun[_ ]sens|aucune emergence|aucun incident", " ", t)
    props = _proportions(cites)
    for mots, test, libelle in ((QUANT_TOUS, lambda p: p >= 1.0, "tous"),
                                (QUANT_AUCUN, lambda p: p <= 0.0, "aucun"),
                                (QUANT_MAJORITE, lambda p: p > 0.5, "la plupart"),
                                (QUANT_MINORITE, lambda p: 0.0 < p < 0.5, "une minorite"),
                                (QUANT_MOITIE, lambda p: abs(p - 0.5) < 0.05, "la moitie")):
        if any(m in q for m in mots):
            if not props:
                return f"quantificateur \"{libelle}\" sans proportion citee"
            if not any(test(p) for p in props):
                return f"quantificateur \"{libelle}\" contraire aux faits cites"
    # Sujet : une lecture sur le port, le sens ou l'emergence cite un fait de ce sujet.
    natures = {f.get("nature") for f in cites}
    for motif, admis, sujet in THEMES:
        if motif.search(t) and cites and not natures & admis:
            return f"source hors sujet ({sujet})"
    # Citation : entre guillemets, mot pour mot dans une parole citee.
    paroles_citees = " ".join(_norm(f["texte"]) for f in cites if f.get("role") == "parole")
    for c in CITATION.findall(a["texte"]):
        if _norm(c).strip(" .,;:!?") not in paroles_citees:
            return "citation absente des paroles citees"
    # Sens d'une variation : il doit suivre le signe mesure, et etre mesure.
    variations = [f["variation"] for f in cites if f.get("variation") is not None]
    for mots, test, libelle in ((HAUSSE, lambda v: v > 0, "hausse"),
                                (BAISSE, lambda v: v < 0, "baisse"),
                                (STABLE, lambda v: abs(v) <= SEUIL_STABLE, "stabilite")):
        if any(m in t for m in mots):
            if not variations:
                return f"{libelle} affirmee sans fait de variation cite"
            if not all(test(v) for v in variations):
                return f"{libelle} contraire a la variation mesuree"
    # Emergence : seulement en citant l'indicateur corrige, et dans son sens.
    if "emerg" in t:
        verdicts = [f["emergence"] for f in cites if f.get("emergence") is not None]
        if not verdicts:
            return "emergence sans l'indicateur corrige"
        nie = any(n in t for n in NEGATION)
        if any(verdicts) and nie or not any(verdicts) and not nie:
            return "emergence contraire a l'indicateur"
    return None


def assembler(affirmations):
    lignes = [f"[{a['type']}] {a['texte']}" for a in affirmations if a["statut"] == "verifiee"]
    return "\n".join(lignes)


def statut(affirmations, incident):
    if incident:
        return "incident"
    ok = [a for a in affirmations if a["statut"] == "verifiee"]
    if not ok:
        return "vide"
    return "valide" if len(ok) == len(affirmations) else "partiel"


# -------------------------------------------------------------- narrations
def narrer(client, fenetre, etat_avant, etat_apres, taille="llm_grand",
           emergence=None, max_tokens=600, essais=2):
    """Une narration (dict au format narration.v1, hors enveloppe).

    client peut etre None (faits sans modele : statut incident, texte vide).
    Ne leve jamais : une erreur du modele devient un incident de la narration.
    """
    k, evs, r0, r1 = fenetre
    table, paroles = faits(fenetre, etat_avant, etat_apres, emergence)
    noms = [p["nom"] for p in etat_apres.pop.values()]
    jours = {r0["t_sim"] // 1440 + 1, r1["t_sim"] // 1440 + 1, r1["t_sim"] // 1440}
    brutes, incident, brut, mesure = None, None, None, {}
    if client is None:
        incident = "sans_modele"
    else:
        try:
            rep = client.json(SYSTEME, consigne(table, paroles, r0["t_sim_lisible"],
                                                r1["t_sim_lisible"]),
                              taille, essais=essais, schema=SCHEMA, cle=f"narration:{k}",
                              max_tokens=max_tokens)
            brut = client.dernier_brut
            mesure = dict(client.derniere_mesure or {})
            if rep is None:
                incident = mesure.get("echec") or "reponse_illisible"
            elif not isinstance(rep.get("affirmations"), list):
                incident = "reponse_sans_affirmations"
            else:
                brutes = rep["affirmations"]
        except Exception as e:     # le modele ne doit jamais arreter la narratrice
            incident = f"erreur : {type(e).__name__}"
    affirmations = valider(brutes or [], table, paroles, noms, jours)
    cites = sorted({s for a in affirmations if a["statut"] == "verifiee" for s in a["sources"]},
                   key=lambda x: int(x.rsplit("#", 1)[1]))
    return {
        "narration": f"N{k}",
        "fenetre": {"releve_debut": journal.identifiant(r0), "releve_fin": journal.identifiant(r1),
                    "seq_debut": r0["seq"], "seq_fin": r1["seq"],
                    "debut": r0["t_sim_lisible"], "fin": r1["t_sim_lisible"]},
        "texte": assembler(affirmations),
        "affirmations": affirmations,
        "affirmations_brutes": brutes,
        "sources": cites,
        "indicateurs": [s for s in cites if s in (journal.identifiant(r0), journal.identifiant(r1))],
        "empreinte_faits": empreinte_faits(table, paroles),
        "modele": {"taille": taille, "modele": mesure.get("modele"),
                   "validateur": VERSION_VALIDATEUR,
                   "temperature": getattr(client, "temperature", None),
                   "graine": mesure.get("graine")},
        "empreinte_prompt": EMPREINTE_PROMPT,
        "statut": statut(affirmations, incident),
        "incident": incident,
        "reponse_brute": brut,
        "mesure": {k_: mesure.get(k_) for k_ in ("latence_s", "essais", "tokens_entree",
                                                 "tokens_sortie")},
        "_t_sim": r1["t_sim"], "_t_sim_lisible": r1["t_sim_lisible"],
    }


class Sortie:
    """Fichier de narration : son propre seq, verifie par le contrat.

    Refuse tout chemin que le monde pourrait lire : le journal du run, un
    dossier lu par les agents (corpus, config), ou un nom qui ne finit pas
    par .narration.jsonl (journal.lire et le pont ne l'ouvrent pas).
    """

    def __init__(self, chemin, run, journal_observe):
        chemin = os.path.abspath(chemin)
        if not chemin.endswith(".narration.jsonl"):
            raise ValueError("une sortie de narratrice finit par .narration.jsonl")
        if chemin == os.path.abspath(journal_observe):
            raise ValueError("la narratrice n'ecrit jamais dans le journal du monde")
        for d in DOSSIERS_AGENTS:
            interdit = os.path.join(RACINE, d) + os.sep
            if chemin.startswith(interdit):
                raise ValueError(f"la narratrice n'ecrit jamais dans {d}/, lu par les agents")
        self.chemin, self.run, self.seq = chemin, run, 0
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        self._f = open(chemin, "w", encoding="utf-8")

    def ecrire(self, schema, t_sim=0, t_sim_lisible="J01 00:00", **corps):
        evt = {"schema": schema, "run": self.run, "seq": self.seq, "t_sim": t_sim,
               "t_sim_lisible": t_sim_lisible,
               "t_emission": datetime.now().isoformat(timespec="milliseconds"),
               "t_traitement": None, **corps}
        ok, raison = contrat.verifier(evt)
        if not ok:
            raise ValueError(f"narration non conforme : {raison}")
        self._f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        self._f.flush()
        self.seq += 1
        return evt

    def narration(self, n):
        corps = {k: v for k, v in n.items() if not k.startswith("_")}
        return self.ecrire("narration.v1", n["_t_sim"], n["_t_sim_lisible"], **corps)

    def fermer(self):
        self._f.close()


def sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# ------------------------------------------------------------------ rejeu
def parcourir(evenements, periode, emergence=None):
    """Pour chaque fenetre : (fenetre, etat_avant, etat_apres). Sans modele."""
    etat = Etat()
    i = 0
    liste = list(fenetres(evenements, periode))
    for n, fen in enumerate(liste):
        k, evs, r0, r1 = fen
        while i <= r0["seq"]:
            etat.appliquer(evenements[i])
            i += 1
        avant = _copie(etat)
        while i <= r1["seq"]:
            etat.appliquer(evenements[i])
            i += 1
        # Le fait d'emergence ne vaut que pour un run termine, a la derniere fenetre.
        fin = n == len(liste) - 1 and any(e["schema"] == "bilan.v1" for e in evenements)
        if fin:
            # Le bilan suit le dernier releve : on l'ajoute a la derniere fenetre.
            fen = (k, evs + evenements[r1["seq"] + 1:], r0, r1)
        yield fen, avant, _copie(etat), (emergence if fin else None)


def _copie(etat):
    c = Etat()
    c.pop, c.id_pop = dict(etat.pop), etat.id_pop
    c.porte, c.sens = dict(etat.porte), dict(etat.sens)
    return c


def lire_narrations(chemin):
    with open(chemin, encoding="utf-8") as f:
        evs = [json.loads(l) for l in f if l.strip()]
    if not evs or evs[0]["schema"] != "narratrice.v1":
        raise ValueError(f"{chemin} : pas d'en-tete narratrice.v1")
    return evs[0], evs[1:]


def rejouer(chemin_narration, chemin_journal, emergence=None):
    """Relit les narrations et les revalide depuis le journal, sans modele.

    Renvoie (narrations, ecarts) : ecarts liste, par narration, ce qui differe
    entre l'enregistre et le recalcule (faits, affirmations, texte, statut).
    """
    entete, narrations = lire_narrations(chemin_narration)
    evenements = journal.lire(chemin_journal)
    jeu = {f"N{fen[0]}": (fen, av, ap, em) for fen, av, ap, em
           in parcourir(evenements, entete["periode"], emergence)}
    ecarts = []
    for n in narrations:
        if n["narration"] not in jeu:
            ecarts.append((n["narration"], "fenetre absente du journal"))
            continue
        version = n["modele"].get("validateur", 1)
        if version != VERSION_VALIDATEUR:
            ecarts.append((n["narration"], f"validee par la version {version} du validateur, "
                                           f"version actuelle {VERSION_VALIDATEUR}"))
            continue
        fen, av, ap, em = jeu[n["narration"]]
        table, paroles = faits(fen, av, ap, em)
        if empreinte_faits(table, paroles) != n["empreinte_faits"]:
            ecarts.append((n["narration"], "faits differents"))
            continue
        noms = [p["nom"] for p in ap.pop.values()]
        r0, r1 = fen[2], fen[3]
        jours = {r0["t_sim"] // 1440 + 1, r1["t_sim"] // 1440 + 1, r1["t_sim"] // 1440}
        refait = valider(n["affirmations_brutes"] or [], table, paroles, noms, jours)
        for champ, a, b in (("affirmations", refait, n["affirmations"]),
                            ("texte", assembler(refait), n["texte"]),
                            ("statut", statut(refait, n["incident"]), n["statut"])):
            if a != b:
                ecarts.append((n["narration"], f"{champ} different"))
    return entete, narrations, ecarts
