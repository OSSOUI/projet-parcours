# Architecture hybride : évaluation hors simulation de B (réflexes) et C′ (décision courte Qwen)

4 novembre 2026, copie d'intégration.

**Ce qui n'a pas changé :**
- aucun moteur, aucun journal, aucun run ;
- aucune configuration gelée ;
- l'expérience mémoire n'a pas été relancée.

**Ce qui a été ajouté :**
- un outil, `evaluation_hybride.py` ;
- les résultats, dans `resultats/evaluation_hybride/`.

## Conclusion

**Ni B ni C′ ne sont des optimisations acceptables pour la configuration scientifique.** Chacune ne fait gagner du temps qu'en modifiant ce qu'ÉPHÉMÈRE étudie :
- **B :** les seules règles qui se déclenchent assez souvent font monter la persistance du sens et suppriment des publications ;
- **C′ :** il supprime toute la parole des agents et fait basculer le verdict d'émergence, même sans rétroaction.

Pour gagner du temps sans toucher aux agents, les leviers sont ailleurs : moins d'ombres, de la parallélisation, deux machines (partie 6).

## 1. Peut-on reconstruire fidèlement le contexte de décision ?

**`perception.v1` seul ne suffit pas.** Il lui manque :
- le texte du prompt lui-même : seuls ses ingrédients sont enregistrés ;
- la raison de chaque souvenir de décision. Elle est affichée dans le prompt, mais elle se trouve dans `decision.v1`, pas dans `perception.v1` ;
- le texte des passages retrouvés : seuls leurs identifiants y figurent, le texte est dans `corpus/` ;
- les réponses brutes des ombres : seuls le port et le sens y figurent.

**La reconstruction par rejeu, elle, est exacte.**
- **Méthode :** chaque run est rejoué dans la boucle du simulateur, avec la réponse enregistrée à chaque décision, et le prompt construit par le simulateur est capturé.
- **Monde rejoué :** identique au journal dans les 6 runs (1 572 décisions).
- **Contrôle direct :** les 474 prompts de A100 et A101 ont été reposés à Qwen, avec le même modèle, la même graine et la même température (passe A′). Résultat :
  - 469 réponses sur 474 identiques au caractère près, soit 98,9 % (IC 97,6 à 99,5 %) ;
  - **100 % de décisions identiques** ;
  - les mêmes incidents : 6 et 17, comme dans les runs originaux.

**Conséquence importante.** À prompt et graine égaux, Qwen est déterministe sur cette machine. A′ sert donc de plafond d'accord : 100 %. Tout écart de B ou de C′ vient de la règle ou du format, pas du bruit du modèle.

## 2. B : réflexes, sans aucun appel au modèle

**Données :** 5 runs de référence (A100 à A104), 1 310 décisions LLM.

**Méthode de substitution.** La règle remplace les décisions qu'elle couvre. Une règle « garder » reprend la dernière décision *effective*, réflexes compris. Les déclencheurs (messages, vue), eux, restent ceux du run original : il n'y a pas de rétroaction (voir les limites).

| Règle | Statut | Couverture | Accord port + sens (IC 95 %) | Δ persistance | Verdicts émergents (six sens / regroupé) | Publications perdues | Prompts ultérieurs avec un souvenir de réflexe |
|---|---|---|---|---|---|---|---|
| Référence | — | — | — | — | 0 / 1 | — | — |
| R0 : toujours garder | témoin | 95 % | 25,8 % (23,4 à 28,3) | **+0,28** | 0 / 0 | 98 % | 95 % |
| R1 : rien de neuf, strict | pré-enregistrable | **0,1 %** | 1 / 1 | 0 | 0 / 1 | 0 | 0 % |
| R2 : rien de neuf, à un étudiant près | exploratoire | 0,2 % | 2 / 2 | 0 | 0 / 1 | 0 | 1 % |
| R3 : R2, et deux décisions stables | exploratoire | 0,2 % | 2 / 2 | 0 | 0 / 1 | 0 | 1 % |
| R5 : vue inchangée, messages ignorés | exploratoire | 42 % | 66,4 % (62,2 à 70,2) | **+0,13** | **1 / 2** | 47 % | 72 % |
| R6 : R5, et deux décisions stables | exploratoire | 31 % | 81,3 % (77,2 à 84,9) | **+0,07** | **0 / 0** | 36 % | 59 % |
| R4 : moteur à règles du projet | témoin | 100 % | 24,9 % (22,6 à 27,4) | +0,18 | 0 / 0 | 100 % | 100 % |

