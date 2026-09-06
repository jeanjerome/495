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
minimal de contrôles du dépôt. `495 change` sait invoquer Codex CLI sur un dépôt
Git propre, observer le candidat, exécuter les contrôles de l’application avec
`codex sandbox` et restituer un JSON validé. `495 verify` vérifie un candidat
déjà présent par rapport à une référence Git sans invoquer l’agent ni exiger
d’authentification. `495 configure` fait proposer un contrat par Codex en
lecture seule, valide un contrat présent et n’enregistre une proposition que
sur action explicite.

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

La fonctionnalité disponible est le
[premier incrément vertical](docs/parcours-utilisateur.md#premier-incrément-vertical),
recevoir une demande visant un dépôt local, invoquer un véritable client
d’agent, identifier le candidat produit, exécuter les contrôles de l’application
cible et restituer le résultat, étendu par la configuration et la vérification
réutilisables décrites ci-dessous. Elle ne met pas encore en œuvre les états et
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
uv run 495 change \
  --repository /chemin/vers/application \
  --contract /chemin/vers/application/495.json \
  --codex-home /chemin/vers/codex-home-495 \
  --request-file /chemin/vers/demande.md
```

L’invocation historique sans sous-commande reste acceptée : lorsque le premier
argument commence par `--`, `495` se comporte comme `495 change`, et
`495 --help` affiche l’aide de cette sous-commande. `495 -h` et `495` sans
argument affichent l’aide générale. `tools/run_change.py` reste disponible comme
lanceur de compatibilité vers la même interface.

495 ne crée aucun commit et ne conserve pas les événements ou rapports
temporaires. Codex peut toutefois créer ses propres caches et fichiers d’état
dans le `CODEX_HOME` dédié ; ce répertoire reste sous le contrôle de
l’utilisateur.

### Vérifier un candidat déjà présent

`495 verify` applique les contrôles du contrat à l’écart entre l’arbre de
travail et une référence Git, sans invoquer l’agent. Il n’exige ni demande, ni
`CODEX_HOME`, ni authentification : seul le binaire `codex` doit être installé,
car ses profils sandbox exécutent les contrôles. Le dépôt peut être modifié,
puisque c’est cet écart qui est vérifié.

```sh
uv run 495 verify [--repository .] [--contract <dépôt>/495.json] [--baseline HEAD]
```

La référence doit être `HEAD` ou un ancêtre de `HEAD`. Avec `HEAD`, le
candidat est le travail non commité ; avec une référence antérieure comme
`HEAD~1`, il inclut les commits intermédiaires. Lorsque l’arbre de travail est
identique à la référence, aucun contrôle n’est lancé et l’issue vaut
`no_candidate`.

### Configurer un dépôt

`495 configure` prépare le contrat d’un dépôt en trois opérations distinctes.
Aucune n’écrit dans le dépôt sans `write`.

```sh
uv run 495 configure propose  [--repository .] --codex-home <répertoire> [--agent-timeout-seconds 900] [--timeout-seconds <secondes>]
uv run 495 configure validate [--repository .] [--contract <dépôt>/495.json]
uv run 495 configure write    [--repository .] --proposal <fichier> [--contract <dépôt>/495.json] [--overwrite]
```

`propose` fait inspecter le dépôt par Codex avec `--sandbox read-only` et
restitue une proposition sans rien enregistrer. Comme `change`, il exige un
`CODEX_HOME` dédié et authentifié, contacte le service Codex et peut consommer
un quota. Le document contient le contrat proposé, au même format que celui
consommé par `verify`, l’attestation citée par l’agent pour chaque contrôle
dans `evidence`, les choix qu’il n’a pas pu trancher dans `questions` et
l’exécutable résolu de chaque contrôle dans `commands`, `null` lorsqu’il est
introuvable. Un timeout n’est proposé que lorsque le dépôt l’atteste ; sinon
l’agent le laisse à `null`, et 495 ne complète ces contrôles qu’avec la valeur
passée par `--timeout-seconds`. Sans cette option, ils restent sans borne de
durée, ce que `limitations` signale. Une proposition n’est jamais une preuve :
elle est relue par une personne, qui reste responsable de la pertinence des
contrôles. Une
proposition qui viole le format du contrat, un agent qui modifie le dépôt
malgré la lecture seule ou une réponse bloquée produisent `agent_failed` ;
une inspection qui ne détecte aucun contrôle attesté produit
`no_checks_detected` avec les questions à trancher.

`validate` contrôle un contrat présent sans authentification : format,
exécutable de chaque contrôle résolu depuis la racine du dépôt ou le `PATH`
transmis, puis sonde des profils sandbox. `write` extrait le contrat d’une
proposition enregistrée depuis la sortie de `propose`, éventuellement
modifiée, applique la même validation, puis l’écrit indenté dans le dépôt.
Sans `--overwrite`, un contrat existant n’est ni lu ni remplacé et la commande
rend `execution_impossible` ; avec `--overwrite`, le remplacement est
atomique. Un contrat écrit à la main sans passer par `propose` se contrôle
avec `validate`. Aucun commit n’est créé.

### Résultat et codes de sortie

Chaque commande écrit un seul document JSON sur sa sortie standard, indenté,
en UTF-8, avec des clés triées. La sortie d’erreur ne reçoit que les erreurs
d’usage des arguments. Le code de sortie découle de l’issue `outcome` :

| Code | Issue | Commandes |
| --- | --- | --- |
| `0` | `candidate_verified`, `proposal_ready`, `configuration_valid`, `configuration_written` | toutes |
| `1` | `candidate_failed` | `verify`, `change` |
| `2` | `execution_impossible`, `configuration_invalid` | toutes |
| `3` | `agent_failed` | `change`, `configure propose` |
| `4` | `no_candidate`, `no_checks_detected` | `verify`, `configure propose` |

`configuration_invalid` signale un contrat présent et lisible dont le format
est refusé ; `execution_impossible` couvre les autres préconditions manquantes,
comme un dépôt, un contrat ou un `codex` absent, une référence irrésoluble,
un exécutable de contrôle introuvable, une sandbox indisponible ou un contrat
existant sans `--overwrite`. Le code `4` signale que tout était prêt mais
qu’il n’y avait rien à vérifier ou rien à proposer.

Les sorties capturées sont bornées : 495 conserve les premiers 4 MiB de chaque
flux d’un processus et vide le reste sans le retenir, sans jamais bloquer le
processus. Chaque contrôle rapporte `stdout_bytes`, `stderr_bytes`,
`stdout_truncated` et `stderr_truncated` en plus du texte conservé ; le bloc
`agent` rapporte les mêmes comptages sans restituer le flux JSONL. Le champ
`output_limit_bytes` rappelle la borne dans chaque document. Un flux JSONL de
l’agent qui dépasse cette borne ne permet pas de confirmer la fin du tour et
produit `agent_failed`.

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
dont les commandes `verify` et `configure` et les bornes de taille des sorties
sont implémentées.
La [reprise de CodeServo](docs/reprise-de-codeservo.md) distingue les
comportements hérités des mécanismes qui redeviennent conditionnels.
L’[état de l’implémentation](docs/implementation.md) décrit précisément le
comportement disponible.
