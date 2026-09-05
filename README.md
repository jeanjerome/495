# 495

**495** encadre le développement logiciel assisté par IA avec une boucle de travail explicite, vérifiable et maîtrisée.

Le nom vient de la *constante de Kaprekar* pour les nombres à trois chiffres. À partir d'un nombre dont au moins deux chiffres sont différents, on ordonne ses chiffres dans les deux sens, on soustrait le plus petit nombre du plus grand, puis on répète l'opération en conservant les zéros initiaux. On atteint alors toujours 495, où le processus se stabilise (`954 − 459 = 495`). La convergence illustre l'ambition du projet : faire progresser une production variable vers un résultat dont la conformité peut être vérifiée. Elle ne promet pas que l'IA produira toujours le même code.

Le nom se prononce « quatre neuf cinq ». Les commandes `495 init`, `495 run` et `495 verify` sont des noms d'interface envisagés ; elles ne sont pas encore définies par un contrat CLI ni implémentées.

## État du projet

Le dépôt contient une **proposition de conception**, pas une implémentation. Les documents décrivent les contrats à implémenter ; ils n'apportent aucune preuve expérimentale de fiabilité.

495 applique à lui-même la disposition d'artefacts qu'il définit pour un projet cible : son propre travail est décrit sous `495/`. **`495/project.json` est l'état courant faisant foi** ; ce README en est un résumé.

| Incrément | Objet | Profil | Phase |
| --- | --- | --- | --- |
| `INC-0001` | Définir la base du harnais | `exploration` | `closed`, motif `exploration_complete` |
| `INC-0002` | Noyau du domaine — lot A | `standard` | `closed`, motif `superseded` |
| `INC-0003` | Noyau du domaine sous profil de bootstrap | `self-hosting-bootstrap` | `designing`, G0 et G1 franchies |

`INC-0001` est une exploration : elle a produit des connaissances et des décisions, sans code.

`INC-0002` a franchi G1 à la sixième évaluation — cinq refus, trente-quatre constats corrigés — puis a été clos. G2 y était bloquée : §6.8 exige un worker autorisé qui n'existera qu'aux lots D et E, et `REQ-11` interdit de changer le profil d'un incrément. Son `requirement_set` r7 reste scellé et **repris par référence** par `INC-0003` ; son verdict G1 n'est pas transféré.

`INC-0003` reprend le travail sous un profil dont les limites sont déclarées. Chaque décision de gate y porte le digest d'`ADR-0006 r6` comme `policy_digest`, et chaque phase enregistre son contrat scellé et sa tentative.

### Reprendre le travail

| Question | Où est la réponse |
| --- | --- |
| Où en est-on ? | `495/project.json` — phase, gates, tentatives, `state_version`, `known_gaps` |
| Qu'est-ce qui est approuvé ? | `495/approvals.json`, **seule autorité** sur l'état d'approbation |
| Quelles décisions précisent ou remplacent la conception ? | `495/decisions/` et son manifeste |
| Comment contrôler la cohérence publique des octets courants ? | `python3 tools/verify_state.py` — diagnostic partiel de bootstrap, sans autorité |

**Prochaine étape :** produire `design.md`, `contracts/` et `tasks.json` d'`INC-0003`, puis G2. G2 exigera une observation du dispositif hôte — identité et digest de configuration, refus réseau qualifié différentiellement contre un pair contrôlé, bornage de l'ensemble des chemins inscriptibles. Sans mécanisme d'immutabilité qualifié sur cette machine, G2 n'ouvrira qu'une tentative limitée aux contrôles de progression et **G4 restera `INDETERMINATE`**.

**Aucun de ces invariants n'est encore imposé par un contrôleur.** Les phases et les gates sont tenues à la main, et les enregistrements sous `495/` sont des conventions publiques lisibles. `tools/verify_state.py` compare les artefacts courants à leurs manifestes, vérifie l'adressage des objets et quelques liaisons structurelles ; il ne démontre ni l'exhaustivité de l'historique ni une propriété de sécurité. Un manifeste permet de constater une dérive entre les octets approuvés et ceux du disque ; il ne l'empêche pas. La conception l'énonce d'ailleurs elle-même en §4.1 : le magasin contrôlé ne doit pas être un répertoire du workspace.

## Principe

Selon son profil, un incrément peut parcourir tout le workflow de livraison ou être clos plus tôt. Pour un incrément de livraison, les spécifications définissent le résultat attendu, la conception structure la solution et les validations confrontent l'implémentation aux exigences. Les écarts observés orientent les corrections jusqu'à satisfaire les critères d'acceptation, ou jusqu'à rendre nécessaire une décision humaine.

