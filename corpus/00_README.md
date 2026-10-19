# Corpus de Tessaline

Base de connaissances fictive du campus, écrite pour ce projet (exigence F1).
Chaque fichier porte un en-tête qui dit **qui peut le lire** et **à partir de
quand**, ce qui permet de respecter la cohérence temporelle (exigence C6) : un
agent ne peut pas citer un article paru après le moment simulé où il décide.

En-tête de chaque document :

    --- id: identifiant court
    --- titre: titre lisible
    --- source: d'où ça vient
    --- jour: jour simulé de parution (0 ou négatif = existait déjà avant le run)
    --- groupes: tous, ou la liste des groupes qui y ont accès

Rien ici n'est réel. Tessaline, La Criée, les associations et les modes
anciennes sont inventées pour les besoins de la simulation.
