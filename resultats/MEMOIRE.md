# Mémoire individuelle : audit et proposition d'expérience (étape 6, 4 novembre 2026)

**Dans la configuration de référence, la mémoire individuelle d'un agent LLM est surtout la liste de ses propres décisions récentes.**
- 91 % des souvenirs injectés dans les prompts sont des décisions de l'agent.
- Les échanges reçus sont rares : de 7 à 14 messages privés par run.
- Le sens que l'agent donnait au ruban la veille n'est jamais affiché explicitement. Il ne passe qu'indirectement, par la raison de la décision.

La variante « sens de la veille » est implémentée, désactivée par défaut et testée. Les prompts de référence restent identiques à l'octet près.

> **Mise à jour du 4 novembre, 7 h.** Le protocole a été validé avec 10 graines et un critère à 9 graines sur 10. Il est rédigé dans `resultats/PROTOCOLE_MEMOIRE.md`, gelé à 06:59 (`resultats/memoire_gel.json`), et l'expérience est lancée (`experience_memoire.py --lancer`). Le protocole fait foi : il remplace la proposition de la partie 3 ci-dessous, conservée pour l'historique.

## 1. Ce que la mémoire conserve, et ce qui est injecté

**Méthode.** Le journal n'enregistre pas la mémoire elle-même, seulement les souvenirs injectés (`perception.v1`). `audit_memoire.py` reconstruit donc, sans aucun appel au modèle, la mémoire disponible de chaque agent LLM au moment de chaque décision. Il utilise pour cela les fonctions mêmes du simulateur (`monde.memoriser`, `agents_llm.choisir_souvenirs`).

**Validation de la reconstruction.** Elle redonne exactement les souvenirs injectés dans les 1 310 décisions LLM des 5 runs de référence (100 %). Les chiffres ci-dessous sont donc des mesures, pas des estimations.

