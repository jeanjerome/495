# INC-0002 — Noyau du domaine

Proposition de cadrage du lot A. Autorité de cadrage : responsable du projet 495.

Le verdict de gate et le scellement de ce document lui sont extérieurs, pour éviter qu'un artefact contienne la décision qui porte sur ses propres octets.

## Objectif

Implémenter le module `domain` défini en §5.1 de la conception : références, états, obligations et décisions, sans accès réseau, filesystem ni SDK d'agent. Ce module est la dépendance commune des lots suivants — il fixe les types que la politique, la persistance et le protocole manipuleront.

Correspond au lot A de §10, dont le critère de sortie est : *cas de transitions et d'obsolescence testés sans agent*.

Entrée scellée : `INC-0001`, manifeste `sha256:917e2ed9…`. Une correction de la conception ne se fait pas en éditant `INC-0001/design.md`, mais par un ADR ou un incrément qui le remplace.

## Périmètre

| Sujet | Référence | Contenu attendu |
| --- | --- | --- |
| Références et identité | §4.3 | `artifact_id`, révision monotone, `kind`, `schema_version`, `digest` ; refus de `latest` dans un contrat scellé |
| Types d'artefacts | §4.2 | Les treize types et leur contenu minimum, comme vocabulaire du domaine |
| Phases et statut | §3.3 | Enum de phase, enum de statut opérationnel, transitions autorisées et retours |
| Commandes | §3.4 | Les onze commandes, leurs préconditions et leur effet sur l'état |
| Obligations | §3.5 | Ce qu'une gate exige, exprimé comme obligations nommées et vérifiables |
| Liens et invalidation | §4.4 | Liens typés, acyclicité de `depends_on`, calcul de l'obsolescence |

## Hors-périmètre

| Sujet | Renvoi |
| --- | --- |
| `evaluate_gate` et politique JSON bornée | Lot B — §5.2, §5.3 |
| Journal, magasin d'objets, projection SQLite, reprise | Lot C — §5.5 |
| Protocole CSAP, adaptateurs, kit de conformité | Lot D — §6 |
| Validation par JSON Schema | Lot B |
| Analyse Gherkin, templates d'artefacts | Lot F |
| Calcul d'un digest à partir de fichiers | Infrastructure : le domaine porte la valeur, il ne lit pas le disque |
| Tout appel d'agent ou d'environnement d'exécution | Interdit au module `domain` par §5.1 |

## Règles

| ID | Règle | Source |
| --- | --- | --- |
| R-01 | Une référence utilisée dans un contrat scellé porte un digest ; `latest` est refusé | §4.3 |
| R-02 | La révision est monotone par `artifact_id` | §4.3 |
| R-03 | Un artefact scellé est immuable ; une modification produit une nouvelle révision | INV-05 |
| R-04 | Une approbation vise un digest, jamais un chemin ; une nouvelle révision ne peut pas réutiliser l'approbation de l'ancienne, qui reste conservée | §4.4 |
| R-05 | Le graphe `depends_on` est acyclique | §4.4 |
| R-06 | `related_to` est informatif et n'entraîne aucune invalidation | §4.4 |
| R-07 | Phase et statut opérationnel sont indépendants : `blocked` n'efface pas la phase | §3.3 |
| R-08 | Un retour avant G2 crée une révision de travail ; après G2, une modification du contrat termine ou suspend la tentative courante | §3.3 |
| R-09 | Un incrément intégré n'est pas rouvert ; son évolution passe par un nouvel incrément | §3.3 |
| R-10 | Une clôture porte un motif parmi `abandoned`, `superseded`, `budget_exhausted`, `exploration_complete`, `invalid_protocol` | §3.4 |
| R-11 | Le profil de workflow est fixé au départ ; on ne bascule pas vers `exploration` pour contourner une gate | §3.1 |
| R-12 | La validité d'une preuve dépend des digests de ses entrées, pas de son ancien statut | INV-06 |

## Exemples

Ils constituent le matériau des cas de transition et d'obsolescence exigés par le critère de sortie.

| Situation | Résultat attendu |
| --- | --- |
| La révision 2 d'une exigence est créée alors qu'une approbation vise la révision 1 | L'approbation n'est pas applicable à la révision 2 ; celle sur la révision 1 est conservée |
| Une décision de conception change | G2 et les contrôles concernés deviennent obsolètes ; G1 reste valide |
| Une note `related_to` non consommée change | Aucune preuve exécutoire invalidée |
| Un incrément en `implementing` passe au statut `blocked` | La phase reste `implementing` |
| Un lien `depends_on` fermerait un cycle | Refusé |
| `ReviseIncrement` sur un incrément `integrated` | Refusé |
| Une référence sans digest est placée dans un contrat scellé | Refusée |
| Le candidat change après un résultat vert | Les résultats liés à l'ancien candidat ne sont plus réutilisables |
| La base de destination avance après G4 | L'incrément reste accepté, mais l'intégration est bloquée |
| Une exigence obligatoire est modifiée | G1 et tous ses dépendants sont à réévaluer |

## Questions résolues

Résolues par le responsable du projet. Une proposition qui n'a pas été retenue est remplacée par la décision, elle n'est pas conservée comme alternative.

| ID | Question | Décision |
| --- | --- | --- |
| Q-01 | Version minimale de Python ? | **3.12.** Aucune dépendance externe dans le domaine |
| Q-02 | `Attempt` appartient-il au lot A ? | Oui pour son identité et son cycle de vie ; son contrat relève du lot B et son opération d'adaptateur du lot D |
| Q-03 | L'invalidation est-elle calculée par le domaine ? | Oui, comme fonction pure. Le contrôleur applique le résultat, il ne le recalcule pas |
| Q-04 | Les obligations de gate sont-elles des données du domaine ou de la politique ? | Le domaine définit le type `Obligation` et la notion de profil ; le contenu des profils arrive au lot B |
| Q-05 | Nom du paquet et disposition ? | Disposition `src/`, paquet importable distinct du nom de distribution, un module par sujet de §5.1 |
| Q-06 | Le domaine refuse-t-il à la construction ou valide-t-il à la demande ? | Refus à la construction pour les invariants structurels ; la validation dépendant d'entrées externes relève du lot B |
| Q-07 | Que faire des types d'artefacts dont le contenu appartient à des lots ultérieurs ? | Nommer les treize types et fixer leur identité ; ne pas modéliser leur contenu avant l'ouverture du lot correspondant |

Aucune question n'a été exclue du périmètre sans réponse.
