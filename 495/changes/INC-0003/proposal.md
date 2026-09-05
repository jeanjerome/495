# INC-0003 — Noyau du domaine sous profil de bootstrap

Proposition de cadrage du lot A. Autorité de cadrage : responsable du projet 495.

Produit sous la tentative `ATT-INC-0003-0001`, contrat de phase `INC-0003/contract-clarification` r1. Le verdict de gate et le scellement de ce document lui sont extérieurs.

## Objectif

Reprendre l'objectif d'`INC-0002` — implémenter le module `domain` de §5.1 — sous le profil `self-hosting-bootstrap`, dont les limites sont déclarées.

`INC-0002` a franchi G1 sous le profil `standard`, mais G2 y est bloquée : §6.8 exige un worker autorisé, qui relève des lots D et E. `REQ-11`, scellée, interdit de changer le profil d'un incrément après sa création. La reprise passe donc par un incrément neuf, non par une modification du précédent.

## Profil

Cet incrément est lié à la référence complète du profil, et non à son nom :

| Champ | Valeur |
| --- | --- |
| `artifact_id` | `ADR-0006` |
| `revision` | 6 |
| `kind` | `decision` |
| `schema_version` | `0.1-draft` |
| `digest` | `sha256:7ac71f73087f4122eb55b69b393970502b18d61fc6e87e602275857ed0e52ed2` |

Chaque décision de gate de cet incrément porte ce digest comme `policy_digest`. Une révision ultérieure du profil ne s'y appliquera pas.

## Périmètre

Le périmètre technique est **identique** à celui d'`INC-0002` : références et identité, types d'artefacts, phases et statut, commandes, obligations, liens et invalidation. Il n'est pas réécrit ici.

Les exigences sont **reprises par référence**, non recopiées :

| Champ | Valeur |
| --- | --- |
| `artifact_id` | `INC-0002/requirements` |
| `revision` | 7 |
| `kind` | `requirement_set` |
| `digest` | `sha256:f503f82932ab6f6b5c172c5d7aeabb24cdf36291e2e50c0c3a207d79bb622c92` |

Ces octets sont scellés et inchangés. Les vingt exigences et leurs quatre-vingt-dix-huit critères portent sur le modèle du domaine ; aucun ne dépend du profil d'exécution.

## Ce que le changement de profil modifie

Rien dans les exigences. Tout dans ce qu'un résultat autorise à conclure.

| Aspect | Sous `standard` | Sous `self-hosting-bootstrap` |
| --- | --- | --- |
| Oracles des exigences | Inchangés | Inchangés |
| G2 | Bloquée faute de worker autorisé | Franchissable, tentative limitée aux contrôles de progression si l'hôte n'offre pas d'immutabilité |
| G3 | — | Franchissable |
| G4 | — | `INDETERMINATE` sans mécanisme d'immutabilité qualifié |
| Portée d'un résultat vert | Preuve d'acceptation | Preuve fonctionnelle de bootstrap ; jamais une preuve d'isolation ni de séparation du vérificateur |

L'incrément peut donc produire et mesurer le noyau du domaine. Il ne peut pas revendiquer une acceptation tant qu'aucun mécanisme d'immutabilité n'est qualifié, ni une conformité au profil standard avant requalification.

## Hors-périmètre

Identique à `INC-0002` : évaluation de gate et politique bornée au lot B, persistance au lot C, protocole CSAP au lot D, analyse Gherkin au lot F. S'y ajoutent le choix et la qualification d'un dispositif hôte, qui relèvent du contrat d'exécution de G2 et non du cadrage.

## Relation à INC-0002

`INC-0003` **supersede** `INC-0002`. La décision de gate `GD-INC-0002-G1-6` n'est ni réécrite ni invalidée : elle reste attachée à la révision 7 qu'elle évaluait, sous le profil `standard`. Elle n'est pas transférée à cet incrément.

`INC-0002` est clos avec le motif `superseded`, sans reconstitution rétroactive de la tentative qui n'y a jamais été enregistrée.

## Questions ouvertes

| ID | Question | Bloque |
| --- | --- | --- |
| Q-16 | `APP-0008` approuve la référence `INC-0002/requirements` r7. Ces octets étant inchangés, cette approbation satisfait-elle `OBL-G1-05` pour le G1 d'`INC-0003` ? Ou faut-il réémettre le requirement set sous l'identifiant `INC-0003/requirements`, ce qui produirait une référence neuve exigeant une approbation neuve ? | G1 |

`REQ-16` attache une approbation à une référence complète, pas à un incrément : l'argument existe dans les deux sens. La question porte sur l'identité logique de l'artefact, `artifact_id` étant préfixé par l'incrément qui l'a produit.

Cette question ne bloque pas G0 : elle porte sur la disponibilité d'une approbation de spécification, non sur le cadrage.
