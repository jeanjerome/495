# ADR-0003 — Transitions de clôture

Statut : accepté. Complète la table de transitions de `SRC-DESIGN §3.3`.

## Contexte

Le diagramme de §3.3 ne comporte aucune arête vers `closed`, alors que `CloseIncrement` figure en §3.4 et que `closed` figure dans l'énumération des phases. La table est donc incomplète, et l'oracle de REQ-07 — « toute transition absente de la table est refusée » — inapplicable.

## Décision

`integrated` est la phase terminale de réussite ; `closed` la phase terminale d'arrêt sans intégration.

| Phase de départ | `CloseIncrement` |
| --- | --- |
| Toute phase non terminale | Autorisée avec un motif valide de §3.4 |
| `integrated` | Refusée |
| `closed` | Refusée, sans mutation |

Une clôture termine la tentative courante s'il en existe une, avec le motif `increment_closed` d'ADR-0002, et conserve tout l'historique.

L'oracle de REQ-07 devient : une transition est acceptée si et seulement si elle figure dans la table **et** que les préconditions de sa commande sont satisfaites. Dans tous les autres cas, refus sans mutation.

## Conséquences

- Sept arêtes vers `closed` sont ajoutées, depuis `clarifying`, `specifying`, `designing`, `implementing`, `verifying`, `accepted` et `integrating`.
- La table de transitions devient close : `vocabulary.phase_transitions.closed` passe à vrai.
- REQ-07 et REQ-10 cessent d'être bloquées.
