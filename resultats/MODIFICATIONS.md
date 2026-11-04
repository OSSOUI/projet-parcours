# Modifications non commitées, rangées par évolution (4 novembre 2026)

Rien n'est commité. Chaque évolution peut faire l'objet d'un commit séparé, dans l'ordre des dépendances : 1, puis 2, puis 3 et 4, qui sont indépendantes l'une de l'autre.

- Les fichiers nouveaux appartiennent chacun à une seule évolution.
- Cinq fichiers existants sont partagés entre plusieurs évolutions. Le tableau du bas indique quelle partie va avec laquelle, pour un `git add -p`.

## 0. Modifications antérieures de l'utilisatrice (non touchées)

`README.md`, `godot/campus3d.gd`, `.vscode/`, `Mondes-Vivants_Projet-5A-IABD.html`.

Leurs empreintes ont été vérifiées identiques à l'instantané du 4 novembre après chaque étape.

## 1. Base expérimentale : ombres, indicateur corrigé, référence

- **Fichiers propres :**
  - `emergence.py`
  - `tests/test_ombres.py`
  - `resultats/REFERENCE.md`
  - `resultats/emergence_reference.json`
  - `ephemere/indicateurs.py` : `persistance`, `modele_nul_markov`, `ecart_ombres`
  - `experience.py` : configuration `llm_reference`, plan `reference`
  - les runs `runs/exp_reference_*` et `runs/exp_x0_*`
- **Parties de fichiers partagés :**
  - `agents_llm.py` : `MASQUES` (deux masques), `INCONNU_*`, `_consigne(masque)`, `ombre()`
  - `contrat.py` : `ombre.v1`, `MASQUES_OMBRE`, version 1.8.0
  - `llm.py` : `empreintes()`
  - `simuler.py` : `--ombres`, `_decider` (ombres), `enregistrer` (`ombre.v1`), en-tête (`ombres`, `temperature`, `empreinte_prompt`, `modeles`), `appels_ombres`

## 2. Identifiants d'événements et Kafka (C1)

- **Fichiers propres :**
  - `ephemere/bus.py` (confirmations, pertes, ordre)
  - `ephemere/campus.py` (`deja_vu`, doublons et trous)
  - `pont.py` (doublons écartés)
  - `verifier_kafka.py`
  - `tests/test_identifiants.py`
  - `resultats/C1_KAFKA.md`
  - `resultats/c1_*.json`
- **Parties de fichiers partagés :**
  - `journal.py` : `seq`, `lire()`, `identifiant()`, `JournalIllisible`, bilan `.kafka.json`
  - `contrat.py` : `OPTIONNELS` (`seq`), contrôle de `seq`, version 1.9.0

## 3. Narratrice externe (dépend de 2 pour `seq`)

- **Fichiers propres :**
  - `narratrice.py`
  - `ephemere/narration.py`
  - `verifier_narrations.py`
  - `tests/test_narratrice.py`
  - `resultats/NARRATRICE.md`
  - `resultats/narratrice_validation*.json`
  - `resultats/audit_v3_*`, `resultats/audit_v4_*`
  - `resultats/emergence_complet_llm_synchrone*.json`
  - `evaluation_humaine.py` et `resultats/evaluation_humaine/` : dossier pour l'évaluateur, et la clé à ne pas transmettre
  - dans `narratrice.py` : affichage en trois canaux (`recit`, `--hypotheses`), sans effet sur les fichiers de narration
- **Parties de fichiers partagés :**
  - `contrat.py` : `SCHEMAS_OBSERVATEUR`, `TYPES_AFFIRMATION`, `STATUTS_NARRATION`, `narratrice.v1`, `narration.v1` et leurs contrôles, version 1.10.0
  - `journal.py` : refus des schémas d'observateur dans `ecrire()`
  - `llm.py` : paramètre `max_tokens` de `json()`
- **Le simulateur et le code des agents ne contiennent rien de cette évolution.** C'est vérifié par `tests/test_narratrice.py`.

## 4. Mémoire individuelle (dépend de 1 pour les ombres)

- **Fichiers propres :**
  - `audit_memoire.py`
  - `tests/test_memoire.py`
  - `resultats/MEMOIRE.md`
  - `resultats/audit_memoire_reference.json`
  - `verifier_comparabilite.py` et `resultats/comparabilite_reference.json`
  - `experience_memoire.py`, `resultats/PROTOCOLE_MEMOIRE.md` et `resultats/memoire_gel.json`, gelés avant le lancement
  - `resultats/memoire_lancement.json` et `resultats/memoire_experience.json`, écrits par l'expérience
  - les runs `runs/exp_memoire_A_g105` à `g109` et `runs/exp_memoire_E_g100` à `g109`
- **Parties de fichiers partagés :**
  - `agents_llm.py` : masque `sans_souvenirs`, `MASQUES_SOCIAUX`, `souvenirs(…, avec_sens)`, paramètre `memoire_sens` de `DecideurLLM`, `sens_affiche` dans la perception
  - `contrat.py` : `sans_souvenirs` dans `MASQUES_OMBRE`
  - `simuler.py` : `categorie` dans le souvenir de décision (`appliquer`), `--memoire-sens`, `memoire_sens` passé à `DecideurLLM` et écrit dans l'en-tête
- **La narratrice ne contient rien de cette évolution.**

## Fichiers partagés

| Fichier | 1. Base | 2. Identifiants et Kafka | 3. Narratrice | 4. Mémoire |
|---|---|---|---|---|
| `ephemere/contrat.py` | `ombre.v1`, 1.8.0 | `seq`, 1.9.0 | schémas d'observateur, 1.10.0 | `sans_souvenirs` |
| `ephemere/journal.py` | | `seq`, `lire`, `identifiant`, `.kafka.json` | refus des observateurs | |
| `ephemere/llm.py` | `empreintes()` | | `max_tokens` | |
| `ephemere/agents_llm.py` | masques sociaux, `ombre()` | | | `sans_souvenirs`, `memoire_sens` |
| `simuler.py` | `--ombres`, en-tête | | | `--memoire-sens`, `categorie` |

Les numéros de version du contrat se suivent : 1.8.0, puis 1.9.0, puis 1.10.0. Commiter dans l'ordre 1, 2, 3, 4 garde un contrat cohérent à chaque commit.

## Runs créés, exclus par le `.gitignore`

`runs/c1_*`, `runs/n4_*`, `runs/n5_*`, `runs/n6_*`, `runs/n7_*` et leurs `.narration.jsonl`, ainsi que `runs/c1_llm_01.narration.jsonl`.

Le `.gitignore` ne garde que les runs `exp_*` et `demo_*`. Les rapports qui s'appuient sur ces runs sont dans `resultats/`.
