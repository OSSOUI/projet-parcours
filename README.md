# Éphémère · naissance, gloire et mort d'une mode à Tessaline

Simulation multi-agents LLM du sujet 04 du projet *Mondes Vivants*
(EIGSI Casablanca, 5A, option IA & Big Data).

Un lundi, deux étudiantes de l'atelier de design nouent un ruban à leur poignet.
La simulation observe ce que ce ruban finit par **vouloir dire** pour le campus,
et si ce sens se stabilise, se fragmente ou s'effondre.

## Lancer

```bash
# Baseline sans aucun LLM, instantanée, aucun appel (exigence E1)
python3 simuler.py --agents 20 --jours 25 --tout-regles --nom baseline

# Agents LLM en local, sans quota ni clé
ollama pull qwen2.5:7b && ollama pull qwen2.5:1.5b
python3 simuler.py --agents 20 --jours 25 --mode synchrone --fournisseur ollama

# Agents LLM via une API gratuite (coller la clé dans .env)
cp .env.example .env
python3 simuler.py --agents 20 --jours 25 --mode asynchrone --fournisseur groq --pause 2

# Vérifications des agents, sans aucun appel réseau
python3 tests/test_agents.py
python3 tests/test_rag.py
```

### Avec la visualisation

Trois terminaux.

```bash
# 1. Kafka
docker compose up -d

# 2. Le pont
pip install -r requirements.txt
python3 pont.py

# 3. La simulation
python3 simuler.py --agents 20 --jours 25 --fournisseur ollama --kafka
```

Puis ouvrir le dossier `godot/` dans Godot 4 et lancer la scène.

Filet de sécurité pour la soutenance, sans Kafka ni appel LLM :

```bash
python3 pont.py --rejeu runs/votre_run.jsonl
```

Aucune dépendance à installer : bibliothèque standard uniquement.

## Ce que fait l'étape 1

Le squelette, c'est-à-dire les trois fondations qu'on ne peut pas rajouter après coup.

### 1. Contrat d'événements versionné (`ephemere/contrat.py`)

Chaque événement porte un nom de schéma (`decision.v1`, `indicateurs.v1`, ...).
Un événement non conforme est **isolé** dans `runs/<run>.rejets.jsonl` avec la
raison, et la simulation continue.

Pour faire évoluer un schéma on ajoute `decision.v2`, on ne modifie jamais `v1` :
sinon les runs déjà enregistrés deviennent illisibles et le rejeu casse.

### 2. Deux horloges distinctes (`ephemere/horloge.py`)

Chaque événement porte :

| champ | sens |
|---|---|
| `t_sim` | minutes simulées depuis J1 00:00 |
| `t_sim_lisible` | `J03 14:30`, pour la lecture humaine |
| `t_emission` | horloge réelle à la production |
| `t_traitement` | horloge réelle au traitement, rempli par le consommateur |

`t_traitement` vaut `null` tant que personne n'a consommé l'événement. C'est le
pont qui l'horodate, à la milliseconde comme `t_emission`. En direct, il calcule
`delai_ms = t_traitement - t_emission` pour chaque événement, l'enregistre dans
`runs/<run>.traitement.jsonl` et en affiche la moyenne, la médiane, le p95 et le
pire cas à la fin du run : c'est la mesure de l'exigence C7. En rejeu, ce délai
n'est pas calculé, car il ne mesurerait que l'ancienneté du fichier.

### 3. Deux modes d'exécution

**Synchrone.** Tous les agents décident au même pas de temps, à partir de l'état
de la veille. On interroge tout le monde avant d'appliquer quoi que ce soit : une
publication du matin n'est visible que le lendemain.

Les pionnières font exception : elles se relaient, une sur deux réévalue à
chaque pas. Quand elles décidaient toutes ensemble sur le même état, elles
abandonnaient le même jour puis revenaient le même jour, et l'adoption oscillait
avec une période de deux jours (13 runs sur 30 en baseline, 24 sur 30 dans le
témoin). C'est un artefact de la simultanéité, pas un phénomène du campus. Avec
le relais, il n'y a plus aucun run oscillant, et la séparation B3 est intacte
(23/30 contre 0/30). `--pionnieres-simultanees` rétablit l'ancien comportement
pour le montrer.

**Asynchrone.** Chaque agent se réveille à sa propre cadence (720 min pour un
pionnier, 1440 pour un suiveur), avec un décalage individuel. Le monde change
entre deux agents, donc celui qui parle tôt influence ceux qui parlent après.
Une décision qui a demandé du temps de réflexion repasse par l'échéancier et
prend effet à `t + réflexion` : les agents réveillés entre-temps décident sur
l'état d'avant, et l'horloge n'a jamais à reculer.

