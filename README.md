# 495

495 orchestre des agents d’IA pour faire progresser un changement logiciel du
besoin initial à son intégration. Il automatise le workflow autant que possible
tout en rendant explicites les exigences, les décisions, les contrôles exécutés
et les fichiers auxquels un résultat se rapporte.

Le nom vient de la constante de Kaprekar pour les nombres à trois chiffres. Il
évoque une progression guidée par des règles, sans promettre que la production
d’un agent est déterministe ni qu’elle converge automatiquement.

## État actuel

Le seul point d’entrée actif est un lanceur minimal de contrôles. Les anciennes
implémentations du domaine, des décisions, des tentatives, de la persistance,
des adaptateurs et de l’orchestration ont été retirées : elles anticipaient des
usages qui n’étaient exposés par aucune interface utilisateur.

Le workflow `clarifying` → `specifying` → `designing` → `implementing` →
`verifying` → `accepted` → `integrating` → `integrated` reste la colonne
vertébrale du produit. Il est défini par les
[parcours utilisateur](docs/parcours-utilisateur.md), mais aucune
implémentation courante ne l’applique encore.

La prochaine fonctionnalité partira des
[parcours utilisateur](docs/parcours-utilisateur.md) avant de définir son
modèle de domaine ou son architecture.

## Utilisation

Le projet utilise [uv](https://docs.astral.sh/uv/) pour sélectionner Python,
créer l’environnement local et verrouiller les dépendances. Le fichier
`pyproject.toml` déclare le projet et `uv.lock` décrit son environnement résolu.

Valider la configuration :

```sh
uv run python tools/run_bootstrap.py validate
```

Exécuter les contrôles :

```sh
uv run python tools/run_bootstrap.py run
```

Conserver exceptionnellement un rapport JSON :

```sh
uv run python tools/run_bootstrap.py run --report
```

`uv sync` permet de préparer explicitement l’environnement. `uv run` le fait
automatiquement lorsque cela est nécessaire.

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
Les [parcours utilisateur](docs/parcours-utilisateur.md) définissent les usages
visés et les responsabilités laissées aux outils existants.
L’[état de l’implémentation](docs/implementation.md) décrit précisément le
comportement disponible.
