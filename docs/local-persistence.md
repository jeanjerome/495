# Persistance locale vérifiable

## Statut

Ce document décrit le candidat de persistance locale du contrôleur 495. Le
contrat exécutable est `bootstrap/contract.json`.

L’écriture sous `src/persistence/` et `tests/` exige une décision humaine visant
le digest exact du contrat courant. Une autorisation visant un contrat antérieur
ne s’y transfère pas.

## Objectif

Conserver localement les objets et événements nécessaires à la reprise du
contrôleur, détecter toute rupture de chaîne et garantir l’idempotence d’une
commande sous un verrou mono-écrivain.

Le journal append-only est l’autorité métier. Toute projection est
reconstructible depuis ce journal et ne devient jamais une seconde source de
vérité.

## Organisation locale

Une racine de dépôt contient uniquement :

```text
objects/sha256/<digest hexadécimal>
journal/events.jsonl
journal/write.lock
quarantine/
```

Les chemins sont dérivés de la racine fournie par l’appelant. Le paquet ne lit
aucune variable d’environnement et ne choisit aucun emplacement global.

## Magasin d’objets

Le magasin reçoit des octets et calcule leur SHA-256. Une écriture :

1. calcule le digest sur les octets exacts ;
2. écrit un fichier temporaire dans le répertoire de destination ;
3. synchronise son contenu ;
4. le publie atomiquement sous son digest ;
5. synchronise le répertoire lorsque la plateforme le permet.

Un objet déjà présent avec les mêmes octets est un succès idempotent. Un objet
présent sous le digest attendu mais dont les octets diffèrent bloque
l’opération. Aucun objet publié n’est remplacé ou modifié.

La lecture recalcule le digest. Un objet absent ou corrompu produit un refus
explicite.

## Journal chaîné

Chaque ligne complète de `events.jsonl` est un objet JSON canonique terminé par
un retour à la ligne. L’enveloppe contient au minimum :

- `sequence`, entier consécutif à partir de 1 ;
- `previous_hash`, nul pour la première entrée puis égal au hash précédent ;
- `command_id` et le digest canonique de la commande ;
- `expected_state_version` ;
- `event_type` ;
- `payload` et `result`, limités aux valeurs JSON ;
- `event_hash`, calculé sur tous les champs précédents.

Une entrée n’est ajoutée qu’après vérification complète de la chaîne existante.
L’ajout est synchronisé avant de retourner un succès.

Une séquence non consécutive, un lien précédent incorrect, un hash invalide ou
un JSON corrompu au milieu du journal bloque la lecture et toute nouvelle
écriture.

Une dernière ligne incomplète est déplacée dans `quarantine/` sous un nom
inédit, puis le journal est tronqué à la dernière ligne complète et
synchronisé. Cette réparation ne s’applique jamais à une corruption située au
milieu du journal.

## Idempotence et version d’état

L’application d’une commande s’effectue sous le verrou exclusif du dépôt.

- Un `command_id` inconnu exige que `expected_state_version` égale la version
  reconstruite, puis ajoute exactement un événement et avance la version de 1.
- Le même `command_id` avec le même digest canonique retourne le résultat déjà
  journalisé, sans nouvelle ligne et sans nouvel incrément.
- Le même `command_id` avec un digest différent est refusé.
- Une version attendue différente de la version reconstruite est refusée avant
  tout ajout.

La commande et le résultat sont des documents JSON déjà normalisés par la
couche appelante. La persistance ne décide ni de leur validité métier ni d’un
verdict de gate.

## Reconstruction

La reconstruction vérifie le journal depuis sa première ligne et produit une
projection immutable contenant :

- le dernier numéro de séquence ;
- la version d’état courante ;
- la tête de chaîne ;
- l’index des commandes et de leurs résultats ;
- les références d’objets mentionnées par les événements.

Supprimer cette projection en mémoire puis rejouer le journal produit une valeur
égale. Les objets référencés peuvent être contrôlés pendant la reconstruction ;
un objet absent ou corrompu rend alors la reprise défavorable.

## Interfaces visées

```text
ObjectStore.put(raw) -> StoredObject | PersistenceRefusal
ObjectStore.get(digest) -> bytes | PersistenceRefusal
Journal.read() -> JournalState | PersistenceRefusal
Journal.append(event) -> JournalState | PersistenceRefusal
LocalRepository.execute(command, result, object_writes=())
    -> ExecutionRecord | PersistenceRefusal
LocalRepository.reconstruct(verify_objects=True)
    -> Projection | PersistenceRefusal
```

Les refus sont des valeurs structurées. Une entrée invalide ou un échec
d’intégrité ne produit aucune mutation partielle reconnue comme réussie.

## Hors périmètre

Le candidat ne fournit pas encore :

- de projection SQLite ;
- de sérialisation automatique des objets du domaine ;
- de CLI ;
- de journal distribué ou multi-écrivain ;
- de réplication, signature ou point de contrôle externe ;
- d’effet réseau ;
- d’authentification des acteurs ;
- de suppression ou collecte des objets non référencés.

Le journal détecte les incohérences relativement à sa tête locale. Il ne résiste
pas à un administrateur capable de réécrire intégralement le journal et tous les
points de confiance locaux.

## Contraintes

- Python 3.12 ou ultérieur et bibliothèque standard uniquement.
- Aucun accès réseau, secret ou sous-processus.
- Toutes les écritures de test restent sous le `TMPDIR` du contrat.
- Aucun lien symbolique n’est suivi dans la racine persistée.
- Les octets publiés dans le magasin d’objets sont immuables.
- Les opérations métier de `domain`, `validation` et `policy` restent sans
  entrée-sortie.
- `persistence` peut importer les types de valeur inférieurs, mais aucun paquet
  inférieur n’importe `persistence`.

## Stratégie de contrôle

La suite `tests/persistence/` vérifie notamment :

- le digest des octets exacts et la déduplication ;
- le refus d’un objet absent ou corrompu ;
- la publication atomique et l’absence de remplacement ;
- les séquences et hashes d’une chaîne valide ;
- le blocage sur corruption d’une ligne intermédiaire ;
- la mise en quarantaine exclusive d’une fin de ligne partielle ;
- l’idempotence positive et le conflit de payload ;
- le contrôle de `expected_state_version` ;
- l’absence de nouvel événement après tout refus ;
- l’égalité de deux reconstructions indépendantes ;
- la reprise défavorable lorsqu’un objet référencé manque ;
- l’exclusion mutuelle de deux écrivains.

Les suites unitaires et d’énumération existantes restent obligatoires afin de
détecter toute régression des couches pures.

## Conditions d’arrêt

L’exécution s’arrête sur une dérive du contrat ou du candidat, un fichier hors
périmètre, un lien symbolique, un contrôle obligatoire défavorable ou un accès
interdit constaté.

Tant que le bootstrap n’applique pas de mécanismes de sécurité qualifiés, un
rapport favorable conserve la qualification `progress`.

## Décisions humaines

L’écriture du candidat sous `src/persistence/` et `tests/` est autorisée par la
décision suivante :

```text
AUTORISÉ — contrat sha256:e9574ff0ce6c1c9731d0c0e8cd027e369c9ce817a6426d0f12ffaf24addf28d6 — local:owner — 2026-09-06
```

Cette autorisation ne s’étend à aucun autre digest de contrat.
