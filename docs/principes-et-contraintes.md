# Principes et contraintes de 495

## Statut

Ce document gouverne les décisions techniques du projet. Une règle plus
spécifique peut s’en écarter lorsqu’elle explique le besoin concret qui le
justifie.

Les termes employés sont :

| Statut | Signification |
| --- | --- |
| **Obligatoire** | Protège une propriété nécessaire du comportement courant. |
| **Défaut** | Choix recommandé, révocable avec une justification concrète. |
| **Conditionnelle** | S’applique seulement lorsqu’un usage ou un risque identifié la déclenche. |
| **Retirée** | Ne gouverne plus le projet. |

## Évaluer une contrainte

Une contrainte n’est adoptée que si les questions suivantes ont une réponse
satisfaisante :

1. Quel comportement ou risque concret protège-t-elle ?
2. Quel mécanisme l’applique ou quel oracle la vérifie ?
3. Son coût est-il proportionné à la fréquence et à l’impact du risque ?
4. Répond-elle à un usage observé plutôt qu’à un scénario hypothétique ?

Une propriété non vérifiée peut être signalée comme limite. Elle ne devient pas
une condition artificielle de réussite.

## Gouvernance

| Règle | Statut | Application |
| --- | --- | --- |
| Demande explicite avant une modification | **Obligatoire** | Elle définit l’intention et le périmètre. |
| Autorisation par digest pour modifier le dépôt | **Retirée** | Elle dupliquait la demande pour des changements locaux et réversibles. |
| Confirmation d’un effet externe, destructif ou difficilement réversible | **Obligatoire** | Elle est distincte de l’autorisation d’éditer. |
| Acceptation humaine d’un résultat | **Conditionnelle** | Elle est utile pour une livraison ou une décision formelle. |
| Une seule autorité par information | **Obligatoire** | Les copies calculées ne deviennent pas des registres concurrents. |

## Documentation et historique

| Règle | Statut | Application |
| --- | --- | --- |
| Documentation conforme au comportement courant | **Obligatoire** | Un mécanisme retiré n’est pas présenté comme disponible. |
| Archive fonctionnelle conservée dans l’arbre courant | **Retirée** | Git porte déjà l’historique du projet. |
| Rapports d’exécution versionnés | **Retirée** | Ils sont générés à la demande et ignorés par Git. |
| Documentation en français | **Défaut** | Une interface ou un écosystème peut imposer une autre langue. |
| Commentaires centrés sur le comportement | **Défaut** | Ils expliquent ce qui doit rester vrai. |
| Format conventionnel des commits | **Défaut** | Il reste recommandé sans constituer une propriété du produit. |

## Exécution et rapports

| Règle | Statut | Application |
| --- | --- | --- |
| Contrat formel pour toute commande locale | **Retirée** | Les commandes ordinaires peuvent être lancées directement. |
| Configuration explicite d’une exécution à rapporter | **Conditionnelle** | Elle identifie les commandes et les fichiers concernés. |
| Commandes exécutées sans shell | **Défaut** | Une liste d’arguments évite les expansions implicites. |
| Timeout par commande | **Obligatoire** | Dans le lanceur, il borne une exécution bloquée. |
| Une exécution par commande et par rapport | **Obligatoire** | Le rapport ne sélectionne pas une tentative favorable. |
| Manifeste et digest des fichiers contrôlés | **Obligatoire** | Dans un rapport, ils relient le résultat au contenu observé. |
| Stabilité de la configuration et des fichiers pendant l’exécution | **Obligatoire** | Dans un rapport, sinon le résultat ne décrit pas les entrées initiales. |
| Rapport créé automatiquement à chaque exécution | **Retirée** | `--report` exprime le besoin de conservation. |
| Snapshot de tout le workspace | **Retirée** | Il est coûteux, incomplet et distinct du contenu contrôlé. |
| `allowed_workspace_writes` présenté comme confinement | **Retirée** | Une comparaison après coup n’empêche aucune écriture. |
| Résultat fonctionnel couplé à une assurance de sécurité | **Retirée** | Ces questions sont indépendantes. |

## Environnement, réseau et dépendances

| Règle | Statut | Application |
| --- | --- | --- |
| Environnement courant hérité | **Défaut** | Il correspond à l’usage local ordinaire. |
| Environnement hermétique | **Conditionnelle** | Une revendication de reproductibilité doit le justifier et le vérifier. |
| `TMPDIR` imposé par le contrat | **Retirée** | Les tests choisissent leurs propres emplacements temporaires. |
| Interdiction globale du réseau | **Retirée** | Elle empêchait des intégrations légitimes sans fournir d’isolation. |
| Besoin de réseau, secret ou service externe annoncé | **Obligatoire** | Il permet une décision informée avant l’effet. |
| Restriction réseau technique | **Conditionnelle** | Elle exige un risque identifié et un mécanisme vérifiable. |
| Bibliothèque standard uniquement | **Retirée** | L’absence de dépendance n’est pas une garantie suffisante. |
| Dépendance tierce évaluée et déclarée | **Défaut** | Sa valeur, sa maintenance et sa licence doivent être acceptables. |
| Verrouillage des dépendances | **Conditionnelle** | Il est requis lorsqu’une application doit être reproductible. |

## Architecture et données

| Règle | Statut | Application |
| --- | --- | --- |
| Architecture en couches imposée avant l’usage | **Retirée** | La structure découle du premier parcours vertical. |
| Domaine sans entrée-sortie | **Défaut** | Utile lorsque de vraies règles métier doivent être isolées. |
| Immutabilité universelle | **Retirée** | Elle ajoute du cérémonial aux objets qui n’en bénéficient pas. |
| Résultats métier explicites | **Défaut** | Les exceptions restent adaptées aux erreurs techniques inattendues. |
| Champs inconnus refusés | **Défaut** | Ce choix concerne surtout les frontières versionnées ; une interface interne peut évoluer plus librement. |
| Sérialisation canonique | **Conditionnelle** | Elle est utile lorsqu’un digest ou une signature dépend des octets. |
| `pickle` pour des données externes ou persistées | **Retirée** | Un format sûr et interopérable est requis à ces frontières. |
| SQLite pour une persistance locale transactionnelle | **Défaut** | Il remplace avantageusement un journal fichier construit sur mesure. |

## Modèles écartés du socle

Les mécanismes suivants ne sont plus considérés comme le modèle par défaut de
495 :

- cycle fermé de phases, gates, tentatives et approbations ;
- taxonomie exhaustive des commandes et artefacts ;
- graphe général d’invalidation ;
- magasin d’objets adressé par digest et journal JSONL chaîné ;
- version globale partagée entre tous les travaux ;
- protocole d’adaptateurs à ports et opérations fixés ;
- adaptateur simulé et kit de conformité sans intégration réelle ;
- orchestrateur reliant ces composants sans interface utilisateur.

Ils pourront inspirer une future implémentation, mais ne seront pas réintroduits
sans parcours réel démontrant leur nécessité.

## Socle actuel

Le socle obligatoire se limite à :

1. une demande utilisateur explicite pour le travail ;
2. une documentation qui décrit honnêtement le comportement disponible ;
3. des contrôles pertinents avec un résultat observable ;
4. pour un rapport formel, une configuration, un manifeste, des digests et des
   commandes bornées par un timeout ;
5. aucune revendication de sécurité sans mécanisme et preuve correspondants.
