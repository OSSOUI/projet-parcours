"""Agents LLM : decision, memoire, echanges et detection des derives.

Couvre les exigences A1 (memoire propre qui influence la decision),
A2 (echanges en langage naturel qui modifient le destinataire),
A3 (deux profils differents decident differemment) et
A4 (le systeme tient quand un agent deraille, et chaque incident est compte).

Le piege du sujet, annonce dans la fiche : un LLM aligne sur la securite
repond volontiers en assistant prudent au lieu d'incarner un etudiant.
On ne peut pas l'empecher, alors on le MESURE : detecter_derive() repere
la posture d'assistant et chaque occurrence part dans un evenement
incident.v1. Le taux de sortie de role devient un resultat du rapport.
"""
import re

from .contrat import SENS, normaliser_categorie

SYSTEME = """Tu es un etudiant de la cite universitaire de Tessaline.
Tu restes dans ton personnage du debut a la fin.
Tu n'es pas un assistant : tu ne donnes aucun conseil et tu ne fais jamais la morale.
On ne te demande pas de juger les modes ni de defendre ton independance.
On te demande seulement de vivre ta journee et de decider comme ce personnage
deciderait, avec ses interets, ses envies et ses contradictions.
Tu reponds uniquement par un objet JSON, sans aucun texte autour."""

CONSIGNE = """Tu es {nom}, {profil} du groupe {groupe}. {personnalite}

Nous sommes {date}. {situation}

Ce que tu vois autour de toi :
- dans ton groupe ({groupe}) : {nb_groupe}{noms_groupe}
- sur le campus : {nb_campus} etudiants sur {total} le portent, {tendance}

Ce que tu as lu sur le reseau interne depuis ton dernier passage :
{messages}

Ce dont tu te souviens :
{souvenirs}

Aujourd'hui, tu {etat} le ruban. Decide pour la suite.

Reponds par un objet JSON avec exactement ces six champs :

"porte" : true si tu as le ruban au poignet a partir de maintenant, false si tu
ne l'as pas. C'est ton geste, pas ton avis.

"categorie" : ce que le ruban signifie POUR TOI aujourd'hui. Une seule valeur,
copiee exactement depuis cette liste : {categories}

"sens" : la meme chose, mais avec tes mots. Une phrase courte, en "je".

"publication" : ce que tu ecris sur le reseau interne, avec tes mots a toi,
ou "" si tu n'as rien a dire aujourd'hui.

"destinataire" : le prenom d'une personne a qui tu t'adresses, ou "".{voisins}

"raison" : pourquoi tu as fait ce geste. Une phrase courte, en "je".

Attention : "porte" et "raison" doivent dire la meme chose. Si tu ecris que tu
veux le mettre, alors "porte" vaut true. Si tu ecris que tu le refuses, alors
"porte" vaut false.

N'utilise aucune phrase de cette consigne dans tes reponses : ecris les tiennes.
Reponds uniquement par ton objet JSON, sans aucun texte avant ni apres."""

# Tournures typiques d'un modele qui repond en assistant au lieu d'incarner
# un etudiant. Liste a assumer et a citer dans le rapport : elle est lexicale,
# donc faillible, et c'est une limite a discuter en soutenance.
MARQUEURS_ASSISTANT = [
    r"\ben tant qu('|e )", r"\bje suis une? (ia|intelligence artificielle|mod[eè]le)",
    r"\bil est important de\b", r"\bil convient de\b", r"\bje ne peux pas\b",
    r"\bn'h[eé]sitez pas\b", r"\bje vous (conseille|recommande|invite)\b",
    r"\bvoici (quelques|une liste)\b", r"\ben conclusion\b", r"\bil faut noter que\b",
    r"\bcependant, il\b", r"\bje n'ai pas d'(opinion|avis|pr[eé]f[eé]rence)",
    r"\bje suis (l[aà] pour|con[cç]u)", r"\bce ph[eé]nom[eè]ne (s'appelle|est connu)",
]
_MARQUEURS = [re.compile(m, re.IGNORECASE) for m in MARQUEURS_ASSISTANT]

