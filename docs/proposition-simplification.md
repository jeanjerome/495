# Simplification du bootstrap de 495

Statut : adoptée pour le bootstrap minimal. Ce document explique la décision ;
`docs/implementation.md` et `bootstrap/contract.json` portent l’état actif.

## Décision

Remplacer le bootstrap documentaire actuel par un mécanisme minimal fondé sur trois éléments :

1. un document de travail lisible par un humain ;
2. un contrat d’exécution concret et directement exécutable ;
3. un rapport généré pour chaque exécution contrôlée.

Les mécanismes avancés — magasin d’objets, scellement individuel, références à cinq champs, automate des tentatives, gates multiples et journal de commandes — ne sont pas supprimés de la conception cible. Leur application est différée jusqu’à ce qu’un contrôleur puisse réellement les imposer.

Pendant le bootstrap, Git conserve l’historique des fichiers. Cette utilisation n’est pas présentée comme une garantie d’immutabilité ou d’authenticité.

## Constat

Le bootstrap actuel demande de maintenir manuellement plusieurs représentations du même état :

- état global du projet ;
- manifeste de l’incrément ;
- contrat de phase ;
- tentative active ;
- décisions de gate ;
- approbations ;
- copies adressées par digest ;
- résumés de reprise.

Cette duplication crée trois difficultés.

Premièrement, chaque changement utile entraîne plusieurs mutations de registre et plusieurs recoupements de digest. La maintenance du protocole devient plus importante que la production contrôlée.

Deuxièmement, les contrôles intermédiaires valident surtout la cohérence des documents entre eux. Ils ne garantissent pas que le contrat final soit effectivement réalisable sur l’hôte disponible.

Troisièmement, les règles du bootstrap peuvent empêcher d’obtenir les preuves qu’elles exigent. La qualification réseau en fournit un exemple : une branche doit réussir un accès réseau alors que toute actuation gouvernée interdit cet accès.

Le résultat est formellement détaillé, mais inexécutable sans interprétation supplémentaire.

## Objectifs

Le bootstrap simplifié doit :

- permettre de commencer une implémentation après une décision humaine compréhensible ;
- fixer les droits, les limites et les commandes avant l’exécution ;
- rattacher chaque résultat au contrat et au candidat réellement utilisés ;
- distinguer un résultat de progression d’une preuve d’acceptation ;
- rendre les blocages matériels visibles avant le début de l’implémentation ;
- éviter toute synchronisation manuelle de représentations redondantes ;
- rester suffisamment simple pour être compris en moins de quinze minutes.

Il ne cherche pas encore à fournir :

- une preuve opposable à un tiers ;
- un historique inviolable ;
- une isolation qu’aucun dispositif technique n’applique ;
- un contrôleur transactionnel ou distribué ;
- une reproduction bit à bit de l’environnement complet.

## Modèle documentaire minimal

| Élément | Rôle | Autorité |
| --- | --- | --- |
| Document de travail | Objectif, périmètre, décisions, critères essentiels, questions et décisions humaines | Intention et décisions |
| Contrat d’exécution | Entrées, chemins, droits, environnement requis, commandes et conditions d’arrêt | Autorisation d’exécuter |
| Rapport d’exécution | Digests observés, environnement effectif, commandes et résultats | Faits observés pendant une exécution |

L’organisation active est :

```text
docs/implementation.md
bootstrap/contract.json
bootstrap/runs/<run-id>.json
src/
tests/
```

Aucun manifeste supplémentaire n’est nécessaire. L’état est dérivé de ces éléments et du contenu du dépôt.

## Document de travail

`docs/implementation.md` réunit ce qu’une personne doit comprendre avant d’autoriser le travail :

- objectif ;
- périmètre fonctionnel ;
- exclusions ;
- principales décisions de conception ;
- critères d’acceptation essentiels ;
- risques connus ;
- questions bloquantes ;
- décisions humaines.

Les exigences détaillées existantes peuvent rester consultables en annexe. Elles ne nécessitent pas chacune un état, un manifeste et une copie dans un magasin d’objets.

Une décision humaine référence le digest du contrat qu’elle autorise. Une acceptation finale référence le digest du rapport d’exécution retenu.

L’identité locale reste déclarative tant qu’aucun mécanisme d’authentification n’existe.

## Contrat d’exécution

Le contrat ne contient aucune valeur `UNBOUND`. Une valeur inconnue est soit
déterminée avant l’autorisation, soit relevée dans le rapport lorsqu’elle ne
constitue pas une précondition.

Le contrat actif est `bootstrap/contract.json`. Il fixe :

- les motifs fermés du candidat ;
- les commandes `unittest` ;
- l’environnement minimal ;
- les chemins lisibles et inscriptibles ;
- l’interdiction du réseau, des secrets et des effets externes ;
- les mécanismes de sécurité disponibles et leur qualification ;
- les conditions d’arrêt et le répertoire des rapports.

Le chemin réel de l’interpréteur, sa version et son digest sont relevés dans le rapport d’exécution. Ils n’ont pas besoin d’être copiés manuellement dans le contrat, sauf si une identité précise de l’interpréteur constitue une précondition.

## Périmètre du candidat

Le périmètre repose sur des règles fermées simples plutôt que sur l’énumération préalable de chaque fichier.

Par exemple, le candidat peut être limité aux fichiers Python réguliers sous `src/domain/` et `tests/`. Tout fichier ne correspondant pas aux motifs autorisés provoque un échec du contrôle de périmètre.

