# Validation de la chaîne Kafka (C1), 4 novembre 2026

**C1 est validé techniquement sur cette machine.** Sur 4 runs de validation, aucun événement n'a été perdu, déformé ou reçu dans le désordre. Les doublons créés par un consommateur interrompu sont tous reconnus. Lors d'une panne du broker, le fichier du run reste complet et chaque événement manquant dans Kafka est annoncé par le producteur. Pour l'instant, Kafka ne rattrape pas de lui-même les événements perdus pendant une panne : c'est la limite principale.

Les runs `c1_*` servent à la validation seule. Ils ne font pas partie de la série de référence (`exp_reference_*`).

## Environnement

| Élément | Valeur |
|---|---|
| Broker | `apache/kafka:3.8.0`, un nœud en mode KRaft, `localhost:9092`, topic `ephemere.evenements` à 1 partition |
| Client | `kafka-python` 2.3.3 dans `.venv` (Python 3.15.0), déjà présent : rien n'a été installé |
| Producteur | `acks="all"`, 5 renvois, 1 requête en vol par connexion (ordre garanti), rappel de succès ou d'échec sur chaque envoi |
| Clé | le nom du run : tous ses événements vont sur la même partition, dans l'ordre |
| Identifiant | `seq` (contrat 1.9.0) : rang de l'événement conforme dans le run, égal au numéro de ligne du fichier |

Le conteneur `ephemere-kafka` existait déjà : il a été créé le 14 octobre depuis `~/Downloads/ephemere-mvp`, avec la même image et le même port. Il a été redémarré tel quel, sans être recréé.

## Méthode

Commande : `verifier_kafka.py`. Un consommateur de groupe dédié se place en fin de topic, puis lance `simuler.py --kafka` et reçoit le run en direct. Le rapport compare trois sources :

- le fichier du run ;
- ce que le topic a livré, avec offsets et heure de réception ;
- le bilan du producteur (`runs/<run>.kafka.json`).

L'état du campus est reconstruit comme le fait le pont, une fois depuis Kafka (doublons compris), une fois depuis le fichier. Les deux sont ensuite comparés.

## Résultats

| Run | Contenu | Événements | Reçus (uniques) | Pertes | Doublons reconnus | Désordres | Contenu différent | État Kafka = fichier | Latence médiane / p95 |
|---|---|---|---|---|---|---|---|---|---|
| `c1_regles_01` | 20 agents à règles, 25 jours | 493 | 493 (493) | 0 | 0 | 0 | 0 | oui | 5 / 8 ms |
| `c1_regles_coupure` | idem, consommateur arrêté après 320 messages puis relancé | 493 | 513 (493) | 0 | 20 sur 20 | 0 | 0 | oui | 7 / 480 ms |
| `c1_llm_01` | LLM synchrone, 5 jours, conversations, coupure après 60 messages | 217 | 227 (217) | 0 | 10 sur 10 | 0 | 0 | oui | 21 / 394 ms |
| `c1_panne` | LLM synchrone, 4 jours, broker arrêté au bout de 45 s | 188 | 44 (44) | 144, toutes annoncées | 0 | 0 | 0 | non (attendu) | 20 / 23 ms |

- **Doublons.** Le consommateur commite tous les 50 messages. Interrompu, il fait relivrer ce qui n'était pas commité : 320 − 300 = 20, puis 60 − 50 = 10. Le pont les écarte grâce à `(run, seq)`. Sans cette déduplication, ajoutée le même jour, il les aurait appliqués deux fois.
- **Latence.** Le p95 élevé des runs avec coupure mesure le temps que met le second consommateur à rejoindre le groupe, pour les messages produits pendant la coupure. Sans coupure : 5 à 8 ms pour les règles, 20 à 23 ms en LLM.
- **Panne.** Le moteur n'est pas bloqué : 150 s pour 4 jours, contre 161 s pour 5 jours sans panne. Le fichier est complet, avec 188 événements et le bilan. Les 144 événements absents du topic sont comptés par le producteur comme restés sans réponse à la fermeture, donc 0 perte silencieuse. Ils ne figurent pas dans `perdus` : le client n'a pas signalé d'échec avant l'expiration du délai de fermeture.
- **Rejeu.** Les 4 états reconstruits depuis le fichier sont ceux que `pont.py --rejeu` affiche, sans Kafka ni LLM. Dans les 3 runs sans panne, ils sont égaux aux états reconstruits depuis Kafka.

## Limites

- Après une panne, Kafka reste incomplet : seul le fichier fait foi. On peut ajouter une republication des `seq` manquants depuis le fichier, rendue sans risque par la déduplication. Elle n'est pas faite.
- Les mesures portent sur un seul nœud et une seule partition, sur la machine locale. Ni la charge, ni plusieurs consommateurs en parallèle n'ont été testés.
- Une heure d'émission et de réception sur la même machine donne une latence fiable ici. Ce ne serait plus vrai entre deux machines.
- La séquence `seq` des anciens runs est déduite du numéro de ligne. Cette déduction est vérifiée fichier par fichier par `journal.lire()`, et les 120 journaux de `runs/` passent la vérification.

## Rejouer la validation

```
docker start ephemere-kafka            # ou : docker compose up -d
.venv/bin/python verifier_kafka.py --run c1_regles_01 -- --tout-regles --agents 20 --jours 25 --graine 100
.venv/bin/python verifier_kafka.py --run c1_regles_coupure --coupure 320 -- --tout-regles --agents 20 --jours 25 --graine 100
.venv/bin/python verifier_kafka.py --run c1_llm_01 --coupure 60 -- --agents 20 --jours 5 --graine 100 --mode synchrone --conversation 2
```

Rapports : `resultats/c1_*.json`. Runs : `runs/c1_*.jsonl`.
