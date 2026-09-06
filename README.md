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

Deux points d’entrée sont actifs : la commande applicative `495` et le lanceur
minimal de contrôles du dépôt. La commande sait invoquer Codex CLI sur un dépôt
Git propre, observer le candidat, exécuter les contrôles de l’application avec
`codex sandbox` et restituer un JSON validé. Le paquet sait aussi vérifier un
candidat déjà présent par rapport à une référence Git sans invoquer l’agent ni
exiger d’authentification ; aucune commande n’expose encore cette opération.

Cette intégration est couverte avec un double déterministe du client. Un parcours
réel complet avec Codex CLI `0.153.3` valide en plus la skill de projet, la
sortie structurée, l’environnement filtré, le refus réseau de l’agent et des
contrôles ainsi que leur sandbox sur macOS. La portée exacte des lectures et le
comportement Linux restent à vérifier.

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

La fonctionnalité en cours de validation est le
[premier incrément vertical](docs/parcours-utilisateur.md#premier-incrément-vertical) :
recevoir une demande visant un dépôt local, invoquer un véritable client
d’agent, identifier le candidat produit, exécuter les contrôles de l’application
cible et restituer le résultat. Elle ne met pas encore en œuvre les états et
gates du workflow complet. Son architecture découle de l’étude des harnais
d’agents de code et composants open source qui fournissent déjà le comportement
recherché.

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

### Exécuter un changement avec Codex

L’application cible doit être un dépôt Git propre avec un commit initial. Son
contrat JSON, suivi dans ce dépôt, déclare ses contrôles et l’environnement
transmis :

```json
{
  "version": 1,
  "environment": ["PATH", "LANG"],
  "checks": [
    {
      "name": "tests",
      "command": ["uv", "run", "pytest"],
      "timeout_seconds": 300,
      "filesystem": "workspace-write"
    }
  ]
}
```

Le client utilise un `CODEX_HOME` dédié, déjà authentifié et dépourvu de skills
personnelles. L’appel réel contacte le service Codex et peut consommer un quota.
Une demande enregistrée dans un fichier est exécutée ainsi :

```sh
uv run 495 \
  --repository /chemin/vers/application \
  --contract /chemin/vers/application/495.json \
  --codex-home /chemin/vers/codex-home-495 \
  --request-file /chemin/vers/demande.md
```

Le résultat JSON est écrit sur la sortie standard. Le code vaut `0` pour un
candidat vérifié, `1` pour un candidat dont un contrôle échoue, `2` pour une
exécution impossible et `3` pour un échec du client ou de sa réponse. 495 ne
crée aucun commit et ne conserve pas les événements ou rapports temporaires.
Codex peut toutefois créer ses propres caches et fichiers d’état dans le
`CODEX_HOME` dédié ; ce répertoire reste sous le contrôle de l’utilisateur.
`tools/run_change.py` reste disponible comme lanceur de compatibilité vers la
même interface.

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
L’[état de l’art](docs/etat-de-l-art.md) compare les clients d’agents, les
harnais et les runtimes d’exécution confinée examinés avant une conception.
Le [plan global d’évolution](docs/chantiers/plan-global.md) ordonne les
fonctionnalités à ajouter et leurs impacts sur l’architecture applicative.
Les documents de `docs/chantiers/` détaillent chaque incrément : l’[étude
ciblée](docs/chantiers/00-parcours-vertical/etat-de-l-art.md) et la
[conception](docs/chantiers/00-parcours-vertical/conception.md) du premier
parcours vertical, puis la
[configuration et la vérification réutilisables](docs/chantiers/01-configuration-verification/conception.md),
dont seule l’opération de vérification est implémentée à ce jour.
La [reprise de CodeServo](docs/reprise-de-codeservo.md) distingue les
comportements hérités des mécanismes qui redeviennent conditionnels.
L’[état de l’implémentation](docs/implementation.md) décrit précisément le
comportement disponible.
