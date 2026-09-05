# ADR-0005 — Commande portant chaque transition de phase

Révision 2. **Statut : proposé.** Requiert une approbation propre, sur sa référence complète.

La révision 1 laissait `accepted → integrating` sans commande, comptait sept franchissements de gate là où il y en a six, et ne déclarait pas remplacer l'ensemble clos des onze commandes.

## Contexte

REQ-07 exige que les préconditions de la commande portant une transition soient satisfaites. Seules les sept arêtes de clôture nommaient une commande. Par ailleurs, ADR-0001 règle le sort de la tentative lors d'un retour post-G2 sans qu'aucune arête de ce type figure dans la table.

## Décision proposée

### Une douzième commande

`SRC-DESIGN §3.4` énumère onze commandes. Aucune ne porte `accepted → integrating` : le diagramme de §3.3 trace cette arête sans étiquette de gate. `ApplyGateDecision` ne convient pas, puisqu'aucune décision de gate ne porte cette transition ; sortir la transition du domaine contredirait INV-01, qui réserve l'application d'une transition au contrôleur.

**L'ensemble clos des commandes passe donc de onze à douze.** La douzième est `StartIntegration`.

| Aspect | Contenu |
| --- | --- |
| Préconditions | Phase `accepted` ; un `PASS` G4 courant sur le candidat exact ; une destination attendue ; aucune intégration non réconciliée |
| Effet | Enregistre l'intention d'intégration et fait passer la phase à `integrating` |
| Hors de son périmètre | L'application de G5, qui reste portée par `ApplyGateDecision` après réception du reçu d'intégration |

L'intention durable précédant l'envoi suit `SRC-DESIGN §5.5` ; la précondition d'absence d'intégration non réconciliée suit INV-09.

### Liaison des arêtes

| Arêtes | Commande |
| --- | --- |
| Les six franchissements de gate, G0 à G5 | `ApplyGateDecision` |
| `accepted → integrating` | `StartIntegration` |
| `specifying → clarifying`, `designing → specifying` | `ReviseIncrement` |
| `verifying → implementing` | `StartAttempt`, sous le contrat inchangé |
| Les huit retours de révision | `ReviseIncrement` |
| Les sept clôtures | `CloseIncrement` |

### Retours de révision

`SRC-DESIGN §3.4` autorise `ReviseIncrement` depuis tout incrément non intégré et non clos. Huit arêtes en découlent, vers la phase de l'artefact révisé, terminant la tentative courante avec le motif `revision_requested` :

- depuis `implementing` et `verifying`, vers `specifying` et `designing` ;
- depuis `accepted` et `integrating`, vers `specifying` et `designing`.

Depuis `integrating`, une intention d'intégration a été enregistrée et un effet externe peut être en vol. `ReviseIncrement` y porte donc la précondition supplémentaire qu'aucun effet externe ne reste non réconcilié, par cohérence avec INV-09 et avec la précondition de `CloseIncrement`.

## Conséquences

- La table compte vingt-cinq arêtes, toutes liées à une commande. `vocabulary.phase_transitions.closed` repasse à vrai.
- `vocabulary.commands` compte douze valeurs et remplace l'énumération de §3.4. REQ-12 porte sur douze commandes.
- Q-12 est close ; REQ-07 cesse d'être bloquée.
- Cette décision n'est pas approuvée par l'approbation d'un autre artefact : REQ-16 attache une approbation à une référence complète, et une approbation transitive la contournerait.
