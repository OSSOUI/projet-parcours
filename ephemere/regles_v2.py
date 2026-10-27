"""Agents a regles du modele social v2 : un score, des croyances, aucune etiquette.

Decision du jour (porter demain si S > 0) :

    S = a.E + n.exp(-t/tau) - d.(alpha.R + beta.P) - L - theta + eps

  a, n, d, theta  traits appartenance, nouveaute, distinction, seuil
  E      part ponderee des personnes vues avec le ruban (lien fort 1,0, faible 0,3)
  t      jours depuis que l'agent a vu le ruban pour la premiere fois (la
         nouveaute est relative a chacun : qui le decouvre au J10 le trouve
         neuf) ; option apparition = depuis J1 pour tous, lecture litterale.
         usure a faux : la nouveaute ne s'emousse pas, elle ne fait que lancer.
  R      part des porteurs vus recemment venant d'un groupe d'affinite negative
  P      1 si l'agent croit que le campus le lit comme suivre_la_foule ou ringard
  L      lassitude : monte chaque jour porte, redescend chaque jour sans
  eps    bruit tire de la graine dynamique

Le couplage sens -> adoption tient entierement dans le terme d.(alpha.R + beta.P) :
distinction a faux l'eteint pour tous, alpha = 0 ou beta = 0 n'en garde qu'une
source. Chaque terme a son interrupteur dans config["decision"].

Croyances (inspirees du naming game) :
  sens_percu  le sens le plus entendu (messages et publications) sur la fenetre ;
              sans rien entendu, deduit des porteurs vus : plus de la moitie
              hors de l'atelier -> suivre_la_foule ; sinon inchange.
  sens_perso  avec une probabilite 1 - confiance, l'agent adopte le sens le plus
              entendu chez ses liens forts.
  regle 3     qui abandonne a cause du terme de distinction passe a ringard
              (desactivable : sans elle, ringard ne peut venir que des LLM).
Chaque changement de croyance cite les ids qui l'ont provoque (sources).
"""
import math
import random
from collections import Counter

from .contrat import SENS
from .monde_v2 import exposition

LECTURES_REJETEES = ("suivre_la_foule", "ringard")


def initialiser(agent, reglage):
    """Etat v2 de depart : croyances, lassitude et tampons de perception."""
    porteur = agent["porte"]
    agent.update({
        "sens_perso": agent["categorie"],
        "sens_percu": "aucun_sens",
        "confiance": reglage["confiance_initiale"]["porteur" if porteur else "autre"],
        "lassitude": 0.0,
        "premiere_vue": 0 if porteur else None,
        "vus_recents": [],
        "entendus": [],
    })


def percevoir(agent, vu, t_sim, reglage):
    """Range ce que l'agent vient d'observer dans ses tampons, sur la fenetre."""
    debut = t_sim - reglage["fenetre_jours"] * 1440
    agent["vus_recents"] = [o for o in agent["vus_recents"] if o["t_sim"] > debut] + [
        {**o, "t_sim": t_sim} for o in vu["observations"]]
    entendus = [{"id": m["id"], "categorie": m["categorie"], "canal": m["lien"], "t_sim": m["t_sim"]}
                for m in vu["messages"] if m.get("categorie") in SENS]
    entendus += [{"id": p["id"], "categorie": p["categorie"], "canal": "public", "t_sim": p["t_sim"]}
                 for p in vu["publications"] if p.get("categorie") in SENS]
    agent["entendus"] = [e for e in agent["entendus"] if e["t_sim"] > debut] + entendus
    if agent["premiere_vue"] is None and any(o["porte"] for o in vu["observations"]):
        agent["premiere_vue"] = t_sim


def _plus_entendu(entendus, actuel):
    """Le sens le plus entendu ; a egalite, le sens actuel puis l'ordre de la liste."""
    if not entendus:
        return None, []
    compte = Counter(e["categorie"] for e in entendus)
    ordre = list(SENS)
    sens = max(compte, key=lambda s: (compte[s], s == actuel, -ordre.index(s)))
    return sens, [e["id"] for e in entendus if e["categorie"] == sens]


