# Intégration de bout en bout : audit, développements, validation (4 novembre 2026)

Espace de travail : `~/projet-parcours-integration`. C'est un worktree git sur la branche `integration`, créé depuis `b9445ee` (aucun commit). L'état non commité de `~/projet-parcours` y a été recopié tel quel, sauf les runs de l'expérience mémoire, qui restent dans l'original.

L'expérience mémoire n'est jamais lancée d'ici.

## 1. Audit, avant développement

Légende : **oui** = vérifié par un test ou une mesure enregistrée ; **non** = jamais fait.

| Composant | Déjà implémenté | Testé isolément | Testé en intégration | Ce qui manquait | Dépendances, risques |
|---|---|---|---|---|---|
| Simulation LLM (`simuler.py`, `agents_llm.py`) | Oui : modes synchrone et asynchrone, graine par appel, contrat d'événements | Oui : `test_agents`, `test_mesures_llm` (modèle simulé) | Oui : séries de référence, C1 en LLM avec Kafka (`c1_llm_01`) | Rien pour la démonstration | Ollama partagé, non déterministe (environ 92 % de décisions identiques à graine égale) |
| Mémoire individuelle, `--memoire-sens` | Oui : mémoire de 8 décisions et 30 échanges, variante désactivée par défaut | Oui : `test_memoire` (22 vérifications), audit exact sur 1 310 décisions | Rejeu seulement (`verifier_comparabilite.py`). Jamais en direct avec Kafka ou Godot | **La scène n'affiche pas la mémoire réellement injectée.** Le pont reconstruit sa propre « mémoire » depuis `decision.v1` (« il porte le ruban ») et ignore `perception.v1`, donc la ligne du sens | La mémoire montrée dans Godot n'est pas celle du prompt. **Non corrigé** (voir partie 4) |
| Interactions sociales | Oui : publications publiques, messages privés (`destinataire`), conversations (`--conversation`, `replique.v1`) | Oui : `test_dialogue`, `test_reseau` | Publications : oui (pont et animations Godot). Conversations : jamais avec Kafka ou Godot | **Le rejeu ne couvre pas les conversations** | La configuration E (référence) est sans conversation : la démonstration n'en a pas |
| Ombres contrefactuelles | Oui : `--ombres`, `ombre.v1`, jamais appliquées | Oui : `test_ombres`, rejeu des 5 références | Les `ombre.v1` passent dans Kafka. Le pont les ignore (non appliquées, non affichées) | Pas de preuve directe de non-application en conditions réelles | Voir partie 3 : preuve ajoutée par rejeu perturbé |
| Journal JSONL et `run#seq` | Oui : `seq` = ligne, `lire()` migre les anciens runs, refus des schémas d'observateur | Oui : `test_identifiants` (21) | Oui : C1 | Rien | Le journal est écrit et vidé sur disque **avant** la publication Kafka (vérifié dans `journal.ecrire`) |
| Kafka (`bus.py`) | Oui : `acks=all`, bilan du producteur (confirmés, perdus, sans réponse) | Oui | Oui (C1) : 0 perte, consommateur coupé, broker coupé | **Le pont lisait le topic « depuis maintenant » et sans filtre de run :**<br>• un pont démarré après le simulateur perdait le début du run ;<br>• un pont relancé repartait à vide ;<br>• après une coupure du broker, rien n'était rattrapé | Le conteneur `ephemere-kafka` est partagé avec les essais C1 : le topic contient d'anciens runs |
| Narratrice V4 | Oui : modes post, `--suivre` et `--rejeu`, validateur v4 | Oui : `test_narratrice` (68), 133/133 constats vrais sur données inédites | `--suivre` sur un run en cours (série n6). **Jamais reliée au pont ni à Godot** | Transport des narrations vers la scène | Une narratrice relancée renarre tout et réécrit son fichier |
| Rejeu | En morceaux :<br>• `pont.py --rejeu` (affichage) ;<br>• `narratrice.py --rejeu` ;<br>• `verifier_comparabilite.py` (monde, runs de référence seulement) | Oui, chacun | Non : aucun rejeu unique du monde, des ombres, des narrations et de la scène | Outil unique, ombres perturbées, narrations post-run | — |
| Pont Python vers Godot (`pont.py`) | Oui : Kafka ou fichier, WebSocket, doublons écartés, délais C7 | `test_campus` | Oui : C1, état reconstruit depuis Kafka = depuis fichier | Filtre de run, rattrapage depuis le journal, narrations, bilan écrit, refus des injections en démonstration | — |
| Affichage 3D et constats (`godot/main.gd`, `campus3d.gd`) | Campus 3D, panneau, courbe, rejeu piloté | Manuel (aucun test automatique) | Manuel, avec le pont | **Aucun affichage des narrations.** Aucune trace de ce que la scène reçoit | **Le Godot installé (`~/Downloads/Godot_mono.app`, 4.7.2 mono) ne démarre pas sur cette machine.** Il se bloque à l'initialisation .NET (dotnet absent), même pour un script minimal, avec ou sans fenêtre |