**Lecture**
- **Les règles propres, pré-enregistrables (R1 à R3), ne se déclenchent presque jamais.** Un agent LLM a presque toujours un message nouveau à lire : il y a 606 publications pour 1 310 décisions.
- **Pour couvrir une part utile des décisions, il faut ignorer les messages (R5, R6).**
  - C'est exactement retirer le discours, ce que mesure l'ombre `sans_discours`.
  - Et ces règles **fabriquent de la persistance** : de +0,07 à +0,13. C'est l'ordre de grandeur de l'effet que l'expérience mémoire cherche à détecter.
  - Elles **changent aussi des verdicts d'émergence**, dans un sens ou dans l'autre selon la règle.
- **Désaccords de R6 :** 49 sur le sens seul, 15 sur le port seul, 9 sur les deux. Le réflexe garde le sens alors que le LLM l'aurait changé.
- **R4 (le moteur à règles appliqué aux agents LLM) n'est d'accord qu'une fois sur quatre.** Il écrase l'émergence : ΔA de −0,22 en six sens.

**Effets indirects, non simulés ici mais mesurés.**
- Avec R6, 59 % des prompts suivants contiendraient un souvenir de décision sans raison écrite par l'agent.
- 36 % des publications disparaîtraient, et ne seraient donc plus lues par les autres.

## 3. C′ : décision courte Qwen (nouveaux appels au modèle)

**Coût :** 948 nouveaux appels à Qwen (474 en A′, 474 en C′) sur A100 et A101, soit 21 minutes d'inférence. Ce n'est pas une évaluation sans coût.

**Ce qui est resté identique à A :**
- les modèles qwen2.5:7b (`845dbda0ea48`) et 3b (`357c53fb659c`) ;
- la température 0,9 ;
- la graine de chaque appel (même clé `decision:agent:instant`) ;
- le texte système ;
- toute la partie « situation » du prompt.

**Ce qui diffère :**
- la fin du prompt : « exactement ces deux champs », suivi des seuls paragraphes `porte` et `categorie`, repris mot pour mot. La phrase « porte et raison doivent dire la même chose » est retirée, puisqu'il n'y a plus de raison ;
- un schéma JSON imposé (port booléen, sens parmi les 6). A tournait sans schéma.

Les deux passes ont tourné séparément, dans le même ordre, pour que le cache de préfixe d'Ollama n'avantage ni l'une ni l'autre.

