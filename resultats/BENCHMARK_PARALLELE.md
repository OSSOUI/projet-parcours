# Benchmark de la parallélisation (chantier 2) : critères non atteints, pas d'intégration

4 et 5 novembre 2026. Script séparé : `benchmark_parallele.py`. Données : `resultats/benchmark_parallele/`.

**Ce qui n'a pas changé :**
- aucune modification du moteur ni du simulateur ;
- l'expérience mémoire est arrêtée, son gel est intact ;
- **Ollama n'a jamais été reconfiguré** : la série avec `OLLAMA_NUM_PARALLEL=4` n'a pas été lancée. Son état final est identique à l'état initial relevé (`etat_ollama_initial.json`) : application 0.40.12, aucune variable `OLLAMA_*`, mêmes empreintes de modèles.

## Conclusion

**Les deux critères préenregistrés ne sont pas atteints.** Conformément au garde-fou 7, **la parallélisation n'est pas intégrée par défaut.**

- **Accélération d'au moins 1,5 fois : non établie.**
  - Ollama charge chaque modèle avec **un seul emplacement de calcul** (`n_seq_max = 1`, relevé dans son journal). Il traite donc les requêtes une par une : N = 2 et N = 4 ne font que les mettre en file d'attente.
  - La seule comparaison propre, faite sur des séries contiguës, donne au mieux environ **1,3 fois** : N = 2 en 367 s, contre N = 1 répété en 477 s.
- **Au moins 99 % de décisions identiques à N = 1 : non atteint** au sens préenregistré, avec 96,3 % par rapport à la première série N = 1.
  - **Mais cet écart ne vient pas du parallélisme** : il touche aussi la série N = 1 répétée (voir la partie 2).

## 1. Mesures

190 décisions par série : les prompts exacts reconstruits des 10 premiers jours de A100 et A101, soit 20 pas simulés. Mêmes graines, mêmes modèles, température 0,9. Un client par fil d'exécution.

| Série | N | Fin | Durée totale | Latence médiane / p95 | Jetons générés | Incidents | Décisions identiques à la série 1 | Réponses brutes identiques |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 04/11 12:37 | 682 s | 3,04 / 6,03 s | 16 776 | 12 | — | — |
| 2 | 2 | 12:43 | 367 s | 3,75 / 5,74 s | 16 905 | 13 | 96,3 % | 80,0 % |
| 3 | 4 | 12:49 | 372 s | 6,61 / 11,04 s | 16 905 | 13 | 96,3 % | 80,0 % |
| 4 | 1 | 14:23 | 477 s | 1,97 / 3,82 s | 16 905 | 13 | 96,3 % | 80,0 % |
| 5 | 2 | 21:09 | 1 410 s | 12,3 / 30,5 s | 16 905 | 13 | 96,3 % | 80,0 % |
| 6 | 4 | 05/11 07:42 | 1 192 s | 16,5 / 46,8 s | 16 905 | 13 | 96,3 % | 80,0 % |

**La série 1 reproduit la passe A′ du 4 novembre au matin :** 100 % des décisions et 99,5 % des réponses brutes. **Les séries 2 à 6 sont identiques entre elles** (190 sur 190, décisions comme réponses brutes), qu'elles aient tourné avec N = 1, 2 ou 4.

## 2. Ce que les mesures établissent, et ce qu'elles n'établissent pas

- **N ne change pas les réponses.** Avec un serveur qui traite les requêtes une par une, les séries N = 1, 2 et 4 (2 à 6) donnent exactement les mêmes sorties.
- **En revanche, les sorties ont changé une fois, entre la série 1 et la série 2, et ont été stables ensuite :**
  - 7 décisions sur 190 et 38 réponses brutes différentes ;
  - cela touche aussi la série 4, pourtant séquentielle ;
  - aucun rechargement des modèles n'apparaît dans le journal d'Ollama entre les deux. Les seuls chargements visibles sont à 12:06 et à 12:25, au début du benchmark.
  - **Cause non élucidée.** Hypothèses plausibles, non testées : un état interne du serveur après la première série (cache du début du prompt, choix des noyaux de calcul après le premier passage). Un test dédié serait nécessaire : relancer Ollama, puis enchaîner deux séries N = 1.
- **Conséquence pour la reproductibilité.** Le constat « à prompt et graine égaux, Qwen redonne la même décision » (`EVALUATION_HYBRIDE.md`, 100 % sur 474 décisions) est vrai **pour un état donné du serveur**. Après le changement observé ici, 96,3 % des décisions restent identiques. C'est cohérent avec X0 (92 % sur des runs complets, où les écarts se propagent). Cela ne touche pas l'expérience mémoire, qui compare des paires A/E par graine et traite déjà ce bruit comme tel. Mais il ne faut pas présenter le modèle comme strictement déterministe.
- **Durées.** La machine s'est mise en veille pendant le benchmark :
  - environ 1 h 30 entre les séries 3 et 4 ;
  - puis plusieurs heures avant et pendant les séries 5 et 6 ;
  - `caffeinate -i` ne l'a pas empêché, probablement parce que l'écran a été rabattu ;
  - de plus, une mise à jour logicielle de macOS tournait au moment du relevé.

  **Les durées des séries 5 et 6 ne sont pas exploitables** : latences de 12 à 47 s, une expiration réseau. Seules les séries 1 à 4 se comparent, et la variabilité entre les deux N = 1 (682 s contre 477 s) est déjà de l'ordre de l'effet cherché.

## 3. Recommandations

1. **Pas de parallélisation dans les futures séries, en l'état.** Côté client, elle n'apporte pas d'accélération démontrée, car le serveur traite déjà les requêtes une par une.
2. **Si l'équipe veut retenter :** le seul levier réel est côté serveur (`OLLAMA_NUM_PARALLEL` supérieur à 1, donc plusieurs emplacements de calcul). Cela change la configuration d'Ollama, donc potentiellement les sorties. Il faudrait :
   - un nouveau benchmark, sur une machine qui ne se met pas en veille ;
   - au moins 3 répétitions par condition ;
   - le test du changement d'état (redémarrage, puis deux séries N = 1) ;
   - et, avant tout, une décision explicite, puisqu'Ollama doit être reconfiguré puis restauré.

   Cela ne concernerait jamais l'expérience mémoire en cours.
3. **Avant de reprendre l'expérience mémoire (environ 14 h) :**
   - lancer `caffeinate -dimsu`, et laisser l'écran ouvert, sur secteur ;
   - vérifier qu'aucune mise à jour logicielle n'est en cours.

   Le lanceur de l'expérience contrôle les runs, mais une veille allongerait la durée et fausserait les mesures de temps. Elle ne changerait pas les décisions.
