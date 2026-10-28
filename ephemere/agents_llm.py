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
Tu ecris toujours en francais, comme un etudiant francophone.
Tu reponds uniquement par un objet JSON, sans aucun texte autour."""

CONSIGNE = """Tu es {nom}, {profil} du groupe {groupe}. {personnalite}

Nous sommes {date}. {situation}

Ce que tu vois autour de toi :
- dans ton groupe ({groupe}) : {nb_groupe}{noms_groupe}
- sur le campus : {campus}

Ce que tu as lu sur le reseau interne depuis ton dernier passage :
{messages}

Ce dont tu te souviens :
{souvenirs}

Ce que tu as lu ou entendu dire sur le campus :
{documents}

Aujourd'hui, tu {etat} le ruban. Decide pour la suite.

Reponds par un objet JSON avec exactement ces six champs :

"porte" : true si tu as le ruban au poignet a partir de maintenant, false si tu
ne l'as pas. C'est ton geste, pas ton avis.

"categorie" : ce que le ruban VEUT DIRE aujourd'hui sur le campus, selon toi,
que tu le portes ou non. Ce n'est pas ton geste, c'est ta lecture du signe.
Une seule valeur, copiee exactement depuis cette liste :
{categories}

"sens" : ce que le ruban veut dire, avec tes mots. Une phrase courte.

"publication" : ce que tu ecris sur le reseau interne, avec tes mots a toi,
ou "" si tu n'as rien a dire aujourd'hui.

"destinataire" : le prenom d'une personne a qui tu t'adresses, ou "".{voisins}

"raison" : pourquoi tu as fait ce geste. Une phrase courte, en "je".

Attention : "porte" et "raison" doivent dire la meme chose. Si tu ecris que tu
veux le mettre, alors "porte" vaut true. Si tu ecris que tu le refuses, alors
"porte" vaut false.

N'utilise aucune phrase de cette consigne dans tes reponses : ecris les tiennes.
Reponds uniquement par ton objet JSON, sans aucun texte avant ni apres."""

# Sortie structuree (option --sortie-structuree) : le schema est donne au
# fournisseur, qui contraint la generation (Ollama le fait), puis la reponse
# est verifiee contre le MEME schema par valider(), en bibliotheque standard :
# le moteur ne depend d'aucun paquet (ni pydantic, ni LangChain).
CHAMPS_TEXTE = ("sens", "publication", "destinataire", "raison")
SCHEMA_DECISION = {
    "type": "object",
    "properties": {"porte": {"type": "boolean"},
                   "categorie": {"type": "string", "enum": list(SENS)},
                   **{c: {"type": "string"} for c in CHAMPS_TEXTE}},
    "required": ["porte", "categorie", *CHAMPS_TEXTE],
    "additionalProperties": False,
}
SCHEMA_REPLIQUE = {
    "type": "object",
    "properties": {"texte": {"type": "string"},
                   "categorie": {"type": "string", "enum": list(SENS)}},
    "required": ["texte", "categorie"],
    "additionalProperties": False,
}
_TYPES = {"object": dict, "string": str, "boolean": bool}


def valider(reponse, schema):
    """Ecarts entre une reponse et un schema (le sous-ensemble utilise ici).

    Renvoie la liste des ecarts, vide si la reponse est conforme.
    """
    if not isinstance(reponse, dict):
        return [f"pas un objet : {type(reponse).__name__}"]
    ecarts = [f"champ absent : {c}" for c in schema["required"] if c not in reponse]
    if schema.get("additionalProperties") is False:
        ecarts += [f"champ en trop : {c}" for c in reponse
                   if c not in schema["properties"] and not c.startswith("_")]
    for champ, regle in schema["properties"].items():
        if champ not in reponse:
            continue
        v = reponse[champ]
        if not isinstance(v, _TYPES[regle["type"]]):
            ecarts.append(f"{champ} : {type(v).__name__} au lieu de {regle['type']}")
        elif "enum" in regle and v not in regle["enum"]:
            ecarts.append(f"{champ} : {v!r} hors liste")
    return ecarts


REPLIQUE = """Tu es {nom}, {profil} du groupe {groupe}. {personnalite}

Nous sommes {date}. Aujourd'hui, tu {etat} le ruban, et pour toi il veut dire :
{sens}

{autre} te parle du ruban, en prive. Votre conversation jusqu'ici :
{echanges}

Reponds-lui, avec tes mots, en une ou deux phrases. Tu peux etre d'accord,
pas d'accord, changer d'avis ou non : c'est ton personnage qui decide.

