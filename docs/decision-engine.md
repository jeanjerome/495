# Moteur de décision déterministe

## Statut

Ce document décrit la prochaine capacité du contrôleur 495. Le contrat
exécutable est `bootstrap/contract.json`.

L’écriture sous `src/validation/`, `src/policy/` et `tests/` exige une décision
humaine visant le digest exact du contrat courant. Aucune autorisation accordée
à un contrat antérieur ne s’y transfère.

## Objectif

Transformer un ensemble explicite d’obligations et de faits en une décision de
gate reproductible, sans accès au système de fichiers, au réseau, à l’heure ou
à un agent.

À entrées identiques, le moteur retourne une `GateDecision` identique. Il ne
modifie pas l’état de l’incrément : l’application atomique de la décision reste
assurée par `domain.commands.ApplyGateDecision`.

## Périmètre fonctionnel

Le candidat ajoute deux paquets au noyau existant.

`validation` :

- représente les observations et leur provenance ;
- vérifie les références complètes, les digests attendus et la fraîcheur
  fournie comme un fait explicite ;
- distingue une preuve conforme, une violation démontrée et une observation
  inutilisable ;
- refuse les structures inconnues sans exécuter leur contenu.

`policy` :

- représente une politique comme un arbre immutable ;
- accepte uniquement les opérateurs prédéfinis `all_of`, `any_of`,
  `check_passed`, `approval_present`, `artifact_present`, `digest_matches`,
  `capability_satisfied` et `within_budget` ;
- évalue les obligations dans un ordre déterministe ;
- produit `PASS` seulement lorsque toutes les obligations bloquantes sont
  satisfaites ;
- produit `FAIL` lorsqu’au moins une violation valide est établie ;
- produit `INDETERMINATE` lorsque les données utilisables ne suffisent pas et
  qu’aucune violation valide n’impose `FAIL` ;
- conserve simultanément les violations et les preuves manquantes dans les
  raisons structurées ;
- rattache la décision à la gate, au candidat éventuel, à la version d’état et
  aux digests de la politique et du bundle d’entrée.

## Interfaces visées

Le paquet `validation` expose des valeurs immuables pour les faits et une
fonction pure de qualification d’une observation.

Le paquet `policy` expose :

```text
build_policy(document) -> Accepted[Policy] | Refused
evaluate_gate(state, gate, policy, facts, approvals, context) -> GateDecision
```

`build_policy` est la seule construction sanctionnée d’une politique. Elle
rejette les opérateurs, champs et formes inconnus. Aucun `eval`, import
dynamique, expression Python ou rappel utilisateur n’est admis.

Le contexte d’évaluation porte explicitement l’identifiant de décision, la
version du moteur, la version d’état attendue et les digests d’entrée. Le moteur
ne lit ni horloge ni variable d’environnement pour les produire.

## Règles de verdict

Les résultats atomiques d’une obligation sont :

- `SATISFIED` : preuve utilisable conforme ;
- `VIOLATED` : preuve utilisable établissant une violation ;
- `UNRESOLVED` : preuve absente, périmée, mal formée ou non applicable.

La réduction d’un ensemble d’obligations suit cet ordre :

1. une ou plusieurs violations valides donnent `FAIL` ;
2. en l’absence de violation, toute obligation non résolue donne
   `INDETERMINATE` ;
3. `PASS` exige que toutes les obligations soient satisfaites.

Chaque résultat différent de `PASS` comporte au moins une `DecisionReason`.
Une raison nomme son code, l’obligation concernée et les références de preuve
utilisées. L’ordre des raisons est stable et indépendant de l’ordre des
collections fournies par l’appelant.

Une approbation ne satisfait une obligation que si elle est `approved` et vise
exactement la référence complète attendue. Un refus explicite constitue une
violation ; une approbation absente constitue une donnée non résolue.

`any_of` accepte une alternative lorsqu’une branche est satisfaite. Il est
`VIOLATED` seulement lorsque toutes les branches sont violées ; dans les autres
cas sans branche satisfaite, il est `UNRESOLVED`.

## Hors périmètre

Le candidat ne fournit pas encore :

- de persistance ou de journal de commandes ;
- de projection SQLite ;
- de CLI ;
- d’exécution de contrôles ou d’agents ;
- de protocole d’adaptateur ;
- de lecture de fichiers de politique depuis le domaine applicatif ;
- d’authentification des approbations ;
- de mécanisme de sécurité qualifié.

Le chargement JSON appartient aux futurs adaptateurs. Les fonctions du candidat
reçoivent des octets ou valeurs déjà fournis par leur appelant.

## Contraintes

- Python 3.12 ou ultérieur et bibliothèque standard uniquement.
- Données d’état immuables.
- Fonctions déterministes et sans entrée-sortie sous `src/domain/`,
  `src/validation/` et `src/policy/`.
- Dépendances descendantes : `validation` peut importer `domain`, `policy` peut
  importer `domain` et `validation`; aucun de ces paquets n’importe
  `application`, `ports` ou `infrastructure`.
- Toute structure ou précondition invalide retourne un refus explicite et ne
  produit aucune décision partielle.
- Le noyau de domaine existant reste compatible avec ses contrôles publics.

## Stratégie de contrôle

La suite unitaire vérifie notamment :

- chaque opérateur positif et négatif ;
- le rejet des opérateurs et champs inconnus ;
- les tables de vérité de `all_of` et `any_of` ;
- la priorité de `FAIL` sur `INDETERMINATE` ;
- la conservation simultanée d’une violation et d’une preuve manquante ;
- l’applicabilité exacte des approbations ;
- la liaison de la gate, du candidat, de la version et des digests ;
- le déterminisme par permutation des entrées ;
- l’absence d’entrée-sortie et d’import interdit dans les trois paquets.

La suite d’énumération conserve les quatorze domaines existants et ajoute les
domaines finis du moteur : huit opérateurs, trois résultats atomiques, trois
verdicts et les gates G0 à G5.

## Conditions d’arrêt

L’exécution s’arrête sur toute dérive du contrat ou du candidat, tout fichier
hors périmètre, tout lien symbolique, tout test obligatoire défavorable ou tout
accès interdit constaté.

Tant que les mécanismes de sécurité du bootstrap restent non qualifiés, un
rapport favorable conserve la qualification `progress`.

## Décisions humaines

L’écriture du candidat sous `src/validation/`, `src/policy/` et `tests/` est
autorisée par la décision suivante :

```text
AUTORISÉ — contrat sha256:84199954b59dead734032aa80279988a0fccbbe8e1a29cc40ff941d95d0f5724 — local:owner — 2026-09-06
```

Cette autorisation ne s’étend à aucun autre digest de contrat.
