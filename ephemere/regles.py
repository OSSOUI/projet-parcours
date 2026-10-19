"""Agents a regles, sans aucun appel LLM (exigences A6 et E1).

Modele a seuils inspire de Granovetter (1978), avec la distinction qui
fait tout le sel d'Ephemere : un pionnier ABANDONNE quand la mode devient
banale, alors qu'un suiveur n'adopte que lorsqu'elle l'est devenue.

Ces agents servent a deux choses, a ne pas confondre :
  A6  ils vivent au milieu des agents LLM, dans le meme run ;
  E1  un run ou TOUS les agents sont a regles sert de baseline.
"""


class Regles:
    seuil_banalite = 0.5      # au-dela, un pionnier considere que c'est devenu banal
    lassitude_minutes = 5760  # 4 jours simules : la figure populaire passe a autre chose

    def decider(self, agent, monde, t_sim, horloge_lisible=""):
        percu = monde.adoption_percue(agent)
        profil, porte = agent["profil"], agent["porte"]

        if profil == "pionnier":
            porte = percu < agent["seuil"]
            cat = "cercle_creatif" if porte else "ringard"  # le pionnier part quand c'est banal
        elif profil == "suiveur":
            porte = percu >= agent["seuil"] or (porte and percu >= 0.2)
            if percu >= 0.6:
                cat = "suivre_la_foule"
            else:
                cat = "tendance" if porte else "aucun_sens"
        elif profil == "figure_populaire":
            lasse = agent["minutes_porte"] >= self.lassitude_minutes
            porte = (percu >= agent["seuil"] or porte) and not lasse
            cat = "tendance" if porte else ("ringard" if lasse else "aucun_sens")
        elif profil == "refractaire":
            porte = False
            cat = "suivre_la_foule" if percu >= 0.3 else "aucun_sens"
        elif profil == "ironique":
            porte = percu >= self.seuil_banalite
            cat = "ironie" if porte else "aucun_sens"
        else:
            cat = agent["categorie"]

        from .contrat import SENS
        return {"porte": bool(porte), "categorie": cat, "sens": SENS[cat],
                "raison": f"regle a seuil, adoption percue {percu:.0%}",
                "publication": "", "destinataire": "",
                "valide": True, "moteur": "regles"}
