# Implémentation du noyau de 495

## Statut

Ce document décrit le travail courant sous le bootstrap minimal. Il rassemble
l’intention, les contraintes de conception, les critères essentiels et les
décisions humaines.

Le contrat exécutable est `bootstrap/contract.json`. L’implémentation du
candidat n’est autorisée qu’après ajout, dans la section « Décisions humaines »,
d’une autorisation visant le digest exact de ce contrat.

## Objectif

Implémenter en Python le noyau de domaine de 495 : références d’artefacts,
révisions, scellement, phases, commandes, tentatives, liens, invalidation et
évolution de l’état.

Le noyau doit rester déterministe, sans entrée-sortie et indépendant des
adaptateurs, du stockage, du réseau et des fournisseurs d’IA.

## Sources de conception

Les documents historiques suivants restent consultables comme matière de
conception :

- `495/changes/INC-0002/requirements.json` : vingt exigences et
  quatre-vingt-dix-huit critères ;
- `495/changes/INC-0003/design.md` : interfaces et allocation des exigences ;
- `495/changes/INC-0003/tasks.json` : ordre de dépendance proposé ;
- `495/changes/INC-0003/checks/check-plan.json` : oracles et inventaires
  proposés ;
- `495/decisions/` : décisions affinant la conception initiale.

Ces fichiers appartiennent à l’archive `495/`. Ils ne constituent pas les
registres actifs du bootstrap minimal et ne doivent pas être modifiés.

## Périmètre fonctionnel

Le candidat couvre :

- la construction et la validation des références complètes ;
- les révisions et le scellement d’artefacts ;
- les résultats acceptés ou refusés, sans exception métier ;
- les phases, transitions et préconditions des commandes ;
- les tentatives et leurs états ;
- les liens entre artefacts et les règles d’invalidation ;
- l’évolution immutable de l’état du domaine.

Les modules suivent un graphe de dépendance descendant :

1. `vocabulary` ;
2. `outcomes` ;
3. `references` ;
4. `revisions`, `sealing`, `links`, `invalidation`, `phases`,
   `attempts` ;
5. `state` ;
6. `commands`.

Un module n’importe que des modules situés plus haut dans cette liste.

## Hors périmètre

Le candidat ne fournit pas encore :

- de CLI ;
- de persistance ;
- de journal idempotent de commandes ;
- de moteur de gate ;
- d’adaptateur d’exécution ou de dépôt ;
- de protocole CSAP ;
- d’intégration distante ;
- d’authentification des décisions humaines ;
- de mécanisme d’isolation.

Les noms `495 init`, `495 run` et `495 verify` restent des interfaces
envisagées, pas des commandes disponibles.

## Contraintes

- Python 3.12 ou ultérieur.
- Bibliothèque standard uniquement.
- Aucun accès réseau, secret ou effet externe.
- Aucun accès au système de fichiers depuis `src/domain/`.
- Pas d’import dynamique.
- Données immutables lorsque leur rôle représente un état ou une référence.
- Toute opération métier retourne un résultat explicite accepté ou refusé.
- Une entrée invalide ne produit aucune mutation partielle.

Le contrat limite les fichiers du candidat aux fichiers Python réguliers sous
`src/domain/` et `tests/`. Les liens symboliques sont interdits.

## Stratégie de contrôle

Deux suites `unittest` sont séparées :

- `tests/unit/` contrôle les comportements et préconditions ;
- `tests/enumeration/` énumère exhaustivement les domaines finis.

Les contrôles obligatoires :

- échouent si aucun test n’est découvert ;
- exigent un code de sortie nul ;
- refusent tout test ignoré, échec attendu ou succès inattendu ;
- enregistrent le nombre et l’identité des tests réellement exécutés ;
- lient leurs résultats au digest du contrat et au manifeste du candidat.

L’inventaire historique de 88 tests unitaires et 14 tests d’énumération guide
l’implémentation. Il n’est pas une contrainte de nommage : un regroupement reste
possible si tous les comportements attendus sont couverts.

## Réseau et environnement

La qualification d’un dispositif de restriction réseau appartient à la
préparation de l’hôte, avant l’exécution du candidat. L’exécution gouvernée
utilise ensuite la configuration fermée et n’effectue aucun accès réseau.

Le bootstrap local actuel ne dispose d’aucun mécanisme qualifié d’isolation,
d’immutabilité ou de restriction réseau. Les rapports produits dans cet état
sont donc des informations de progression, même lorsque les contrôles
fonctionnels réussissent.

Le rapport relève l’interpréteur réellement utilisé, le commit Git, le digest
du contrat, le manifeste du candidat, les commandes et leurs résultats.

## Conditions d’arrêt

L’exécution s’arrête sur :

- une écriture hors des chemins autorisés ;
- un fichier candidat hors des motifs autorisés ;
- un lien symbolique dans le candidat ;
- une tentative d’accès réseau ou à un secret constatée ;
- un changement du contrat ;
- l’échec ou l’expiration d’un contrôle obligatoire.

Une correction fonctionnelle peut conserver le même contrat. Toute modification
de l’objectif, du périmètre, des droits ou des commandes exige une nouvelle
autorisation du digest du contrat.

## Décisions humaines

Le bootstrap minimal est adopté pour les modifications documentaires et
l’outillage décrits par `docs/proposition-simplification.md`.

L’écriture du candidat sous `src/` et `tests/` est autorisée par la décision
suivante :

```text
AUTORISÉ — contrat sha256:92deede997afee5a6d8b98c575967e475009fc1f5bdcfd50cd56a4dfb0b5cc80 — local:owner — 2026-09-06
```

Cette autorisation ne s’étend à aucun autre digest de contrat.

Une acceptation finale visera de la même manière le digest exact d’un rapport
dont `acceptance_eligible` vaut `true`. Aucun outil ne crée ces décisions à la
place d’une personne.

## Critères de réussite du bootstrap

Le bootstrap minimal est opérationnel lorsque :

- le contrat est validable par une commande unique ;
- aucun état courant n’est dupliqué dans plusieurs registres ;
- un rapport est généré sans saisie manuelle de digest ;
- le rapport nomme clairement les limites de sa qualification ;
- les artefacts historiques restent intacts ;
- l’autorisation et l’acceptation sont des décisions humaines distinctes des
  contrôles techniques.
