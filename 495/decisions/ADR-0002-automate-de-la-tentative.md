# ADR-0002 — Automate minimal de la tentative

Révision 5. Complète `SRC-DESIGN §3.1` et respecte `SRC-DESIGN §3.7`.

La révision 3 laissait une tentative de phase sans déclencheur de terminaison lorsqu'elle réussit. La révision 4 comblait ce manque mais gardait une contradiction de concurrence : la tentative d'implémentation restait active pendant `verifying`, où une tentative de revue peut être créée sous son propre contrat, alors que la conséquence interdisait deux tentatives de phases différentes actives simultanément.

## Contexte

La conception définit une `Attempt` liée à un contrat scellé, sans fixer ses états ni ses transitions. Les statuts de §6.3 sont ceux d'une opération d'adaptateur et relèvent du lot D.

## Décision

### Création

Une tentative est créée lorsque son **contrat de phase** est scellé et que la **condition d'entrée** de cette phase est satisfaite. Deux champs distincts, car une condition d'entrée n'est pas toujours une gate.

| Phase de la tentative | `entry_gate` | `required_contract` |
| --- | --- | --- |
| Clarification | aucune | Contrat de clarification ; incrément et brief initial enregistrés |
| Spécification | G0 | Contrat de spécification |
| Conception | G1 | Contrat de conception |
| Implémentation | G2 | Contrat d'implémentation complet |
| Revue | aucune | Contrat de revue à entrées scellées |

### États et déclencheurs de transition

| État | Signification | Transitions |
| --- | --- | --- |
| `running` | Tentative en cours sous un contrat scellé | `suspended`, `finished` |
| `suspended` | Exécution arrêtée, contrat conservé. **Non terminal** | `running`, `finished` |
| `finished` | Tentative définitivement terminée | Aucune |

| Transition | Déclencheur |
| --- | --- |
| `running → suspended` | `ApplyGateDecision` appliquant G3 avec `PASS`, pour la tentative d'implémentation ; ou suspension explicite de l'exécution |
| `suspended → running` | `StartAttempt` après un G4 `FAIL`, sous le contrat inchangé ; ou reprise explicite |
| `running → finished`, `suspended → finished` | Selon la table des motifs de terminaison |

### Terminaison

Six motifs, chacun avec **exactement un déclencheur déclaré** : un motif sans déclencheur serait inatteignable, et une tentative sans motif applicable resterait indéfiniment active.

| Motif | Nature | Déclencheur |
| --- | --- | --- |
| `phase_completed` | Commande | Sortie normale de la tentative, selon la table ci-dessous |
| `integration_succeeded` | Commande | `ApplyGateDecision` appliquant G5 avec le verdict `PASS` |
| `revision_requested` | Commande | `ReviseIncrement` |
| `increment_closed` | Commande | `CloseIncrement` |
| `budget_exhausted` | Observation | Budget de tentatives fixé par le contrat atteint, §6.7 |
| `definitive_failure` | Observation | Règle d'arrêt du contrat atteinte, aucune correction autorisée, §6.7 |

**Sortie normale d'une tentative**, par phase :

| Phase de la tentative | Déclencheur de sortie | Motif |
| --- | --- | --- |
| Clarification | `ApplyGateDecision` appliquant G0 avec `PASS` | `phase_completed` |
| Spécification | `ApplyGateDecision` appliquant G1 avec `PASS` | `phase_completed` |
| Conception | `ApplyGateDecision` appliquant G2 avec `PASS` | `phase_completed` |
| Revue | `SealArtifact` sur le rapport de revue | `phase_completed` |
| Implémentation | `ApplyGateDecision` appliquant G5 avec `PASS` | `integration_succeeded` |

### Cycle de la tentative d'implémentation

Elle ne se termine qu'à l'intégration, mais n'est pas `running` tout du long :

| Événement | État après |
| --- | --- |
| G2 `PASS`, contrat scellé | `running` |
| G3 `PASS` | `suspended` — le candidat est capturé, la revue peut s'exécuter |
| G4 `FAIL` puis `StartAttempt` | `running` — correction sous le contrat inchangé |
| G4 `PASS` | `suspended` |
| G5 `PASS` | `finished`, motif `integration_succeeded` |

Un verdict `FAIL` de gate ne termine pas une tentative : une correction reste possible sous le même contrat. Changer ce contrat impose une nouvelle tentative.

## Conséquences

- Aucune tentative ne peut rester active sous un contrat périmé après le franchissement de sa gate de sortie.
- **Deux tentatives de phases différentes ne sont jamais à l'état `running` simultanément sur la même révision.** Une tentative `suspended` reste non terminale : la tentative d'implémentation coexiste avec la tentative de revue, sans être active.
- L'automate est orthogonal à la phase de l'incrément et au statut opérationnel : trois dimensions indépendantes.
- Les statuts d'opération de §6.3 restent au lot D.

L'énumération des motifs est fixée ici parce que la conception ne la donne pas. `budget_exhausted` suit §6.7 ; `phase_completed` et la suspension à G3 comblent les manques relevés en revue.
