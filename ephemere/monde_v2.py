"""Le campus du modele v2 : un agent ne connait que ce qu'il observe.

En v1, chaque agent lisait directement le taux d'adoption de son groupe et du
campus (adoption_percue). En v2, ce taux reste calcule pour l'observateur (les
indicateurs), mais aucun agent n'y a acces. Il ne recoit que trois canaux,
chacun tracable par identifiant :

  observation   le poignet de ses voisins du reseau, plus 2 ou 3 personnes
                croisees au hasard dans son lieu (graine dynamique) ;
  conversation  les messages prives qu'un voisin du reseau lui a adresses ;
  public        les dernieres publications du reseau interne, coupable dans
                une configuration de controle.

Ce qu'un agent voit d'un autre, c'est s'il porte le ruban et de quel groupe il
est. Jamais le sens qu'il lui donne : le sens ne circule que par les messages.

En cloisonne (reseau sans ponts), rien ne vient d'un autre groupe, par aucun
canal. Chaque decision v2 enregistre les identifiants de ce qu'elle a vu
(perception.v2) : c'est ce qui relie un changement de croyance a sa cause.
"""
import random

from .monde import Monde, memoriser
from .reseau import voisins


class AccesInterdit(RuntimeError):
    """Un agent v2 a demande un agregat qu'il ne peut pas connaitre."""


class MondeV2(Monde):
    def __init__(self, agents, liens, reglage, graine_dynamique, cloisonne=False,
                 canal_public=True, agregat_v1=False):
        super().__init__(agents)
        # Reserve au test de coherence : donne a l'agent l'entree de v1 (taux du
        # groupe et du campus), pour comparer les deux modeles a entrees egales.
        self.agregat_v1 = agregat_v1
        self.liens = liens
        self.voisins = voisins(liens)
        self._cloisonne = cloisonne
        self.canal_public = canal_public
        self.croises = reglage["croises"]
        self.poids_croise = reglage["poids_croise"]
        self.publications_lues = reglage["publications_lues"]
        self.rng = random.Random(graine_dynamique)
        self.boites = {aid: [] for aid in self.agents}
        self._compteurs = {"o": 0, "m": 0, "p": 0}

    def _nouvel_id(self, prefixe):
        self._compteurs[prefixe] += 1
        return f"{prefixe}{self._compteurs[prefixe]}"

    @property
    def cloisonne(self):
        return self._cloisonne

    # ------------------------------------------- ce que v2 interdit a l'agent
    def adoption_percue(self, agent):
        raise AccesInterdit("v2 : un agent ne connait pas le taux d'adoption, seulement ses observations")

    def porteurs_du_groupe(self, agent):
        raise AccesInterdit("v2 : un agent ne voit que ses voisins et les personnes croisees")

    def meneurs_porteurs(self):
        raise AccesInterdit("v2 : un agent ne sait pas qui sont les meneurs")

    # ------------------------------------------------------------- canaux
    def publier(self, agent_id, texte, t_sim, portee="campus", categorie=None):
        """Publication sur le reseau interne. Renvoie son id, ou None si le canal est coupe.

        categorie : le sens que l'auteur transmet, quand il le dit (un agent a
        regles le dit toujours). C'est ce que les autres "entendent".
        """
        if not self.canal_public:
            return None
        pid = self._nouvel_id("p")
        self.fil.append({"id": pid, "agent": agent_id, "nom_auteur": self.agents[agent_id]["nom"],
                         "texte": texte, "t_sim": t_sim, "portee": portee, "categorie": categorie})
        return pid

    def adresser(self, de, vers_nom, texte, t_sim, t_lisible, categorie=None):
        """Message prive a un voisin du reseau. Renvoie (destinataire, id) ou None.

        Comme en v1, il entre dans la memoire du destinataire comme echange,
        mais avec l'id du message : un changement de sens pourra le citer.
        """
        cible = next((a for a in self.agents.values()
                      if a["nom"].lower() == vers_nom.strip().lower()), None)
        if cible is None or cible["id"] == de or cible["id"] not in self.voisins[de]:
            return None
        mid = self._nouvel_id("m")
        message = {"id": mid, "de": de, "nom_auteur": self.agents[de]["nom"],
                   "texte": texte, "t_sim": t_sim, "categorie": categorie,
                   "lien": "fort" if self.voisins[de][cible["id"]] >= 1 else "faible"}
        self.boites[cible["id"]].append(message)
        cible["memoire"] = memoriser(cible.get("memoire", []), {
            "genre": "echange", "t_sim": t_sim, "t_sim_lisible": t_lisible,
            "fait": f"{self.agents[de]['nom']} m'a dit : \"{texte}\"", "raison": "",
            "source": mid,
        })
        return cible["id"], mid

    def _vu(self, autre, via, poids):
        return {"id": self._nouvel_id("o"), "qui": autre["id"], "groupe": autre["groupe"],
                "porte": autre["porte"], "via": via, "poids": poids}

    def observer(self, agent, t_sim):
        """Tout ce que l'agent apprend a t_sim, chaque element avec son id.

        Les messages et publications lus sont marques comme vus : un second
        appel au meme instant ne les renvoie plus.
        """
        aid = agent["id"]
        observations = [self._vu(self.agents[v], "fort" if p >= 1 else "faible", p)
                        for v, p in sorted(self.voisins[aid].items())]
        deja = set(self.voisins[aid]) | {aid}
        lieu = sorted(a for a, x in self.agents.items()
                      if x["groupe"] == agent["groupe"] and a not in deja)
        nb = min(len(lieu), self.rng.randint(*self.croises))
        observations += [self._vu(self.agents[a], "lieu", self.poids_croise)
                         for a in self.rng.sample(lieu, nb)]

        boite = self.boites[aid]
        messages = [m for m in boite if m["t_sim"] <= t_sim]
        self.boites[aid] = [m for m in boite if m["t_sim"] > t_sim]

        publications = []
        if self.canal_public:
            publications = self.fil_visible(agent, t_sim, limite=self.publications_lues)
            self.marquer_lu(agent, t_sim)
        vu = {"observations": observations, "messages": messages, "publications": publications}
        if self.agregat_v1:
            vu["agregat_v1"] = Monde.adoption_percue(self, agent)
        return vu


def exposition(observations):
    """Part ponderee des personnes vues avec le ruban : le terme E du score."""
    total = sum(o["poids"] for o in observations)
    return sum(o["poids"] for o in observations if o["porte"]) / total if total else 0.0
