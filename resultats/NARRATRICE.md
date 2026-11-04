# Narratrice externe, version fichier JSONL (étapes 4 et suite, 4 novembre 2026)

**Version 4 : les constats publiés atteignent la cible de 95 % sur des données inédites.**
- **Constats :** 133 constats factuels acceptés sur 4 runs jamais narrés. Ils sont jugés vrais tous les 133 par deux évaluateurs (IC 95 % : 97,2 à 100 %).
- **Interprétations :** elles restent faibles. Sur 25 interprétations acceptées, aucune ne contredit un fait, mais environ une sur trois en dit plus que ses faits.
- **Évaluateurs :** ce sont moi et un programme que j'ai écrit, pas deux personnes indépendantes. Un fichier d'audit à l'aveugle est prêt pour une évaluation humaine.
- **Intégrations :** Godot et Kafka restent différés, comme demandé.

## Évaluation humaine indépendante (préparée le 4 novembre, en attente d'un évaluateur)

La V4 est gelée pendant l'évaluation : `ephemere/narration.py` n'est pas modifié. Toute erreur trouvée sera documentée ici avant toute correction.

**Dossier à remettre à l'évaluateur :** `resultats/evaluation_humaine/dossier_evaluateur/`. Il est construit par `evaluation_humaine.py --preparer`.

- **`grille.csv`, la grille à remplir :**
  - 133 constats, mélangés à nouveau (graine 20261104) et renumérotés C001 à C133 ;
  - les fenêtres et les identifiants des événements cités ;
  - les colonnes `verdict` (`vrai`, `faux` ou `insuffisamment_etaye`) et `justification` (obligatoire pour un constat contesté) ;
  - séparateur point-virgule, pour Excel ou LibreOffice.
