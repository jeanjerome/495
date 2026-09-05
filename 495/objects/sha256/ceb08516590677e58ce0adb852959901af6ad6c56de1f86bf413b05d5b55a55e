# ADR-0001 — La commande portant un retour décide du sort de la tentative

Révision 4. Remplace la formulation « termine ou suspend » de `SRC-DESIGN §3.3`.

La révision 1 appliquait la terminaison à tout retour, correction comprise. La révision 2 indexait la règle sur la position par rapport à G2, laissant sans réponse les retours antérieurs. La révision 3 corrigeait ce point mais comptait huit arêtes portées par `ReviseIncrement` alors que la table en contient dix : les deux retours de type `return` avaient été cités sans être comptés.

## Contexte

La conception écrit qu'après G2, une modification du contrat « termine ou suspend la tentative courante et ouvre une nouvelle révision ». Deux comportements incompatibles, sans règle de choix.

## Décision

Le discriminant n'est ni la direction du retour ni sa position par rapport à G2, mais **la commande qui le porte**.

La table contient **onze arêtes de retour**, partitionnées ainsi :

| Commande | Arêtes | Effet sur la tentative courante |
| --- | --- | --- |
| `ReviseIncrement` | **Dix** : deux de type `return` — `specifying → clarifying`, `designing → specifying` — et huit de type `revision`, depuis `implementing`, `verifying`, `accepted` et `integrating` vers `specifying` et `designing` | Terminée, motif `revision_requested` |
| `StartAttempt` | **Une** : `verifying → implementing` | Conservée : le contrat est inchangé, c'est une correction |

La suspension explicite d'une exécution conserve elle aussi la tentative et son contrat scellé ; la reprise utilise exactement ce contrat.

`ReviseIncrement` ouvre une révision de travail dans tous les cas et change le contrat de la phase visée. Une nouvelle tentative attend la validation de ce nouveau contrat par la condition d'entrée de sa phase.

## Conséquences

- La règle couvre les dix arêtes portées par `ReviseIncrement`, quelle que soit leur position par rapport à G2 et quel que soit leur type.
- `ReviseIncrement` est le déclencheur unique de `revision_requested`, conformément à ADR-0002.
- L'oracle de REQ-08 partitionne onze arêtes : dix terminent la tentative, une la conserve.
- Cohérent avec §3.5, qui prévoit qu'un refus de gate est corrigible, et avec ADR-0002, où un `FAIL` ne termine rien.
