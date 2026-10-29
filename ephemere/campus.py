"""Reconstruction de l'etat du campus a partir du flux d'evenements.

Le pont ne garde aucun etat de la simulation : il le RECONSTRUIT en lisant les
evenements, exactement comme le fera n'importe quel consommateur du topic. C'est
ce qui rend le rejeu d'un fichier (E3) strictement equivalent a une lecture en
direct de Kafka.

C'est aussi ici qu'est pose t_traitement (exigences C3 et C7) : le producteur
dit QUAND l'evenement s'est produit dans le monde, le consommateur dit QUAND il
l'a traite. L'ecart entre les deux est la latence du systeme, et elle se mesure.

Modele social v2 : le pont garde en plus le reseau (reseau.v1), les croyances
et les termes du score (decision.v2), et resout les sources citees par une
decision (ids o, m et p) en phrases lisibles. La scene peut ainsi dire
POURQUOI un agent a change de sens sans rien recalculer (exigence D2).
"""
from collections import Counter, OrderedDict
from datetime import datetime

from .contrat import SCHEMAS_RUN, SENS, modele_social

# Contre-tendance (affichage, pas indicateur de l'etude) : au moins 15 % du
# campus, et au moins 2 agents, qui le meme jour se mettent a porter le ruban
# par ironie, ou l'enlevent.
PART_ENSEMBLE = 0.15

# Ids d'observation, de message et de publication gardes pour resoudre les
# sources : la fenetre de perception est de 3 jours, 20 agents en voient
# environ 5 par jour chacun, la marge est large.
IDS_GARDES = 5000