- **`evenements.md`** donne, pour chaque constat :
  - les événements cités, en JSON brut (pas les résumés de l'évaluateur B) ;
  - pour chaque étudiant cité, sa décision valide précédente, marquée « contexte, non cité ».
- **`journaux/`** contient les 4 journaux complets.
- **`CONSIGNES.md`** explique la tâche. Les consignes ne mentionnent ni la version, ni le validateur, ni les verdicts déjà rendus.

**Hors du dossier :** `resultats/evaluation_humaine/cle_ne_pas_transmettre.json` relie chaque numéro à son constat d'origine et aux verdicts des évaluateurs A et B. Il ne faut pas le transmettre.

**Au retour :** `evaluation_humaine.py --comparer <grille> --evaluateur <nom>`. Le calcul est fixé avant tout retour :
- la grille brute est archivée telle quelle dans `retours/` ;
- comptes des trois verdicts, part de vrais et part de faux avec IC de Wilson ;
- verdicts manquants, hors liste, ou contestés sans justification, à reprendre avec l'évaluateur ;
- liste de tous les désaccords avec A et B, justification comprise ;
- avec deux évaluateurs, leur accord et leur kappa de Cohen.

Le kappa avec B n'a pas de sens ici : B a jugé les 133 constats vrais, et un évaluateur constant donne un kappa nul par construction. On rapporte donc l'accord brut et la liste des désaccords.

## Affichage : trois canaux, interprétations masquées par défaut

Les fichiers de narration ne changent pas : les interprétations y restent, étiquetées. L'affichage, lui, les sépare (`narratrice.py`, fonction `recit`) :

| Canal | Affirmations | Affichage |
|---|---|---|
| Constats | `observation` et `mesure`, statut `verifiee` : calculés depuis le journal et vérifiés | Récit principal |
| Hypothèses | `interpretation`, statut `verifiee` (lecture prudente acceptée, non démontrée) | Masquées ; avec `--hypotheses`, à part, préfixées « hypothèse, non vérifiée » |
| Incertitudes | `incertitude`, statut `verifiee` | Masquées ; avec `--hypotheses`, à part, préfixées « incertitude » |
| Rejetées | statut `rejetee` | Jamais affichées, seulement comptées avec leur motif |

**Pour la future intégration Godot :** le champ `texte` d'une narration mêle les canaux (chaque ligne est étiquetée). Un afficheur doit partir de `affirmations`, rangées par `type` et `statut`, et non de ce champ. Godot n'est pas modifié.

## Versions 3 et 4 : ce qui a changé, et pourquoi

| Version | Changement | Défaut traité |
|---|---|---|
| 3 | Les constats ne sont plus rédigés par le modèle. Il choisit un fait par son étiquette, et le texte publié est celui du fait, calculé depuis le journal. Le texte libre est réservé aux lectures (interprétation, incertitude), étiquetées. Une lecture ne contient aucun nombre, est au conditionnel, et ses quantificateurs (« tous », « aucun », « la plupart », « la moitié ») doivent être conformes à une proportion citée. Le sujet de la lecture doit correspondre à celui des sources. Une action ne peut pas être déduite d'une parole | Paraphrases fausses, quantificateurs, attribution des quantités, parole présentée comme une action, sources hors sujet |
| 3 | Le sens initial d'un agent est inconnu tant qu'il n'a pas décidé (`population.v1` ne le donne pas) | Faux « changement de lecture » au jour 1 |
| 4 | Une égalité au sommet est dite (« ironie et tendance à égalité »), et aucune bascule n'est annoncée sur une égalité | Sens « dominant » qui cache un ex æquo (9 constats sur 112 en version 3) |
| 4 | L'indicateur d'émergence forme un seul fait, avec ses deux lectures | Lecture regroupée « émergent » publiée sans la lecture six sens « non émergent » |
| 4 | Toute cause est refusée dans une interprétation, même au conditionnel (« influence », « pousse »…). « Stabiliser » est contrôlé comme « stable » | « Possible influence sociale » sans appui ; « se stabilise » face à +10 points |

Chaque version a été mesurée sur des runs qu'elle n'avait jamais vus :
- la version 3 sur les références 03, 04 et 05 et sur un run LLM de graine 105 suivi en direct ;
- la version 4 sur `exp_complet_llm_synchrone_01` à `04`.

Le validateur porte un numéro de version. Le rejeu d'une narration produite par une autre version le signale, au lieu d'annoncer des différences.

## Mesure

| | Version 3 (série n6, 80 narrations) | Version 4 (série n7, 100 narrations) |
|---|---|---|
| Constats factuels proposés / acceptés par le validateur | 112 / 112 | 133 / 133 |
| Évaluateur A (moi, chaque constat relu face aux événements bruts) | 112 littéralement exacts ; **103** si un ex æquo caché compte comme faux | **133** vrais |
| Évaluateur B (`verifier_narrations.py`, recalcul séparé, strict sur les ex æquo) | **103** vrais, 9 faux (tous des ex æquo cachés) | **133** vrais |
| Fiabilité factuelle (IC 95 %, Wilson) | 92,0 % (85 à 96 %) : **sous la cible** | **100 % (97,2 à 100 %)** |
| Lectures proposées / acceptées | 95 / 21 | 120 / 25 |
| Lectures acceptées qui dépassent leurs faits (évaluateur A) | 7 sur 21, dont 2 en contradiction (ex æquo, « se stabilise » face à +10) | environ 8 sur 25, aucune en contradiction (motifs prêtés, « opinions » ou « attitudes » déduites de l'adoption) |
| Sources invalides | 0 | 0 |
| Rejeu sans modèle (Ollama injoignable) | 80 sur 80 identiques | 100 sur 100 identiques |
| Latence médiane / jetons par narration | 7,1 s / environ 1 300 | 7,1 s / environ 1 260 |

**Ce que la mesure établit.** Avec la version 4, un constat publié par la narratrice reprend un fait calculé sans modèle, et ce fait a été retrouvé exact dans les 133 cas audités. La fiabilité factuelle tient désormais au calcul des faits, que l'on peut auditer, et non plus à la discipline du modèle.

**Ce qu'elle n'établit pas :**
- **Pas d'évaluateurs indépendants.** A et B viennent de la même personne : B est un programme que j'ai écrit, à partir d'une lecture différente du journal. Des fichiers d'audit à l'aveugle, sans verdict et mélangés, attendent un ou deux évaluateurs humains : `resultats/audit_v4_aveugle.csv` et `resultats/audit_v3_aveugle.csv`.
- **Peu de diversité dans les constats.** Le modèle choisit presque toujours les mêmes faits : 75 % de constats d'adoption et 20 % de sens dominant. La narration est fiable, mais répétitive et peu informative. Les faits de groupe, de messages et d'émergence ne sont presque jamais choisis.
- **Interprétations encore faibles.** Elles sont étiquetées et séparées des constats, mais environ une sur trois en dit trop. Elles ne devraient pas être affichées dans Godot comme les constats.
- **Échantillons modestes.** Les mesures portent sur 7 runs, tous en mode synchrone, et sur un seul modèle (`qwen2.5:7b`).

Fichiers : `resultats/narratrice_validation_v3.json`, `resultats/narratrice_validation_v4.json`, `resultats/audit_v3_evaluateur_b.json`, `resultats/audit_v4_evaluateur_b.json`, `resultats/emergence_complet_llm_synchrone*.json`.


## Architecture

```
simuler.py ──écrit──> runs/<run>.jsonl ──lu par──> narratrice.py ──écrit──> runs/<run>.narration.jsonl
   (monde)            (journal du monde)          (processus séparé)        (fichier de l'observateur)
```

- **Fichiers.** `narratrice.py` gère la ligne de commande et les trois modes. `ephemere/narration.py` calcule les faits, construit la consigne, valide les affirmations et fait le rejeu.
- **Modes.**
  - Post-traitement d'un run terminé : `python3 narratrice.py runs/X.jsonl`.
  - Suivi pendant le run : `--suivre`. Ce mode est refusé pour un run asynchrone, où la latence du modèle devient du temps simulé.
  - Rejeu : `--rejeu runs/X.narration.jsonl`.
- **Désactivée par défaut.** Sans cette commande, il n'y a aucune narration et aucun appel au modèle. Le simulateur n'a pas d'option de narratrice.
- **Une narration par relevé (un jour simulé)**, réglable avec `--periode`. Modèle par défaut : `qwen2.5:7b`, température 0,3, graine dérivée du run, délai de 60 s, 2 essais, 600 jetons au plus.
- **Coût mesuré :** environ 9 s et 1 200 jetons par narration, soit environ 4 min et 25 appels pour un run de 25 jours. Le run de référence en fait 786.

## Chaîne d'une narration (versions 1 et 2 ; voir plus haut pour les versions 3 et 4)

1. **Faits, sans modèle.**
   - À partir des événements de la fenêtre, le programme calcule le taux d'adoption et sa variation, la répartition des sens, le taux par groupe, qui a noué, retiré ou changé de lecture, les messages, les répliques et les incidents.
   - Sur un run terminé, il ajoute l'indicateur d'émergence corrigé et l'écart réel moins ombre (`emergence.py`).
   - Chaque fait porte une étiquette `F3`, les nombres qu'il autorise, ses sources `run#seq` et les agents qu'il nomme. Jusqu'à 4 paroles publiques (`P1`…) sont citées mot pour mot.
2. **Consigne.** Le modèle ne voit que ces faits et ces paroles. Il rend des affirmations typées (observation, mesure, interprétation ou incertitude), et chacune cite ses étiquettes.
3. **Validateur indépendant, sans modèle.** Une affirmation est rejetée dans les cas suivants :
   - elle cite une étiquette inconnue ;
   - elle n'a pas de source (sauf une incertitude) ;
   - elle contient un nombre, en chiffres ou en lettres, absent des faits cités ;
   - c'est une mesure sans nombre ;
   - elle nomme une personne absente des faits cités ;
   - elle attribue un retrait ou une adoption que le fait ne dit pas ;
   - elle annonce une hausse, une baisse ou une stabilité contraire à la variation mesurée, ou sans fait de variation cité ;
   - elle affirme une cause dans un constat, ou dans une interprétation qui n'est pas au conditionnel ;
   - elle prête une intention dans un constat ;
   - elle présente une parole comme un fait ;
   - elle met entre guillemets un texte absent des paroles citées ;
   - elle parle d'émergence sans citer l'indicateur corrigé, ou contre son verdict ;
   - elle dépasse la limite de 6 affirmations.

   Une affirmation rejetée sort du texte publié, mais reste dans l'événement avec sa raison.
4. **Statut de la narration :** `valide` (tout est vérifié), `partiel`, `vide` (rien de vérifiable) ou `incident` (modèle en erreur, délai dépassé, réponse illisible). Le texte vide est alors écrit tel quel : la narratrice continue, et le monde n'est pas concerné.

## Contrat (1.10.0, ajouts seuls)

- **`narratrice.v1`** (en-tête du fichier) : journal observé, empreinte SHA-256 de ce journal en post-traitement, mode, période, modèle, température, empreinte de la consigne, version du contrat.
- **`narration.v1`** : identifiant `N<k>`, fenêtre (relevés et `seq` de début et de fin), texte, affirmations validées (type, texte, étiquettes, sources `run#seq`, statut, raison), affirmations brutes du modèle, sources, indicateurs cités, empreinte des faits, modèle (dont la version du validateur), empreinte de la consigne, statut, incident, réponse brute, mesure (latence, jetons).
- Enveloppe : `t_sim` est la fin de la fenêtre, `t_emission` l'heure réelle de génération, et `seq` est propre au fichier de narration.
- `journal.Journal` refuse ces deux schémas. Un événement d'observateur ne peut donc pas entrer dans le journal du monde.

## Non-influence : ce qui est démontré, et dans quelles limites

| Contrôle | Résultat |
|---|---|
| Graphe complet des imports de `simuler.py` (20 fichiers, imports dans les fonctions compris) | Ni `ephemere/narration.py` ni `narratrice.py` n'y figurent |
| Recherche dans ces 20 fichiers du nom du fichier ou du module de narration | Seul `contrat.py` les nomme. Il définit les schémas et ne fait aucune entrée-sortie |
| Code qui construit les prompts (`simuler`, `agents_llm`, `monde`, `rag`, `dialogue`, `regles_v1`, `population`) | Ne mentionne pas la narratrice |
| `Journal` reçoit `narratrice.v1` ou `narration.v1` | Événement refusé et isolé dans le fichier de rejets |
| Sortie de la narratrice vers `corpus/`, `config/`, vers le journal observé, ou sous un autre nom que `*.narration.jsonl` | Refusée |
| Vrai run LLM sur 3 jours (boucle du simulateur, modèle simulé), avec une narration piège portant un marqueur à côté du journal | Marqueur absent des 25 prompts et du journal du monde. Le corpus ne lit rien dans `runs/` |
| Runs à règles, graines 100 et 101, 25 jours, sans narratrice puis avec la narratrice en suivi | 493 événements sur 493 identiques, hors horloge réelle et nom du run |
| Aucun journal du monde de `runs/` ne contient `narration.v1` ou `narratrice.v1` | Vérifié |

**Ce que cela permet de conclure.**
- Par construction et par test, le simulateur ne lit pas les narrations.
- Aucune narration n'atteint un prompt, une perception, une mémoire ou un document d'agent dans le code actuel.
- Pour des agents à règles, la présence de la narratrice ne change aucun événement.

**Ce que cela ne permet pas de conclure.**
- **Agents LLM.** Ollama n'étant pas déterministe (92 % de décisions identiques à graine égale), comparer deux runs LLM ne peut pas isoler l'effet de la narratrice. La non-influence y repose sur les contrôles structurels, pas sur une comparaison de résultats.
- **Charge partagée.** En suivi, la narratrice et les agents partagent la même instance d'Ollama : elle ralentit les appels des agents. En synchrone, cela ne change pas le temps simulé. En asynchrone, si, et c'est pourquoi le suivi y est refusé.
- **Chevauchement des runs à règles.** Ces runs durent moins d'une seconde. La première narration est arrivée après leur fin, donc ils n'ont presque pas chevauché le suivi. Le chevauchement réel a été vérifié sur les runs LLM : 4 narrations sur 5 générées pendant le run, pour chacun des deux runs suivis.
- **Code futur.** Les tests protègent le code actuel. Un futur changement, par exemple une mémoire collective qui indexerait `runs/`, devra repasser `tests/test_narratrice.py`, qui échouera s'il fait lire la narration.

## Historique : fiabilité des versions 1 et 2

Deux versions, mesurées sur des runs différents. La version 2 a été mesurée sur des données que la narratrice n'avait jamais vues : le run à règles de graine 101, le run LLM de graine 103 et la référence 02.

| | Version 1 | Version 2 (données neuves) |
|---|---|---|
| Runs narrés | règles graine 100 en suivi, LLM graine 102 en suivi, `c1_llm_01`, référence 01 | règles graine 101 en suivi, LLM graine 103 en suivi, référence 02 |
| Narrations | 60 : 36 valides, 24 partielles | 55 : 31 valides, 24 partielles |
| Incidents | 0 | 0 |
| Affirmations factuelles (observation et mesure) vérifiées | 198/228 = **86,8 %** (IC 95 % : 82 à 91 %) | 150/177 = **84,7 %** (IC 95 % : 79 à 89 %) |
| Principales raisons de rejet | intention prêtée (15), nombre non conforme (10) | intention prêtée (12), parole présentée comme un fait (10) |
| Sources citées / invalides | 314 / 0 | 548 / 0 |
| Interprétations et incertitudes | 2 | 18 |
| Latence médiane / maximale | 9,8 / 25 s | 8,4 / 27 s |

- **Cible de 95 % non atteinte.** Le modèle `qwen2.5:7b` enfreint encore les consignes, surtout en prêtant des intentions.
- **La version 2 n'améliore pas ce taux.** Son validateur est plus strict : nombres en lettres, paroles rapportées. Et sa consigne, plus stricte, n'a pas suffi à compenser.
- **Audit manuel de la version 2.** Je l'ai fait moi-même, sur 25 affirmations acceptées tirées au hasard. 4 sont fausses ou non étayées, soit environ 16 % (IC 95 % : 6 à 35 %) :
  - un quantificateur faux : « tous les étudiants n'ont donné aucun sens », alors qu'ils sont 16 sur 20 ;
  - un nombre rattaché au mauvais mot : « Imane a noué le ruban deux fois », alors que le fait dit « Karim et Imane (2) » ;
  - une parole déformée en action ;
  - une source hors sujet.

  Les nombres, les noms, les rôles, les citations et les variations ne sont jamais en défaut dans cet échantillon. Les erreurs sont des erreurs de lecture que le validateur mécanique ne voit pas.
- **Ce que cela vaut.** Une narration publiée est entièrement rattachée à des événements réels, ses nombres existent dans les faits, et ses noms et citations sont exacts. Mais ce n'est pas une garantie de vérité phrase par phrase. Elle se lit comme un résumé à vérifier par ses sources, que le format permet de consulter.

## Rejeu

- `narratrice.py --rejeu` relit l'en-tête et les narrations, recalcule les faits depuis le journal et revalide les réponses brutes enregistrées. Il compare ensuite les affirmations, le texte et le statut à ce qui a été écrit.
- **Résultat.** Les 7 fichiers de narration se rejouent avec 0 écart, Ollama étant rendu injoignable (`OLLAMA_URL` vers un port fermé). Un test vérifie en plus, dans un processus neuf, que le module du client LLM n'est même pas importé.
- **Écarts signalés.** Une narration retouchée à la main est signalée (« texte différent »). Les fichiers de la version 1 sont signalés comme « validés par la version 1 du validateur », et non comme identiques.
- **Godot.** L'affichage dans la scène n'est pas fait. Il demande de modifier `godot/main.gd` et `godot/campus3d.gd`, que je n'ai pas touchés.

## Tests

`tests/test_narratrice.py` contient 65 vérifications sans réseau (validateur version 4) :
- séparation et graphe d'imports ;
- refus par le journal ;
- refus des sorties interdites ;
- vrai run LLM avec narration piège ;
- faits et sources ;
- 25 cas du validateur ;
- 6 erreurs du modèle (absence de réponse, délai dépassé, connexion coupée, réponse sans affirmation, rien de vérifiable, absence de modèle) ;
- rejeu, retouche et changement de version.

Les 15 scripts de test du dépôt passent (`test_coherence_v2` en échec attendu, documenté).

## Fichiers

- Code : `narratrice.py`, `ephemere/narration.py`, `ephemere/contrat.py` (1.10.0), `ephemere/journal.py` (refus des schémas d'observateur), `ephemere/llm.py` (`max_tokens` facultatif, absent des appels des agents).
- Mesures : `resultats/narratrice_validation.json` (version 1), `resultats/narratrice_validation_v2.json` (version 2).
- Narrations : `runs/n4_*.narration.jsonl`, `runs/c1_llm_01.narration.jsonl`, `runs/n5_*.narration.jsonl`. Elles sont exclues par le `.gitignore`, qui ne garde que les runs `exp_*` et `demo_*`.
- Les journaux de référence 01 et 02 n'ont pas été modifiés : leurs narrations sont dans des fichiers `n4_` et `n5_` à part, et leurs empreintes sont vérifiées identiques.
