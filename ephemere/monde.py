"""Etat du campus et indicateurs d'emergence (exigences B1, B2).

Le contexte commun d'Ephemere, defini en termes observables : la part
des agents qui attribuent au ruban le MEME sens, pris dans la liste
fermee de contrat.SENS.

  part_sens_dominant = 1.0  tout le campus donne le meme sens au ruban
  part_sens_dominant = 0.3  six lectures concurrentes, aucune ne domine

Le taux d'adoption seul ne suffit pas : on peut avoir 80 % de porteurs
qui ne s'accordent sur rien. C'est justement la difference entre une mode
et un contexte commun.
"""
from collections import Counter

from .contrat import SENS


class Monde:
    def __init__(self, agents, perception=None):
        self.agents = {a["id"]: a for a in agents}
        p = perception or {}
        self.poids_groupe = p.get("poids_groupe", 0.4)
        self.poids_campus = p.get("poids_campus", 0.6)
        self.fil = []          # messages du reseau interne, horodates en temps simule
        self.historique = []   # un point d'indicateurs par releve

    # ------------------------------------------------------------ reseau
    def publier(self, agent_id, texte, t_sim, portee="campus"):
        """Message public sur le reseau interne du campus."""
        self.fil.append({"agent": agent_id,
                         "nom_auteur": self.agents[agent_id]["nom"],
                         "texte": texte, "t_sim": t_sim, "portee": portee})

    def adresser(self, de, vers_nom, texte, t_sim, t_lisible):
        """Message adresse a une personne precise (exigence A2).

        Il n'entre pas dans le fil public : il atterrit directement dans la
        memoire du destinataire, en tant qu'echange. C'est ce souvenir-la que
        l'exigence A1 demande de pouvoir retrouver plusieurs jours plus tard.
        Renvoie l'id du destinataire, ou None si le nom ne correspond a personne.
        """
        cible = next((a for a in self.agents.values()
                      if a["nom"].lower() == vers_nom.strip().lower()), None)
        if cible is None or cible["id"] == de:
            return None
        cible["memoire"] = (cible.get("memoire", []) + [{
            "genre": "echange", "t_sim": t_sim, "t_sim_lisible": t_lisible,
            "fait": f"{self.agents[de]['nom']} m'a dit : \"{texte}\"",
            "raison": "",
        }])[-12:]
        return cible["id"]

    def fil_visible(self, agent, t_sim, limite=8):
        """Messages qu'un agent POUVAIT avoir lus a cet instant simule (C6).

        Un message publie apres t_sim n'existe pas encore pour lui, et un
        message publie avant son dernier passage sur le reseau est deja vu.
        """
        vus = [m for m in self.fil
               if m["t_sim"] <= t_sim and m["agent"] != agent["id"]
               and (m["portee"] == "campus" or m["portee"] == agent["groupe"])]
        return vus[-limite:]

    # ------------------------------------------------------- observation
    def porteurs(self):
        return [a["id"] for a in self.agents.values() if a["porte"]]

    def taux_adoption(self):
        if not self.agents:
            return 0.0
        return sum(a["porte"] for a in self.agents.values()) / len(self.agents)

    def taux_dans_groupe(self, groupe):
        pairs = [a for a in self.agents.values() if a["groupe"] == groupe]
        if not pairs:
            return 0.0
        return sum(a["porte"] for a in pairs) / len(pairs)

    def adoption_percue(self, agent):
        """Ce que CET agent croit voir : son groupe de pres, le campus de loin."""
        return (self.poids_groupe * self.taux_dans_groupe(agent["groupe"])
                + self.poids_campus * self.taux_adoption())

    def porteurs_du_groupe(self, agent):
        """Les porteurs que l'agent voit AUTOUR de lui, lui-meme exclu.

        Sans cette exclusion, les deux pionnieres seules dans l'atelier voient
        "100 % de mon groupe le porte", en concluent que c'est devenu banal, et
        abandonnent des le jour 2. La mode s'eteignait avant de naitre.
        """
        pairs = [a for a in self.agents.values()
                 if a["groupe"] == agent["groupe"] and a["id"] != agent["id"]]
        return [a for a in pairs if a["porte"]], pairs

    def tendance(self, fenetre=3):
        """en hausse, stable ou en baisse, d'apres les derniers releves."""
        h = [e["taux_adoption"] for e in self.historique[-fenetre:]]
        if len(h) < 2:
            return "trop tot pour le dire"
        ecart = h[-1] - h[0]
        if ecart > 0.05:
            return "en hausse"
        if ecart < -0.05:
            return "en baisse"
        return "stable"

    def indicateurs(self):
        n = len(self.agents) or 1
        cats = Counter(a["categorie"] for a in self.agents.values())
        dominant, nb = cats.most_common(1)[0]
        return {
            "taux_adoption": self.taux_adoption(),
            "repartition_sens": {s: cats.get(s, 0) for s in SENS},
            "sens_dominant": dominant,
            "part_sens_dominant": nb / n,
            "porteurs": self.porteurs(),
        }

    def noter(self, t_sim, ind):
        self.historique.append({"t_sim": t_sim, **ind})
