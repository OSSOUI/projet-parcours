"""Reconstruction de l'etat du campus a partir du flux d'evenements.

Le pont ne garde aucun etat de la simulation : il le RECONSTRUIT en lisant les
evenements, exactement comme le fera n'importe quel consommateur du topic. C'est
ce qui rend le rejeu d'un fichier (E3) strictement equivalent a une lecture en
direct de Kafka.

C'est aussi ici qu'est pose t_traitement (exigences C3 et C7) : le producteur
dit QUAND l'evenement s'est produit dans le monde, le consommateur dit QUAND il
l'a traite. L'ecart entre les deux est la latence du systeme, et elle se mesure.
"""
from collections import Counter
from datetime import datetime

from .contrat import SCHEMAS_RUN, SENS


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

    def _agent(self, aid):
        if aid not in self.agents:
            p = self.profils.get(aid, {})
            self.agents[aid] = {
                "id": aid, "nom": p.get("nom", aid.capitalize()),
                "profil": p.get("profil", "?"), "groupe": p.get("groupe", "?"),
                "moteur": p.get("moteur", "?"), "porte": bool(p.get("porte", False)),
                "categorie": "aucun_sens", "sens": "", "raison": "",
                "memoire": [], "valide": True, "derniere_maj": None,
            }
        return self.agents[aid]

    def appliquer(self, evt, cle=None):
        """Integre un evenement et renvoie l'etat a diffuser."""
        schema = evt.get("schema", "")
        if schema in SCHEMAS_RUN or (cle and cle != self.run):
            self.reinitialiser(cle or evt.get("run"))
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
        elif schema == "publication.v1":
            a = self._agent(evt["agent"])
            self.fil = (self.fil + [{
                "auteur": a["nom"], "texte": evt["texte"],
                "portee": evt.get("portee", "campus"),
                "destinataire": evt.get("destinataire"),
                "t_sim_lisible": evt.get("t_sim_lisible", ""),
            }])[-12:]
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
        return evt

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
        return {"type": "etat", "run": self.run,
                "agents": sorted(self.agents.values(), key=lambda a: a["nom"]),
                "indicateurs": self.indicateurs(),
                "historique": self.historique, "fil": self.fil}


def resumer_delais(delais):
    """Moyenne, mediane, 95e centile et pire cas du delai emission -> traitement."""
    if not delais:
        return None
    tries = sorted(delais)
    return {"n": len(tries), "moyen": round(sum(tries) / len(tries), 1),
            "median": tries[len(tries) // 2],
            "p95": tries[min(len(tries) - 1, int(len(tries) * 0.95))],
            "max": tries[-1]}
