"""Mesures sur les agents LLM d'un run enregistre. Aucun appel LLM.

Six familles, chacune rattachee a son exigence du sujet :

  fiabilite      A4   incidents par modele ET par profil, par nature
  fidelite       A3   deux profils qui voient la meme adoption decident-ils
                      differemment ? taux d'abandon par profil, par tranche
                      d'adoption percue
  memoire        A1   part des decisions dont le prompt contenait un souvenir
                      de plus de 3 jours. En v1, l'agent ne cite pas ses
                      souvenirs : on mesure ce qui lui etait DISPONIBLE, pas
                      ce qu'il a utilise. La citation arrive avec le LLM v2.
  echanges       A2   probabilite de changer de sens dans les 24 h qui suivent
                      un message prive ou une replique recus, comparee a celle
                      sans ; conversations() suit chaque dialogue (--conversation)
  sens           B1, B3
                      changements de sens justifies par une source vue (v2
                      seulement), diversite des sens chez les seuls LLM,
                      messages quasi identiques, recouvrement avec le corpus
  temps          C5, C7, E4
                      latences par modele (moyenne, p95), attente de quota,
                      decisions par agent et par jour simule

L'echantillon F2 (environ 30 decisions a juger a la main) est tire par
echantillon_f2 et ecrit en CSV par analyser.py --echantillon-f2.
"""
import collections
import csv
import difflib
import math
import os
import random
import re

from .rag import Base, normaliser

MOTEURS_LLM = ("llm_grand", "llm_petit")
JOUR = 1440
VIEUX_JOURS = 3            # A1 : un souvenir "vieux" a plus de 3 jours
SEUIL_QUASI_IDENTIQUE = 0.8
SEUIL_RECITE = 0.5         # part des 4-grammes du message presents dans le corpus
TRANCHES = (0.25, 0.5, 0.75)


def lire_jsonl(chemin):
    import json
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _par(evs, schema):
    return [e for e in evs if e.get("schema") == schema]


def profils(evs):
    """id -> {profil, moteur, groupe, porte au depart}, d'apres population.v1/v2."""
    pop = next((e for e in evs if e.get("schema") in ("population.v1", "population.v2")), None)
    return {a["id"]: a for a in (pop or {}).get("agents", [])}


def _decisions(evs):
    return [e for e in evs if e.get("schema") in ("decision.v1", "decision.v2")]


def _avec_veille(evs):
    """Chaque decision avec l'etat de l'agent juste avant (porte, categorie)."""
    pop = profils(evs)
    etat = {i: (bool(a.get("porte")), a.get("categorie") or
                ("cercle_creatif" if a.get("porte") else "aucun_sens")) for i, a in pop.items()}
    sortie = []
    for d in sorted(_decisions(evs), key=lambda e: e["t_sim"]):
        avant = etat.get(d["agent"], (False, "aucun_sens"))
        sortie.append((d, avant))
        etat[d["agent"]] = (d["porte"], d["categorie"])
    return sortie


def _centile(valeurs, q):
    if not valeurs:
        return None
    v = sorted(valeurs)
    return v[min(len(v) - 1, int(len(v) * q))]


# ------------------------------------------------------------------ A4


def fiabilite(evs):
    """Incidents par (moteur, profil), avec leurs natures."""
    pop = profils(evs)
    decisions = collections.Counter()
    for d in _decisions(evs):
        if d["moteur"] in MOTEURS_LLM:
            decisions[(d["moteur"], pop.get(d["agent"], {}).get("profil", "?"))] += 1
    incidents = collections.defaultdict(collections.Counter)
    for i in _par(evs, "incident.v1"):
        if "conversation" in (i.get("details") or {}):
            continue    # incident d'une replique : compte dans conversations()
        a = pop.get(i.get("agent"), {})
        if a.get("moteur") in MOTEURS_LLM:
            incidents[(a["moteur"], a.get("profil", "?"))][i["nature"]] += 1
    return {cle: {"decisions": n, "incidents": sum(incidents[cle].values()),
                  "taux": sum(incidents[cle].values()) / n, "natures": dict(incidents[cle])}
            for cle, n in sorted(decisions.items())}


# ------------------------------------------------------------------ A3


_CAMPUS = re.compile(r"(\d+) etudiants? sur (\d+)")


def _exposition(perception):
    """Adoption percue par l'agent : la phrase "17 etudiants sur 20 le portent" (v1)."""
    vue = perception.get("vue") or {}
    m = _CAMPUS.search(normaliser(str(vue.get("campus", ""))))
    return int(m.group(1)) / int(m.group(2)) if m and int(m.group(2)) else None