Reponds par un objet JSON avec exactement ces deux champs :

"texte" : ta replique a {autre}.

"categorie" : ce que le ruban VEUT DIRE pour toi a la fin de cet echange.
Une seule valeur, copiee exactement depuis cette liste :
{categories}

Reponds uniquement par ton objet JSON, sans aucun texte avant ni apres."""


def derive_replique(reponse):
    """Comme detecter_derive, pour une replique : (nature, details) ou (None, None)."""
    if isinstance(reponse, dict) and "categorie" in reponse:
        reponse["categorie"] = normaliser_categorie(reponse["categorie"])
    if reponse is None:
        return "appel_echoue", {}
    if not isinstance(reponse, dict):
        return "json_illisible", {"type": type(reponse).__name__}
    if reponse.get("categorie") not in SENS:
        return "categorie_hors_liste", {"recu": repr(reponse.get("categorie"))[:80]}
    texte = str(reponse.get("texte", "")).strip()
    if not texte:
        return "replique_vide", {}
    for motif in _MARQUEURS:
        trouve = motif.search(texte)
        if trouve:
            return "posture_assistant", {"marqueur": trouve.group(0)[:60]}
    for motif in _FUITES:
        trouve = motif.search(texte)
        if trouve:
            return "fuite_de_consigne", {"extrait": trouve.group(0)[:60]}
    return None, None


# Tournures typiques d'un modele qui repond en assistant au lieu d'incarner
# un etudiant. Liste a assumer et a citer dans le rapport : elle est lexicale,
# donc faillible, et c'est une limite a discuter en soutenance.
#
# Chaque motif doit viser une tournure d'ASSISTANT, pas du francais courant.
# "en tant que", "je ne peux pas" ou "cependant, il" seuls attrapaient des
# reponses parfaitement en role ("en tant que membre du club d'humour",
# "je ne peux pas le porter en cours") : la decision etait jetee a tort,
# le taux d'incidents gonfle et une partie des refus disparaissait.
_IA = r"(une? )?(ia|intelligence artificielle|assistant|mod[eè]le( de langage)?|programme)\b"
MARQUEURS_ASSISTANT = [
    r"\ben tant qu(e |')" + _IA, r"\bje suis " + _IA,
    r"\bil est (important|essentiel|crucial) de\b", r"\bil convient de\b",
    r"\bje ne (peux|suis pas en mesure de) (pas )?(vous |t')?(aider|r[eé]pondre|fournir"
    r"|donner (un |une |d'|de )?(avis|conseil|opinion)|incarner|jouer ce r[oô]le"
    r"|pr[eé]tendre|avoir (d'|des )?(opinion|avis|go[uû]ts?|pr[eé]f[eé]rences?))",
    r"\bn'h[eé]sitez pas\b", r"\bje vous (conseille|recommande|invite)\b",
    r"\bvoici (quelques|une liste)\b", r"\ben conclusion\b", r"\bil faut noter que\b",
    r"\bje n'ai pas d'(opinion|avis|pr[eé]f[eé]rence)",
    r"\bje suis (l[aà] pour (vous|t')|con[cç]u)", r"\bce ph[eé]nom[eè]ne (s'appelle|est connu)",
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

# Ce que l'agent affirme faire, pour le confronter a son champ porte. Les
# tournures viennent des reponses observees ("je prends part a l'engouement"
# avec porte=false). Une phrase qui contient les deux sens n'est pas jugee.
_DIT_PORTE = re.compile(
    r"\bje (le |la )?porte\b(?! pas)(?! plus)"
    r"|\bje (le |la )?(mets|remets|noue|garde|adopte)\b(?! pas)(?! plus)"
    r"|\bj'adopte\b|\bje prends part\b|\bje (me )?joins\b|\bje rejoins\b"
    r"|(?<!pas )(?<!plus )(?<!jamais )(?<!refuse de )(?<!refuser de )\bporter (le|ce) ruban\b"
    r"|(?<!pas )(?<!plus )\b(de|a|à) le porter\b",
    re.IGNORECASE)
_DIT_PAS = re.compile(
    r"\bje ne (le |la )?(porte|mets|garde|mettrai|porterai)\s+(pas|plus|jamais)\b"
    r"|\bje refuse de (le )?porter\b|\bne (pas|plus) (le )?porter\b"
    r"|\bje (l'|le )?(enl[eè]ve|retire|abandonne)\b|\bj'(enl[eè]ve|abandonne)\b",
    re.IGNORECASE)

# Reperage d'une reponse ecrite dans une autre langue (vu : qwen2.5:3b repond
# parfois en italien). Seuls des mots sans equivalent francais comptent comme
# etrangers, et des mots outils francais tres frequents comme francais.
_MOTS = re.compile(r"[a-zà-ÿ']+", re.IGNORECASE)
_ETRANGERS = {
    "questo", "questa", "una", "sono", "che", "della", "dello", "voglio", "io", "nel",
    "anche", "molto", "perche", "perché", "the", "and", "is", "to", "my", "this",
    "that", "with", "not", "it", "el", "los", "las", "por", "muy", "pero", "yo",
    "quiero", "porque", "das", "ich", "nicht", "und", "ist",
}
_FRANCAIS = {
    "le", "les", "des", "du", "je", "ne", "pas", "et", "un", "est", "pour", "au",
    "ce", "mon", "suis", "qui", "dans", "avec", "mais", "on", "tu", "nous", "c'est",
    "j'ai", "plus", "veux", "aux", "cette", "ruban", "moi",
}


def detecter_derive(reponse):
    """Renvoie (nature, details) si la reponse deraille, sinon (None, None).

    La categorie est d'abord ramenee a la liste fermee quand il ne s'agit que
    d'une variante de forme (majuscule, espace, accent). La reponse est corrigee
    sur place, pour que l'appelant utilise la valeur normalisee.
    """
    if isinstance(reponse, dict) and "categorie" in reponse:
        brute = reponse["categorie"]
        reponse["categorie"] = normaliser_categorie(brute)
        if (isinstance(brute, str) and reponse["categorie"] in SENS
                and reponse["categorie"] != brute.strip().lower().replace(" ", "_")):
            reponse["_categorie_brute"] = brute
    if reponse is None:
        return "appel_echoue", {}
    if not isinstance(reponse, dict):
        return "json_illisible", {"type": type(reponse).__name__}
    if not isinstance(reponse.get("porte"), bool):
        return "champ_porte_invalide", {"recu": repr(reponse.get("porte"))[:80]}
    if reponse.get("categorie") not in SENS:
        return "categorie_hors_liste", {"recu": repr(reponse.get("categorie"))[:80]}
    texte = " ".join(str(reponse.get(k, "")) for k in ("sens", "raison", "publication"))
    mots = [m.lower() for m in _MOTS.findall(texte)]
    etrangers = sum(m in _ETRANGERS for m in mots)
    francais = sum(m in _FRANCAIS for m in mots)
    if etrangers >= 3 and etrangers > francais:
        return "hors_langue", {"mots_etrangers": etrangers, "mots_francais": francais}
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
    dit_porte, dit_pas = _DIT_PORTE.search(avis), _DIT_PAS.search(avis)
    if dit_porte and not dit_pas and not reponse["porte"]:
        return "incoherence_texte_etat", {"porte": False, "dit": dit_porte.group(0)[:60]}
    if dit_pas and not dit_porte and reponse["porte"]:
        return "incoherence_texte_etat", {"porte": True, "dit": dit_pas.group(0)[:60]}
    return None, None


def choisir_souvenirs(agent, limite_recents=4):
    """Selection de memoire injectee dans le prompt (exigence A1).

    On donne les souvenirs recents ET le plus ancien echange avec une
    personne, pour que l'agent puisse tenir compte d'un echange vieux de
    plusieurs jours simules, ce que A1 demande explicitement.
    """
    memoire = agent.get("memoire", [])
    echanges = [m for m in memoire if m.get("genre") == "echange"]
    return echanges[:1] + [m for m in memoire[-limite_recents:] if m not in echanges[:1]]


def souvenirs(agent, limite_recents=4, choisis=None):
    """Les souvenirs choisis, mis en forme pour le prompt."""
    if choisis is None:
        choisis = choisir_souvenirs(agent, limite_recents)
    if not choisis:
        return "- (rien pour l'instant)"
    lignes = []
    for m in choisis:
        lignes.append(f"- {m.get('t_sim_lisible', '')} : {m.get('fait', '')}"
                      + (f" ({m['raison']})" if m.get("raison") else ""))
    return "\n".join(lignes)


def controler_c6(perception, t_sim):
    """Verifie qu'aucune information du contexte ne vient du futur (exigence C6).

    Les filtres du fil, de la memoire et de la base empechent deja ces cas :
    ce controle independant les COMPTE, pour qu'un zero soit une mesure et pas
    une supposition. Un document vaut pour toute sa journee de parution.
    """
    jour = t_sim // 1440 + 1
    violations = []
    for m in perception["messages"]:
        if m["t_sim"] > t_sim:
            violations.append({"source": "message", "auteur": m["auteur"], "t_sim": m["t_sim"]})
    for m in perception["souvenirs"]:
        if m.get("t_sim") is not None and m["t_sim"] > t_sim:
            violations.append({"source": "souvenir", "t_sim": m["t_sim"]})
    for d in perception["documents"]:
        if d["jour"] > jour:
            violations.append({"source": "document", "id": d["id"], "jour": d["jour"]})
    return violations


# Ce que chaque profil va chercher dans la base. La requete depend de l'agent,
# donc deux profils places dans la meme situation ne retrouvent pas la meme
# chose : c'est ce qui rend la recuperation defendable (exigences F1 et A3).
ANGLES = {
    "pionnier": ("se distinguer cercle creatif devenir banal abandonner les premiers "
                 "signe distinctif membres atelier"),
    "figure_populaire": "populaire imite surprendre entrainer equipe distinguer groupe",
    "suiveur": "adopter attendre que le groupe s'y mette majorite",
    "refractaire": "refuser une mode par principe detonner",
    "ironique": "detournement moquerie second degre tourner en derision",
}


def requete_de(agent):
    """La question que l'agent se pose, transformee en requete documentaire."""
    # Pas de prefixe commun du type "ruban au poignet" : "ruban" et "poignet",
    # rares dans le corpus, ramenaient le meme passage pour TOUS les profils
    # (33 passages sur 54 lors du run d'essai). La requete est faite de l'angle
    # du profil et de son etat, rien d'autre.
    etat = "porter garder" if agent["porte"] else "refuser abandonner"
    return f"{ANGLES.get(agent['profil'], '')} {etat}"