| | A′ (prompt original) | C′ (sortie courte) |
|---|---|---|
| Réponses valides | 451 sur 474 (23 incidents, comme l'original) | 474 sur 474 |
| Accord avec la décision originale, port + sens | 100 % | **75,2 % (71,0 à 78,9)** |
| Accord sur le port seul | 100 % | 90,7 % (87,7 à 93,0) |
| Accord sur le sens seul | 100 % | 80,7 % (76,8 à 84,1) |
| Latence médiane, 3b / 7b | 2,97 s / 5,8 s | 0,7 à 1,05 s / 1,34 s |
| Temps d'inférence total | 1 774 s | **500 s (−72 %)** |
| Jetons générés par décision | environ 90 | environ 16 (−82 %) |
| Jetons lus par décision | environ 1 240 | environ 1 050 (−15 %) |
| Publications produites | 224 | **0** |

**Effets d'une substitution sur les deux runs** (statique, donc sans rétroaction) :

| | Référence | A′ | C′ |
|---|---|---|---|
| Persistance A100 / A101 | 0,745 / 0,725 | identique | 0,743 / 0,720 |
| Adoption finale | 0,70 / 0,75 | identique | identique |
| Émergence six sens (ΔA ; seuil) | non / non | identique | **émergent / émergent** (0,37 ; 0,24 et 0,31 ; 0,26) |
| Émergence regroupé | non / non | identique | **émergent / émergent** |

**Lecture**
- **Le gain est réel, mais seulement sur l'appel de décision :** environ 2,4 s gagnées par décision.
- **Il a un prix :**
  - **un quart des décisions change ;**
  - **les sens choisis sont plus concentrés :** le gain d'accord ΔA monte de 8 à 10 points, et les deux runs deviennent « émergents ». L'accord entre agents augmente quand ils n'écrivent plus ce que le ruban veut dire pour eux ;
  - **la parole disparaît entièrement.** Dans une vraie simulation, les autres agents ne liraient plus aucun message, ce qui change tout le canal social (effet `sans_discours`).

C′ n'est donc pas une version plus rapide de A, mais une autre expérience.

## 4. Gains, sans les confondre

Estimation par run de référence (environ 262 décisions LLM, 786 appels avec les 2 ombres, durée réelle 2 270 à 3 000 s) :

| | Appels évités | Jetons générés économisés | Temps d'inférence économisé | Durée du run | Comportement des agents |
|---|---|---|---|---|---|
| B, R6 (sans les ombres des décisions réflexes) | 31 % des appels | environ 31 % | environ 31 % | environ −30 % | persistance +0,07, émergence modifiée, 36 % de publications perdues |
| B, R1 à R3 | environ 0 | environ 0 | environ 0 | environ 0 | inchangé |
| C′ sur la décision seule (ombres inchangées) | 0 (des appels plus courts) | environ 30 % du run | environ 640 s par run | **−24 à −27 %** | un quart des décisions change, verdict d'émergence basculé, aucune publication |
| C′ sur la décision et les ombres | 0 | environ 80 % | environ 70 % | environ −70 % | idem, et les ombres ne mesurent plus le même contrefactuel |
| Retirer les ombres (démonstration, run sans mesure) | **67 %** (référence), 75 % (E) | idem | idem | environ −65 % | **inchangé** |

## 5. Limites

- **Pas de rétroaction.** Dans une vraie simulation :
  - une décision substituée change ce que voient les autres agents ;
  - les publications perdues ne sont plus lues ;
  - les souvenirs sans raison modifient les prompts suivants.

  Les effets réels de B (avec ignorance des messages) et de C′ seraient probablement **plus grands**, pas plus petits. Les colonnes « publications perdues » et « souvenirs » en donnent l'ampleur.
- **Taille des échantillons.**
  - B porte sur 5 runs ; C′ sur 2 runs (474 décisions).
  - Les effets au niveau du run (persistance, verdicts) n'ont pas d'intervalle : 2 à 5 runs ne le permettent pas.
  - Les accords ont leur IC de Wilson, mais les décisions d'un même run ne sont pas indépendantes : ces intervalles sont optimistes.
- **Les seuils de R2, R5 et R6 ont été choisis après avoir regardé les données.** Ils sont exploratoires : seule une définition fixée d'avance pourrait servir à une future expérience.
- **Écart au protocole mémoire.** Une première passe de B a inclus `exp_memoire_A_g105`, un run de l'expérience mémoire, avant que je ne l'en retire. J'ai donc vu ses mesures propres (persistance, adoption, verdict d'émergence). Ce run est la condition A seule : aucune information sur E ni sur la comparaison A/E n'a été vue, et le critère était déjà gelé. Cet écart est à consigner dans le rapport de l'expérience.

## 6. Recommandation

1. **Ne pas retenir B ni C′ comme optimisations de la configuration de référence ou de E,** ni leur combinaison. Leur gain vient d'une modification du discours ou de la persistance, c'est-à-dire du phénomène étudié.
2. **Pour réduire le coût, dans l'ordre :**
   - pas d'ombres pour les runs qui ne mesurent pas l'émergence : −65 % de durée, comportement inchangé ;
   - répartir l'inférence sur deux machines : moitié de charge chez vous, déjà en place ;
   - paralléliser les décisions d'un même pas en mode synchrone. Elles sont indépendantes par construction, mais le gain est à mesurer, et c'est à réserver aux nouvelles séries, pas à l'expérience gelée.
3. **Si l'équipe veut tout de même étudier une cognition hybride, en faire une question de recherche et non une optimisation.** Par exemple : « que devient l'émergence quand les agents décident sans écrire ? ». Il faudrait alors :
   - une configuration nouvelle ;
   - des critères écrits avant les runs ;
   - les mêmes graines ;
   - une vraie simulation, puisque la rétroaction du discours est justement l'effet à mesurer.

   Je recommande de ne pas lancer cela avant la fin de l'expérience mémoire.

**Fichiers produits :**
- `resultats/evaluation_hybride/*.b.json` : B, par run ;
- `*.c_prime.json` : C′, synthèse par run ;
- `*.a_prime.jsonl` et `*.c_prime.jsonl` : chaque réponse brute, avec latence et jetons ;
- `c_prime.log`.