def _tranche(x):
    for i, borne in enumerate(TRANCHES):
        if x < borne:
            return i
    return len(TRANCHES)


def fidelite(evs):
    """Taux d'abandon par profil, a adoption percue comparable (A3).

    Abandon : l'agent portait le ruban avant la decision et ne le porte plus
    apres. Comparer les profils DANS une meme tranche d'adoption percue retire
    l'effet de l'exposition : un ecart qui reste vient du profil.
    """
    pop = profils(evs)
    perception = {(p["agent"], p["t_sim"]): p for p in _par(evs, "perception.v1")}
    compte = collections.defaultdict(lambda: [0, 0])   # (moteur, profil, tranche) -> [abandons, porteurs]
    for d, (portait, _) in _avec_veille(evs):
        if not portait:
            continue
        p = perception.get((d["agent"], d["t_sim"]))
        x = _exposition(p) if p else None
        if x is None:
            continue
        a = pop.get(d["agent"], {})
        cle = (d["moteur"], a.get("profil", "?"), _tranche(x))
        compte[cle][1] += 1
        compte[cle][0] += not d["porte"]
    return {cle: {"abandons": ab, "porteurs": n, "taux": ab / n} for cle, (ab, n) in
            sorted(compte.items())}


def libelle_tranche(i):
    bornes = (0.0,) + TRANCHES + (1.0,)
    return f"{bornes[i]:.0%}-{bornes[i + 1]:.0%}"


# ------------------------------------------------------------------ A1, A2


def memoire(evs):
    """Part des decisions LLM dont le prompt contenait un souvenir de plus de 3 jours."""
    perc = [p for p in _par(evs, "perception.v1") if p["moteur"] in MOTEURS_LLM]
    vieux = sum(1 for p in perc if any(p["t_sim"] - s.get("t_sim", p["t_sim"]) > VIEUX_JOURS * JOUR
                                       for s in p.get("souvenirs", [])))
    return {"decisions": len(perc), "avec_souvenir_ancien": vieux,
            "part": vieux / len(perc) if perc else None}


def echanges(evs, moteurs=MOTEURS_LLM):
    """P(changer de sens | message prive recu) contre P(... | aucun message prive).

    Un echange, c'est un message PRIVE adresse a l'agent dans les 24 h
    simulees avant sa decision : en v1, tout le monde lit le fil public a
    presque chaque decision, il n'y aurait pas de groupe de comparaison. On
    ne compte pas le passage d'"aucun sens" a un premier sens : l'agent forme
    alors une croyance, il n'en change pas. Un ecart positif est le signe que
    les echanges modifient les croyances (A2) ; il reste une correlation.
    """
    pop = profils(evs)
    nom_vers_id = {str(a.get("nom", "")).lower(): i for i, a in pop.items()}
    recus = collections.defaultdict(list)    # agent -> instants des messages prives recus
    for p in evs:
        if p.get("schema") == "replique.v1" and p.get("valide"):
            recus[p["destinataire"]].append(p["t_sim"])
        elif p.get("schema") in ("publication.v1", "publication.v2") and p.get("portee") == "personne":
            dest = str(p.get("destinataire") or "")
            dest = dest if dest in pop else nom_vers_id.get(dest.lower())
            if dest:
                recus[dest].append(p["t_sim"])
    groupes = {True: [0, 0], False: [0, 0]}
    for d, (_, sens_avant) in _avec_veille(evs):
        if d["moteur"] not in moteurs or sens_avant == "aucun_sens":
            continue
        recu = any(d["t_sim"] - JOUR <= t < d["t_sim"] for t in recus[d["agent"]])
        groupes[recu][1] += 1
        groupes[recu][0] += d["categorie"] != sens_avant
    return {("avec_message" if k else "sans_message"):
            {"changements": c, "decisions": n, "taux": c / n if n else None}
            for k, (c, n) in groupes.items()}


