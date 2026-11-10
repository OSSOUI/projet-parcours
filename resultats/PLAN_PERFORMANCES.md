# Plan de consolidation des performances (proposé le 4 novembre 2026, rien d'exécuté)

## Périmètre

Ce plan comporte deux chantiers, et seulement eux :
1. **Retrait sécurisé des ombres,** pour les runs qui ne mesurent pas l'émergence.
2. **Benchmark de la parallélisation,** fait hors du moteur.

**Hors périmètre :**
- le moteur cognitif : `agents_llm.py`, le prompt, la logique de décision, la mémoire ;
- l'expérience mémoire (`~/projet-parcours`, protocole gelé) ;
- la configuration de référence et les runs existants.

Tout le travail se fait dans la copie d'intégration.

**Pourquoi ces deux chantiers.** L'évaluation hybride (`EVALUATION_HYBRIDE.md`) montre deux choses :
- **les ombres représentent 67 % des appels en référence, et 75 % en E.** Elles ne touchent pas au monde : c'est démontré par le rejeu avec ombres inversées ;
- **à prompt et graine égaux, Qwen redonne la même décision** (100 % sur 474 décisions). On peut donc vérifier exactement qu'un changement d'infrastructure ne change rien aux décisions.

## Chantier 1 : retrait sécurisé des ombres hors expérimentation

**État actuel.** Les ombres sont déjà facultatives : `--ombres` est vide par défaut. Le risque n'est donc pas dans le moteur. Il est dans le fait de **perdre une mesure sans le savoir**, ou de **mélanger un run sans ombres à une série mesurée**.

**Règle proposée.**
- **Ombres obligatoires :**
  - la série de référence et ses extensions (`llm_reference`) ;
  - l'expérience mémoire (A et E, `experience_memoire.py`, déjà contrôlée par son lanceur gelé) ;
  - tout run dont un verdict d'émergence ou un effet du social (H6) est rapporté.
- **Ombres facultatives :**
  - les démonstrations ;
  - les essais Kafka, Godot ou narratrice ;
  - les tests de fumée ;
  - les runs de développement.

### Étapes

