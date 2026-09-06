# 495

495 est un harnais d’agents de code qui fait progresser un changement logiciel
du besoin initial à son intégration. Ses contrôles en amont (*feedforward*)
déterminent ce que l’agent tente, avec quel contexte, quels outils et quelles
permissions. Ses contrôles en retour (*feedback*) observent le candidat produit
et fournissent à l’agent un écart précis à corriger.

Le produit vise ainsi à automatiser le workflow tout en rendant explicites les
exigences, les décisions, les contrôles exécutés et les fichiers auxquels un
résultat se rapporte. Le contexte de chaque agent est limité aux informations
utiles à son intervention, son exécution est confinée par une sandbox et le
résultat remis à l’orchestrateur possède une forme JSON validée par JSON
Schema.

Le nom vient de la constante de Kaprekar pour les nombres à trois chiffres. Il
évoque une progression guidée par des règles, sans promettre que la production
d’un agent est déterministe ni qu’elle converge automatiquement.

## État actuel

Le seul point d’entrée actif est un lanceur minimal de contrôles. Les anciennes
implémentations du domaine, des décisions, des tentatives, de la persistance,
des adaptateurs et de l’orchestration ont été retirées : elles anticipaient des
usages qui n’étaient exposés par aucune interface utilisateur.

Le harnais, l’intégration d’agents, la construction de leur contexte, leur
confinement et leur contrat de réponse ne sont donc pas encore implémentés. Ils
décrivent la cible fonctionnelle, pas les garanties du lanceur actuel.

Le workflow `clarifying` → `specifying` → `designing` → `implementing` →
`verifying` → `accepted` → `integrating` → `integrated` reste la colonne
vertébrale du produit. Il est défini par les
[parcours utilisateur](docs/parcours-utilisateur.md), mais aucune
implémentation courante ne l’applique encore.

495 reprend la boucle `implementing`–`verifying` expérimentée dans
[CodeServo](https://github.com/jeanjerome/codeservo), en conservant ses
comportements utiles, en retirant sa complexité expérimentale par défaut et en
l’étendant au cycle complet. La
[stratégie de reprise](docs/reprise-de-codeservo.md) fixe cette frontière.

Les applications confiées à 495 peuvent employer n’importe quels langages,
frameworks et chaînes d’outils. Elles conservent leurs propres conventions et
leur architecture ; 495 orchestre les agents et les commandes qu’elles exposent
sans leur imposer les choix techniques de son implémentation interne.

La prochaine fonctionnalité est le
[premier incrément vertical](docs/parcours-utilisateur.md#premier-incrément-vertical) :
recevoir une demande visant un dépôt local, invoquer un véritable client
d’agent, identifier le candidat produit, exécuter les contrôles de l’application
cible et restituer le résultat. Elle ne met pas encore en œuvre les états et
gates du workflow complet. Avant de choisir son architecture ou un composant,
l’implémentation de 495 examine les harnais d’agents de code et composants open
source qui fournissent déjà le comportement recherché.

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
La [reprise de CodeServo](docs/reprise-de-codeservo.md) distingue les
comportements hérités des mécanismes qui redeviennent conditionnels.
L’[état de l’implémentation](docs/implementation.md) décrit précisément le
comportement disponible.
