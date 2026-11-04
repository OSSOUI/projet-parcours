# Évaluation de constats sur des journaux de simulation

Merci d'avoir accepté cette évaluation. Elle demande environ deux heures.

## Ce qu'on vous demande

Un programme a lu quatre journaux de simulation (un campus de 20 étudiants, pendant 25 jours, qui adoptent ou non un ruban et lui donnent un sens). Il a écrit des **constats** : des phrases qui affirment des faits sur ce qui s'est passé.

Pour chacun des 133 constats de `grille.csv`, dites s'il est vrai **au vu des événements du journal**. Vous ne jugez ni le style ni l'intérêt de la phrase, seulement son exactitude.

## Les trois verdicts possibles (colonne `verdict`)

- `vrai` : tout ce que la phrase affirme (nombres, noms, sens, citations, moments) est confirmé par les événements.
- `faux` : au moins un élément est contredit par les événements.
- `insuffisamment_etaye` : les événements fournis ne permettent ni de confirmer ni de contredire un élément de la phrase, ou la phrase est ambiguë.

**Pour `faux` et `insuffisamment_etaye`, la colonne `justification` est obligatoire** : quel élément, et quel événement le contredit ou manque. Pour `vrai`, elle est facultative.

## Les pièces

- `grille.csv` : la grille à remplir (séparateur point-virgule ; s'ouvre dans Excel ou LibreOffice). Ne modifiez que les colonnes `verdict` et `justification`.
- `evenements.md` : pour chaque constat, les événements qu'il cite, en brut, et pour les constats sur des étudiants, leur décision précédente (marquée « contexte, non cité »).
- `journaux/` : les quatre journaux complets (un événement JSON par ligne), si vous voulez vérifier autre chose. Un identifiant `run#n` désigne la ligne n (comptée à partir de 0) du fichier `run.jsonl`.

## Comment lire les événements

- `indicateurs.v1` est un relevé quotidien :
  - `adoption` : la part des 20 étudiants qui portent le ruban ;
  - `porteurs` : leur nombre ;
  - `sens` : le nombre d'étudiants qui donnent chaque sens au ruban (agents « à règles » compris).
- `decision.v1` est la décision d'un étudiant :
  - `porte` : s'il porte le ruban ;
  - `categorie` : le sens qu'il lui donne ;
  - `valide` : faux si la réponse était inexploitable (l'étudiant garde alors son état précédent).
- `publication.v1` est un message publié sur le réseau du campus.
- **La fenêtre d'un constat** est la période qu'il couvre. Le relevé de fin de fenêtre en fait partie.

## Règles

- **Travaillez seul,** sans échanger avec quelqu'un qui a participé au développement du programme.
- **Ne cherchez pas d'autres verdicts :** vous n'en avez pas reçu, et c'est voulu.
- **En cas de doute, préférez `insuffisamment_etaye` et dites pourquoi.**
- Renvoyez `grille.csv` remplie, avec votre nom et la date dans le nom du fichier.
