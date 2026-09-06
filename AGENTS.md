# AGENTS.md

## Objet

495 cherche à rendre le développement logiciel assisté par IA compréhensible
et vérifiable. Le dépôt ne doit revendiquer que les comportements effectivement
disponibles.

## Sources actives

- `README.md` décrit l’état et l’utilisation du dépôt.
- `docs/principes-et-contraintes.md` porte les règles de décision.
- `docs/implementation.md` décrit le comportement implémenté.
- `pyproject.toml` déclare le projet Python et ses dépendances.
- `uv.lock` verrouille l’environnement Python résolu.
- `bootstrap/contract.json` configure l’exécution contrôlée facultative.

Git suffit pour retrouver les versions antérieures. Les rapports générés et les
archives de conception ne sont pas des sources actives.

## Travail dans le dépôt

Une demande explicite de l’utilisateur autorise les modifications locales et
réversibles comprises dans son périmètre. Aucun digest ni document
d’autorisation supplémentaire n’est requis.

Demande une confirmation dédiée avant un effet externe, destructif ou
difficilement réversible qui n’est pas déjà explicite dans la demande. Signale
avant exécution tout besoin de réseau, de secret ou d’accès à un service tiers.

Préserve les modifications utilisateur sans rapport avec la demande. N’ajoute
pas de mécanisme destiné à un usage hypothétique : pars d’un parcours
utilisateur observable et introduis seulement les abstractions qu’il exige.

## Dépendances

`uv` est l’unique gestionnaire du projet et des dépendances Python. Déclare les
dépendances dans `pyproject.toml`, mets à jour `uv.lock` avec `uv` et exécute
les commandes Python du projet avec `uv run`. Ne maintiens pas en parallèle de
fichier `requirements.txt` ou de configuration propre à un autre gestionnaire.

Les dépendances tierces sont autorisées lorsqu’elles apportent une valeur
concrète. Évalue leur maintenance, leur licence et leur coût d’exploitation.
Le lockfile est versionné pour rendre l’environnement de l’application
reproductible.

L’absence de dépendance n’est pas un objectif en soi.

## Contrôles et rapports

Les commandes de développement ordinaires peuvent être exécutées directement.
Le lanceur `tools/run_bootstrap.py` sert lorsqu’il faut rattacher un résultat à
une configuration et à un ensemble de fichiers précis.

- `validate` contrôle la configuration sans lancer les commandes.
- `run` exécute chaque commande une fois avec son timeout.
- `run --report` conserve en plus un rapport JSON ignoré par Git.

Un rapport décrit des faits. Il ne constitue ni une acceptation humaine, ni une
preuve de sécurité, d’isolation ou de reproductibilité complète.

## Code et documentation

La structure du code découle des usages présents. Aucune architecture en
couches, immutabilité universelle, sérialisation canonique ou taxonomie fermée
n’est imposée sans besoin démontré.

La documentation du projet est rédigée en français par défaut. Les commentaires
expliquent le comportement ou une décision technique durable. Les formats
d’interface conservent la langue attendue par leur écosystème.

Les messages de commit utilisent de préférence `<type>: <description>`, avec un
type parmi `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf` et `ci`.

## Critères de fin

Avant de remettre un changement :

- valide les formats touchés ;
- exécute les contrôles pertinents et disponibles ;
- vérifie que la documentation décrit le comportement courant ;
- indique les contrôles réellement exécutés et les limites restantes.