def conversations(evs):
    """Les conversations privees (option --conversation) : combien, et ce
    qu'elles changent.

    Pour chaque conversation, on compare le sens de chaque participant juste
    avant (sa derniere decision), pendant (sa derniere replique) et apres (sa
    decision suivante). "Bouge pendant" : sa replique donne un autre sens que
    sa decision d'avant. "Bouge apres" : sa decision suivante aussi.
    """
    repliques = _par(evs, "replique.v1")
    if not repliques:
        return None
    par_conv = collections.defaultdict(list)
    for r in repliques:
        par_conv[r["conversation"]].append(r)
    decisions = collections.defaultdict(list)
    for d in sorted(_decisions(evs), key=lambda e: e["t_sim"]):
        decisions[d["agent"]].append(d)
    def avant(agent, t):
        prec = [d for d in decisions[agent] if d["t_sim"] <= t]
        return prec[-1]["categorie"] if prec else None
    def apres(agent, t):
        suiv = [d for d in decisions[agent] if d["t_sim"] > t]
        return suiv[0]["categorie"] if suiv else None
    pendant = bouge_pendant = bouge_apres = suivis = 0
    for conv in par_conv.values():
        t = conv[0]["t_sim"]
        derniere = {}
        for r in conv:
            if r["valide"]:
                derniere[r["agent"]] = r["categorie"]
        for agent, cat in derniere.items():
            a, b = avant(agent, t), apres(agent, t)
            pendant += 1
            bouge_pendant += a is not None and cat != a
            if b is not None:
                suivis += 1
                bouge_apres += a is not None and b != a
    incidents = collections.Counter(i["nature"] for i in _par(evs, "incident.v1")
                                    if "conversation" in (i.get("details") or {}))
    return {"conversations": len(par_conv), "repliques": len(repliques),
            "repliques_valides": sum(r["valide"] for r in repliques),
            "participants": pendant,
            "bouge_pendant": bouge_pendant, "part_bouge_pendant": bouge_pendant / pendant if pendant else None,
            "suivis": suivis, "bouge_apres": bouge_apres,
            "part_bouge_apres": bouge_apres / suivis if suivis else None,
            "incidents": dict(incidents)}


# ------------------------------------------------------------------ B1, B3


def sources_valides(evs):
    """v2 : part des changements de sens qui citent au moins une source que
    l'agent a effectivement vue (observation, message ou publication)."""
    vus = collections.defaultdict(set)
    for p in _par(evs, "perception.v2"):
        for canal in ("observations", "messages", "publications"):
            vus[p["agent"]].update(x["id"] for x in p.get(canal, []))
    changements = justifies = 0
    for d, (_, sens_avant) in _avec_veille(evs):
        if d.get("schema") != "decision.v2" or d["categorie"] == sens_avant:
            continue
        changements += 1
        justifies += bool(set(d.get("sources", [])) & vus[d["agent"]])
    return {"changements": changements, "justifies": justifies,
            "part": justifies / changements if changements else None}