| # | Action | Fichiers | Coût modèle |
|---|---|---|---|
| 1.1 | `demo_integration.py` : option `--ombres {aucune,e}`, `aucune` par défaut pour une démonstration. Le choix est écrit dans le rapport. | `demo_integration.py` (copie d'intégration) | 0 |
| 1.2 | Garde-fou d'analyse : `emergence.py` et l'analyse mémoire signalent déjà un run sans ombres. On ajoute à l'audit d'intégration la mention « run sans ombres : aucun effet du social mesurable », et un refus explicite si un tel run est passé à `experience_memoire.py --analyser`. Ce refus existe déjà, puisque le lanceur gelé contrôle les ombres : à vérifier, sans rien modifier. | `demo_integration.py`, lecture seule de `experience_memoire.py` | 0 |
| 1.3 | Test de non-régression sans modèle : dans le scénario de `test_memoire.py` (modèle simulé), les prompts des décisions **réelles** d'un run avec ombres sont identiques, octet par octet, à ceux d'un run sans ombres. Seuls les prompts d'ombres s'ajoutent. | nouveau test dans `tests/` | 0 |
| 1.4 | Rejeu : `rejeu_integration.py` sur un run sans ombres donne un monde identique, des narrations identiques et une scène égale au dernier relevé. | aucun (outil existant) | 0 |
| 1.5 | **Contrôle apparié réel.** Un run de 4 jours, graine 200, configuration E **sans ombres**, comparé à `demo_fumee` (même graine, avec 3 ombres). Si Qwen est déterministe comme mesuré, le monde doit être identique événement par événement : seuls les `ombre.v1` disparaissent. | nouveau run `demo_sans_ombres_g200` (copie d'intégration) | 38 appels, environ 3 min |

**Critère de validation, fixé d'avance.**
- 1.3 et 1.4 doivent passer.
- En 1.5, le monde doit être identique à `demo_fumee`.

S'il ne l'est pas, on documente l'écart : on mesure le premier événement différent et sa cause (non-déterminisme, latence). On ne présente pas le retrait comme neutre.

**Gain attendu, à mesurer en 1.5.** Environ −65 % de durée pour une démonstration de 25 jours (en E : environ 950 appels réduits à environ 237 décisions).

## Chantier 2 : benchmark de la parallélisation, hors du moteur

**Pourquoi le faire hors du moteur.**
- **La parallélisation est possible en principe.** En mode synchrone, les agents d'un même pas décident tous sur l'état précédent, et les décisions ne sont appliquées qu'après (`tourner_synchrone`). Elles sont donc indépendantes.
- **Mais le moteur actuel n'est pas prêt pour des appels simultanés.** Les agents d'une même taille de modèle partagent un client, dont `derniere_mesure` et `dernier_brut` sont des attributs uniques. Des appels simultanés mélangeraient les mesures et les réponses brutes enregistrées.
- **Le benchmark évite cette difficulté.** Il rejoue des prompts reconstruits, sans passer par le simulateur.

### Étapes

| # | Action | Coût modèle |
|---|---|---|
| 2.0 | Relever la configuration actuelle d'Ollama (application Ollama 0.40.12, aucune variable `OLLAMA_NUM_PARALLEL` ni `OLLAMA_MAX_LOADED_MODELS` définie) et la noter. C'est l'état à restaurer, et à revérifier avant toute reprise de l'expérience mémoire. | 0 |
| 2.1 | `benchmark_parallele.py` (nouveau, copie d'intégration). Il reprend les prompts exacts reconstruits par `evaluation_hybride.reconstruire()`, groupés **par pas simulé**, pour reproduire la concurrence réelle : environ 8 à 13 agents LLM par pas. Il les envoie avec N requêtes simultanées. **Un client par fil d'exécution :** aucun état partagé. | 0 (outil) |
| 2.2 | Échantillon fixé d'avance : les 10 premiers jours simulés de A100 et A101, environ 190 décisions. On reprend les mêmes graines (`decision:agent:instant`), les mêmes modèles et la même température. | — |
| 2.3 | Conditions :<br>• N = 1, la référence séquentielle (doit redonner exactement la passe A′ déjà enregistrée) ;<br>• N = 2 et N = 4, côté client, avec le réglage serveur par défaut ;<br>• si N = 4 plafonne, une série avec `OLLAMA_NUM_PARALLEL=4` (Ollama relancé, puis restauré).<br>Chaque condition est répétée 2 fois, dans un ordre alterné. Un appel d'échauffement précède chaque série. | environ 190 × 7 passes, soit 1 330 appels, environ 45 à 60 min |
| 2.4 | Mesures :<br>• durée murale par pas simulé et au total ; débit en décisions par minute ;<br>• latence p50 et p95, par taille de modèle ;<br>• **décisions et réponses brutes identiques à la référence N = 1** ;<br>• incidents ;<br>• mémoire résidente d'Ollama (`ps`) ;<br>• charge de la machine (moyenne de charge). | — |
| 2.5 | Rapport `resultats/BENCHMARK_PARALLELE.md` : gain par condition, avec la dispersion des 2 répétitions, et identité des décisions. | 0 |

**Critères de décision, fixés d'avance.**
- **Gain utile :** une durée par pas au moins **1,5 fois** plus courte que N = 1, pour une condition donnée.
- **Neutralité :**
  - **au moins 99 % de décisions identiques à N = 1 :** la parallélisation est neutre pour le comportement. Elle peut être proposée pour les nouvelles séries, mais jamais pour compléter une série commencée en séquentiel, comme l'expérience mémoire ;
  - **moins de 99 % :** le traitement par lots d'Ollama change les sorties. Une série parallélisée ne serait alors comparable qu'à elle-même. On le documente et on ne recommande pas l'intégration.

**Ce que le chantier 2 ne fait pas.** Il ne modifie pas `simuler.py`, ni le client, ni `agents_llm.py`. Si le benchmark est concluant, l'intégration dans le moteur fera l'objet d'une **proposition séparée**, soumise à votre validation, avec deux éléments :
- un client par fil d'exécution, ou des mesures portées par la réponse et non par le client ;
- un test d'identité : à graine égale, le journal d'un run parallèle doit être identique à celui du run séquentiel.

## Ordre, coûts et points d'arrêt

1. **Chantier 1, étapes 1.1 à 1.4.** Pas d'appel au modèle.
   - **Point d'arrêt :** les tests passent.
2. **Étape 1.5.** Environ 3 min de modèle.
   - **Point d'arrêt :** monde identique à `demo_fumee`, ou écart documenté.
3. **Chantier 2, étapes 2.0 à 2.5.** Environ 1 h de modèle, avec Ollama remis dans son état d'origine à la fin.
   - **Point d'arrêt :** rapport de benchmark, puis votre décision sur une éventuelle intégration.

**Contraintes, à toutes les étapes :**
- pas de reprise ni de perturbation de l'expérience mémoire : elle doit rester arrêtée pendant les étapes 1.5 et 2.x, qui utilisent Ollama ;
- aucune modification de `~/projet-parcours`, du moteur cognitif ou des runs existants ;
- aucun commit sans votre accord.

**Fichiers qui seraient touchés (copie d'intégration seulement) :**
- `demo_integration.py` ;
- un nouveau test dans `tests/` ;
- `benchmark_parallele.py` (nouveau) ;
- `resultats/BENCHMARK_PARALLELE.md` ;
- un run `demo_sans_ombres_g200` ;
- une mise à jour de `resultats/INTEGRATION.md`.

## Résultats des étapes 1.1 à 1.4 (4 novembre 2026)

**Périmètre de l'exécution :**
- aucun appel au modèle, aucun run ;
- aucune modification du moteur, de la narratrice, de `emergence.py`, des analyses ou des configurations expérimentales ;
- l'expérience mémoire est arrêtée et son gel est intact.

**Fichiers (copie d'intégration) :** `demo_integration.py` (option `--ombres`, bloc `ombres` du rapport) et `tests/test_ombres_retrait.py` (nouveau, 33 vérifications).

**1.1. Option et métadonnées.**
- Option `--ombres {aucune,e}`, avec `aucune` par défaut.
- Le rapport indique :
  - les masques déclarés dans l'en-tête et le nombre de `ombre.v1` ;
  - leur cohérence ;
  - si l'effet du social est mesurable ;
  - un avertissement pour un run sans ombres.
- L'en-tête `run.v2` porte déjà toujours le champ `ombres` (`[]` sans ombres).

**1.2. Les analyses refusent ou le disent.**
- L'expérience mémoire juge un run sans ombres non recevable, en A comme en E (écart « ombres [] »).
- `emergence.py` ne calcule aucun témoin et l'affiche en clair. Il étiquette, il ne refuse pas. Il n'a pas été modifié, car l'analyse gelée en dépend.

**1.3. Identité des prompts réels.**
- **Modèle simulé**, avec A et E, et 0, 2 ou 3 ombres :
  - 51 prompts réels identiques octet par octet ;
  - seuls des prompts d'ombre s'ajoutent ;
  - le monde est identique.
- **Run réel `demo_fumee` rejoué :** 38 prompts réels identiques avec et sans ses 3 ombres, et un monde identique au journal.

**1.4. Rejeu d'un run sans ombres** (`demo_fumee` rejoué sans ombres) :
- monde identique (174 événements, 0 ombre) ;
- scène égale au dernier relevé ;
- faits de la narratrice calculables (59), aucun fait d'ombre, indicateur d'émergence présent.

**Incident de montage, corrigé avec votre accord.**
- **Défaut :** le premier montage du journal dérivé n'avait pas d'événements de fin. C'est `simuler.py` (`main`) qui les écrit, et non la boucle. La narratrice n'émet le fait d'émergence que sur la fenêtre qui contient `bilan.v1`.
- **Correction :** les trois événements de fin du run enregistré sont recopiés après contrôle : même run, trois derniers événements, contigus, postérieurs au dernier relevé, `seq` recalés.
- **Limite :** le `bilan.v1` recopié garde les chiffres d'appels du run original, ombres comprises (152 appels). Il ne sert ici qu'à clore le run.

**Suite de tests.** 17 scripts. Les 16 existants passent toujours (`test_coherence_v2` reste en échec attendu, comme avant), et le nouveau passe : 33 sur 33.

## Résultats de l'étape 1.5 : contrôle réel sans ombres (4 novembre 2026, 12:06 à 12:10)

**Run :** `runs/demo_sans_ombres_g200.jsonl` (nouveau, `demo_fumee` intact). Lancé par `demo_integration.py --nom demo_sans_ombres_g200 --jours 4 --graine 200 --ombres aucune`.
- **Paramètres de simulation identiques à `demo_fumee` :** 20 agents, 4 jours, graine 200, synchrone, `--memoire-sens`, qwen2.5 7b et 3b (mêmes empreintes), température 0,9, Kafka, narratrice en direct.
- **Seule différence d'en-tête :** `ombres` (`[…3 masques…]` contre `[]`).
- **Différence de déroulement, sans effet sur le monde :** `demo_fumee` avait subi des pannes provoquées (pont, scène, narratrice, broker), pas ce run.

**Comparaison** : `comparer_sans_ombres.py`, rapport dans `runs/demo_sans_ombres_g200.comparaison.json`.

| Contrôle | Résultat |
|---|---|
| Événements communs (ombres, en-tête et fin de run exclus ; `run`, `seq` et horodatages ignorés) | **175 sur 175 identiques** |
| Détail | `population.v1` 1, `indicateurs.v1` 5, `decision.v1` 74 (port, sens, `sens`, raison, validité), `perception.v1` 38 (vue, messages, **souvenirs**, réponse brute), `recuperation.v1` 38, `publication.v1` 16, `incident.v1` 3 |
| Divergences | **Aucune** |
| Événements `ombre.v1` | 114 contre 0 |
| Fin de run naturelle | Oui : `energie.v1`, puis `coherence.v1`, puis `bilan.v1`, non interrompu, `seq` continus |
| Bilan | 38 appels contre 152 (−75 %), 160,5 s contre 496,4 s (−68 %). La durée de `demo_fumee` inclut une coupure du broker et des pannes |
| Indicateur d'émergence | **Identique :** persistance 0,885 ; six sens ΔA −8 points pour un seuil de 19, non émergent ; regroupé −1 point pour un seuil de 15, non émergent. Pas de témoin asservi sans ombres |
| Faits de la narratrice recalculés depuis le nouveau journal | Fenêtres 1 à 3 identiques. Fenêtre 4 : identique, **sauf les 3 faits d'ombre**, absents par construction |
| Fait d'émergence | Présent, et conforme à `emergence.py` (verdicts et valeurs) |
| Constats publiés par la narratrice en direct | 4 narrations, **constats identiques** à ceux de `demo_fumee` ; 6 sur 6 vrais pour l'évaluateur B |
| Kafka, pont, scène | 179 publiés, 179 confirmés, topic identique au fichier ; 179 appliqués, 0 doublon, 0 manquant ; 179 reçus par la scène témoin |
| Rejeu, modèle injoignable | Monde identique, 4 narrations sur 4 identiques, scène égale au dernier relevé |

**Écart documenté, sans effet.** Les empreintes de faits (`empreinte_faits`) des narrations diffèrent entre les deux runs, alors que les textes des faits sont identiques. Ces empreintes incluent les identifiants des sources (`run#seq`), qui changent forcément : nom du run différent, et `seq` décalés par l'absence des 114 `ombre.v1`.

**Conclusion de l'étape 1.5.** Retirer les ombres ne change rien au monde simulé, aux décisions, aux souvenirs, aux publications, à l'indicateur d'émergence ni aux constats de la narratrice. Cela supprime le témoin asservi : plus d'effet du social ni d'usage de la mémoire mesurables. Le run est 3 à 4 fois moins coûteux en appels.

## Règle d'usage des ombres (adoptée après les étapes 1.1 à 1.5)

| Type de run | Ombres | Pourquoi | Garde-fou existant |
|---|---|---|---|
| **Runs expérimentaux** : série de référence `llm_reference`, expérience mémoire A et E, tout run dont un verdict d'émergence, un effet du social (H6) ou un usage de la mémoire est rapporté | **Obligatoires**, telles que le protocole les fixe (2 masques en référence, 3 en E) | Le témoin asservi est la mesure de l'effet du social et de l'usage de la mémoire. Sans lui, ces analyses sont impossibles | `experience_memoire.py --controler` / `--lancer` juge non recevable un run dont les ombres diffèrent du protocole (vérifié : écart « ombres [] »). `emergence.py` affiche « pas d'ombres : seul le contrôle analytique s'applique » |
| **Démonstrations** : `demo_integration.py` sans `--ombres`, soutenance, Godot, Kafka | **Désactivées** (`--ombres aucune`, par défaut) | Étape 1.5 : monde, décisions, souvenirs, publications, indicateur d'émergence et constats identiques ; −75 % d'appels | Le rapport `integration.json` porte le bloc `ombres`, avec « mesure du social impossible » et un avertissement « à ne jamais verser dans une série d'analyse » |
| **Tests d'intégration** : fumée, pannes, rejeu, Godot, narratrice | **Facultatives,** selon ce qui est mesuré : avec (`--ombres e`) si le test porte sur les ombres elles-mêmes (transport Kafka des `ombre.v1`, rejeu perturbé, faits d'ombre de la narratrice) ; sans dans tous les autres cas | Une ombre ne touche pas au monde (rejeu à réponses inversées, étape 1.5). La garder ne sert qu'à tester son propre circuit | Le même bloc `ombres` dans le rapport |

L'en-tête `run.v2` de chaque run porte toujours le champ `ombres`, avec la liste des masques, ou `[]`. C'est la métadonnée de référence.

## Résultats du chantier 2 (benchmark de parallélisation)

Voir `resultats/BENCHMARK_PARALLELE.md`.

**Verdict.** Critères non atteints (accélération d'au moins 1,5 fois non établie ; 96,3 % de décisions identiques à la première série N = 1). **Pas de parallélisation par défaut** (garde-fou 7).

**Ce qui explique ce résultat :**
- Ollama traite les requêtes une par une (`n_seq_max = 1`) ;
- N ne change pas les sorties, mais l'état du serveur les a changées une fois, après la première série ;
- la machine s'est mise en veille pendant les séries 4 à 6.

Ollama n'a pas été reconfiguré, et son état initial est inchangé.