## 2. Développements réalisés (copie d'intégration seulement)

| Fichier | Ajout | Statut |
|---|---|---|
| `pont.py` | `--run` : un seul run, lu depuis le début du topic | Testé |
| | Rattrapage depuis le journal d'un `seq` sauté | Testé |
| | Veille de fin de run : la fin perdue par Kafka est reprise du journal | Testé |
| | Narrations lues dans leur fichier (jamais dans Kafka), envoyées en trois canaux. Le champ `texte`, qui mélange les canaux, n'est pas envoyé | Testé |
| | `runs/<run>.pont.json` : reçus, rattrapés, doublons, envois | Testé |
| | `--sans-injections`, arrêt propre sur SIGTERM | Testé |
| `godot/main.gd` | Message `narration` | **Écrit, non exécuté** (Godot ne démarre pas ici) |
| | Panneau « Récit de l'observatrice : constats vérifiés », sans sélection d'étudiant | **Écrit, non exécuté** |
| | N : récit ou réseau interne ; H : hypothèses et incertitudes, à part et en gris, masquées par défaut | **Écrit, non exécuté** |
| | `EPHEMERE_TRACE` (trace de réception), `EPHEMERE_CAPTURES` (image tous les 5 jours) | **Écrit, non exécuté** |
| | `campus3d.gd` n'est pas touché | — |
| `scene_temoin.py` (nouveau) | Client WebSocket qui reçoit exactement ce que reçoit Godot et applique la même règle d'affichage du récit. Ce n'est pas Godot | Testé |
| `rejeu_integration.py` (nouveau) | Monde resimulé sans modèle, en rendant à chaque ombre une réponse **contraire** au réel | Testé |
| | Narrations recalculées, émergence comprise pour les narrations post-run | Testé |
| | État de la scène reconstruit depuis le fichier | Testé |
| `demo_integration.py` (nouveau) | Orchestrateur : pont, puis scène(s), puis narratrice, puis simulateur (configuration E) | Testé |
| | Avec `--pannes` : arrêt du pont, de la scène et de la narratrice, coupure du broker | Testé |
| | Audit : topic contre fichier, producteur, pont, traces de scène, évaluateur B, rejeu | Testé |
| | Refuse de démarrer si l'expérience mémoire tourne | Testé |

**Isolement de la narratrice, inchangé et vérifié :**
- Les narrations ne vont que du fichier au pont, puis du pont à la scène.
- Le pont n'écrit dans Kafka que les injections de la scène, refusées en démonstration.
- Le simulateur ne lit ni le fichier de narration ni un topic qui en contienne.
- L'audit vérifie qu'aucun événement d'observateur n'est dans le journal ni dans le topic.

## 3. Validations

