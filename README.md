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
pont Kafka qui l'horodatera, à l'étape 4. Le décalage entre `t_sim` et
`t_traitement` est la mesure attendue par l'exigence C7.

### 3. Deux modes d'exécution

**Synchrone.** Tous les agents décident au même pas de temps, à partir de l'état
de la veille. On interroge tout le monde avant d'appliquer quoi que ce soit : une
publication du matin n'est visible que le lendemain.

**Asynchrone.** Chaque agent se réveille à sa propre cadence (720 min pour un
pionnier, 1440 pour un suiveur), avec un décalage individuel. Le monde change
entre deux agents, donc celui qui parle tôt influence ceux qui parlent après.

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

### Détection des dérives (A4)

La fiche du sujet prévient : un LLM aligné sur la sécurité répond volontiers
en assistant prudent au lieu d'incarner un étudiant. On ne peut pas l'empêcher,
donc on le **mesure**. Cinq natures de dérive sont détectées et comptées :

| nature | déclencheur |
|---|---|
| `appel_echoue` | quota, réseau, ou réponse vide |
| `json_illisible` | la réponse n'est pas un objet JSON |
| `champ_porte_invalide` | `porte` n'est pas un booléen |
| `categorie_hors_liste` | une catégorie inventée hors des six |
| `posture_assistant` | tournures du type « en tant qu'IA », « il est important de » |

Dans tous les cas, **l'agent garde son état de la veille et le run continue**.
Chaque incident part dans un événement `incident.v1`, et le total figure dans
le bilan : le taux de sortie de rôle devient un résultat du rapport.

Le détecteur de posture est lexical, donc faillible. C'est une limite à
assumer dans le rapport plutôt qu'à cacher.

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
| F1 F2 F3 RAG et corpus | étape 3, reste à faire |
| B3 E2 E5 protocole expérimental | étape 6, reste à faire |

## Suite

2. ~~Agents LLM, mémoire et échanges~~ fait
3. Corpus de Tessaline et RAG (F1, F2, F3)
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
    journal.py          écriture des événements et isolement des rejets
  tests/test_agents.py  vérifications hors ligne des agents
  runs/                 un fichier .jsonl par run
  corpus/               base de connaissances de Tessaline (étape 3)
  pont.py               Kafka vers WebSocket, et rejeu d'un run
  analyser.py           chiffres d'un run, pour le rapport
  docker-compose.yml    Kafka en un seul nœud
  godot/main.gd         la scène du campus
```