Les deux modes relèvent les indicateurs sur la **même grille de temps simulé**,
sans quoi leur comparaison ne voudrait rien dire.

### Population hybride et paramétrable

`config/tessaline.json` est de la donnée, pas du code. Le nombre d'agents se fixe
avec `--agents`, la répartition des moteurs dans le fichier.

Trois moteurs cohabitent **dans le même run** :

| moteur | pour qui | pourquoi |
|---|---|---|
| `llm_grand` | pionniers, figure populaire | ils fabriquent le sens, il faut qu'ils argumentent |
| `llm_petit` | suiveurs, réfractaires, ironiques | imiter ou refuser demande moins |
| `regles` | 6 suiveurs sur 10 | aucun appel LLM : c'est le levier de sobriété |

L'attribution repose sur le **rôle dans le phénomène**, jamais sur une catégorie
sociale. Chaque profil porte sa propre justification dans la config.

À ne pas confondre : les agents à règles au milieu des agents LLM, c'est
l'exigence A6. Un run entier sans aucun LLM (`--tout-regles`), c'est la baseline
de l'exigence E1. Ce sont deux choses différentes.

### Le contexte commun, en termes observables

Le ruban peut vouloir dire six choses, et six seulement :
`cercle_creatif`, `tendance`, `suivre_la_foule`, `ringard`, `ironie`, `aucun_sens`.

La catégorie dit ce que le ruban **veut dire sur le campus** selon l'agent, que
celui-ci le porte ou non. Son geste est un champ séparé (`porte`). Un
non-porteur peut donc très bien répondre « ironie » : pour lui, le ruban, on le
porte pour s'en moquer. Le prompt donne la définition de chacun des six sens.
Le run d'essai du 21 octobre a montré pourquoi c'est nécessaire. Avec la seule
liste des mots et la question « ce que le ruban signifie pour toi », des
non-porteurs choisissaient « ironie » ou « suivre la foule » pour dire leur
propre refus, et l'indicateur mélangeait deux questions.

L'indicateur d'émergence est **`part_sens_dominant`** : la fraction du campus qui
attribue au ruban le même sens.

- `1.0` tout le campus lit le ruban de la même façon
- `0.3` six lectures concurrentes, aucune ne domine

Le taux d'adoption seul ne suffit pas : on peut avoir 80 % de porteurs qui ne
s'accordent sur rien. C'est exactement la différence entre une mode et un
contexte commun.

## Ce que fait l'étape 2

### Agents LLM à deux tailles (`ephemere/llm.py`, `ephemere/agents_llm.py`)

Le client appelle deux tailles de modèle et **compte séparément** les appels,
les tokens et les latences de chacune. C'est ce comptage qui permettra de
démontrer le levier de sobriété de l'exigence E5.

Les noms de modèles sont dans `config/tessaline.json`, par fournisseur. Ils
changent souvent chez les fournisseurs gratuits : à vérifier au démarrage.

### Mémoire et échanges

Un agent peut adresser son message à **une personne précise** de son groupe.
Ce message n'entre pas dans le fil public : il atterrit directement dans la
mémoire du destinataire, rangé comme un échange.

La mémoire injectée dans le prompt mélange les souvenirs récents **et le plus
ancien échange avec une personne**. C'est exactement ce que l'exigence A1
demande : pouvoir tenir compte d'un échange vieux de plusieurs jours simulés.

