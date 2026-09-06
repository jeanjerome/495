# État de l’implémentation

## Disposition du dépôt

| Élément | Décision | Motif |
| --- | --- | --- |
| `README.md` | Conservé et raccourci | Point d’entrée pour comprendre et utiliser le dépôt |
| `docs/principes-et-contraintes.md` | Conservé | Autorité sur les règles techniques |
| `docs/implementation.md` | Conservé | Description du comportement réellement disponible |
| `docs/presentation.md` | Conservé et raccourci | Présentation du but et du nom du projet |
| `pyproject.toml` | Ajouté | Déclaration standard du projet Python et de ses dépendances |
| `uv.lock` | Ajouté | Résolution reproductible de l’environnement Python |
| `.python-version` | Ajouté | Sélection de Python 3.12 par `uv` |
| Documents dédiés au domaine, aux gates, à la persistance, aux adaptateurs et à l’orchestrateur | Supprimés | Ils décrivaient des composants sans parcours utilisateur |
| `495/` | Supprimé | Archive redondante avec l’historique Git |
| `bootstrap/runs/` | Supprimé | Résultats anciens sans rôle dans l’état courant |
| `bootstrap/contract.json` | Conservé et simplifié | Configuration facultative d’une exécution liée à des fichiers |
| `tools/run_bootstrap.py` | Conservé et simplifié | Seul parcours exécutable utile |
| `tools/test_run_bootstrap.py` | Conservé et simplifié | Vérification directe du lanceur |
| `tools/verify_state.py` | Supprimé | Ne contrôlait que l’archive retirée |
| `src/domain/`, `src/validation/` et `src/policy/` | Supprimés | Modèle fermé conçu avant un usage réel |
| `src/persistence/` | Supprimé | Infrastructure sur mesure sans consommateur réel |
| `src/csap/` et `src/application/` | Supprimés | Protocole simulé et orchestration sans intégration réelle |
| `tests/` | Supprimé avec les composants correspondants | Tests d’un comportement écarté du socle |

## Comportement disponible

Le seul point d’entrée exécutable du projet est actuellement
`tools/run_bootstrap.py`. Il offre deux commandes :

- `validate` valide une configuration et résout les fichiers qu’elle désigne ;
- `run` exécute les contrôles et retourne un code de sortie favorable seulement
  si toutes les commandes réussissent et si les entrées restent stables.

L’option `--report` de `run` conserve le résultat. Sans cette option, le
lanceur n’écrit aucun historique d’exécution.

Les commandes documentées passent par `uv run`. `uv` sélectionne Python 3.12,
crée si nécessaire un environnement `.venv` ignoré par Git et le synchronise
avec `uv.lock`. Le projet est déclaré non packagé tant qu’aucune commande
utilisateur `495` n’existe ; aucun backend de build n’est donc imposé.

## Configuration

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

## Résultat

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

## Comportements absents

Le projet ne fournit pas encore de commande utilisateur `495`, de workflow
métier, de stockage applicatif, d’intégration avec un agent ou un dépôt, ni de
mécanisme d’approbation.

Il ne contrôle pas le réseau, les secrets ou les écritures du processus. Le
lockfile rend la résolution des dépendances reproductible, mais ne rend pas à
lui seul le système d’exploitation ni l’exécution hermétiques.

## Règle d’évolution

La prochaine implémentation doit commencer par un parcours vertical précisant
un acteur, une entrée, une action et un résultat observable. Les modèles,
adaptateurs et choix de persistance seront dérivés de ce parcours. Une
dépendance tierce peut être adoptée si elle simplifie concrètement cette
fonctionnalité.