Une case « tâche terminée » cochée par un agent reste une déclaration à vérifier : seul le contrôleur applique une transition, et une décision favorable exige des preuves rattachées aux entrées exactes qu'elles concernent.

## Séparation des responsabilités

| Partie | Responsabilité |
| --- | --- |
| **495** | Organiser le travail, préparer le contexte de l'IA, gérer les gates, conserver les preuves |
| **Application cible** | Spécifications, conception, code, tests et configuration de build |
| **Environnement d'exécution** | Exécuter les agents, builds et contrôles, derrière un adaptateur |
| **Fournisseur d'IA** | Produire ou examiner des propositions, via un adaptateur interchangeable |

La technologie interne retenue pour la future implémentation de 495 est Python, mais aucun langage, framework de test ou système de build n'est imposé à l'application cible. La conception prévoit que la distribution embarque son runtime, ses bibliothèques et ses ressources méthodologiques, sans exiger d'outil supplémentaire installé manuellement pour le noyau.

## Trois profils de workflow

| Profil | Source | Usage |
| --- | --- | --- |
| `standard` | §3.5 | Exige un worker autorisé et les trois capacités d'isolation de §6.8 |
| `exploration` | §3.1 | Produit des connaissances et des décisions ; peut être clos sans code |
| `self-hosting-bootstrap` | `ADR-0006 r6` | Construire 495 avant qu'un worker existe, avec ses limites déclarées |

Le profil de bootstrap n'est pas une exception au profil standard : §3.6 ne permet d'excepter qu'un défaut de baseline identifié, pas une obligation technique dure. C'est un profil distinct, lié par le **digest** de sa définition et non par son nom. Son extinction exige cumulativement un worker implémentant CSAP 1.0 et ayant passé son kit de conformité, les trois capacités d'isolation qualifiées séparément, et la compatibilité avec la toolchain concernée.

Un résultat obtenu sous ce profil est une preuve fonctionnelle de bootstrap. Il n'est jamais une preuve d'isolation ni de séparation du vérificateur, et il devra être réévalué sous le profil standard avant toute revendication d'auto-hébergement conforme.

## Composants

| Élément | Responsabilité |
| --- | --- |
| Workflow par incrément | Déterminer le travail actuellement permis et les livrables attendus |
| Artefacts versionnés | Exprimer le besoin, les décisions, les tâches et leurs dépendances |
| Noyau embarqué | Vérifier les observations et autoriser les transitions |
| Protocole d'adaptateurs | Accéder aux agents et environnements techniques |

## Workflow par incrément

Le workflow ordonne clarification, spécification, conception, implémentation et intégration. Un incrément parcourt les étapes exigées par son profil, avec des retours possibles, une traçabilité des modifications et la possibilité d'être clos avant l'implémentation. Les méthodes retenues sont l'Example Mapping, le BDD avec Gherkin lorsqu'il est pertinent, les ADR et les contrats d'interface.

Six progressions sont portées par `ApplyGateDecision`, après évaluation des gates G0 à G5 :

| Gate | Garantie | Limite |
| --- | --- | --- |
| **G0** — besoin cadré | Le travail est cadré | Sa valeur économique n'est pas démontrée |
| **G1** — spécification prête | Une spécification approuvée et vérifiable est disponible | Sa justesse ne découle pas du parseur |
| **G2** — contrat d'exécution prêt | Le contrat est scellé avant actuation | Aucun résultat futur n'est promis |
| **G3** — candidat recevable | Le candidat est évaluable | Il n'est pas encore correct |
| **G4** — candidat accepté | Les critères de la politique sont satisfaits sur ce candidat précis | Selon ces contrôles et ce périmètre uniquement |
| **G5** — intégré | L'état intégré correspond au candidat accepté | — |

La transition `accepted → integrating` est distincte : `StartIntegration` la porte sous précondition d'un G4 `PASS` courant sur le candidat exact. Les retours et les clôtures sont eux aussi portés par leurs commandes propres.

L'évaluation d'une gate est une fonction pure qui produit un verdict `PASS`, `FAIL` ou `INDETERMINATE`. L'absence de preuve, un résultat mal formé ou un contrôle obligatoire non exécuté ne valent jamais réussite.

## Invariants principaux

- Seul le contrôleur applique une transition ; ni un agent ni un adaptateur ne peut accepter un résultat.
- Un artefact scellé est immuable ; toute modification crée une nouvelle révision.
- La validité d'une preuve dépend des digests de ses entrées, pas seulement de son ancien statut « réussi ».
- Le candidat accepté est le candidat vérifié.
- Un jugement favorable de modèle ne neutralise jamais une violation déterministe obligatoire.
- Une gate structurelle ne prétend pas prouver la pertinence métier d'un document.