Les décisions et les échanges ont des plafonds **séparés** : 8 décisions et
30 échanges. Avec un plafond commun de 12, une pionnière, qui décide deux fois
par jour, perdait un échange au bout de 6 jours. Désormais, un échange du J1 est
encore là au J25 (c'est vérifié par `tests/test_agents.py`).

Le fil du réseau ne montre que les messages **nouveaux** depuis le dernier
passage de l'agent (curseur `vu_jusqu_a`). L'injection « relais massif » remet
ce curseur à zéro : au passage suivant, chacun relit tout le fil en plus de
l'article. Elle ne touche pas au temps de port, qui se compte depuis la
décision précédente.

### Détection des dérives (A4)

La fiche du sujet prévient : un LLM aligné sur la sécurité répond volontiers
en assistant prudent au lieu d'incarner un étudiant. On ne peut pas l'empêcher,
donc on le **mesure**. Ces natures de dérive sont détectées et comptées :

| nature | déclencheur |
|---|---|
| `appel_echoue` | quota, réseau, ou réponse vide |
| `json_illisible` | la réponse n'est pas un objet JSON |
| `champ_porte_invalide` | `porte` n'est pas un booléen |
| `categorie_hors_liste` | une catégorie inventée hors des six |
| `hors_langue` | réponse écrite dans une autre langue (vu : du qwen2.5:3b en italien) |
| `posture_assistant` | tournures du type « en tant qu'IA », « il est important de » |
| `fuite_de_consigne` | le modèle recopie la consigne au lieu de la remplir |
| `incoherence_texte_etat` | le texte dit « je le porte » ou « je prends part » alors que `porte` vaut `false`, ou l'inverse |

Une faute de frappe très proche d'une catégorie (`suivre_la_folle`) est ramenée
à la bonne valeur au lieu d'être comptée comme dérive. La correction est notée
dans `perception.v1` (`categorie_corrigee`), si bien que le taux de fautes par
taille de modèle reste mesurable. Une vraie invention (`seulement_circulaire`)
reste une dérive.

Le contrôle de cohérence entre texte et état est lexical. Il repère les
tournures observées dans les runs, pas toutes les façons de dire qu'on porte
ou non le ruban : c'est une limite à mentionner.

Dans tous les cas, **l'agent garde son état de la veille et le run continue**.
Chaque incident part dans un événement `incident.v1`, et le total figure dans
le bilan : le taux de sortie de rôle devient un résultat du rapport.

Le détecteur de posture est lexical, donc faillible. C'est une limite à
assumer dans le rapport plutôt qu'à cacher. Chaque motif vise une tournure
d'assistant et non du français courant. « En tant que membre du club
d'humour », « je ne peux pas le mettre à l'atelier » et « cependant, il
commence à se voir » ne sont plus signalés, alors que « en tant qu'IA » ou
« je ne peux pas donner d'avis » le restent. Les tests fixent ces cas dans
les deux sens.

### Ce que l'agent a vu (`perception.v1`)

Chaque décision d'un agent LLM produit un événement `perception.v1` qui contient :
- les messages du fil qu'il avait sous les yeux ;
- les souvenirs injectés ;
- les passages retrouvés dans la base ;
- ce qu'il voyait de son groupe et du campus ;
- la **réponse brute** du modèle, mot pour mot.

Trois usages :
- le détecteur de dérives se recalcule hors ligne, sans relancer un seul appel ;
- les échanges qui précèdent un basculement se retrouvent (B4) ;
- deux profils placés devant le même contexte se comparent directement (A3).

### Cohérence temporelle mesurée (C6)

Les filtres du fil, de la mémoire et de la base empêchent un agent de voir
l'avenir. Un contrôle indépendant le **vérifie** à chaque décision LLM : aucun
message, souvenir ou document ne doit être postérieur au moment simulé de la
décision. Le total du run part dans `coherence.v1` : contextes contrôlés,
violations trouvées, et le détail de chacune. Un zéro est donc une mesure,
pas une supposition.

### Énergie (E4)

Si CodeCarbon est installé (`pip install codecarbon`), chaque run mesure
l'énergie de la machine locale et l'écrit dans `energie.v1`. Avec Ollama, cela
comprend l'inférence. Avec une API, seule la machine locale est couverte, et
l'événement le précise. Sans CodeCarbon, l'événement est quand même écrit, avec
`kwh: null` et la raison.

### Cloisonnement

Quand la perception du campus vaut zéro (configuration témoin, ou injection
« cloisonnement »), un agent LLM est cloisonné exactement comme un agent à
règles. Son prompt ne donne plus le compteur ni la tendance du campus. Il ne
montre plus les messages des autres groupes. Les échanges adressés d'un groupe
à l'autre n'arrivent pas. Seules les injections de la scène restent visibles
de tous.

### Le temps de réflexion devient du temps simulé

En mode asynchrone, la latence réelle du modèle est convertie en minutes
simulées (`--minutes-par-seconde`, 5 par défaut). Un gros modèle lent
réfléchit donc plus longtemps dans le monde, et son avis arrive après celui
des autres. C'est la matière de la comparaison C5 et de la question Q6 du jury.

## Ce que font les étapes 4 et 5

### Kafka (`ephemere/bus.py`)

Un événement Kafka par événement métier, exactement les mêmes que ceux du
fichier. Pas d'agrégation. La raison tient à l'exigence F6 : tout indicateur
affiché doit pouvoir être remonté jusqu'aux événements bruts, donc les
événements bruts doivent circuler.

La clé du message est le nom du run, donc tous les événements d'un run partent
sur la même partition et arrivent dans l'ordre. Sans cela une décision pourrait
être traitée avant la publication qui l'a provoquée.

Si Kafka est injoignable, le run s'arrête **avant le premier appel LLM**. Si le
broker tombe en cours de route, le fichier continue et le run va au bout.

### Le pont (`pont.py`, `ephemere/campus.py`)

Godot ne parle pas Kafka. Le pont lit le topic, reconstruit l'état du campus et
diffuse en WebSocket sur `ws://localhost:8765`.

Le pont ne garde aucun état de la simulation, il le **reconstruit** à partir des
événements. C'est ce qui rend le rejeu d'un fichier strictement équivalent à une
lecture en direct, et c'est aussi là qu'est posé `t_traitement` : le producteur
dit quand l'événement s'est produit dans le monde, le consommateur dit quand il
l'a traité.

### La scène (`godot/main.gd`)

Un bloc par groupe, un rond par étudiant. La **couleur dit ce que le ruban veut
dire** pour lui, le ruban dessiné autour dit qu'il le porte, un liseré rouge
signale un agent dont la dernière réponse était inexploitable.

Clic sur un étudiant : son sens, la justification de sa dernière décision et sa
mémoire. Quatre boutons en bas injectent un événement dans le monde en cours.

### Les injections (`ephemere/commandes.py`)

La scène demande, le pont publie dans `ephemere.commandes`, la simulation lit ce
topic sans bloquer entre deux pas de temps. Quatre leviers, repris de la fiche
du sujet :

| bouton | effet sur le monde |
|---|---|
| Relais massif | tout le campus redécouvre le fil d'un coup |
| Tendance rivale | un signe concurrent apparaît sur le réseau |
| Rumeur | un message anonyme entre dans le fil |
| Cloisonner | les groupes cessent de se voir, seul le groupe compte |

Chacune agit sur la **situation**, jamais sur la décision d'un agent.

## Ce que fait l'étape 3

### Le corpus de Tessaline (`corpus/`)

Neuf documents fictifs, écrits pour ce projet : trois archives du journal
étudiant *La Criée* sur les modes passées du campus (les lacets dépareillés, les
badges émaillés, le bonnet de mai), les chartes de trois associations, le
règlement des résidences, un portrait de l'atelier de design, et une enquête sur
le ruban qui paraît **au jour 9 de la simulation**.

Chaque document porte un en-tête qui dit qui peut le lire et à partir de quand.

### La recherche (`ephemere/rag.py`)

BM25 écrit à la main, soixante lignes, aucune dépendance. Le sujet autorise les
frameworks à condition de savoir expliquer leur fonctionnement interne : BM25 se
démontre au tableau, un moteur vectoriel beaucoup moins, et sur neuf documents il
n'apporterait rien de mesurable.

Deux filtres s'appliquent **avant** le classement, et ils ne sont pas cosmétiques.

**Le temps.** Un article paru au jour 9 n'existe pas pour un agent qui décide au
jour 4. Vérifié : la même requête ne renvoie l'enquête sur le ruban qu'à partir
du jour 9, jamais avant. Sans ce filtre, les agents citeraient l'avenir et
l'exigence C6 tomberait.

**Le groupe.** La charte de l'atelier de design n'est lisible que par ses
membres. Vérifié : elle est invisible depuis la résidence B, visible pour un
membre de l'atelier.

### Ce que chaque agent va chercher

La requête dépend du profil, donc deux agents dans la même situation ne
retrouvent pas la même chose. Un pionnier cherche autour de « se distinguer,
devenir banal, signe distinctif de l'atelier », un réfractaire autour de
« refuser une mode par principe ». C'est ce qui rend la récupération défendable,
et c'est aussi une partie de la réponse à l'exigence A3.

La requête ne contient **pas** de préfixe commun comme « ruban au poignet ». Lors
du run d'essai, ces deux mots rares ramenaient le même paragraphe du même
article pour tous les profils : 33 passages sur 54 venaient de lui. Chaque
recherche renvoie aussi au plus **un passage par document**.

### La preuve (exigence F2)

Chaque recherche produit un événement `recuperation.v1` qui contient la requête,
les identifiants retrouvés, leurs scores et le jour de chaque document.
`analyser.py` en sort le nombre de recherches, la moyenne de passages par
décision, la part de recherches sans résultat et les documents les plus
retrouvés. C'est ce tableau qui répond à « montrez la qualité de votre
récupération », et à la question Q5 du jury.

## Protocole expérimental

```bash
python3 experience.py --liste                     # plans et hypothèses
python3 experience.py --plan socle --jours 25     # 30 graines, sans LLM
python3 experience.py --plan b3_llm --fournisseur ollama   # B3 et Q2 côté LLM
python3 experience.py --plan temps  --fournisseur ollama   # C5
python3 experience.py --plan sobriete --fournisseur ollama # E5
```

Toutes les configurations d'un plan tournent sur les **mêmes graines**, et la
comparaison se fait aussi graine par graine. L'hypothèse de chaque
configuration est écrite dans `experience.py` avant toute mesure.

L'accord mesuré est la part du campus sur le sens le plus répandu **autre que
« aucun sens »**, avec les non-porteurs au dénominateur. Quand « aucun sens »
domine, le relevé n'est donc plus jeté.

## Couverture des exigences

| Exigence | État à l'étape 1 |
|---|---|
| B1 contexte commun observable | fait |
| C2 nombre d'agents paramétrable | fait, via `--agents` |
| C3 moment simulé et moment de traitement | fait côté production |
| C4 modes synchrone et asynchrone | fait |
| F4 schéma versionné, non-conforme isolé | fait |
| A6 agents à règles parmi les agents LLM | fait |
| A5 deux tailles de modèle | fait |
| A1 mémoire propre qui influence la décision | fait |
| A2 échanges en langage naturel | fait |
| A4 le système tient, incidents comptés | fait |
| E1 baseline sans LLM | fait, via `--tout-regles` |
| E4 coût mesuré par run | fait, par taille de modèle |
| B2 indicateur pendant le run | calculé, pas encore affiché près de la scène |
| A3 deux profils décident différemment | à démontrer par un run |
| C1 événements dans Kafka | fait |
| C3 horodatage du traitement | fait, des deux côtés |
| D1 scène Godot en direct | fait |
| D2 inspection d'un agent | fait |
| D3 injection depuis l'interface | fait |
| E3 rejeu sans appel LLM | fait, `pont.py --rejeu` |
| F1 décisions appuyées sur une base de connaissances | fait |
| F2 qualité de la récupération démontrée | fait, traçée dans le flux |
| F3 où vivent flux, état, historique, base | fait |
| C6 cohérence temporelle de l'information | fait, vérifié par les tests |
| C5 comparaison synchrone / asynchrone | outillée (`experience.py --plan temps`), runs LLM à faire |
| C7 délai entre émission et traitement | fait, `runs/<run>.traitement.jsonl` écrit par le pont |
| F6 indicateur remontable aux événements bruts | fait, un événement Kafka par événement métier |
| B3 E2 protocole socle | fait : 30 graines communes, 23/30 runs émergents contre 0/30 pour le témoin |
| C6 violations détectées et comptées | fait, `coherence.v1` à chaque run |
| E4 énergie | outillé avec CodeCarbon, `energie.v1` |
| B3 avec agents LLM | plan `b3_llm` prêt, runs à faire |
| E5 sobriété | plan `sobriete` prêt (`--tout-grand`), runs à faire |

## Suite

2. ~~Agents LLM, mémoire et échanges~~ fait
3. ~~Corpus de Tessaline et RAG~~ fait
4. ~~Kafka et pont WebSocket~~ fait
5. ~~Scène Godot, inspection, injection~~ fait
6. Protocole expérimental, runs répétés, bilan de sobriété (B3, E2, E5)
7. Revenir sur la qualité des agents LLM, laissée de côté

## Arborescence

```
Ephemere/
  simuler.py            point d'entrée
  config/tessaline.json population et perception, modifiables sans toucher au code
  ephemere/
    contrat.py          schémas d'événements versionnés, les six sens
    horloge.py          horloge simulée et échéancier
    population.py       construction de la population hybride
    monde.py            état du campus et indicateurs d'émergence
    regles.py           agents à seuils, sans appel LLM
    llm.py              client Groq / OpenRouter / Ollama, deux tailles
    agents_llm.py       prompts, mémoire, échanges, détection des dérives
    bus.py              publication des événements dans Kafka
    campus.py           reconstruction de l'état à partir du flux
    commandes.py        injections venues de la scène
    rag.py              base de connaissances et recherche BM25
    journal.py          écriture des événements et isolement des rejets
  tests/test_agents.py  vérifications hors ligne des agents
  tests/test_rag.py     vérifications du corpus et des filtres
  runs/                 un fichier .jsonl par run
  corpus/               les neuf documents fictifs de Tessaline
  pont.py               Kafka vers WebSocket, et rejeu d'un run
  analyser.py           chiffres d'un run, pour le rapport
  docker-compose.yml    Kafka en un seul nœud
  godot/main.gd         la scène du campus
```