# Morceaux de la consigne que le modele recopie au lieu de les remplir.
# Observe sur qwen2.5:1.5b : 8,9 % des publications d'un premier run.
FUITES = [
    r"cha[iî]ne vide", r"un message pour le reseau", r"ce que le ruban (veut|signifie)",
    r"pourquoi tu decides", r"une phrase a la premiere personne",
    r"le prenom d'une personne", r"valeurs d'exemple",
]
_JSON_IMBRIQUE = re.compile(r'^\s*[\{\[]\s*["\{]')
_FUITES = [re.compile(m, re.IGNORECASE) for m in FUITES]

# Ce que l'agent affirme faire, pour le confronter a son champ porte.
_DIT_PORTE = re.compile(r"\bje (le )?porte\b(?! pas)", re.IGNORECASE)
_DIT_PAS = re.compile(r"\bje ne (le )?porte pas\b|\bje refuse de (le )?porter\b", re.IGNORECASE)


def detecter_derive(reponse):
    """Renvoie (nature, details) si la reponse deraille, sinon (None, None).

    La categorie est d'abord ramenee a la liste fermee quand il ne s'agit que
    d'une variante de forme (majuscule, espace, accent). La reponse est corrigee
    sur place, pour que l'appelant utilise la valeur normalisee.
    """
    if isinstance(reponse, dict) and "categorie" in reponse:
        reponse["categorie"] = normaliser_categorie(reponse["categorie"])
    if reponse is None:
        return "appel_echoue", {}
    if not isinstance(reponse, dict):
        return "json_illisible", {"type": type(reponse).__name__}
    if not isinstance(reponse.get("porte"), bool):
        return "champ_porte_invalide", {"recu": repr(reponse.get("porte"))[:80]}
    if reponse.get("categorie") not in SENS:
        return "categorie_hors_liste", {"recu": repr(reponse.get("categorie"))[:80]}
    texte = " ".join(str(reponse.get(k, "")) for k in ("sens", "raison", "publication"))
    for motif in _MARQUEURS:
        trouve = motif.search(texte)
        if trouve:
            return "posture_assistant", {"marqueur": trouve.group(0)[:60]}
    for motif in _FUITES:
        trouve = motif.search(texte)
        if trouve:
            return "fuite_de_consigne", {"extrait": trouve.group(0)[:60]}
    if _JSON_IMBRIQUE.match(str(reponse.get("publication", ""))):
        return "fuite_de_consigne", {"extrait": "json imbrique dans publication"}
    # L'agent dit l'inverse de ce que dit son champ porte : la decision est
    # inexploitable, meme si le JSON est parfaitement forme.
    avis = " ".join(str(reponse.get(k, "")) for k in ("sens", "raison"))
    if _DIT_PORTE.search(avis) and not reponse["porte"]:
        return "incoherence_texte_etat", {"porte": False, "dit": "je porte"}
    if _DIT_PAS.search(avis) and reponse["porte"]:
        return "incoherence_texte_etat", {"porte": True, "dit": "je ne porte pas"}
    return None, None


def souvenirs(agent, limite_recents=4):
    """Selection de memoire injectee dans le prompt (exigence A1).

    On donne les souvenirs recents ET le plus ancien echange avec une
    personne, pour que l'agent puisse tenir compte d'un echange vieux de
    plusieurs jours simules, ce que A1 demande explicitement.
    """
    memoire = agent.get("memoire", [])
    echanges = [m for m in memoire if m.get("genre") == "echange"]
    choisis = echanges[:1] + [m for m in memoire[-limite_recents:] if m not in echanges[:1]]
    if not choisis:
        return "- (rien pour l'instant)"
    lignes = []
    for m in choisis:
        lignes.append(f"- {m.get('t_sim_lisible', '')} : {m.get('fait', '')}"
                      + (f" ({m['raison']})" if m.get("raison") else ""))
    return "\n".join(lignes)


