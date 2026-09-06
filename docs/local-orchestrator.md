# Orchestrateur local

## Statut

Ce document décrit le prochain candidat du contrôleur 495. Le contrat
exécutable est `bootstrap/contract.json`.

L’écriture sous `src/application/` et `tests/` exige une décision humaine
visant le digest exact du contrat courant. Aucune décision de ce type n’est
encore enregistrée dans ce document.

## Objectif

Relier le noyau de domaine, le moteur de décision, la persistance locale et les
ports CSAP dans une couche d’application unique, sans transport externe ni
effet distant.

Cette couche rend possible un premier parcours local cohérent : reconstruire
l’état, appliquer une commande, persister son résultat atomiquement, rejouer
une requête identique et interroger un adaptateur en processus.

## Principes

- Le domaine reste l’unique autorité sur la validité et l’effet d’une commande.
- Le moteur de décision reste l’unique producteur des verdicts calculés.
- La persistance reste l’unique autorité sur la séquence, la version globale et
  l’idempotence durable des commandes acceptées.
- CSAP reste l’unique interface vers une capacité d’agent, d’exécution, de
  dépôt ou d’approbation.
- L’orchestrateur coordonne ces composants sans dupliquer leurs règles.
- Un refus ne modifie ni l’état, ni le journal, ni le magasin d’objets.

## Périmètre fonctionnel

Le paquet `application` fournit :

- une enveloppe de commande associant explicitement un `increment_id` à une
  commande typée du domaine ;
- un codec canonique et strict pour les commandes, les résultats et les états
  du domaine actuellement pris en charge ;
- une reconstruction de la collection des incréments depuis les résultats
  persistés ;
- un service d’application appliquant une commande à la bonne version d’état ;
- un service d’évaluation de gate sur l’état courant ;
- un registre injecté des quatre ports CSAP ;
- un routage CSAP qui vérifie la séparation du port avant tout appel ;
- des résultats immuables distinguant acceptation, rejeu, refus du domaine,
  refus de persistance et refus de protocole.

L’orchestrateur ne charge aucun module fourni par une application cible.

## Commandes et version d’état

Une commande d’application contient un `increment_id` non vide et une
`domain.commands.Command`. Pour `CreateIncrement`, l’identifiant de
l’enveloppe doit être identique à celui du payload.

Le traitement suit cet ordre :

1. reconstruire la projection persistée et les derniers états d’incrément ;
2. rechercher un éventuel `command_id` déjà enregistré ;
3. retourner le résultat enregistré si le contenu canonique est identique ;
4. refuser avec conflit si le même identifiant vise un contenu différent ;
5. comparer `expected_state_version` à la version globale reconstruite ;
6. demander au domaine de valider et d’appliquer la commande ;
7. persister en une opération la commande et le nouvel état canonique ;
8. retourner la version et l’état effectivement enregistrés.

Le rejeu précède le contrôle de version : une réponse acceptée reste
retrouvable après que l’état global a progressé. Une nouvelle commande portant
une version périmée est refusée sans écriture.

Les commandes refusées par le domaine ne sont pas ajoutées au journal. Leur
refus est déterministe pour l’état observé, mais il ne constitue pas un reçu
durable après évolution de cet état.

## Reconstruction et codecs

Chaque événement de commande accepté conserve une représentation JSON
canonique du nouvel état complet de l’incrément concerné. La reconstruction
parcourt les commandes dans l’ordre du journal et retient le dernier état de
chaque incrément.

Le codec :

- encode explicitement les enums, références, approbations, tentatives,
  décisions, scellements, révisions et intentions d’intégration ;
- refuse les champs inconnus, les tags inconnus et les références incomplètes ;
- ne repose ni sur `pickle`, ni sur l’import dynamique, ni sur le nom qualifié
  arbitraire d’une classe ;
- produit les mêmes octets canoniques pour la même valeur ;
- vérifie que l’état décodé appartient à l’incrément annoncé par l’événement.