class ReglesV2:
    def __init__(self, reglage, graine_dynamique):
        self.r = reglage
        # Chaine distincte de celle du monde (personnes croisees), meme graine.
        self.rng = random.Random(f"{graine_dynamique}:regles")

    def termes(self, agent, vu, t_sim):
        """Chaque terme du score, separement : c'est ce que decision.v2 trace."""
        r, tr = self.r, agent["traits"]
        E = vu["agregat_v1"] if r["exposition"] == "agregat_v1" else exposition(vu["observations"])
        t0 = agent["premiere_vue"] if r["nouveaute_depuis"] == "premiere_vue" else 0
        if t0 is None:
            nouveaute = 0.0
        elif r["usure"]:
            nouveaute = tr["nouveaute"] * math.exp(-(t_sim - t0) / 1440 / r["tau_jours"])
        else:
            nouveaute = tr["nouveaute"]
        porteurs = {}
        for o in agent["vus_recents"]:
            if o["porte"]:
                porteurs[o["qui"]] = o
        repoussoirs = [o for o in porteurs.values() if tr["affinites"].get(o["groupe"], 0) < 0]
        R = len(repoussoirs) / len(porteurs) if porteurs else 0.0
        P = 1.0 if agent["sens_percu"] in LECTURES_REJETEES else 0.0
        distinction = tr["distinction"] * (r["alpha"] * R + r["beta"] * P) if r["distinction"] else 0.0
        return {
            "appartenance": tr["appartenance"] * E,
            "nouveaute": nouveaute if r["nouveaute"] else 0.0,
            "distinction": distinction,
            "lassitude": agent["lassitude"] if r["lassitude"]["actif"] else 0.0,
            "seuil": tr["seuil"],
            "bruit": self.rng.gauss(0, r["bruit"]) if r["bruit"] else 0.0,
            "E": E, "R": R, "P": P,
            "_repoussoirs": [o["id"] for o in repoussoirs],
        }

    def decider(self, agent, monde, vu, t_sim, horloge_lisible=""):
        r = self.r
        t = self.termes(agent, vu, t_sim)
        sans_distinction = (t["appartenance"] + t["nouveaute"] - t["lassitude"]
                            - t["seuil"] + t["bruit"])
        S = sans_distinction - t["distinction"]
        porte = S > 0

        sources = []
        sens_percu, ids = _plus_entendu(agent["entendus"], agent["sens_percu"])
        if sens_percu is None:
            porteurs = [o for o in agent["vus_recents"] if o["porte"]]
            dehors = [o for o in porteurs if o["groupe"] != "atelier_design"]
            if r["deduction_foule"] and porteurs and len(dehors) > len(porteurs) / 2:
                sens_percu, ids = "suivre_la_foule", [o["id"] for o in dehors]
            else:
                sens_percu, ids = agent["sens_percu"], []
        if sens_percu != agent["sens_percu"]:
            sources += ids

        sens_perso, confiance = agent["sens_perso"], agent["confiance"]
        forts = [e for e in agent["entendus"] if e["canal"] == "fort"]
        entendu, ids = _plus_entendu(forts, sens_perso)
        if entendu and entendu != sens_perso and self.rng.random() < 1 - confiance:
            sens_perso, confiance = entendu, r["confiance_apres_changement"]
            sources += ids
        # Regle 3 : il portait, il arrete, et sans le cout de distinction il aurait garde.
        if r["regle3"] and agent["porte"] and not porte and sans_distinction > 0:
            if sens_perso != "ringard":
                sens_perso = "ringard"
                sources += t["_repoussoirs"] or ids
        sources = list(dict.fromkeys(sources))

        publication, destinataire = "", ""
        if sens_perso != "aucun_sens" and self.rng.random() < r["parole"]["p"]:
            publication = SENS[sens_perso]
            if self.rng.random() >= r["parole"]["public"]:
                forts_voisins = sorted(v for v, p in monde.voisins[agent["id"]].items() if p >= 1)
                if forts_voisins:
                    destinataire = monde.agents[self.rng.choice(forts_voisins)]["nom"]

        termes = {k: round(v, 4) for k, v in t.items() if not k.startswith("_")}
        return {"porte": bool(porte), "categorie": sens_perso, "sens": SENS[sens_perso],
                "sens_percu": sens_percu, "confiance": round(confiance, 3), "sources": sources,
                "raison": f"score {S:+.3f}", "termes": {**termes, "S": round(S, 4)},
                "publication": publication, "destinataire": destinataire,
                "categorie_message": sens_perso if publication else None,
                "valide": True, "moteur": "regles"}


def appliquer(agent, d, reglage):
    """Ecrit la decision v2 dans l'etat de l'agent, lassitude comprise."""
    l = reglage["lassitude"]
    if d["porte"]:
        agent["lassitude"] = round(agent["lassitude"] + l["hausse"], 4)
        agent["minutes_porte"] += 1440
    else:
        agent["lassitude"] = round(max(0.0, agent["lassitude"] - l["baisse"]), 4)
    agent["porte"] = d["porte"]
    agent["categorie"] = agent["sens_perso"] = d["categorie"]
    agent["sens"] = d["sens"]
    agent["sens_percu"] = d["sens_percu"]
    agent["confiance"] = d["confiance"]
