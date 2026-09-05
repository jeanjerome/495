# Protocole d’adaptateurs et kit de conformité

## Statut

Ce document décrit le candidat CSAP 1.0 du contrôleur 495. CSAP est un
protocole applicatif propre au projet, pas un standard externe.

Le contrat exécutable est `bootstrap/contract.json`. L’écriture sous
`src/csap/` et `tests/` exige une décision humaine visant le digest exact du
contrat courant.

## Objectif

Définir une sémantique commune pour les adaptateurs d’agent, d’exécution, de
dépôt et d’approbation, puis vérifier cette sémantique avec un kit de conformité
entièrement local et simulé.

Le protocole sépare les capacités : un adaptateur ne reçoit que les opérations
du port qu’il implémente. Une déclaration de capacité décrit un adaptateur ;
elle ne suffit jamais à le rendre fiable ou qualifié.

## Périmètre fonctionnel

Le paquet unique `csap` fournit :

- le vocabulaire fermé de CSAP 1.0 ;
- des enveloppes de requête, de résultat et d’erreur immuables ;
- une construction sanctionnée qui refuse les champs et valeurs inconnus ;
- la négociation d’une version commune ;
- la validation des extensions optionnelles et obligatoires ;
- le cycle non bloquant des opérations longues ;
- la liaison d’une clé d’idempotence au payload canonique exact ;
- les interfaces des quatre ports ;
- un adaptateur simulé en processus ;
- un kit de conformité produisant un rapport structuré.

## Ports

Les quatre ports ont des responsabilités disjointes :

| Port | Opérations |
| --- | --- |
| Agent | `describe`, `start_agent`, `get_operation`, `cancel_operation` |
| Exécution | `describe`, `prepare`, `capture_candidate`, `run_check`, `get_operation`, `cancel_operation`, `release` |
| Dépôt | `describe`, `integrate`, `get_operation` |
| Approbation | `describe`, recueil d’une décision humaine sur une référence exacte |

Le recueil d’approbation possède une opération propre `request_approval`. Il ne
peut pas être déclenché par un jeton destiné à l’agent ou à l’exécution.

## Vocabulaire fermé

Les opérations sont exactement :

```text
describe, prepare, start_agent, capture_candidate, run_check,
get_operation, cancel_operation, release, integrate, request_approval
```

Les états d’une opération longue sont `queued`, `running`, `succeeded`,
`failed`, `cancelled` et `unknown`.

Les résultats de contrôle sont `PASS`, `FAIL`, `ERROR` et `NOT_RUN`.
`succeeded` décrit le transport et l’exploitation du résultat ; un contrôle
terminé avec `FAIL` reste une opération `succeeded`.

Les erreurs communes sont `UNSUPPORTED_VERSION`, `UNSUPPORTED_CAPABILITY`,
`UNSUPPORTED_PARAMETER`, `INVALID_INPUT`, `AUTHORIZATION_DENIED`,
`ENVIRONMENT_UNAVAILABLE`, `TIMEOUT`, `RESOURCE_LIMIT`, `OUTPUT_INVALID`,
`INTEGRITY_MISMATCH`, `CONFLICT` et `OPERATION_UNKNOWN`.

## Enveloppes

Une requête contient :

- `protocol_version` ;
- `request_id` ;
- `idempotency_key` ;
- `operation` ;
- `increment_id` et `attempt_id` lorsque l’opération les exige ;
- une référence complète de contrat lorsque l’opération agit sur un travail ;
- un payload JSON ;
- un objet `extensions`.

Les champs inconnus sont refusés. Une extension est nommée par un identifiant
qualifié contenant au moins un point. Une extension obligatoire porte
`required=true` ; si elle n’est pas déclarée comme comprise par le receveur, la
requête est refusée avec `UNSUPPORTED_CAPABILITY`.

Les références d’artefacts utilisent les cinq champs du noyau, jamais un chemin
ni une valeur symbolique. Les références de blobs transportés sont des digests
`sha256` opaques ; aucune URL arbitraire n’est admise.

## Négociation

