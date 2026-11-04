# Série de référence ÉPHÉMÈRE (gelée le 4 novembre 2026)

Cette série sert de point de comparaison à toutes les expériences suivantes. Elle n'est plus modifiée. **H6 n'est pas confirmée** : le critère fixé avant la mesure demandait 4 runs significatifs sur 5, il y en a 3.

## Configuration

| Paramètre | Valeur |
|---|---|
| Plan | `python3 experience.py --plan reference` (configuration `llm_reference`) |
| Options de simuler.py | `--mode synchrone --ombres sans_discours sans_social` |
| Runs | 5, graines 100 à 104, 20 agents, 25 jours |
| Population | 10 agents à règles, 10 à 13 agents LLM selon la graine (qwen2.5:3b et qwen2.5:7b) |
| Modèles | qwen2.5:7b `845dbda0ea48`, qwen2.5:3b `357c53fb659c`, tous deux en Q4_K_M, via Ollama |
| Température | 0,9, avec une graine LLM dérivée de l'agent et de l'instant |
| Prompt | empreinte `ceb1fc47a4f9` (SYSTEME + CONSIGNE) |
| Corpus | `corpus/`, statique, BM25, 3 passages, filtres de date et de groupe |
| Conversations | aucune (`--conversation 0`) |
| Kafka | inactif (C1 n'est pas couvert par cette série) |
| Contrat | 1.8.0 |

## Hypothèse écrite avant la mesure

> H6 : si le sens partagé vient des interactions, l'accord réel dépasse celui de l'ombre `sans_social` (p < 0,05) dans au moins 4 runs sur 5. L'écart avec l'ombre `sans_discours` dit la part du discours (H1). Au vu de la relecture du 3 novembre (0 run sur 6 émergent en six sens avec le seuil à persistance), l'absence d'écart est plausible et sera écrite telle quelle.

Ce texte est celui de `experience.py`, dans la configuration `llm_reference`.

## Méthode

- **Ombres (témoin asservi).** Chaque décision LLM est reposée au même agent, au même instant, dans le même état, avec les mêmes documents et la même clé de graine.
  - `sans_discours` retire le fil public et les échanges reçus.
  - `sans_social` retire aussi l'adoption vue (groupe et campus).
  - Une ombre n'est jamais appliquée au monde. Elle est écrite en `ombre.v1`, avec la décision réelle.
- **Accord exprimé.** C'est la part du sens dominant parmi les agents LLM qui expriment un sens. Il se lit de deux façons : en six sens, ou regroupé en lectures de foule.
- **Seuil à persistance.**
  - ΔA = minimum de la meilleure fenêtre de 3 relevés, moins A0.
  - A0 vient du point zéro, un prompt sans adoption (`resultats/sens_a_priori_g100_complet_t5.json`).
  - Le seuil est le 95e centile de ΔA sous un modèle nul de Markov. Il est tiré à la persistance mesurée dans le run, sur 1 000 tirages.
- **Écart réel moins ombre.** C'est l'écart moyen d'accord entre la série réelle et la série de l'ombre. La p-valeur est unilatérale : elle est obtenue en permutant les paires (1 000 permutations, graine 0).
- **Incidents.** Une décision en incident est une valeur manquante, et non un sens.

## Résultats (six sens)

| Graine | Persistance | ΔA / seuil | Écart réel − `sans_social` | p | Écart réel − `sans_discours` | p |
|---|---|---|---|---|---|---|
| 100 | 78 % | +27 / 28 pts | +5 pts | 0,014 | +7 pts | 0,002 |
| 101 | 76 % | +22 / 26 pts | +1 pt | 0,415 | +3 pts | 0,065 |
| 102 | 76 % | +21 / 24 pts | +11 pts | 0,001 | +12 pts | 0,001 |
| 103 | 74 % | +14 / 26 pts | +2 pts | 0,216 | +3 pts | 0,082 |
| 104 | 79 % | +12 / 24 pts | +7 pts | 0,001 | +10 pts | 0,001 |

- **Émergence au seuil à persistance :** 0 run sur 5 en six sens. En lecture regroupée, 1 run sur 5 (graine 103 : +25 points pour un seuil de 22).
- **Ombre `sans_social` en lecture regroupée :** p < 0,05 pour les graines 100, 102 et 104, soit encore 3 sur 5.
- **Coût :** 3 929 appels LLM et 66 incidents, environ 46 minutes par run.
- **Cohérence temporelle (C6) :** 0 violation sur 1 310 contextes contrôlés.

## Ce que la série permet de dire, et ce qu'elle ne permet pas

- L'écart entre la décision réelle et l'ombre sans social est positif dans les 5 runs, et faible : de +1 à +11 points.
- H6 n'est pas confirmée selon le critère fixé. Les 3 runs significatifs ne valent pas confirmation générale.
- Aucune émergence forte n'est observée. Les déclarations d'émergence antérieures au 3 novembre sont conservées comme historique d'une correction de méthode, pas comme résultats.
- L'ombre `sans_discours` garde l'adoption vue, et donne des écarts du même ordre que `sans_social`. Ajouter l'adoption vue ne change donc pas l'accord de façon décelable. Ce qui existe comme effet semble passer par les messages. C'est une indication en faveur de H1, pas une démonstration causale.
- **Limite.** Le test par permutation échange les paires une à une. Il ne tient pas compte de la corrélation entre les décisions successives d'un même agent. Les p-valeurs sont donc probablement optimistes. Une comparaison entre conditions doit prendre le run comme unité.
- **Limite.** Avec 5 graines, un test apparié par run ne peut pas descendre sous p = 1/32 (unilatéral). Il faut un effet de même signe dans les 5 runs.
- **Limite.** Malgré la graine, Ollama n'est pas déterministe (X0 : 92 % de décisions identiques). La série se reproduit par rejeu des fichiers, pas en relançant le modèle.

## Reproduire l'analyse sans appel LLM

```
python3 emergence.py --json /tmp/verif.json runs/exp_reference_llm_reference_0[1-5].jsonl
cmp resultats/emergence_reference.json /tmp/verif.json
```

Vérifié le 4 novembre 2026 : sortie identique à l'octet près.

## Empreintes SHA-256 des fichiers gelés

```
0117eda06ebae532f985d5d08fcfeaabe9a86be1eb7701be07e3465f30d31b82  resultats/emergence_reference.json
7111ca4dcf02465fcfad806c9d6ea9244c557f460dd34f31ecd372bb1f4cab37  runs/exp_reference_llm_reference_01.jsonl
e87f038abe5293c54754a0b4a2eb4cd3eeb71980ca1f8c8d7dc2af88ea950368  runs/exp_reference_llm_reference_02.jsonl
9d22f907b08ba4020ee265e149823eb788f23d3a1726cb5dc9b59bb7befab182  runs/exp_reference_llm_reference_03.jsonl
fa1ce36a93120e701412eae03e2e6cf2792d88cb8854b2c5d2159fbf7a691b6f  runs/exp_reference_llm_reference_04.jsonl
4474c6042250028ca658f37e59fb6e2a82edaa3beb2cf3db3b5d2c9b3b50a6f3  runs/exp_reference_llm_reference_05.jsonl
```

Vérification : `shasum -a 256 -c` sur ce bloc. Ces fichiers ne sont pas encore commités : seul un commit ou une étiquette Git les protège vraiment.