class Campus:
    def __init__(self, agents=None, en_direct=True):
        self.profils = {a["id"]: a for a in (agents or [])}
        # En rejeu, t_emission date du run d'origine : l'ecart avec
        # t_traitement ne mesurerait que l'anciennete du fichier.
        self.en_direct = en_direct
        self.reinitialiser(None)

    def reinitialiser(self, run):
        self.run = run
        self.t_sim = 0
        self.t_sim_lisible = "J01 00:00"
        self.agents = {}
        self.fil = []
        self.historique = []
        self.incidents = Counter()
        self.latences_ms = []     # duree du traitement dans le pont
        self.delais_ms = []       # t_traitement - t_emission, exigence C7
        self.vus = 0
        self.modele_social = "v1"
        self.cloisonne = False
        self.liens = []
        self.ids = OrderedDict()  # id o/m/p -> phrase lisible
        self.injections = []      # D3 : reperees sur la courbe pour en voir l'effet
        self.regards = []         # v2 : [qui voit, qui est vu, via, porte], jour en cours
        self.regards_t = None
        self.jours = None
        self.sens_groupes = []    # B1 : par releve, le sens de chaque groupe
        self.contre_tendances = []
        self._releve_avant = None

    def _agent(self, aid):
        if aid not in self.agents:
            p = self.profils.get(aid, {})
            self.agents[aid] = {
                "id": aid, "nom": p.get("nom", aid.capitalize()),
                "profil": p.get("profil", "?"), "groupe": p.get("groupe", "?"),
                "moteur": p.get("moteur", "?"), "porte": bool(p.get("porte", False)),
                "categorie": "aucun_sens", "sens": "", "raison": "",
                "memoire": [], "valide": True, "derniere_maj": None,
                "traits": p.get("traits"),
            }
        return self.agents[aid]

    def appliquer(self, evt, cle=None):
        """Integre un evenement et renvoie l'etat a diffuser."""
        schema = evt.get("schema", "")
        if schema in SCHEMAS_RUN or (cle and cle != self.run):
            self.reinitialiser(cle or evt.get("run"))
        if schema in SCHEMAS_RUN:
            self.modele_social = modele_social(evt)
            self.cloisonne = bool(evt.get("cloisonne", False))
            self.jours = evt.get("jours")
        self.vus += 1

        # Horodatage du traitement : la deuxieme horloge exigee par C3, meme
        # format et meme precision que t_emission pour pouvoir les soustraire.
        traite = datetime.now()
        evt["t_traitement"] = traite.isoformat(timespec="milliseconds")
        evt["delai_ms"] = None
        if self.en_direct and evt.get("t_emission"):
            try:
                emis = datetime.fromisoformat(evt["t_emission"])
                evt["delai_ms"] = round((traite - emis).total_seconds() * 1000, 1)
                self.delais_ms.append(evt["delai_ms"])
            except ValueError:
                pass
        if evt.get("t_sim") is not None:
            self.t_sim = evt["t_sim"]
            self.t_sim_lisible = evt.get("t_sim_lisible", "")

        if schema == "population.v1":
            for a in evt.get("agents", []):
                self.profils[a["id"]] = a
                self._agent(a["id"])["porte"] = bool(a.get("porte"))
                self.agents[a["id"]]["categorie"] = (
                    "cercle_creatif" if a.get("porte") else "aucun_sens")
        elif schema == "population.v2":
            for a in evt.get("agents", []):
                self.profils[a["id"]] = a
                x = self._agent(a["id"])
                x["porte"] = bool(a.get("porte"))
                x["categorie"] = a.get("categorie") or (
                    "cercle_creatif" if a.get("porte") else "aucun_sens")
                x.update({"sens_percu": "aucun_sens", "confiance": None, "termes": None,
                          "sources": [], "sources_quand": "", "vu": None})
        elif schema == "reseau.v1":
            self.liens = [{"a": l["a"], "b": l["b"], "type": l["type"]}
                          for l in evt.get("liens", [])]
            self.cloisonne = bool(evt.get("cloisonne", self.cloisonne))
        elif schema == "perception.v2":
            self._percevoir(evt)
        elif schema == "decision.v2":
            self._decider_v2(evt)
        elif schema == "decision.v1":
            a = self._agent(evt["agent"])
            a.update({k: evt[k] for k in ("porte", "categorie", "sens", "raison",
                                          "moteur", "valide") if k in evt})
            a["derniere_maj"] = evt.get("t_sim_lisible")
            a["memoire"] = (a["memoire"] + [{
                "t_sim_lisible": evt.get("t_sim_lisible", ""),
                "fait": ("il porte le ruban" if evt["porte"] else "il ne le porte pas"),
                "raison": evt.get("raison", ""),
            }])[-8:]
        elif schema in ("publication.v1", "publication.v2"):
            a = self._agent(evt["agent"])
            dest = evt.get("destinataire")
            self._au_fil({
                "auteur": a["nom"], "texte": evt["texte"],
                "portee": evt.get("portee", "campus"),
                "destinataire": self.agents[dest]["nom"] if dest in self.agents else dest,
                "categorie": evt.get("categorie"),
                "t_sim_lisible": evt.get("t_sim_lisible", ""),
            })
            if evt.get("id"):
                ou = "lui a écrit" if evt.get("portee") == "personne" else "a publié"
                self._retenir(evt["id"], f"{a['nom']} {ou} : \"{evt['texte']}\"")
        elif schema == "replique.v1" and evt.get("valide"):
            # Conversation privee (A2) : au fil comme un message prive, et dans
            # la memoire du destinataire pour l'inspection (D2).
            a = self._agent(evt["agent"])
            dest = evt["destinataire"]
            self._au_fil({"auteur": a["nom"], "texte": evt["texte"], "portee": "personne",
                          "destinataire": self._nom(dest), "categorie": evt.get("categorie"),
                          "t_sim_lisible": evt.get("t_sim_lisible", "")})
            d = self._agent(dest)
            d["memoire"] = (d["memoire"] + [{
                "t_sim_lisible": evt.get("t_sim_lisible", ""),
                "fait": f"{a['nom']} m'a répondu : \"{evt['texte']}\"", "raison": "",
            }])[-8:]
        elif schema == "injection.v1":
            self.injections.append({"t_sim": evt.get("t_sim", self.t_sim),
                                    "t_sim_lisible": evt.get("t_sim_lisible", ""),
                                    "nature": evt.get("nature", "?")})
        elif schema == "incident.v1":
            self.incidents[evt.get("nature", "?")] += 1
            if evt.get("agent"):
                self._agent(evt["agent"])["valide"] = False
        elif schema == "indicateurs.v1":
            self.historique = [h for h in self.historique if h["t_sim"] < evt["t_sim"]]
            self.historique.append({
                "t_sim": evt["t_sim"], "t_sim_lisible": evt.get("t_sim_lisible", ""),
                "taux_adoption": evt["taux_adoption"],
                "sens_dominant": evt["sens_dominant"],
                "part_sens_dominant": evt["part_sens_dominant"],
            })
            self._relever_groupes(evt)
        return evt

    def _au_fil(self, m):
        """Un message identique a un message deja au fil s'y ajoute, au lieu de
        repousser les autres : "c'est depasse x12, J24 a J26"."""
        meme = next((f for f in self.fil if f["texte"] == m["texte"]), None)
        if meme is None:
            m.update({"n": 1, "premier": m["t_sim_lisible"], "auteurs": [m["auteur"]]})
            self.fil = (self.fil + [m])[-12:]
            return
        self.fil.remove(meme)
        meme["n"] += 1
        meme.update({k: m[k] for k in ("auteur", "portee", "destinataire", "t_sim_lisible")})
        if m["auteur"] not in meme["auteurs"]:
            meme["auteurs"].append(m["auteur"])
        self.fil.append(meme)

    def _relever_groupes(self, evt):
        """Sens de chaque groupe au releve (B1), et contre-tendances du jour."""
        groupes = {}
        for a in self.agents.values():
            g = groupes.setdefault(a["groupe"], {"total": 0, "porteurs": 0, "repartition": Counter()})
            g["total"] += 1
            g["porteurs"] += a["porte"]
            g["repartition"][a["categorie"]] += 1
        for g in groupes.values():
            dominant, nb = g["repartition"].most_common(1)[0]
            g.update({"dominant": dominant, "part": round(nb / g["total"], 3),
                      "repartition": dict(g["repartition"])})
        self.sens_groupes = [s for s in self.sens_groupes if s["t_sim"] < evt["t_sim"]] + [
            {"t_sim": evt["t_sim"], "t_sim_lisible": evt.get("t_sim_lisible", ""),
             "groupes": groupes}]

        etat = {i: (a["porte"], a["categorie"]) for i, a in self.agents.items()}
        avant, self._releve_avant = self._releve_avant, etat
        if avant is None:
            return
        seuil = max(2, PART_ENSEMBLE * len(etat))
        ironie = [i for i, (p, c) in etat.items() if p and c == "ironie"
                  and avant.get(i, (False, ""))[:2] != (True, "ironie")]
        abandon = [i for i, (p, _) in etat.items() if not p and avant.get(i, (False, ""))[0]]
        for nature, qui in (("ironie", ironie), ("abandon", abandon)):
            if len(qui) >= seuil:
                self.contre_tendances.append({
                    "t_sim": evt["t_sim"], "t_sim_lisible": evt.get("t_sim_lisible", ""),
                    "nature": nature, "qui": sorted(self._nom(i) for i in qui)})

    def _retenir(self, ident, phrase):
        self.ids[ident] = phrase
        while len(self.ids) > IDS_GARDES:
            self.ids.popitem(last=False)

    def _nom(self, aid):
        return self.agents[aid]["nom"] if aid in self.agents else aid

    def _percevoir(self, evt):
        """Ce que l'agent a vu ce jour-la, et de quoi resoudre ses futures sources."""
        a = self._agent(evt["agent"])
        obs = evt.get("observations", [])
        # Les regards du jour, pour le plan du campus : chaque jour remplace le precedent.
        if evt.get("t_sim") != self.regards_t:
            self.regards, self.regards_t = [], evt.get("t_sim")
        self.regards += [[evt["agent"], o["qui"], o.get("via", ""), bool(o["porte"])]
                         for o in obs]
        for o in obs:
            via = {"fort": "un proche", "faible": "une connaissance"}.get(o.get("via"), "croisé")
            self._retenir(o["id"], f"vu {self._nom(o['qui'])} ({via}, "
                                   f"{o['groupe'].replace('_', ' ')}) "
                                   f"{'avec' if o['porte'] else 'sans'} le ruban")
        a["vu"] = {
            "personnes": len(obs),
            "porteurs": sum(1 for o in obs if o["porte"]),
            "porteurs_noms": [self._nom(o["qui"]) for o in obs if o["porte"]],
            "messages": len(evt.get("messages", [])),
            "publications": len(evt.get("publications", [])),
        }
        for m in evt.get("messages", []):
            a["memoire"] = (a["memoire"] + [{
                "t_sim_lisible": evt.get("t_sim_lisible", ""),
                "fait": f"{m.get('nom_auteur', self._nom(m.get('de', '')))} m'a dit : "
                        f"\"{m.get('texte', '')}\"", "raison": "",
            }])[-8:]

    def _decider_v2(self, evt):
        a = self._agent(evt["agent"])
        avant_porte, avant_sens = a["porte"], a["categorie"]
        a.update({k: evt[k] for k in ("porte", "categorie", "sens", "sens_percu", "confiance",
                                      "raison", "moteur", "valide", "termes") if k in evt})
        # Les sources du dernier CHANGEMENT d'avis : la plupart des jours, rien
        # ne change et la decision n'en cite aucune.
        if evt.get("sources"):
            a["sources"] = [{"id": i, "texte": self.ids.get(i, "(hors fenêtre)")}
                            for i in evt["sources"]]
            a["sources_quand"] = evt.get("t_sim_lisible", "")
        a["derniere_maj"] = evt.get("t_sim_lisible")
        faits = []
        if a["porte"] != avant_porte:
            faits.append("met le ruban" if a["porte"] else "enlève le ruban")
        if a["categorie"] != avant_sens:
            faits.append(f"le lit désormais comme {a['categorie'].replace('_', ' ')}")
        if faits:
            a["memoire"] = (a["memoire"] + [{
                "t_sim_lisible": evt.get("t_sim_lisible", ""),
                "fait": ", ".join(faits), "raison": evt.get("raison", ""),
            }])[-8:]

    def indicateurs(self):
        """Recalcules en direct, sans attendre le prochain releve (exigence B2)."""
        n = len(self.agents) or 1
        cats = Counter(a["categorie"] for a in self.agents.values())
        dominant, nb = cats.most_common(1)[0] if cats else ("aucun_sens", 0)
        return {
            "t_sim": self.t_sim, "t_sim_lisible": self.t_sim_lisible,
            "taux_adoption": sum(a["porte"] for a in self.agents.values()) / n,
            "repartition_sens": {s: cats.get(s, 0) for s in SENS},
            "sens_dominant": dominant, "part_sens_dominant": nb / n,
            "incidents": dict(self.incidents),
            "evenements_vus": self.vus,
            "delai_traitement_ms": resumer_delais(self.delais_ms),
        }

    def instantane(self):
        return {"type": "etat", "run": self.run, "modele_social": self.modele_social,
                "cloisonne": self.cloisonne, "liens": self.liens,
                "agents": sorted(self.agents.values(), key=lambda a: a["nom"]),
                "indicateurs": self.indicateurs(),
                "historique": self.historique, "fil": self.fil,
                "injections": self.injections, "regards": self.regards,
                "regards_t": self.regards_t, "jours": self.jours,
                "sens_groupes": self.sens_groupes,
                "contre_tendances": self.contre_tendances}


def resumer_delais(delais):
    """Moyenne, mediane, 95e centile et pire cas du delai emission -> traitement."""
    if not delais:
        return None
    tries = sorted(delais)
    return {"n": len(tries), "moyen": round(sum(tries) / len(tries), 1),
            "median": tries[len(tries) // 2],
            "p95": tries[min(len(tries) - 1, int(len(tries) * 0.95))],
            "max": tries[-1]}
