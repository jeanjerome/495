# ADR-0004 — Dépendances entre les modules du noyau

Statut : accepté pour `domain`. Le graphe complet reste ouvert.

## Contexte

REQ-20 interdisait au paquet `domain` d'importer un autre paquet du projet, sans que la conception l'énonce : une dérivation présentée comme une exigence.

Précision factuelle : `SRC-DESIGN §5.1` **donne bien** la liste des six modules et leurs responsabilités — `domain`, `validation`, `policy`, `application`, `ports`, `infrastructure` — chacun avec son interdiction propre. Ce qui manque n'est pas la liste, mais le sens des arêtes entre ces modules.

## Décision

`domain` ne dépend d'aucun des cinq autres modules.

Le sens des dépendances entre les cinq autres n'est pas fixé ici. Le lot A ne l'exige pas, et le fixer sans les lots B à D reviendrait à décider d'une architecture avant d'en connaître les contraintes.

## Conséquences

- REQ-20 cesse d'être une dérivation : elle cite cette décision.
- L'interdiction porte sur la direction des dépendances. Elle est distincte de l'interdiction d'entrées/sorties (REQ-18, §5.1) et de celle des bibliothèques tierces (REQ-19, décision Q-01).
- Une décision ultérieure fixera le graphe complet lorsque les lots B à D seront cadrés.
