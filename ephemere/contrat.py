"""Contrat d'evenements d'Ephemere (exigence F4).

Chaque evenement porte un nom de schema versionne. Un evenement non conforme
est detecte, isole dans runs/<run>.rejets.jsonl avec la raison, et la
simulation continue : c'est precisement ce que F4 demande.

Pour faire evoluer un schema on AJOUTE une version (decision.v2) au lieu de
modifier decision.v1, sinon les runs deja enregistres deviennent illisibles
et le rejeu (E3) casse.
"""

import difflib

VERSION_CONTRAT = "1.1.0"   # 1.1 : perception, coherence, energie (ajouts seuls)

# Les six sens possibles du ruban. Liste fermee : c'est ce qui rend
# l'emergence d'un sens partage mesurable (exigence B1).
#
# Chaque sens dit ce que le ruban VEUT DIRE sur le campus, pas ce que fait
# celui qui repond : un non-porteur peut tres bien penser que le ruban, c'est
# "pour s'en moquer". Formules a la premiere personne ("je le porte pour m'en
# moquer"), ces sens melangeaient lecture du signe et geste de l'agent, et des
# non-porteurs repondaient "ironie" ou "suivre la foule" pour dire leur refus.
SENS = {
    "cercle_creatif": "c'est le signe du cercle creatif de l'atelier",
    "tendance": "c'est ce qui est dans le coup en ce moment",
    "suivre_la_foule": "c'est le signe de ceux qui suivent la foule",
    "ringard": "c'est depasse",
    "ironie": "on le porte pour s'en moquer",
    "aucun_sens": "ca ne veut rien dire",
}

NUL = type(None)

# Enveloppe commune a TOUS les evenements.
# t_sim et t_traitement sont les deux horloges distinctes exigees par C3.
ENVELOPPE = {
    "schema": str,
    "run": str,
    "t_sim": int,            # minutes simulees depuis J1 00:00
    "t_sim_lisible": str,    # "J03 14:30"
    "t_emission": str,       # horloge reelle a la production (ISO 8601)
    "t_traitement": (str, NUL),  # horloge reelle au traitement, rempli par le consommateur
}

CORPS = {
    "run.v1": {"mode": str, "nb_agents": int, "graine": int, "jours": int,
               "config": str, "version_contrat": str},
    "population.v1": {"agents": list, "resume": dict},
    "decision.v1": {"agent": str, "porte": bool, "categorie": str, "sens": str,
                    "raison": str, "moteur": str, "valide": bool},
    "publication.v1": {"agent": str, "texte": str, "portee": str,
                       "destinataire": (str, NUL)},
    "indicateurs.v1": {"taux_adoption": float, "repartition_sens": dict,
                       "sens_dominant": str, "part_sens_dominant": float,
                       "porteurs": list},
    "injection.v1": {"nature": str, "details": dict, "source": str},
    "recuperation.v1": {"agent": str, "requete": str, "resultats": list,
                        "nb_resultats": int, "corpus": dict},
    "incident.v1": {"agent": (str, NUL), "nature": str, "details": dict},
    # Ce que l'agent LLM avait sous les yeux, et ce qu'il a repondu mot pour mot.
    # Sert a recalculer le detecteur hors ligne (A4), a remonter les echanges
    # qui precedent un basculement (B4) et a comparer deux profils (A3).
    "perception.v1": {"agent": str, "moteur": str, "messages": list, "souvenirs": list,
                      "documents": list, "vue": dict, "reponse_brute": (str, NUL),
                      "violations_c6": list},
    # Controle de coherence temporelle sur tout le run (C6) : combien de
    # contextes ont ete verifies, combien contenaient une info venue du futur.
    "coherence.v1": {"controles": int, "violations": int, "details": list},
    # Energie de la machine locale pendant le run (E4). kwh vaut None quand
    # la mesure n'est pas disponible : l'absence est ecrite, pas cachee.
    "energie.v1": {"outil": (str, NUL), "kwh": (float, NUL), "co2_kg": (float, NUL),
                   "portee": str, "note": str},
    "bilan.v1": {"appels": int, "tokens_entree": int, "tokens_sortie": int,
                 "duree_run_s": float, "interrompu": bool,
                 "incidents": int, "par_taille": dict},
}


def normaliser_categorie(brut):
    """Ramene une categorie a la liste fermee malgre les variantes de forme.

    Le modele renvoie parfois "Tendance", "suivre la foule" ou "cercle creatif".
    Ce sont des ecarts de forme, pas des inventions : on les ramene. Une vraie
    invention ("licorne") reste refusee et compte comme une sortie de role.
    """
    if not isinstance(brut, str):
        return brut
    t = brut.strip().lower().replace(" ", "_").replace("-", "_")
    for ancien, nouveau in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ç", "c")):
        t = t.replace(ancien, nouveau)
    if t in SENS:
        return t
    # Faute de frappe ("suivre_la_folle") : ramenee si elle est tres proche
    # d'une valeur de la liste. L'original reste dans la reponse brute, et la
    # correction est notee dans perception.v1 pour etre comptee (A5).
    proches = difflib.get_close_matches(t, list(SENS), n=1, cutoff=0.85)
    return proches[0] if proches else brut


def verifier(evt):
    """Renvoie (True, None) si l'evenement respecte son schema, sinon (False, raison)."""
    if not isinstance(evt, dict):
        return False, "l'evenement n'est pas un objet"
    nom = evt.get("schema")
    if nom not in CORPS:
        return False, f"schema inconnu : {nom!r}"
    for champ, attendu in {**ENVELOPPE, **CORPS[nom]}.items():
        if champ not in evt:
            return False, f"champ absent : {champ}"
        valeur = evt[champ]
        # bool est une sous-classe de int en Python : on ne les confond pas.
        if attendu is int and isinstance(valeur, bool):
            return False, f"{champ} : booleen la ou un entier est attendu"
        if attendu is float and isinstance(valeur, int) and not isinstance(valeur, bool):
            valeur = float(valeur)
            evt[champ] = valeur
        if not isinstance(valeur, attendu):
            return False, f"{champ} : {type(valeur).__name__} au lieu de {attendu}"
    if nom == "decision.v1" and evt["categorie"] not in SENS:
        return False, f"categorie hors liste fermee : {evt['categorie']!r}"
    if nom == "indicateurs.v1" and evt["sens_dominant"] not in SENS:
        return False, f"sens_dominant hors liste fermee : {evt['sens_dominant']!r}"
    return True, None