def diversite(evs):
    """Entropie normalisee des sens chez les seuls agents LLM, relevee chaque jour.

    0 : tous les LLM donnent le meme sens au ruban ; 1 : les six sens a parts
    egales. On regarde l'etat de chaque agent apres les decisions du jour.
    """
    pop = profils(evs)
    llm = {i for i, a in pop.items() if a.get("moteur") in MOTEURS_LLM}
    if not llm:
        return None
    etat = {}
    par_jour = {}
    for d in sorted(_decisions(evs), key=lambda e: e["t_sim"]):
        if d["agent"] in llm:
            etat[d["agent"]] = d["categorie"]
            par_jour[d["t_sim"] // JOUR] = dict(etat)
    def entropie(cats):
        c = collections.Counter(cats.values())
        n = sum(c.values())
        h = -sum(k / n * math.log(k / n) for k in c.values())
        return h / math.log(6)
    serie = [entropie(v) for _, v in sorted(par_jour.items())]
    return {"moyenne": sum(serie) / len(serie), "fin": serie[-1],
            "sens_distincts_fin": len(set(par_jour[max(par_jour)].values()))} if serie else None


def _norme(texte):
    return " ".join(re.findall(r"[a-z]+", normaliser(texte)))


def quasi_identiques(evs):
    """Messages LLM presque identiques a celui d'un AUTRE agent (ratio >= 0,8).

    Repond a "tous les agents pensent-ils pareil ?" cote formulation : un
    taux eleve veut dire que les agents recitent la meme phrase.
    """
    pop = profils(evs)
    msgs = [(p["agent"], _norme(p["texte"])) for p in evs
            if p.get("schema") in ("publication.v1", "publication.v2")
            and pop.get(p["agent"], {}).get("moteur") in MOTEURS_LLM and p["texte"].strip()]
    doublons = 0
    for i, (a, t) in enumerate(msgs):
        if any(b != a and difflib.SequenceMatcher(None, t, u).ratio() >= SEUIL_QUASI_IDENTIQUE
               for j, (b, u) in enumerate(msgs) if j != i):
            doublons += 1
    return {"messages": len(msgs), "quasi_identiques": doublons,
            "part": doublons / len(msgs) if msgs else None,
            "textes_distincts": len({t for _, t in msgs})}


def _quadrigrammes(texte):
    mots = _norme(texte).split()
    return {tuple(mots[i:i + 4]) for i in range(len(mots) - 3)}


def recouvrement_corpus(evs, dossier_corpus):
    """Part des 4-grammes de chaque texte LLM (message, sens) deja presents dans
    le corpus. Au-dela de 0,5, le LLM recite le corpus au lieu de raisonner."""
    base = Base(dossier_corpus)
    corpus = set()
    for d in base.documents:
        corpus |= _quadrigrammes(d.passage)
    pop = profils(evs)
    textes = [p["texte"] for p in evs if p.get("schema") in ("publication.v1", "publication.v2")
              and pop.get(p["agent"], {}).get("moteur") in MOTEURS_LLM]
    textes += [d["sens"] for d in _decisions(evs) if d["moteur"] in MOTEURS_LLM and d.get("valide")]
    parts = []
    for t in textes:
        q = _quadrigrammes(t)
        if q:
            parts.append(len(q & corpus) / len(q))
    return {"textes": len(parts), "moyenne": sum(parts) / len(parts) if parts else None,
            "max": max(parts) if parts else None,
            "recites": sum(1 for x in parts if x >= SEUIL_RECITE)}


# ------------------------------------------------------------------ C5, C7, E4


def temps(evs, telemetrie):
    """Latences par modele (moyenne, p95), attente de quota, rythme des decisions."""
    appels = collections.defaultdict(list)
    attente = collections.Counter()
    for t in telemetrie:
        if t.get("type") == "appel" and t.get("latence_s") is not None:
            appels[t.get("modele", "?")].append(t["latence_s"])
            attente[t.get("modele", "?")] += t.get("attente_s") or 0.0
    latences = {m: {"appels": len(v), "moyenne": sum(v) / len(v), "p95": _centile(v, 0.95),
                    "attente_s": round(attente[m], 1)} for m, v in sorted(appels.items())}
    par_agent_jour = collections.Counter()
    for d in _decisions(evs):
        if d["moteur"] in MOTEURS_LLM:
            par_agent_jour[(d["agent"], (d["t_sim"] - 1) // JOUR)] += 1
    n = list(par_agent_jour.values())
    return {"latences": latences,
            "decisions_par_agent_jour": sum(n) / len(n) if n else None,
            "decisions_par_agent_jour_max": max(n) if n else None}


# ------------------------------------------------------------------ F2


def echantillon_f2(evs, dossier_corpus, n=30, graine=0):
    """Environ 30 decisions LLM tirees au hasard (graine fixe), avec ce que la
    recherche a retrouve, pour un jugement de pertinence fait a la main (F2)."""
    base = Base(dossier_corpus)
    passages = {(d.id, d.numero): d.passage for d in base.documents}
    decision = {(d["agent"], d["t_sim"]): d for d in _decisions(evs)}
    pop = profils(evs)
    candidats = [r for r in _par(evs, "recuperation.v1") if (r["agent"], r["t_sim"]) in decision]
    tirage = random.Random(graine).sample(candidats, min(n, len(candidats)))
    lignes = []
    for r in sorted(tirage, key=lambda r: (r["t_sim"], r["agent"])):
        d = decision[(r["agent"], r["t_sim"])]
        docs = r.get("resultats", [])
        lignes.append({
            "jour": r["t_sim"] // JOUR, "agent": r["agent"],
            "profil": pop.get(r["agent"], {}).get("profil", "?"), "moteur": d["moteur"],
            "requete": r["requete"],
            "documents": " | ".join(f"{x['id']}#{x.get('numero', '?')} ({x['score']})" for x in docs),
            "passages": " | ".join(passages.get((x["id"], x.get("numero")), "?")[:300] for x in docs),
            "decision": f"{'porte' if d['porte'] else 'ne porte pas'}, {d['categorie']}",
            "raison": d.get("raison", ""),
            "pertinent (oui / en partie / non)": "", "commentaire": "",
        })
    return lignes


def ecrire_csv(lignes, chemin):
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        if lignes:
            w = csv.DictWriter(f, fieldnames=list(lignes[0]))
            w.writeheader()
            w.writerows(lignes)
