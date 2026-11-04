# Protocole de l'expérience mémoire : le sens de la veille (A contre E, 10 graines)

**Rédigé et gelé avant le premier run, le 4 novembre 2026.** Les empreintes SHA-256 de ce fichier et de `experience_memoire.py` sont enregistrées dans `resultats/memoire_gel.json`. Le lancement et l'analyse refusent de partir si l'un des deux a changé depuis. Tout écart au protocole sera signalé comme tel dans le rapport.

## 1. Question

Rappeler explicitement à un agent LLM la signification qu'il donnait au ruban lors de ses décisions passées rend-il son sens individuel plus persistant ?

Le but n'est pas de vérifier que l'option fonctionne techniquement : c'est déjà testé par `tests/test_memoire.py`. Le but est de mesurer si elle change le comportement des agents.

## 2. Conditions

| | A : référence gelée | E : sens de la veille |
|---|---|---|
| Options de `simuler.py` | `--mode synchrone --ombres sans_discours sans_social` | les mêmes, plus l'ombre `sans_souvenirs` et `--memoire-sens` |
| Communes | `--agents 20 --jours 25 --fournisseur ollama --pause 0 --graine <g>` | identiques |
| Graines 100 à 104 | les 5 runs de référence gelés `exp_reference_llm_reference_01` à `05`, tels quels | `exp_memoire_E_g100` à `g104`, à produire |
| Graines 105 à 109 | `exp_memoire_A_g105` à `g109`, à produire avec la configuration `llm_reference` inchangée | `exp_memoire_E_g105` à `g109`, à produire |

- **Une seule variable change entre A et E : `--memoire-sens`.** Chaque souvenir de décision ajoute alors « ; pour toi, le ruban voulait alors dire : <définition du sens choisi alors> ».
- **L'ombre `sans_souvenirs` n'est demandée qu'en E.** Elle sert à l'analyse S4. Une ombre ne touche pas au monde : la section 3 le démontre.
- **Les options de A sont lues dans `experience.py` (configuration `llm_reference`), pas recopiées.** Les paramètres de la référence, sa consigne et les seuils d'émergence ne sont pas modifiés.
- **Modèles :** `qwen2.5:7b` (empreinte `845dbda0ea48`) et `qwen2.5:3b` (`357c53fb659c`), Q4_K_M, Ollama 0.40.12, température 0,9, consigne d'empreinte `ceb1fc47a4f9`.

**Ordre des runs (fixé) :** A105, E105, E100, puis A106, E106, E101, et ainsi de suite jusqu'à A109, E109, E104. Chaque nouvelle graine est produite en A puis en E. Les E des graines gelées sont répartis sur toute la série, pour ne pas concentrer une dérive éventuelle de la machine sur une condition.

## 3. Comparabilité des dix paires

| Garantie | Comment elle est assurée | Vérifié |
|---|---|---|
| Même population pour A et E à graine égale | `population.construire(config, 20, graine)` est déterministe | Les comptes de décisions LLM recalculés redonnent ceux des runs gelés : 212, 262, 287, 262, 287 |
| Mêmes graines d'appel au modèle | La graine de chaque appel dépend de la graine du run et de la clé `decision:<agent>:<instant>`. Elle ne dépend ni de l'ordre des appels ni du nombre d'ombres | Lecture du code (`llm.graine_appel`, `agents_llm._options`) |
| Le code actuel refait la référence | `verifier_comparabilite.py` rejoue chacun des 5 runs gelés dans la boucle actuelle du simulateur, en rendant à chaque décision la réponse brute enregistrée | 5 sur 5 : monde et perceptions identiques, événement par événement (1 022 à 1 206 événements par run). Le contrôle échoue bien si une seule réponse est modifiée. Bilan : `resultats/comparabilite_reference.json` |
| Une ombre de plus ne change pas le monde | Même rejeu avec l'ombre `sans_souvenirs` ajoutée | Monde identique, 5 runs sur 5 |
| E ne diffère de A que par la ligne du sens | Même rejeu avec `--memoire-sens` | Monde identique à réponses égales. Les prompts, une fois la ligne du sens retirée, sont identiques à ceux de A. Le sens est montré dans 95 % des prompts (202 à 274 par run) ; les autres n'ont encore aucun souvenir de décision |
| Mêmes modèles | Empreintes Ollama contrôlées avant chaque run et relues dans l'en-tête de chaque run | `experience_memoire.py --lancer` et `--controler` |