Cette règle interdit implicitement les fichiers de dépendances, fichiers temporaires et formats inattendus sans maintenir une liste de trente-cinq chemins.

La liste exacte des fichiers observés et leurs digests est enregistrée dans le rapport.

## Contrôles

Le contrat fixe les commandes et leurs conditions de réussite. Le rapport enregistre l’inventaire réellement découvert.

Le bootstrap n’impose pas à l’avance l’identité exacte de chaque test. Il exige plutôt :

- une découverte limitée aux racines déclarées ;
- un code de sortie nul ;
- aucun test ignoré ;
- aucun échec attendu ou succès inattendu ;
- l’exécution exhaustive des domaines finis déclarés ;
- un échec si aucun test n’est découvert ;
- le rattachement des résultats au digest du candidat.

L’inventaire de 88 tests unitaires et 14 tests d’énumération peut rester une proposition d’implémentation. Un changement de nom ou un regroupement de tests ne doit pas exiger une révision du protocole tant que les critères couverts restent satisfaits.

## Réseau et dispositif hôte

Deux opérations doivent être distinguées.

La préparation du dispositif hôte vérifie que le mécanisme choisi peut bloquer le réseau. Cette qualification appartient à l’administration du dispositif, avant l’exécution gouvernée. Elle peut utiliser un pair contrôlé et comparer une configuration ouverte à une configuration fermée.

L’exécution du candidat utilise ensuite la configuration fermée. Pendant cette exécution, aucun accès réseau n’est autorisé.

Le rapport doit préciser :

- le mécanisme employé ;
- le résultat de sa qualification préalable ;
- la configuration appliquée à l’exécution ;
- les limites connues de cette protection.

Si aucun mécanisme qualifié n’est disponible, les résultats restent des informations de progression. Ils ne fondent pas une acceptation.

## Deux décisions au lieu de six gates

Le bootstrap ne conserve que deux décisions.

### Autorisation d’exécuter

Elle exige :

- un objectif et un périmètre compréhensibles ;
- l’absence de question bloquante ;
- un contrat sans valeur indéterminée nécessaire à l’exécution ;
- des commandes disponibles ;
- des droits et conditions d’arrêt explicites ;
- une décision humaine visant le digest du contrat.

### Acceptation

Elle exige :

- un rapport complet ;
- le rattachement au contrat autorisé ;
- le rattachement au candidat contrôlé ;
- la réussite de tous les contrôles obligatoires ;
- l’absence de violation de périmètre ;
- une décision humaine visant le digest du rapport.

Un résultat défavorable autorise une correction sous le même contrat tant que l’objectif, les droits et le périmètre ne changent pas. Une modification du contrat crée simplement un nouveau digest et requiert une nouvelle autorisation. Elle ne nécessite pas de registre de tentative distinct.

## Rapport d’exécution

Le rapport est généré, jamais rempli manuellement. Il contient au minimum :

- identifiant de l’exécution ;
- digest du contrat ;
- commit Git observé ;
- manifeste et digest du candidat ;
- interpréteur réellement utilisé ;
- mécanisme de restriction appliqué ;
- commandes exactes ;
- codes de sortie ;
- durée ;
- tests découverts ;
- résultats ;
- fichiers créés ou modifiés ;
- violations éventuelles ;
- qualification du résultat : progression ou acceptation possible.

Une exécution n’écrase jamais un rapport précédent.

Le rapport n’est admissible pour une acceptation que si le candidat et le contrat n’ont pas changé depuis l’exécution.

## Réutilisation de l’existant

Les travaux actuels peuvent être repris sans conserver toute leur enveloppe administrative :

- les vingt exigences alimentent le document de travail ;
- les quatre-vingt-dix-huit critères restent une annexe de référence ;
- la conception du domaine fournit la structure initiale ;
- le plan de tâches devient un guide, pas un registre opposable ;
- le plan de contrôles fournit les commandes et oracles utiles ;
- les constats sur l’hôte deviennent des préconditions concrètes ;
- le contrat d’implémentation sert de matière première au contrat minimal.

Les artefacts scellés existants restent intacts. Ils témoignent de l’expérimentation menée, mais ne gouvernent pas implicitement le nouveau bootstrap.

## Critères d’acceptation de la simplification

La simplification est satisfaisante si :

- une personne peut identifier l’objectif, les droits et les commandes sans suivre une chaîne de manifestes ;
- aucune information d’état n’est copiée manuellement dans plusieurs fichiers ;
- aucun digest n’est recopié à la main ;
- le contrat peut être exécuté sans valeur `UNBOUND` ;
- les préconditions matérielles sont contrôlées avant l’autorisation ;
- une correction ordinaire ne nécessite pas de nouvelle tentative administrative ;
- le résultat reste lié au contrat et au candidat exacts ;
- les limites de sécurité sont explicitement déclarées ;
- le workflow peut être appliqué avant que le contrôleur définitif existe.

## Conséquences

Cette simplification réduit la granularité de l’audit pendant le bootstrap. Elle
ne prétend pas offrir les garanties prévues pour le contrôleur final.

En contrepartie, elle rend possible l’implémentation du contrôleur qui pourra ensuite apporter ces garanties de manière effective :

- journal de commandes ;
- transitions atomiques ;
- magasin d’objets ;
- références complètes ;
- invalidation automatique ;
- approbations authentifiées ;
- contrôle technique des droits.

La règle directrice est simple : une propriété n’entre dans le protocole obligatoire que lorsqu’un mécanisme peut réellement l’appliquer ou la vérifier.