Les résultats sont dans `runs/demo_*.integration.json` (copie d'intégration).

- **Rejeu du monde avec ombres perturbées, sur `exp_reference_llm_reference_01`.**
  - Monde identique : 1 022 événements.
  - Les 424 ombres ont été rejouées avec une réponse contraire à la décision réelle (port inversé, autre sens), et le monde ne change pas.
  - Dans le journal, 121 ombres différaient effectivement du réel.
  - C'est la preuve directe qu'aucune décision d'ombre n'est appliquée au monde.
- **Rejeu d'un run narré après coup (`exp_complet_llm_synchrone_01` et sa narration n7) :**
  - monde identique, alors que ce run date du 21 octobre (contrat 1.1.0) ;
  - 25 narrations identiques sur 25 ;
  - scène égale au dernier relevé.
- **Chaîne à règles, sans modèle** (`demo_essai_regles` et `_2`, 5 jours, avec pannes) :
  - 103 événements écrits, confirmés par Kafka, appliqués par le pont, reçus par la scène témoin ;
  - 0 doublon, 0 trou, contenu du topic identique au fichier.
- **Défaut trouvé par le premier essai, puis corrigé.**
  - Le broker a été coupé alors que le run s'achevait : les 3 derniers événements (énergie, cohérence, bilan) ne sont jamais arrivés dans Kafka.
  - Le pont ne rattrapait un trou qu'à l'arrivée de l'événement suivant ; une fin de run perdue n'était donc jamais rattrapée.
  - Correctif : la veille de fin de run. Testée sans Kafka, elle reprend les 103 événements du journal.
- **Test de fumée LLM et démonstration complète :** voir les parties 5 et 6.

## 5. Test de fumée LLM (`demo_fumee`, 4 jours, graine 200, configuration E, 07:45 à 07:54)

**Rapport complet :** `runs/demo_fumee.integration.json`.

**Configuration :** agents LLM, `--memoire-sens`, ombres `sans_discours`, `sans_social` et `sans_souvenirs`, Kafka, narratrice `--suivre`, pont `--run --sans-injections`, scène témoin. Godot n'a pas tourné (partie 4).

**Pannes provoquées :**

| Moment | Panne |
|---|---|
| Après le relevé J02 | Pont arrêté, relancé 5 s plus tard |
| Après J03 | Scène fermée puis rouverte ; narratrice arrêtée (SIGTERM) puis relancée |
| Après J04 | Broker Kafka arrêté 20 s (`docker stop` puis `start ephemere-kafka`) |

**Bilan par étape de la chaîne :**

| Étape | Événements | Pertes | Doublons | Ordre |
|---|---|---|---|---|
| Produits (journal) | 293, `seq` continus de 0 à 292 | — | — | — |
| Producteur Kafka | 293 publiés, 293 confirmés, 0 perdu, 0 sans réponse | 0 | — | — |
| Topic, relu depuis le début | 293 messages, contenu identique au fichier, ligne à ligne | 0 | 0 | 0 hors ordre |
| Pont (relancé, il a relu le run depuis le début) | 293 appliqués, 0 rattrapé, 0 manquant | 0 | 0 écarté | — |
| Scène témoin (3 connexions) | 293 `seq` distincts reçus, état final « 293 événements vus » | 0 jamais reçu | — | — |

- **Délai d'émission à traitement :** médiane 62 ms, 95e centile 6,6 s, maximum 85,7 s. Le maximum correspond aux événements retenus par le producteur pendant la coupure du broker, puis livrés : aucun n'est perdu.
- **Le rattrapage depuis le journal n'a pas servi ici,** puisque le producteur a tout renvoyé. Il est vérifié hors ligne (partie 3).

**Narratrice :**
- 4 narrations, une par jour, refaites en entier après la relance ; le pont a relu le fichier recréé.
- 6 constats vérifiés, 6 vrais pour l'évaluateur B.
- 5 affirmations rejetées par le validateur.
- 0 hypothèse ni incertitude acceptée dans ce run : le masquage des hypothèses n'a donc pas été exercé en direct (il est testé par `test_narratrice`, partie 8).

La scène témoin affiche 4 narrations, avec leurs 6 constats et seulement eux.

**Isolement :** 0 événement d'observateur dans le journal, 0 dans le topic.

**Rejeu sans modèle :**
- **Monde :** identique (174 événements du monde), mémoire du sens comprise.
- **Ombres :** les 114 ombres ont été rejouées avec une réponse contraire au réel, et le monde est resté identique. Dans le journal, 25 ombres différaient effectivement du réel.
- **Narrations :** 4 identiques sur 4.
- **Scène :** état reconstruit égal au dernier relevé (65 %).

Ce run est un test technique. Il ne mesure rien sur la mémoire ni sur l'émergence.

## 6. Godot opérationnel et validé en rejeu

**Moteur.** Godot 4.7.2 standard (sans .NET), téléchargé avec l'accord de l'utilisatrice depuis la page officielle des versions (github.com/godotengine). Il est rangé dans le dossier temporaire de la session : `…/scratchpad/godot_std/Godot.app`.
- SHA-512 conforme à `SHA512-SUMS.txt` de la version.
- Signature Apple valide (équipe 6K46PWY5DM).
- `--version` donne `4.7.2.stable.official`.
- L'installation mono existante (`~/Downloads/Godot_mono.app`) n'est pas touchée.

**Compilation.** `main.gd` et `campus3d.gd` se chargent et passent `--check-only` sans erreur ni avertissement. Aucune incompatibilité n'a été trouvée.

Il reste un avertissement préexistant au chargement de `main.tscn` : UID non valide pour `main.gd`, résolu par le chemin. Il ne vient pas de ces modifications et n'a pas été corrigé.

**Banc du récit (`godot/verifier_recit.gd`, vraie scène, sans pont ni modèle) :** 8 vérifications sur 8, avec et sans fenêtre.
- La narration est reçue, et le récit est la vue par défaut.
- Les trois canaux restent séparés.
- Hypothèses et incertitudes sont masquées par défaut. H les affiche, et H les masque de nouveau.
- N passe au réseau interne.
- Un instantané de reconnexion remplace les narrations.
- **Images :**
  - `runs/verification_godot/recit_hypotheses_masquees.png` : le constat seul ;
  - `runs/verification_godot/recit_hypotheses_affichees.png` : hypothèse et incertitude à part, en gris, préfixées « hypothèse, non vérifiée » et « incertitude ».

**Rejeu de `demo_fumee` dans Godot (`runs/demo_fumee.rejeu_godot/`) :**
- **Événements :** 293 reçus sur 293, dans l'ordre, aucun manquant ; état final « 293 événements vus ».
- **Récit :** 4 narrations, 6 constats, 0 hypothèse ni incertitude (aucune acceptée dans ce run).
- **Modèle :** 0 requête servie par Ollama pendant le rejeu (compté dans `~/.ollama/logs/server.log`).
- **Image finale :** elle correspond au dernier relevé du journal. Adoption 65 % ; sens dominant « suit la foule » à 55 % ; répartition tendance 3, suit la foule 11, ironie 5, ringard 1 ; courbe J0 à J4 ; récit des 4 jours, constats seuls.
- **Captures :** `jour_04.png` et `final.png`.

**Godot en direct dans la chaîne (`demo_essai_godot_direct`, 3 jours, agents à règles, narratrice) :**
- 64 événements reçus sur 64 et 3 narrations reçues, par Godot comme par la scène témoin ;
- 3 constats, 3 vrais pour l'évaluateur B ;
- captures `jour_03.png` et `final.png` ;
- rejeu Godot : 64 sur 64, 0 requête Ollama.

**Incident pendant ces essais, et correctif.**
- Un Godot du rejeu manuel est resté ouvert, à cause d'un motif `pkill` mal écrit. Il s'est reconnecté aux ponts suivants (Godot se reconnecte toutes les 2 s).
- **Ce qui a été touché :** sa trace et ses captures (`runs/rejeu_godot_demo_fumee/`, annoté `A_LIRE.md`), ainsi que le premier rejeu de l'essai direct (renommé `.pollue`).
- **Ce qui ne l'a pas été :** aucune donnée de simulation.
- **Correctif :** `demo_integration.py` refuse désormais de démarrer, ou de lancer un rejeu Godot, si un Godot tourne déjà. Il tue un processus qui ne s'arrête pas.
- Le rejeu refait proprement donne 64 sur 64.

## 4. Ce qui reste à faire, sans l'avoir inventé

- **Exécuter Godot.** Il faut l'une de ces deux solutions :
  - la version standard de Godot 4.7.2 (sans .NET) ;
  - le SDK .NET pour la version mono installée.

  Ensuite, `demo_integration.py --godot <exécutable>` lance Godot avec sa trace et ses captures, et l'audit compare sa trace au journal comme pour la scène témoin. Tant que ce n'est pas fait, l'affichage des constats dans Godot n'est pas vérifié, ni même compilé.
- **Mémoire affichée.** Faire lire au pont `perception.v1` pour montrer les souvenirs réellement injectés, ligne du sens comprise, au lieu de la reconstruction actuelle.
- **Narratrice relancée.** Elle renarre tout le run depuis le début, ce qui coûte des appels au modèle. Il n'y a pas de reprise à la dernière fenêtre.
- **Conversations privées :** non rejouées.
- **Rattrapage sans fichier.** Il suppose que le pont voit le journal (même machine). Avec un pont distant, il faudrait un autre canal (relecture du topic, ou réémission par le producteur).

## 7. Godot validé dans l'application réelle (4 novembre 2026, sans Ollama)

**Ce qui est vérifié.** L'application elle-même (`main.tscn`, Godot 4.7.2 standard, avec fenêtre) est connectée au vrai pont. Un pilote, `godot/verifier_rejeu.gd`, agit comme un utilisateur : touches H, espace et flèche gauche. Les adresses Ollama pointent vers un port fermé, et le journal d'Ollama est relevé avant et après.

**Données de vérification.** `runs/verif_godot_hyp.jsonl` est une copie identique de `exp_complet_llm_synchrone_01` (25 jours, 1 032 événements). Sa narration est une copie de `n7_complet_01` : 25 narrations, 35 constats, 8 hypothèses. Aucune narration enregistrée ne contient d'incertitude acceptée ; leur affichage n'est vérifié que par le banc (`verifier_recit.gd`).

**Défaut trouvé, puis corrigé.**
- **Symptôme.** Au premier essai, Godot a reçu les événements 1 à 990, puis s'est reconnecté et n'a plus reçu qu'un instantané. L'état final était juste, mais les 42 derniers événements ne sont pas arrivés un par un, et une narration non plus.
- **Cause, mesurée.**
  - Chaque message du pont porte l'état complet du campus.
  - Le message n° 991 est le premier à dépasser 65 535 octets, soit le tampon de réception par défaut de `WebSocketPeer`.
  - `demo_fumee` (4 jours) n'atteignait que 25,5 Ko.
  - **La démonstration de 25 jours aurait décroché en fin de run.**
- **Correction (`godot/main.gd` uniquement).** Tampon de réception de 16 Mo, appliqué à la connexion comme à chaque reconnexion (`_connecter()`). Le pont n'est pas modifié.
- **Traces.** Celles des deux essais sont conservées : `runs/verification_godot_rejeu_essai1/` (critère de test mal posé) et `_essai2_tampon_64k/` (le défaut).

**Résultat après correction (`runs/verification_godot_rejeu/`) : 10 vérifications sur 10.**

| Vérification | Résultat |
|---|---|
| L'application démarre et se connecte au pont | Oui |
| Événements reçus | 1 032 sur 1 032, dans l'ordre, une seule connexion |
| Narrations reçues | 25 sur 25 |
| Adoption affichée | 75 %, le dernier relevé du journal |
| Récit | Constats affichés. Hypothèses reçues mais **masquées par défaut** |
| H | Hypothèses affichées à part (gris, « hypothèse, non vérifiée »), puis de nouveau masquées |
| Espace | Le pont accuse « rejeu : en pause » |
| Flèche gauche | Retour au jour 24 : moins d'événements vus, aucune narration postérieure à J24 |
| Requêtes Ollama | 0 |

**Images :** `rejeu_fin_hypotheses_masquees.png`, `rejeu_fin_hypotheses_affichees.png` et `rejeu_jour_precedent.png`.

**Temps réel, sur 25 jours** (`demo_essai_godot_direct_25j`, agents à règles, sans narratrice, Kafka) :
- Godot reçoit 493 événements sur 493 en direct, dans l'ordre ;
- captures des jours 5, 10, 15, 20 et 25, plus l'image finale ;
- le rejeu Godot du même run donne 493 sur 493, avec 0 requête Ollama.

Le temps réel avec agents LLM et narratrice n'a été vérifié que sur 4 jours (`demo_fumee`, avec la scène témoin, puis le rejeu Godot). La démonstration de 25 jours le couvrira.

**Banc du récit, relancé après la correction :** 8 vérifications sur 8.

**Défaut visuel mineur, non corrigé.** Quand le panneau du récit est plein, la dernière ligne déborde de quelques pixels sous son cadre.