**Ce qui reste différent entre A et E, en dehors de l'option :**
- **Ollama n'est pas déterministe, même avec la graine.** L'expérience X0 donnait 92 % de décisions identiques. A et E divergent donc aussi par ce bruit : c'est pour cela que l'unité de comparaison est la paire de runs, et que 10 paires sont nécessaires.
- **Les A des graines 100 à 104 datent du 3 novembre ; tous les autres runs sont produits maintenant.** Le code est différent (contrat 1.8.0 contre 1.10.0), mais le rejeu ci-dessus montre que cela ne change ni le monde ni les prompts. Un effet de lot (machine, charge) n'est pas exclu : l'analyse S5 compare les deux moitiés.

## 4. Critère principal (confirmatoire)

**Mesure : la persistance du sens individuel d'un run.**
- Pour chaque agent LLM, on prend chaque paire de décisions valides consécutives.
- La persistance est la part des paires où l'agent garde la même catégorie de sens.
- Une décision en incident n'est ni comptée ni prise comme référence.
- C'est la mesure de `audit_memoire.py` (0,692 à 0,745 sur les 5 runs gelés).

**Critère : la persistance est plus forte en E qu'en A dans au moins 9 graines sur 10.**
- Une égalité exacte compte comme un échec.
- Test exact des signes, unilatéral : avec 9 graines sur 10, p = 11/1 024 = 0,011 ; avec 10 sur 10, p = 1/1 024.
- Avec 8 graines sur 10 ou moins, le critère n'est pas atteint, quelle que soit la taille de l'écart.

