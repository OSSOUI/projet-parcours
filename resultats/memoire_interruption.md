# Expérience mémoire : arrêt entre deux runs (4 novembre 2026, 07:45)

**Arrêt demandé** pour libérer Ollama pendant l'intégration (Kafka, Godot, narratrice) dans une copie séparée.

**Comment.** Un garde a attendu la fin naturelle du simulateur en cours (A105), puis a arrêté le lanceur (`experience_memoire.py --lancer`) avant qu'il ne démarre le run suivant. Aucun processus n'a été tué en cours de run.

| Run | État |
|---|---|
| A100 à A104 | Gelés (référence), inchangés : empreintes vérifiées par `verifier_gel()` |
| A105 (`exp_memoire_A_g105`) | **Terminé et recevable** (06:59 à 07:45, 786 appels, 13 incidents) |
| E105, E100, A106, … E104 | **Pas commencés** (14 runs) |

**Ce qui n'a pas été touché :** `PROTOCOLE_MEMOIRE.md`, `memoire_gel.json`, `experience_memoire.py` et les runs de référence. Le gel est vérifié intact après l'arrêt.

**Écart technique, sans effet sur les données.** Le lanceur a été arrêté pendant le contrôle de fin d'A105, avant l'écriture de `resultats/memoire_lancement.json`, qui n'existe donc pas encore. Les contrôles d'A105 se refont à l'identique avec `experience_memoire.py --controler` : A105 est recevable. Le fichier sera créé à la reprise, mais sans ligne pour A105.

**Reprise, sans rien changer au protocole :** `caffeinate -i python3 -u experience_memoire.py --lancer`, depuis `~/projet-parcours` et quand Ollama est libre. Le lanceur saute A105 (déjà là, recevable) et reprend à E105, dans l'ordre fixé.

**Écart au protocole à signaler dans le rapport :** une interruption de quelques heures entre A105 et E105, demandée pour l'intégration. Le protocole n'impose pas de continuité. Les poids des modèles sont recontrôlés avant chaque run.