class DecideurLLM:
    """Un moteur par taille de modele : llm_grand ou llm_petit (exigence A5)."""

    def __init__(self, client, taille, personnalites=None):
        self.client = client
        self.taille = taille
        self.personnalites = personnalites or {}

    def _situation(self, agent):
        """Ce que l'agent sait de SA propre histoire avec le ruban.

        Un pionnier doit savoir qu'il l'a lance : sinon le modele le traite
        comme une mode venue d'ailleurs et la refuse par principe.
        """
        jours = agent["minutes_porte"] // 1440
        if agent["profil"] == "pionnier" and agent["porte"]:
            return ("C'est toi qui as noue ce ruban a ton poignet le premier, "
                    "avec une amie de l'atelier. Personne ne t'a rien demande.")
        if agent["porte"]:
            return (f"Tu as un ruban de couleur noue au poignet depuis {jours} jour(s)."
                    if jours else "Tu viens de nouer un ruban de couleur a ton poignet.")
        return ("Tu n'as pas de ruban au poignet. Certains etudiants du campus "
                "en portent un depuis quelques jours.")

    def _consigne(self, agent, monde, t_sim, horloge_lisible):
        groupe = agent["groupe"]
        porteurs, pairs = monde.porteurs_du_groupe(agent)
        noms = [a["nom"] for a in porteurs]
        messages = monde.fil_visible(agent, t_sim, limite=6)
        nb_campus = len(monde.porteurs())
        return CONSIGNE.format(
            nom=agent["nom"], profil=agent["profil"].replace("_", " "), groupe=groupe,
            personnalite=agent.get("personnalite", ""),
            date=horloge_lisible,
            situation=self._situation(agent),
            nb_groupe=(f"{len(porteurs)} personne(s) sur {len(pairs)} le portent"
                       if pairs else "tu es seul dans ton groupe"),
            noms_groupe=(" : " + ", ".join(noms)) if noms else "",
            nb_campus=nb_campus, total=len(monde.agents),
            tendance=monde.tendance(),
            messages="\n".join(
                f"- {m['nom_auteur']} : {m['texte']}" for m in messages
            ) or "- (rien de nouveau)",
            souvenirs=souvenirs(agent),
            etat="portes" if agent["porte"] else "ne portes pas",
            categories=", ".join(SENS),
            voisins=(" Dans ton groupe il y a : "
                     + ", ".join(a["nom"] for a in pairs[:5]) + ".")
                    if pairs else "",
        )

    def decider(self, agent, monde, t_sim, horloge_lisible=""):
        consigne = self._consigne(agent, monde, t_sim, horloge_lisible)
        reponse = self.client.json(SYSTEME, consigne, self.taille)
        mesure = dict(self.client.derniere_mesure)
        nature, details = detecter_derive(reponse)

        if nature:
            # L'agent n'a pas vraiment decide : il garde son etat de la veille.
            # Le monde continue, c'est exactement ce que A4 exige.
            return {"porte": agent["porte"], "categorie": agent["categorie"],
                    "sens": agent.get("sens") or SENS[agent["categorie"]],
                    "raison": f"aucune decision exploitable ({nature})",
                    "publication": "", "destinataire": "",
                    "valide": False, "moteur": self.taille,
                    "incident": {"nature": nature, "details": details},
                    "mesure": mesure}

        return {"porte": reponse["porte"],
                "categorie": reponse["categorie"],
                "sens": str(reponse.get("sens", ""))[:300],
                "raison": str(reponse.get("raison", ""))[:300],
                "publication": str(reponse.get("publication", ""))[:280],
                "destinataire": str(reponse.get("destinataire", ""))[:60],
                "valide": True, "moteur": self.taille, "mesure": mesure}