class DecideurLLM:
    """Un moteur par taille de modele : llm_grand ou llm_petit (exigence A5)."""

    def __init__(self, client, taille, base=None, k=3, structure=False):
        self.client = client
        self.taille = taille
        self.base = base      # base de connaissances, exigence F1
        self.k = k
        self.structure = structure   # sortie structuree : schema JSON impose et verifie

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

    def _recuperer(self, agent, t_sim):
        """Interroge la base avec les filtres de temps et de groupe (F1, C6)."""
        if self.base is None:
            return "", []
        jour = t_sim // 1440 + 1
        requete = requete_de(agent)
        trouves = self.base.chercher(requete, jour, agent["groupe"], k=self.k)
        if not trouves:
            return requete, []
        return requete, trouves

    def _consigne(self, agent, monde, t_sim, horloge_lisible, documents=None):
        """Renvoie (consigne, perception) : le prompt et ce qu'il donne a voir."""
        groupe = agent["groupe"]
        porteurs, pairs = monde.porteurs_du_groupe(agent)
        noms = [a["nom"] for a in porteurs]
        messages = monde.fil_visible(agent, t_sim, limite=6)
        choisis = choisir_souvenirs(agent)
        if monde.cloisonne:
            # Temoin B3 : le campus n'existe plus comme espace commun. Un agent
            # LLM ne doit pas plus le voir qu'un agent a regles.
            campus = "tu ne sais pas ce qui se passe hors de ton groupe"
        else:
            campus = (f"{len(monde.porteurs())} etudiants sur {len(monde.agents)} "
                      f"le portent, {monde.tendance()}")
        perception = {
            "messages": [{"auteur": m["agent"], "t_sim": m["t_sim"], "texte": m["texte"]}
                         for m in messages],
            "souvenirs": [{"genre": m.get("genre", ""), "t_sim": m.get("t_sim"),
                           "fait": m.get("fait", "")} for m in choisis],
            "documents": [{"id": d["id"], "numero": d["numero"], "jour": d["jour"]}
                          for d in (documents or [])],
            "vue": {"porteurs_groupe": noms, "pairs_groupe": len(pairs),
                    "campus": campus, "porte": agent["porte"],
                    "categorie": agent["categorie"]},
        }
        perception["violations_c6"] = controler_c6(perception, t_sim)
        consigne = CONSIGNE.format(
            nom=agent["nom"], profil=agent["profil"].replace("_", " "), groupe=groupe,
            personnalite=agent.get("personnalite", ""),
            date=horloge_lisible,
            situation=self._situation(agent),
            nb_groupe=(f"{len(porteurs)} personne(s) sur {len(pairs)} le portent"
                       if pairs else "tu es seul dans ton groupe"),
            noms_groupe=(" : " + ", ".join(noms)) if noms else "",
            campus=campus,
            documents="\n".join(
                f"- {d['titre']} ({d['source']}) : {d['passage'][:220]}"
                for d in (documents or [])) or "- (rien qui te revienne)",
            messages="\n".join(
                f"- {m['nom_auteur']} : {m['texte']}" for m in messages
            ) or "- (rien de nouveau)",
            souvenirs=souvenirs(agent, choisis=choisis),
            etat="portes" if agent["porte"] else "ne portes pas",
            categories="\n".join(f"- {cle} : {texte}" for cle, texte in SENS.items()),
            voisins=(" Dans ton groupe il y a : "
                     + ", ".join(a["nom"] for a in pairs[:5]) + ".")
                    if pairs else "",
        )
        return consigne, perception

    def decider(self, agent, monde, t_sim, horloge_lisible=""):
        requete, documents = self._recuperer(agent, t_sim)
        consigne, perception = self._consigne(agent, monde, t_sim, horloge_lisible, documents)
        reponse = self.client.json(SYSTEME, consigne, self.taille,
                                   **({"schema": SCHEMA_DECISION} if self.structure else {}))
        mesure = dict(self.client.derniere_mesure)
        brut = getattr(self.client, "dernier_brut", None)
        perception["reponse_brute"] = None if brut is None else str(brut)[:4000]
        nature, details = detecter_derive(reponse)
        if nature is None and self.structure:
            ecarts = valider(reponse, SCHEMA_DECISION)
            if ecarts:
                nature, details = "schema_non_respecte", {"ecarts": ecarts[:5]}
        if isinstance(reponse, dict) and "_categorie_brute" in reponse:
            # Champ facultatif de perception.v1 : faute de frappe ramenee.
            perception["categorie_corrigee"] = {"recu": str(reponse.pop("_categorie_brute"))[:80],
                                                "retenu": reponse["categorie"]}

        if nature:
            # L'agent n'a pas vraiment decide : il garde son etat de la veille.
            # Le monde continue, c'est exactement ce que A4 exige.
            return {"porte": agent["porte"], "categorie": agent["categorie"],
                    "sens": agent.get("sens") or SENS[agent["categorie"]],
                    "raison": f"aucune decision exploitable ({nature})",
                    "publication": "", "destinataire": "",
                    "valide": False, "moteur": self.taille,
                    "incident": {"nature": nature, "details": details},
                    "mesure": mesure, "perception": perception,
                    "recuperation": {"requete": requete, "resultats": documents}}

        return {"porte": reponse["porte"],
                "categorie": reponse["categorie"],
                "sens": str(reponse.get("sens", ""))[:300],
                "raison": str(reponse.get("raison", ""))[:300],
                "publication": str(reponse.get("publication", ""))[:280],
                "destinataire": str(reponse.get("destinataire", ""))[:60],
                "valide": True, "moteur": self.taille, "mesure": mesure,
                "perception": perception,
                "recuperation": {"requete": requete, "resultats": documents}}

    def repondre(self, agent, autre, echanges, horloge_lisible=""):
        """Une replique de conversation privee (A2). Renvoie un dict :
        texte, categorie, valide, incident, mesure."""
        consigne = REPLIQUE.format(
            nom=agent["nom"], profil=agent["profil"].replace("_", " "), groupe=agent["groupe"],
            personnalite=agent.get("personnalite", ""), date=horloge_lisible,
            etat="portes" if agent["porte"] else "ne portes pas",
            sens=agent.get("sens") or SENS[agent["categorie"]], autre=autre["nom"],
            echanges="\n".join(f"- {qui} : {texte}" for qui, texte in echanges),
            categories="\n".join(f"- {cle} : {texte}" for cle, texte in SENS.items()),
        )
        reponse = self.client.json(SYSTEME, consigne, self.taille,
                                   **({"schema": SCHEMA_REPLIQUE} if self.structure else {}))
        mesure = dict(self.client.derniere_mesure)
        nature, details = derive_replique(reponse)
        if nature is None and self.structure:
            ecarts = valider(reponse, SCHEMA_REPLIQUE)
            if ecarts:
                nature, details = "schema_non_respecte", {"ecarts": ecarts[:5]}
        if nature:
            return {"texte": "", "categorie": None, "valide": False,
                    "incident": {"nature": nature, "details": details}, "mesure": mesure}
        return {"texte": str(reponse["texte"]).strip()[:280], "categorie": reponse["categorie"],
                "valide": True, "incident": None, "mesure": mesure}