| Mesure (5 runs de référence, graines 100 à 104) | Valeur |
|---|---|
| Décisions LLM auditées | 1 310 |
| Mémoire disponible : souvenirs de décision (plafond 8) | 6,3 en moyenne ; plafond atteint dans 62 à 64 % des décisions |
| Mémoire disponible : échanges (plafond 30) | 0,3 à 0,7 en moyenne ; plafond jamais atteint |
| Souvenirs injectés par prompt | 3,7 à 3,8 (au plus 5 : les 4 plus récents et le plus ancien échange) |
| Répartition des souvenirs injectés | 4 502 décisions (91 %), 427 échanges (9 %) |
| Prompts qui contiennent au moins un échange | 21 à 36 % |
| Âge moyen / maximal d'un souvenir injecté | 3,0 à 3,3 jours / 20 à 22 jours |
| Échanges distincts reçus | 53 en tout (7 à 14 par run), tous injectés au moins une fois, chacun en moyenne 8 fois |
| Sens explicite de la veille dans le prompt | 0 (le gabarit ne l'affiche jamais) |
| Raisons de décision injectées qui nomment un sens (mots-clés) | 43 à 55 % |
| Persistance du sens individuel (même sens qu'à la décision LLM précédente) | 0,69 à 0,75 |

**Les trois contenus sont bien distincts :**
- **Décisions passées.** Le souvenir dit « j'ai décidé de porter / ne pas porter le ruban », suivi de la raison donnée par le modèle. Dans le prompt, la raison est affichée. Dans `perception.v1`, elle n'est pas enregistrée : elle se retrouve dans `decision.v1`.
- **Conversations reçues.** Le souvenir dit « X m'a dit : "…" ». Un message privé reçu, ou une réplique de conversation ; la référence n'a pas de conversations.
- **Significations attribuées.** Elles ne sont pas en mémoire comme telles. La catégorie choisie est dans l'état de l'agent et dans le journal, jamais dans le prompt. Seule la raison en garde parfois une trace, d'où la mesure par mots-clés. Cette mesure est grossière : elle ne dit pas si le modèle s'en sert.

**Constats qui comptent pour la suite :**
- **Le plus ancien échange reste épinglé en tête de mémoire jusqu'à la fin du run.** C'est la règle de `choisir_souvenirs` (exigence A1). Un message du jour 2 est encore injecté au jour 22.
- **Les souvenirs de décision se ressemblent beaucoup d'un jour à l'autre :** la même phrase, avec une raison différente.
- **Ces mesures disent ce qui est disponible et ce qui est injecté. Elles ne disent pas si le modèle s'en sert.** Pour le mesurer, j'ai ajouté une ombre `sans_souvenirs` (voir la partie 2).

## 2. Ce qui a été ajouté, désactivé par défaut

| Ajout | Effet | Défaut |
|---|---|---|
| `--memoire-sens` (`simuler.py`) | Chaque souvenir de décision ajoute : « pour toi, le ruban voulait alors dire : <définition du sens> ». C'est la variante E | Désactivé |
| Ombre `sans_souvenirs` (`--ombres`) | Repose la décision sans aucun souvenir, en gardant le social. Mesure ce que la mémoire change réellement à la décision | Non demandée |
| Champ `categorie` dans chaque souvenir de décision | Conservé en mémoire pour la variante, jamais affiché sans elle | Toujours, sans effet sur le prompt |
| `sens_affiche` dans `perception.v1` | Trace le sens montré, seulement dans la variante | Absent dans la référence |
| En-tête `run.v2` : `memoire_sens` | L'option est enregistrée dans chaque run | `false` |

**Garde de non-régression.** J'ai relevé les empreintes SHA-256 des prompts réels d'un scénario de 4 jours (boucle du simulateur, modèle simulé, 34 prompts sans ombre et 102 avec ombres) **avant** toute modification. Après, elles sont identiques. `tests/test_memoire.py` vérifie ces empreintes à chaque exécution. L'empreinte du gabarit de référence reste `ceb1fc47a4f9`.

## 3. Proposition d'expérience (à valider avant tout lancement)

**Question.** Rendre explicite le sens que l'agent donnait au ruban la veille change-t-il :
1. la persistance de son sens ;
2. l'accord collectif et le verdict d'émergence ;
3. l'effet du social mesuré par les ombres ?

**Conditions.** A = la série de référence gelée (graines 100 à 104). E = les mêmes options, plus `--memoire-sens`, avec les mêmes graines. Une seule variable change.

**Ombres en E :** `sans_discours` et `sans_social`, comme en A, plus `sans_souvenirs`.

**Hypothèses, à écrire dans `experience.py` avant la mesure :**

| | Hypothèse | Mesure | Critère fixé d'avance |
|---|---|---|---|
| HE1 (principale) | Le sens de la veille rend le sens individuel plus persistant | Persistance du sens individuel, par run, E moins A, apparié par graine | E > A dans 5 graines sur 5 (test du signe unilatéral, p = 1/32) ; écart moyen et intervalle rapportés |
| HE2 | L'accord collectif monte, sans que l'émergence soit acquise | ΔA et verdict avec le seuil à persistance **inchangé** | Rapporté graine par graine. Une persistance plus forte relève aussi le seuil : c'est voulu |
| HE3 | La mémoire est réellement utilisée | En E : part des décisions qui gardent le sens précédent, réel moins ombre `sans_souvenirs` | Écart > 0, test par permutation **par agent**, pas par décision |
| H6 (comparaison) | L'effet du social change-t-il ? | Écart réel moins `sans_social`, E contre A, par graine | Rapporté, sans critère de succès |

**Statistiques.**
- **Unité de comparaison entre conditions : le run.** Les décisions d'un même run ne sont pas des observations indépendantes. Avec 5 graines, il faut une cohérence de signe ; un intervalle par rééchantillonnage des graines sera large.
- **Dans un run, la permutation se fait au niveau de l'agent :** on inverse les signes agent par agent. Elle remplace la permutation par paire de décisions, que `REFERENCE.md` juge optimiste. C'est une fonction nouvelle à ajouter, sans toucher aux indicateurs existants.
- **Résultats rapportés :** effet par graine, effet moyen, intervalle, résultats négatifs, lectures en six sens et regroupée.

**Coût.** Une décision LLM et 3 ombres font environ 1 050 appels par run, soit environ 60 minutes. La série E représente donc environ 5 h de calcul.

**Option plus puissante.** Ajouter les graines 105 à 109 en A et en E, pour environ 9 h de plus.

**Limite assumée.** A n'a pas d'ombre `sans_souvenirs`, puisque la série est gelée. L'usage de la mémoire (HE3) ne se mesure donc qu'en E. Pour le mesurer aussi dans la configuration de référence, il faudrait de nouveaux runs A′ : mêmes options, plus l'ombre `sans_souvenirs`, pour environ 5 h. A′ ne remplacerait pas A, puisque Ollama n'est pas déterministe.

## 4. Fichiers et tests

- `audit_memoire.py` (nouveau) : audit hors ligne. Résultats dans `resultats/audit_memoire_reference.json`.
- `tests/test_memoire.py` (nouveau), 16 vérifications :
  - empreintes des prompts de référence et des ombres inchangées ;
  - variante : la ligne exacte du souvenir, et rien avant la première décision ;
  - ombre `sans_souvenirs` : seule la mémoire disparaît ;
  - contrat ;
  - reconstruction exacte de l'audit.
- `ephemere/agents_llm.py` : ombre `sans_souvenirs`, paramètre `memoire_sens` de `DecideurLLM`, `souvenirs(…, avec_sens)`, `sens_affiche` dans la perception.
- `simuler.py` : `categorie` dans le souvenir de décision, option `--memoire-sens`, champ `memoire_sens` dans l'en-tête.
- `ephemere/contrat.py` : `sans_souvenirs` ajouté à `MASQUES_OMBRE`.
