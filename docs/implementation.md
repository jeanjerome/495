# État de l’implémentation

## Disposition du dépôt

| Élément | Décision | Motif |
| --- | --- | --- |
| `README.md` | Conservé et raccourci | Point d’entrée pour comprendre et utiliser le dépôt |
| `docs/principes-et-contraintes.md` | Conservé | Autorité sur les règles techniques |
| `docs/parcours-utilisateur.md` | Ajouté | Workflow de référence, usages visés et expérience utilisateur |
| `docs/chantiers/plan-global.md` | Ajouté | Ordre des capacités futures et impacts attendus sur l’architecture applicative |
| `docs/etat-de-l-art.md` | Ajouté | Comparaison durable des clients, harnais et runtimes examinés |
| `docs/chantiers/00-parcours-vertical/etat-de-l-art.md` | Ajouté | Étude ciblée et essais du premier parcours vertical |
| `docs/chantiers/00-parcours-vertical/conception.md` | Ajouté | Choix d’intégration appliqués au premier parcours vertical |
| `docs/reprise-de-codeservo.md` | Ajouté | Comportements hérités de CodeServo et simplification attendue |
| `docs/implementation.md` | Conservé | Description du comportement réellement disponible |
| `docs/presentation.md` | Conservé et raccourci | Présentation du but et du nom du projet |
| `pyproject.toml` | Ajouté | Déclaration standard du projet Python et de ses dépendances |
| `uv.lock` | Ajouté | Résolution reproductible de l’environnement Python |
| `.python-version` | Ajouté | Sélection de Python 3.12 par `uv` |
| Documents dédiés au domaine, aux gates, à la persistance, aux adaptateurs et à l’orchestrateur | Supprimés | Ils imposaient des composants avant les comportements et intégrations réels |
| `495/` | Supprimé | Archive redondante avec l’historique Git |
| `bootstrap/runs/` | Supprimé | Résultats anciens sans rôle dans l’état courant |
| `bootstrap/contract.json` | Conservé et simplifié | Configuration facultative d’une exécution liée à des fichiers |
| `tools/run_bootstrap.py` | Conservé et simplifié | Contrôles propres au dépôt 495 |
| `src/harness495/` | Ajouté | Paquet applicatif portant le parcours, ses interfaces et ses adaptateurs |
| `tests/` | Ajouté | Vérification du paquet et du lanceur avec des dépôts temporaires |
| `tools/run_change.py` | Conservé comme compatibilité | Délègue à la CLI du paquet sans porter de comportement applicatif |
| `tools/verify_state.py` | Supprimé | Ne contrôlait que l’archive retirée |
| `src/domain/`, `src/validation/` et `src/policy/` | Supprimés | Modèle fermé conçu avant un usage réel |
| `src/persistence/` | Supprimé | Infrastructure sur mesure sans consommateur réel |
| `src/csap/` et `src/application/` | Supprimés | Protocole simulé et orchestration sans intégration réelle |

## Comportement disponible

`tools/run_bootstrap.py` offre deux commandes pour contrôler 495 lui-même :

- `validate` valide une configuration et résout les fichiers qu’elle désigne ;
- `run` exécute les contrôles et retourne un code de sortie favorable seulement
  si toutes les commandes réussissent et si les entrées restent stables.

L’option `--report` de `run` conserve le résultat. Sans cette option, le
lanceur n’écrit aucun historique d’exécution.

Les commandes documentées passent par `uv run`. `uv` sélectionne Python 3.12,
crée si nécessaire un environnement `.venv` ignoré par Git et le synchronise
avec `uv.lock`. Le paquet `harness495`, construit avec `uv_build`, installe la
commande utilisateur `495`.

La commande `495` expose le premier parcours vers une application cible. Elle
exige une demande dans un fichier, la racine d’un dépôt Git propre avec un
`HEAD`, un contrat cible et un `CODEX_HOME` dédié. Elle exécute une intervention
de `codex exec`, observe l’état Git obtenu, puis lance chaque contrôle avec
`codex sandbox`. La demande est transmise au client par l’entrée standard et
les commandes sont toujours des listes d’arguments sans shell.

