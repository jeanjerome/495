# AGENTS.md

## Objet du projet

495 encadre le développement logiciel assisté par IA par un contrat d’exécution
compréhensible, des contrôles reproductibles et un rapport lié au contenu
réellement contrôlé.

Le dépôt utilise un bootstrap minimal tant que le contrôleur 495 n’existe pas.
Les propriétés avancées de la conception ne sont revendiquées que lorsqu’un
mécanisme exécutable les applique effectivement.

## Sources actives

Trois éléments décrivent le bootstrap courant :

- le document désigné par `bootstrap/contract.json#work_document` : objectif,
  périmètre, décisions, critères et limites ;
- `bootstrap/contract.json` : autorisation d’exécution, chemins, droits et contrôles ;
- `bootstrap/runs/*.json` : rapports générés, un fichier par exécution.

L’état se déduit de ces fichiers et de Git. Il n’existe ni compteur d’état, ni
manifeste courant, ni registre de tentative à synchroniser manuellement.

## Archive historique

Le répertoire `495/` contient l’expérimentation documentaire antérieure. Il est
conservé en lecture seule :

- ne modifie ni ses artefacts, ni ses manifestes, ni ses objets ;
- n’ajoute pas de nouvel état courant sous ce répertoire ;
- ne présente pas ses gates, approbations ou contrats comme applicables au
  bootstrap minimal ;
- utilise `python3 tools/verify_state.py` uniquement pour constater l’intégrité
  de cette archive.

Les documents historiques restent des sources de conception consultables. Ils
ne gouvernent pas implicitement les écritures courantes.

## Autorisation du travail

Une écriture documentaire ou d’outillage répondant à une demande explicite de
l’utilisateur peut modifier `docs/`, `bootstrap/`, `tools/`, `README.md`,
`AGENTS.md` et `CLAUDE.md`.

L’écriture du candidat sous les chemins déclarés par le contrat exige en plus :

- un `bootstrap/contract.json` valide et sans valeur indéterminée nécessaire à
  l’exécution ;
- une décision humaine dans le document de travail désigné par le contrat qui
  vise le digest exact de ce contrat ;
- des écritures limitées aux chemins autorisés par ce contrat.

Ne crée jamais cette décision humaine à la place de l’utilisateur. Un contrat
modifié porte un nouveau digest et requiert une nouvelle autorisation.

Les droits de réseau, de secrets ou d’effets externes doivent être explicites.
Le contrat courant les interdit. Une limitation déclarée mais non appliquée par
un mécanisme qualifié réduit le résultat à une information de progression.

## Contrat et rapports

Le contrat est un JSON UTF-8, avec clés triées, indentation de deux espaces et
retour à la ligne final. Il contient des valeurs exécutables, jamais `UNBOUND`.

`python3 tools/run_bootstrap.py validate` contrôle sa structure et la
compatibilité de l’interpréteur sans exécuter le candidat.

`python3 tools/run_bootstrap.py run` :

- résout et enregistre l’interpréteur effectif ;
- calcule les digests du contrat et du candidat ;
- contrôle le périmètre du candidat ;
- exécute chaque commande une seule fois, sans shell ;
- écrit un nouveau rapport sous `bootstrap/runs/` sans écraser un rapport
  existant.

Un rapport favorable ne vaut acceptation que si `acceptance_eligible` est vrai
et qu’une décision humaine vise son digest exact. En l’absence de mécanisme
qualifié de restriction réseau et d’immutabilité, il reste une information de
progression.

## Code et contrôles

L’implémentation utilise Python 3.12 ou ultérieur et uniquement la bibliothèque
standard pendant le bootstrap.

- Le code du domaine vit sous `src/domain/`.
- Les tests vivent sous `tests/`.
- Les commandes obligatoires sont celles du contrat actif.
- Aucun test découvert est un échec.
- Tout `skipped`, `expected failure` ou `unexpected success` rend le contrôle
  concerné défavorable.
- Les domaines finis sont vérifiés exhaustivement lorsque le contrat le demande.
- Les fichiers produits doivent respecter les motifs fermés du contrat ; un
  fichier hors périmètre est une violation.

N’annonce pas une validation sans indiquer la commande réellement exécutée et
sa portée. Un contrôle absent ou non exécuté reste une absence de preuve.

## Contenu écrit

Décris le comportement du code en termes techniques, jamais le processus qui
l’a produit.

- Aucune référence à un chantier, ticket, lot, phase de planification ou repère
  interne tel que `chantier #24`, `Lot 3`, `(P1)`, `D12` ou `design 6.8`.
- Aucune métadonnée de session ou de planification.
- Aucune attribution à une IA et aucun trailer `Co-Authored-By`.
- La documentation destinée au projet est rédigée en français, sauf convention
  d’interface imposant une autre langue.

## Commits

Les commits suivent exactement :

```text
<type>: <description>
```

Types autorisés : `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`,
`ci`.

## Critères de fin

Avant de remettre un changement :

- préserve `495/` et les modifications utilisateur sans rapport ;
- valide la syntaxe des formats touchés ;
- exécute les contrôles disponibles et autorisés ;
- vérifie qu’aucun état n’est dupliqué entre plusieurs autorités ;
- rapporte honnêtement les contrôles non exécutés et les limites restantes.
