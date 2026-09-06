# 495

495 explore une manière simple d’encadrer le développement logiciel assisté
par IA : rendre explicites le travail demandé, les contrôles exécutés et les
fichiers auxquels un résultat se rapporte.

Le nom vient de la constante de Kaprekar pour les nombres à trois chiffres. Il
évoque une progression guidée par des règles, sans promettre que la production
d’un agent est déterministe ni qu’elle converge automatiquement.

## État actuel

Le seul point d’entrée actif est un lanceur minimal de contrôles. Les anciens
modèles de workflow, gates, tentatives, persistance, adaptateurs et
orchestration ont été retirés : ils anticipaient des usages qui n’étaient
exposés par aucune interface utilisateur.

La prochaine fonctionnalité devra partir d’un parcours réel avant de définir
son modèle de domaine ou son architecture.

## Utilisation

Valider la configuration :

```sh
python3 tools/run_bootstrap.py validate
```

Exécuter les contrôles :

```sh
python3 tools/run_bootstrap.py run
```

Conserver exceptionnellement un rapport JSON :

```sh
python3 tools/run_bootstrap.py run --report
```

Sans `--report`, aucune archive d’exécution n’est créée. Les rapports demandés
sont écrits sous `.495/runs/` et ignorés par Git.

## Ce que fait le lanceur

La configuration [bootstrap/contract.json](bootstrap/contract.json) déclare :

- les motifs des fichiers contrôlés ;
- les commandes à exécuter, sous forme de liste d’arguments ;
- un timeout par commande ;
- le répertoire facultatif des rapports.

Le lanceur calcule le digest du contenu contrôlé, exécute chaque commande une
fois sans shell et vérifie que la configuration et les fichiers contrôlés ne
changent pas pendant l’exécution. Une commande est favorable lorsque son code
de sortie vaut zéro.

Il hérite de l’environnement courant et n’essaie pas de restreindre le réseau,
les secrets ou le système de fichiers. Un rapport ne prétend donc fournir
aucune garantie de sécurité.

## Règles du projet

Les [principes et contraintes](docs/principes-et-contraintes.md) expliquent
quelles règles sont obligatoires, conditionnelles, recommandées ou retirées.
L’[état de l’implémentation](docs/implementation.md) décrit précisément le
comportement disponible.