Le runner crée ses schémas, réponses intermédiaires et répertoires personnels
temporaires hors du dépôt cible. Il fournit au processus Codex uniquement les
variables nommées par le contrat, son identité dédiée et ces chemins
temporaires. La politique des commandes de l’agent exclut `CODEX_HOME`, refuse
les noms ressemblant à des clés, secrets ou jetons, et désactive le réseau du
sandbox `workspace-write`. Les personnalisations utilisateur et skills
personnelles ne sont pas chargées ; les instructions et skills du dépôt restent
disponibles.

## Architecture applicative

Le paquet `harness495` sépare les frontières démontrées par le premier
parcours :

- `change` conduit le cas d’usage sans contenir les détails de la CLI ;
- `composition` assemble ce cas d’usage avec les composants Codex disponibles ;
- `agent` définit les capacités attendues d’un client d’agent et `codex` les
  adapte à Codex CLI ;
- `controls` définit l’exécution des feedbacks et fournit l’adaptation à
  `codex sandbox` ;
- `workspace` observe le candidat Git indépendamment des déclarations de
  l’agent ;
- `contract`, `serialization`, `process` et `errors` portent les mécanismes
  partagés par ces frontières ;
- `cli` transforme les arguments et les erreurs en résultat de commande.

Les interfaces `AgentClient` et `ControlRunner` rendent les dépendances du cas
d’usage explicites. Elles ne prétendent pas encore garantir la compatibilité
d’un second client ou d’un autre runtime : seule l’adaptation Codex est
implémentée et vérifiée. `tools/run_change.py` appelle la même CLI pour préserver
les usages existants.

## Configuration du lanceur de contrôles

`bootstrap/contract.json` utilise quatre champs :

| Champ | Rôle |
| --- | --- |
| `version` | Version du format de configuration |
| `files` | Motifs relatifs des fichiers liés au résultat |
| `checks` | Nom, commande et timeout de chaque contrôle |
| `report_directory` | Destination utilisée uniquement avec `--report` |

Chaque motif de `files` doit correspondre à au moins un fichier. Les doublons
sont éliminés dans le manifeste. Le digest du candidat est calculé à partir du
chemin, de la taille et du SHA-256 de chaque fichier.

Une commande est une liste d’arguments exécutée directement, sans shell. Le
jeton `{python}` désigne l’interpréteur qui exécute le lanceur. Le processus
hérite de l’environnement et utilise la racine du dépôt comme répertoire de
travail.

## Contrat de l’application cible

Le contrat reçu par la commande `495` contient exactement `version`,
`environment` et `checks`. `environment` énumère les variables ordinaires que
495 peut transmettre ; `HOME`, `TMPDIR`, `CODEX_HOME` et les noms contenant
`KEY`, `SECRET` ou `TOKEN` sont refusés.

Chaque contrôle possède un nom unique, une commande non vide, un timeout
strictement positif et un accès fichiers `read-only` ou `workspace-write`. Ces
deux valeurs utilisent respectivement les profils Codex `:read-only` et
`:workspace`. Le runner ajoute une interdiction réseau explicite à chaque
invocation.

## Résultat du lanceur de contrôles

Une commande réussit lorsque son code de sortie vaut zéro avant le timeout. En
cas d’échec, ses sorties standard et d’erreur sont affichées et peuvent être
conservées dans le rapport.

Après les commandes, le lanceur recalcule les digests de la configuration et
des fichiers contrôlés. Un changement rend le résultat défavorable, car les
commandes ne se rapporteraient plus aux entrées initiales.

Un rapport contient uniquement :

- la date d’exécution ;
- le digest de la configuration ;
- le manifeste et le digest des fichiers ;
- l’interpréteur utilisé ;
- les commandes, durées, codes de sortie et timeouts ;
- le résultat global et les éventuelles violations de stabilité.

## Résultat d’un changement

La commande `495` écrit un unique document JSON sur sa sortie standard. Elle
relie le digest de la demande, le commit initial, la version du client, la
réponse de l’agent, le candidat observé, l’environnement nommé et les contrôles.
Les artefacts temporaires ne sont pas conservés.

La réponse de l’agent est contrainte et revalidée avec le même JSON Schema au
moyen de la bibliothèque `jsonschema`. Elle contient un statut, un résumé, des
questions et des limites, mais ne décide ni des chemins modifiés ni du verdict.
Le candidat est calculé à partir du diff Git et des fichiers non suivis ; son
digest incorpore le commit initial, le patch suivi et le contenu non suivi.