**Rapportés avec le critère, sans changer la décision :**
- **Taille d'effet :** écart apparié moyen E − A sur les 10 graines, avec son intervalle de confiance à 95 % par la loi de Student (9 degrés de liberté), l'écart type, la médiane et dz (écart moyen divisé par l'écart type des écarts).
- **Sensibilité :** test des rangs signés de Wilcoxon, exact et unilatéral (zéros retirés).
- **Par graine :** persistance en A et en E, écart, et une permutation par agent à l'intérieur de la graine.
  - On échange, agent par agent, toutes ses décisions entre A et E. C'est possible parce que les agents sont les mêmes à graine égale.
  - La p unilatérale est exacte (2^n tirages, n = 10 à 17 agents LLM).
  - Les agents d'un même run s'influencent : cette p est descriptive. Seul le test des signes au niveau des runs décide.

## 5. Analyses secondaires (fixées d'avance, sans critère de succès sauf mention)

- **S1. Persistance corrigée du hasard.**
  - Pour chaque agent, on retranche la persistance attendue s'il tirait ses sens au hasard dans sa propre distribution du run : la somme des p_k au carré.
  - Une hausse de la persistance brute sans hausse de la persistance corrigée voudrait dire que les agents se concentrent sur moins de sens, et non qu'ils restent fidèles à leur sens précédent. Le rapport le dira ainsi.
- **S2. Persistance au niveau des relevés,** celle qui fixe le seuil du modèle nul de Markov (`emergence.py`).
- **S3. Persistance du port du ruban** d'une décision à la suivante. Elle dit si le rappel du sens stabilise aussi le geste.
- **S4. Usage réel de la mémoire, en E seulement.**
  - On compare la part des décisions qui gardent le sens précédent : décision réelle contre ombre `sans_souvenirs`, sur les paires où les deux sont valides.
  - Par run : permutation par agent, exacte.
  - Sur les 10 runs : nombre de runs à écart positif, test des signes, écart moyen et intervalle de confiance.
  - A n'a pas cette ombre (la série est gelée). On ne mesure donc pas ici l'usage de la mémoire sans le rappel du sens.
- **S5. Effet de lot.** Les écarts E − A sont aussi calculés séparément sur les graines 100 à 104 (A gelé du 3 novembre) et sur les graines 105 à 109 (A et E contemporains).
- **HE2. Émergence.**
  - `emergence.py` est appliqué tel quel, avec le seuil à persistance, en six sens et regroupé : verdict, ΔA, A0 et seuil, pour A et E, graine par graine.
  - Une persistance plus forte relève aussi le seuil du modèle nul. C'est voulu, et cela n'est pas compensé.
- **H6. Effet du social** : écart d'accord réel moins ombre `sans_social` (et moins `sans_discours`), en A et en E.
  - p par permutation des paires de décisions, comme `emergence.py`.
  - p par permutation par agent (1 000 tirages), plus prudente.
- **Contrôles rapportés sans exclusion :**
  - taux d'incidents ;
  - appels, tokens et durée ;
  - part des prompts de E qui montrent le sens.

Aucune correction pour comparaisons multiples n'est appliquée aux analyses secondaires : elles sont descriptives. Seul le critère principal est confirmatoire.

## 6. Règles de déroulement

- **Recevabilité d'un run,** contrôlée automatiquement :
  - run complet et non interrompu ;
  - graine, 20 agents, 25 jours, mode synchrone ;
  - empreintes des modèles et de la consigne ;
  - température 0,9, sortie non structurée, définitions courtes, pas de conversation ;
  - ombres attendues ;
  - `memoire_sens` vrai en E et faux en A ;
  - aucun sens affiché dans un run A.
- **Aucune exclusion sur le résultat.** Les incidents sont comptés et rapportés.
- **Un run non recevable est gardé à côté** (`.echec_<heure>.jsonl`, rien n'est supprimé), puis relancé une fois. Après deux échecs de la même paire, l'expérience s'arrête pour examen.
- **Si les poids d'un modèle changent, l'expérience s'arrête.**
- **Pas d'analyse intermédiaire.** Pendant le lancement, seuls les contrôles techniques sont affichés. `--analyser` refuse de tourner tant que les 10 paires ne sont pas complètes et recevables.
- **Ni le seuil (9 sur 10), ni les mesures, ni les graines ne seront changés au vu des résultats.** Pas de graines supplémentaires si le critère n'est pas atteint.

## 7. Lecture fixée d'avance

| Résultat | Ce qui sera écrit |
|---|---|
| Critère atteint, S1 positif (IC à 95 % au-dessus de 0) | Le rappel explicite du sens rend le sens individuel plus persistant, au-delà de la concentration des choix, dans cette configuration (20 agents, 25 jours, qwen2.5) |
| Critère atteint, S1 non positif | La persistance brute monte, mais elle s'explique par des agents qui utilisent moins de sens différents, pas par une fidélité accrue au sens précédent |
| Critère non atteint | Le rappel explicite du sens n'augmente pas de façon reproductible la persistance du sens individuel. L'écart moyen et son IC sont rapportés : un effet faible n'est pas exclu |

Dans tous les cas :
- HE2 et H6 sont rapportés graine par graine, sans conclusion sur l'émergence au-delà de ce que dit l'indicateur gelé ;
- S4 dit si la mémoire est réellement lue par le modèle quand le sens y figure.

## 8. Coût

Calculé sur la série gelée : 3,50 s par appel en moyenne, de 3,44 à 3,57 selon le run. A fait 3 appels par décision LLM (la décision et 2 ombres), E en fait 4 (la décision et 3 ombres). Les comptes de décisions par graine sont exacts : ils sont déterministes, et recalculés sans modèle.

| Graine | Décisions LLM | A : appels | E : appels | Temps estimé A + E |
|---|---|---|---|---|
| 100 | 212 | gelé (636) | 848 | 49 min |
| 101 | 262 | gelé (785) | 1 048 | 61 min |
| 102 | 287 | gelé (861) | 1 148 | 67 min |
| 103 | 262 | gelé (786) | 1 048 | 61 min |
| 104 | 287 | gelé (861) | 1 148 | 67 min |
| 105 | 262 | 786 | 1 048 | 107 min |
| 106 | 237 | 711 | 948 | 97 min |
| 107 | 262 | 786 | 1 048 | 107 min |
| 108 | 387 | 1 161 | 1 548 | 158 min |
| 109 | 287 | 861 | 1 148 | 117 min |
| **À produire** | | **4 305** (5 runs, ≈ 4,2 h) | **10 980** (10 runs, ≈ 10,7 h) | **15 285 appels, ≈ 14,9 h** |

- **Fourchette :** environ 14,5 à 16,5 h. Les prompts de E sont un peu plus longs (environ 7 % de tokens d'entrée en plus).
- **Déjà dépensé pour les A gelés :** 3 929 appels, 3,8 h.
- **Analyse :** quelques minutes, sans modèle.

## 9. Fichiers

- `experience_memoire.py` : plan, gel, lancement avec reprise, contrôles techniques, analyse.
- `verifier_comparabilite.py` : rejeu des runs gelés dans le code actuel.
- `resultats/memoire_gel.json` : empreintes de gel.
- `resultats/memoire_lancement.json` : contrôles de chaque run.
- `resultats/memoire_experience.json` : résultats, écrits uniquement par `--analyser`.