`describe` reçoit les versions supportées par le client et retourne l’identité,
la version, les versions du protocole, les ports, les opérations, plateformes,
toolchains, limites et capacités d’isolation déclarées par l’adaptateur.

La négociation choisit la version commune la plus élevée. L’absence de version
commune produit `UNSUPPORTED_VERSION`. CSAP 1.0 ne déduit aucune confiance des
capacités déclarées : leur comparaison à un profil de confiance appartient au
contrôleur.

## Idempotence et opérations longues

Une clé d’idempotence est liée au digest canonique de l’enveloppe, hors
`request_id`. Une nouvelle requête avec la même clé et le même contenu retourne
la même opération. La même clé avec un contenu différent produit `CONFLICT`.

`start_agent`, `run_check`, `integrate` et `request_approval` retournent sans
attendre un résultat terminal. `get_operation` expose l’état, les événements
depuis un curseur et le résultat terminal éventuel. Un curseur inconnu ou une
opération expirée produit `OPERATION_UNKNOWN`.

`cancel_operation` accuse la demande. Cet accusé ne prétend pas que l’opération
est déjà arrêtée. Une transition terminale reste terminale et aucun résultat
terminal n’est remplacé.

## Résultats de contrôle

Un résultat de `run_check` lie au minimum :

- le contrôle approuvé ;
- le contrat ;
- le candidat ;
- l’environnement résolu ;
- le résultat `PASS`, `FAIL`, `ERROR` ou `NOT_RUN` ;
- les résultats par exigence ;
- le code de sortie et l’expiration ;
- les références de preuve et de feedback.

Un `PASS` incomplet est `OUTPUT_INVALID`. Un résultat bien formé portant
`outcome=FAIL` est utilisable et ne devient pas une erreur de protocole.

## Kit de conformité

Le kit reçoit un adaptateur en processus et exécute une table de cas sans accès
réseau ni sous-processus. Il vérifie au minimum :

- négociation positive et version incompatible ;
- refus des champs inconnus ;
- extensions optionnelles et obligatoires ;
- séparation des opérations par port ;
- stabilité des identifiants et idempotence ;
- conflit d’une clé réutilisée avec un payload différent ;
- six états d’opération et terminalité ;
- pagination par curseur ;
- sémantique non terminale de l’accusé d’annulation ;
- résultat de contrôle `FAIL` transporté par une opération `succeeded` ;
- refus d’un `PASS` incomplet ;
- douze erreurs communes ;
- références complètes et refus des URL de blobs.

Le rapport contient chaque cas, son résultat et les capacités observées. Un
adaptateur qui réussit la conformité syntaxique n’acquiert aucune qualification
d’isolation ou de confiance.

## Hors périmètre

Le candidat ne fournit pas encore :

- de transport NDJSON par processus enfant ;
- de connexion distante authentifiée ;
- de backend d’agent ;
- de worker exécutant du code non fiable ;
- d’adaptateur Git ou de dépôt réel ;
- d’interface utilisateur d’approbation ;
- de transfert effectif de blobs ;
- de qualification de sécurité.

## Contraintes

- Python 3.12 ou ultérieur et bibliothèque standard uniquement.
- Aucun accès réseau, secret, sous-processus ou système de fichiers dans
  `src/csap/`.
- Données immuables et sérialisation canonique déterministe.
- Aucun import de code fourni par une application cible.
- Les adaptateurs simulés ne produisent aucun effet externe.
- Les couches inférieures n’importent jamais `csap`.

## Stratégie de contrôle

La suite `tests/csap/` porte le kit de conformité et les scénarios de protocole.
Les suites unitaires, d’énumération et de persistance existantes restent
obligatoires.

L’énumération ajoute les domaines finis propres à CSAP : dix opérations, quatre
ports, six états, quatre résultats de contrôle et douze erreurs communes.

## Décisions humaines

L’écriture du candidat sous `src/csap/` et `tests/` est autorisée par la décision
suivante :

```text
AUTORISÉ — contrat sha256:5b2e9232e1fe28078df680eef0d255fea43cc3388de19621b2583b6a27bc4a3f — local:owner — 2026-09-06
```

Cette autorisation ne s’étend à aucun autre digest de contrat.