Les contrôles sont séquentiels. Leur code, leur durée, leur timeout et leurs
sorties sont restitués. Si un contrôle modifie l’état Git visible, 495 arrête la
suite, conserve les fichiers et signale une violation au lieu de vérifier un
candidat différent de celui qu’il avait observé.

Les issues sont `candidate_verified`, `candidate_failed`, `agent_failed` et
`execution_impossible`. Un client non nul, bloqué ou expiré, un flux JSONL
incomplet, une réponse invalide et une absence de candidat sont distingués des
échecs des contrôles.

Le parcours complet a été exécuté avec Codex CLI `0.153.3` sur macOS. Le dépôt
d’essai a confirmé la réponse structurée, le candidat unique, le contrôle
favorable, l’absence de `CODEX_HOME` dans les commandes de l’agent et le refus
réseau de l’agent comme des contrôles. Les tests automatisés couvrent en plus
les issues défavorables sans consommer de quota.

## Comportements absents

Le projet ne fournit pas encore de passage par les états du workflow complet,
de boucle de correction, de stockage applicatif, de reprise, de mécanisme
d’approbation ni d’intégration Git. Le premier incrément ne prend en charge que
Codex CLI, un dépôt initial propre et une seule intervention.

Le runner de bootstrap continue d’hériter de l’environnement et ne constitue
pas une sandbox. Le runner de changement délègue le confinement à la version de
Codex installée : il configure et observe cette frontière, mais ne rend pas le
système d’exploitation hermétique et ne prouve pas encore les lectures
effectivement possibles. Les diagnostics des outils peuvent contenir des
informations sensibles et sont remis localement sans persistance automatique.
Codex peut néanmoins écrire ses caches et fichiers d’état propres dans le
`CODEX_HOME` dédié, que 495 ne supprime pas lorsqu’il appartient à l’utilisateur.
Les sorties des processus sont bornées par leur timeout, mais pas encore par une
taille maximale indépendante.

## Règle d’évolution

Cette section gouverne l’évolution du harnais 495. Elle ne demande pas aux
applications cibles d’utiliser Python, `uv`, les dépendances ou l’architecture
de 495.

Avant d’introduire un composant ou une abstraction dans 495, la conception
examine les clients d’agents, les autres harnais de code et les bibliothèques
open source qui fournissent déjà le comportement recherché. Pour une décision
structurante, cette étude consulte les parties pertinentes de l’implémentation,
des tests, des garanties documentées et des limites connues. Elle compare aussi
la licence, la maintenance, les plateformes, la stabilité de l’interface et le
coût d’exploitation. La décision indique brièvement ce qui est configuré,
composé, adapté ou développé dans 495.

L’[état de l’art](etat-de-l-art.md) porte cette comparaison pour l’ensemble du
projet et l’[étude ciblée](chantiers/00-parcours-vertical/etat-de-l-art.md) du
premier parcours vertical y ajoute ses essais. Toute propriété encore incertaine
doit être confirmée par un essai sur les versions réellement intégrées.

La [conception](chantiers/00-parcours-vertical/conception.md) de ce parcours
retient Codex CLI et son runner sandboxé comme composants à adapter. Le paquet
`harness495` applique cette conception au
[premier incrément vertical](parcours-utilisateur.md#premier-incrément-vertical)
sans prétendre faire traverser au changement les états et gates du workflow
complet.

Cette intégration construit un contexte ciblé, utilise des environnements
d’exécution dont les permissions sont explicites et valide le résultat JSON
attendu. Le confinement de l’agent peut être celui du client retenu si ses
propriétés observables satisfont le besoin. Les contrôles qui exécutent le
candidat doivent bénéficier de garanties équivalentes, sans supposer qu’ils
sont couverts par la sandbox du client. 495 n’ajoute pas une couche redondante
lorsque l’environnement retenu couvre déjà le processus concerné. La CLI est la
première interface. Les modèles, adaptateurs et choix de persistance seront
dérivés de ce comportement plutôt que définis au préalable. Une dépendance
tierce peut être adoptée si elle simplifie concrètement cette fonctionnalité.

La [reprise de CodeServo](reprise-de-codeservo.md) guide l’implémentation de
`implementing` et `verifying`. Elle autorise la réutilisation ciblée de son
code et de ses tests, mais pas le portage préalable de son architecture
complète.