Une entrée persistée mal formée produit un refus explicite. Aucun état partiel
n’est retourné comme s’il était fiable.

## Évaluation des gates

L’orchestrateur peut évaluer une gate à partir de l’état courant, d’une
politique, d’un bundle de faits, des approbations applicables et d’un contexte
explicite. Il délègue le calcul à `policy.evaluate_gate` sans modifier l’état.

L’application du verdict reste une commande de domaine distincte. Elle exige
donc un `command_id`, une version attendue et les préconditions ordinaires.
Cette séparation empêche qu’une simple lecture évaluative fasse évoluer le
journal.

## Routage CSAP

Les ports sont fournis au constructeur de l’orchestrateur. Le registre refuse
les doublons et permet au plus une implémentation par port.

Avant l’appel, le routeur vérifie que :

- le port demandé est enregistré ;
- l’opération appartient au vocabulaire exact de ce port ;
- la version et l’enveloppe ont déjà été validées par CSAP.

Une opération interdite pour le port est refusée sans appeler l’adaptateur.
Les identifiants, curseurs, annulations et résultats terminaux restent gérés
par l’adaptateur CSAP. Le candidat utilise uniquement l’adaptateur simulé en
processus ; ses opérations ne sont pas durables après redémarrage.

## Graphe de dépendances

`application` peut importer `domain`, `validation`, `policy`, `persistence` et
`csap`. Aucun de ces cinq paquets n’importe `application`.

La couche d’application ne contient pas de logique métier déjà portée par les
couches inférieures. Les accès au système de fichiers passent uniquement par
`persistence`.

## Kit de contrôle

La suite `tests/application/` vérifie au minimum :

- création puis reconstruction d’un incrément ;
- application consécutive de commandes et progression monotone de version ;
- rejeu exact après progression de l’état ;
- conflit d’identifiant avec un contenu différent ;
- refus d’une version périmée sans nouvelle ligne de journal ;
- refus métier sans modification persistée ;
- reconstruction de plusieurs incréments ;
- refus d’un snapshot corrompu ou d’un type inconnu ;
- aller-retour canonique des valeurs du domaine ;
- évaluation pure d’une gate puis application explicite de sa décision ;
- routage de chaque opération vers un port autorisé ;
- refus d’un port absent et d’une opération affectée à un autre port ;
- propagation fidèle des refus CSAP ;
- reprise déterministe après création d’une nouvelle instance du service.

Les suites unitaires, d’énumération, de persistance et CSAP existantes restent
obligatoires.

## Hors périmètre

Le candidat ne fournit pas :

- de parsing JSON destiné à une interface publique ;
- de transport NDJSON ou de processus enfant ;
- de worker exécutant du code ;
- d’adaptateur Git ou distant ;
- de transfert effectif de blobs ;
- de CLI ;
- d’authentification des décisions humaines ;
- de migration de schéma persisté ;
- de qualification d’isolation ou de sécurité.

## Contraintes

- Python 3.12 ou ultérieur et bibliothèque standard uniquement.
- Aucun réseau, secret, sous-processus ou effet externe.
- Écritures de test limitées au `TMPDIR` du contrat.
- Données d’application immuables et résultats explicites.
- Aucun import dynamique, `pickle` ou désérialisation permissive.
- Aucun changement du contrat ou du candidat pendant un contrôle.

## Qualification

Le bootstrap n’applique toujours aucun mécanisme qualifié d’immutabilité du
candidat ou de restriction réseau. Un rapport favorable conserve donc la
qualification `progress` et ne permet pas une acceptation finale.

## Décisions humaines

L’écriture du candidat sous `src/application/` et `tests/` est autorisée par la
décision suivante :

```text
AUTORISÉ — contrat sha256:35539613868d6f762fafcb8c77257ace6a3aee1d4c18578b892511c53dd4341e — local:owner — 2026-09-06
```

Cette autorisation ne s’étend à aucun autre digest de contrat.
