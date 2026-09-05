# 495

**495** encadre le développement logiciel assisté par IA par une boucle de
travail explicite, vérifiable et bornée.

Le nom vient de la constante de Kaprekar pour les nombres à trois chiffres. En
ordonnant les chiffres d’un nombre dans les deux sens, puis en soustrayant le
plus petit du plus grand de façon répétée, on atteint 495 :
`954 − 459 = 495`.

Cette convergence illustre l’objectif du projet : faire progresser une
production variable vers un résultat dont la conformité peut être contrôlée.
Elle ne promet ni un code déterministe, ni une convergence automatique.

## État du projet

Le dépôt contient un bootstrap minimal, le noyau de domaine, le moteur de
décision déterministe et la persistance locale. Le prochain candidat est CSAP
1.0 et son kit de conformité, décrits dans `docs/adapter-protocol.md`.

Le bootstrap avancé expérimenté sous `495/` est conservé comme archive. Aucun
contrôleur ne l’applique et ses registres ne décrivent plus l’état courant.

Le bootstrap actif repose sur trois éléments :

| Élément | Rôle |
| --- | --- |
| [`docs/adapter-protocol.md`](docs/adapter-protocol.md) | Objectif, périmètre, critères, limites et décisions humaines du candidat courant |
| [`bootstrap/contract.json`](bootstrap/contract.json) | Droits, périmètre du candidat et commandes exécutables |
| `bootstrap/runs/*.json` | Rapports générés et liés au contrat et au candidat |

La [proposition de simplification](docs/proposition-simplification.md) explique
ce choix et les garanties différées.

## Workflow minimal

Le bootstrap ne conserve que deux décisions humaines.

### Autorisation

Avant toute écriture sous `src/` ou `tests/` :

1. le document de travail expose l’objectif et les limites ;
2. le contrat est concret et validable ;
3. une personne autorise le digest exact du contrat.

Une modification du contrat change son digest et requiert une nouvelle
autorisation.

### Acceptation

Une exécution produit un nouveau rapport. Une acceptation exige :

- tous les contrôles obligatoires favorables ;
- aucune violation de périmètre ;
- le même contrat et le même candidat que ceux du rapport ;
- des mécanismes de sécurité qualifiés ;
- une décision humaine visant le digest exact du rapport.

En l’absence d’isolation ou d’immutabilité qualifiée, un rapport favorable reste
une information de progression.

## Utilisation

Le bootstrap requiert Python 3.12 ou ultérieur et uniquement sa bibliothèque
standard.

Valider le contrat sans exécuter le candidat :

```sh
python3 tools/run_bootstrap.py validate
```

La commande affiche le digest à viser dans la décision d’autorisation.

Après autorisation et présence du candidat, exécuter les contrôles :

```sh
python3 tools/run_bootstrap.py run
```

Le programme :

- contrôle le périmètre fermé du candidat ;
- résout l’interpréteur effectif ;
- exécute les commandes une seule fois, sans shell ;
- relève les tests découverts et les compteurs `unittest` ;
- compare le candidat et le contrat avant et après l’exécution ;
- écrit un rapport inédit sous `bootstrap/runs/`.

Le programme refuse l’exécution si
`docs/implementation.md` ne contient pas une autorisation visant le digest
courant du contrat.

## Candidat courant

Le noyau de domaine fournit déjà :

- références et révisions ;
- scellement ;
- phases et commandes ;
- tentatives ;
- liens et invalidation ;
- état immutable et résultats explicites.

Le code du domaine et du moteur de décision reste déterministe et sans
entrée-sortie. La persistance locale fournit le magasin d’objets, le journal
chaîné, l’idempotence et la reconstruction. Le candidat courant ajoute les
enveloppes CSAP, le cycle des opérations et le kit de conformité. Les
adaptateurs réels, les workers et la CLI restent hors périmètre.

## Archive historique

`495/` conserve les artefacts de l’expérimentation documentaire précédente,
y compris les exigences et la conception détaillée. Ces fichiers sont en
lecture seule.

Leur cohérence historique peut être inspectée avec :

```sh
python3 tools/verify_state.py
```

Cette commande ne valide ni le contrat minimal, ni un candidat, ni une
acceptation.

## Garanties non revendiquées

Le bootstrap minimal ne revendique pas :

- l’immutabilité de Git ;
- une identité humaine authentifiée ;
- une isolation universelle ;
- l’absence de réseau sans mécanisme hôte qualifié ;
- la reproductibilité bit à bit de l’environnement ;
- une preuve opposable à un tiers.

Ces propriétés appartiennent au contrôleur cible. Elles ne deviennent
obligatoires dans le workflow que lorsqu’un mécanisme peut réellement les
appliquer ou les vérifier.

## Documents

- [Présentation](docs/presentation.md)
- [Travail d’implémentation](docs/implementation.md)
- [Moteur de décision](docs/decision-engine.md)
- [Persistance locale](docs/local-persistence.md)
- [Protocole d’adaptateurs](docs/adapter-protocol.md)
- [Simplification du bootstrap](docs/proposition-simplification.md)
- [Conception historique](495/changes/INC-0003/design.md)
- [Exigences historiques](495/changes/INC-0002/requirements.json)