Le modèle de menace considère le code et les sorties de l'agent comme non fiables. Le contrôleur, son magasin d'objets, la configuration de confiance et les workers autorisés appartiennent au périmètre de confiance.

## Protocole d'adaptateurs

La conception définit quatre ports pour isoler 495 des technologies cibles : `AgentPort`, `ExecutionPort`, `RepositoryPort` et `ApprovalPort`. Les adaptateurs placés derrière ces ports échangent avec 495 selon CSAP 1.0, un protocole applicatif proposé par le projet, avec des enveloppes JSON versionnées et des opérations asynchrones idempotentes.

Un adaptateur de projet traduira les capacités demandées — construire, exécuter les tests d'acceptation, vérifier l'architecture et les contrats, produire un candidat — en opérations adaptées à sa technologie. Il retournera un résultat normalisé identifiant le contrôle, les exigences couvertes, les digests des entrées, la version du vérificateur, le statut et les preuves.

## Organisation du dépôt

`495/` suit la disposition décrite en section 4.1 de la conception : identité du projet, exigences intégrées, décisions et dossiers de changement.

| Chemin | Contenu |
| --- | --- |
| [`495/project.json`](495/project.json) | Identité du projet et état des incréments |
| [`495/changes/INC-0001/proposal.md`](495/changes/INC-0001/proposal.md) | Objectif et périmètre : méthodes retenues et socle technique embarquable |
| [`495/changes/INC-0001/design.md`](495/changes/INC-0001/design.md) | Conception du harnais : invariants, workflow, noyau, protocole |
| [`495/changes/INC-0001/manifest.json`](495/changes/INC-0001/manifest.json) | Digests SHA-256 des artefacts scellés de l'incrément |
| [`495/changes/INC-0002/requirements.json`](495/changes/INC-0002/requirements.json) | 20 exigences, 98 critères, vocabulaire normatif et oracles — scellé r7, repris par `INC-0003` |
| [`495/changes/INC-0002/gates/`](495/changes/INC-0002/gates/) | Six évaluations de G1 : entrées, obligations, raisons et constats |
| [`495/changes/INC-0003/`](495/changes/INC-0003/) | Cadrage, contrats de phase scellés, tentatives, observations et gates |
| [`495/decisions/`](495/decisions/) | Six ADR précisant ou remplaçant certains passages de la conception scellée, dont le profil de bootstrap |
| [`495/approvals.json`](495/approvals.json) | Approbations et refus, chacun sur une référence complète |
| `495/objects/sha256/` | Octets conservés, adressés par leur digest ; la révision 1 du requirement set reste perdue et documentée comme telle |
| [`tools/verify_state.py`](tools/verify_state.py) | Diagnostic partiel de cohérence du bootstrap, sans autorité — `python3 tools/verify_state.py` |
| [`docs/presentation.md`](docs/presentation.md) | Origine du nom et intention du projet |

Les artefacts publics encore absents sont `495/specs/` — aucune exigence intégrée —, puis `design.md`, les contrats d'interface sous `contracts/` et `tasks.json` d'`INC-0003`. Le répertoire `contracts/` contient déjà les contrats d'exécution des phases précédentes. `features/` restera absent : les règles du lot A sont des invariants, des ensembles clos et des tables de transitions, que Gherkin exprime mal — `requirements.json` motive ce choix.

`manifest.json`, `gates/`, `attempts/`, `observations/`, `objects/` et `approvals.json` sont des extensions de bootstrap, pas des chemins définis par la conception.

Ces conventions sont exportables et la sécurité ne repose pas sur elles : la configuration exécutoire reste une copie approuvée conservée par le contrôleur.

## Garanties non revendiquées

Déterminisme du modèle, exhaustivité sémantique des tests, sandbox universel sans dépendances système, identité humaine forte en mode local, immunité à un administrateur du contrôleur, atomicité multi-dépôts, équivalence parfaite des environnements de production et de test.

## Références

- [GitHub Spec Kit](https://github.com/github/spec-kit) — séparation des artefacts de spécification, plan et tâches
- [OpenSpec](https://github.com/Fission-AI/OpenSpec) — organisation du travail par proposition de changement
- [BDD — Cucumber](https://cucumber.io/docs/bdd/), [Gherkin](https://github.com/cucumber/gherkin), [Cucumber Messages](https://github.com/cucumber/messages)
- [ADR](https://adr.github.io/) et [OpenAPI](https://www.openapis.org/what-is-openapi)
- [Principes Agile](https://agilemanifesto.org/principles.html)
