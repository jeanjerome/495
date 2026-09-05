# AGENTS.md

## Portée et priorité

Ce fichier s’applique à tout le dépôt. Un fichier `AGENTS.md` plus proche d’un
fichier modifié peut préciser ou renforcer ces règles pour son sous-arbre. Les
instructions explicites de l’utilisateur ont priorité.

## Objet du projet

495 est un harnais de développement logiciel assisté par IA. Il sépare les
propositions, les contrats, les tentatives, les décisions de gate, les preuves
et les approbations afin que toute conclusion reste liée aux octets exacts
qu’elle concerne.

Le dépôt contient actuellement la conception et les enregistrements publics du
bootstrap, pas encore l’implémentation du harnais. Ne présente jamais une
convention de fichiers comme une propriété de sécurité appliquée par un
contrôleur.

## Sources d’autorité

Consulter les sources suivantes avant toute modification :

- `495/project.json` : identité, version d’état, incréments et profil lié ;
- `495/changes/<increment>/manifest.json` : artefacts scellés, brouillons et
  références adoptées ;
- `495/changes/<increment>/contracts/` : objectif, entrées, sorties, droits et
  chemins autorisés de l’opération ;
- `495/changes/<increment>/gates/` : décisions de gate et version d’état visée ;
- `495/decisions/manifest.json` : références exactes et sémantique des liens des
  décisions ;
- `495/approvals.json` : seule autorité pour l’état des approbations et refus ;
- `495/objects/sha256/` : octets historiques adressés par leur SHA-256 ;
- `495/changes/INC-0001/design.md` : conception de référence ;
- `495/changes/INC-0002/requirements.json` : exigences et oracles scellés
  actuellement adoptés.

Le `README.md` donne une vue d’ensemble. Pour un état mutable ou une référence
exacte, les registres ci-dessus font autorité.

## Règles d’intégrité

- Ne modifie jamais en place un artefact scellé.
- Une correction d’un artefact scellé crée une nouvelle révision et conserve
  la précédente intacte.
- Ne modifie et ne remplace jamais un objet existant sous
  `495/objects/sha256/`. Un nouvel objet porte comme nom le digest SHA-256 de
  ses octets exacts.
- Calcule un digest sur les octets du fichier, sans le re-sérialiser. Vérifie
  que le nom de l’objet, le manifeste et le contenu concordent.
- Une référence complète contient `artifact_id`, `revision`, `kind`,
  `schema_version` et `digest`. N’utilise ni chemin ni valeur symbolique telle
  que `latest` à sa place.
- Une approbation ne vaut que pour l’égalité des cinq champs de sa cible. Un
  digest identique ne transfère pas une approbation vers un autre
  `artifact_id` ou une autre révision.
- Ne place pas de statut mutable dans un artefact scellé. Dérive l’état des
  décisions depuis `495/approvals.json`.
- Ne réécris pas une ancienne décision de gate, une tentative ou un historique
  pour refléter un état plus récent. Ajoute un nouvel enregistrement lié aux
  entrées qu’il évalue.
- Respecte `expected_state_version` et l’incrément monotone de `state_version`
  lors de toute transition.
- N’accorde jamais une approbation et ne transforme jamais une preuve absente
  en `PASS`. Une approbation humaine requise reste une action humaine explicite.

## Autorisation du travail

Avant d’écrire, vérifie le profil lié par référence complète, le contrat actif,
les chemins autorisés et la dernière décision de gate utilisable.

- Un contrat de conception autorise des artefacts de conception, pas du code
  livrable.
- L’écriture de code livrable exige un contrat d’implémentation scellé et un G2
  `PASS` applicable à la version d’état courante.
- Une permission de lecture, d’écriture, de réseau ou d’effet externe ne se
  déduit jamais de ce fichier : elle doit figurer dans le contrat applicable.
- Sous le profil `self-hosting-bootstrap`, toute actuation interdit le réseau,
  les secrets et les effets externes. Les écritures restent limitées aux
  chemins du contrat.
- Si le contrat, la gate ou une preuve requise manque, constate la limite au
  lieu de l’assouplir implicitement.

## Organisation attendue du code

L’implémentation prévue est en Python 3.12 ou ultérieur, sous `src/`, avec les
tests publics sous `tests/`. Le domaine ne dépend d’aucun autre module interne ;
respecte les responsabilités et interdictions définies dans la conception et
les ADR approuvés.

Il n’existe actuellement ni configuration de build, ni formateur, ni linter,
ni commande de test exécutable au niveau du dépôt. N’invente pas de commande et
n’installe pas de dépendance pour combler cette absence. Lorsqu’un contrat G2
sera scellé, ses chemins absolus, son environnement, ses contrôles et ses
oracles seront la seule procédure exécutoire autorisée.

Pour les JSON du bootstrap, conserve la sérialisation existante : UTF-8,
`ensure_ascii=false`, clés triées, indentation de deux espaces et retour à la
ligne final. Ne reformate pas un fichier scellé.

## Tests et preuves

Sous le profil `self-hosting-bootstrap` :

- utilise uniquement la bibliothèque standard, notamment `unittest` et `ast` ;
- garde `tests/unit` et `tests/enumeration` disjoints ;
- n’utilise ni `pytest`, ni générateur aléatoire, ni reprise automatique ;
- exige l’inventaire exact des tests attendus, pas seulement un code de sortie
  nul ou un nombre de tests non nul ;
- traite tout `skipped`, `expected failure` ou `unexpected success` d’un
  contrôle obligatoire comme un échec ;
- vérifie les domaines finis par énumération exhaustive et compare leur
  couverture aux cardinalités scellées ;
- ne qualifie un contrôle qu’après acceptation d’une entrée connue conforme et
  rejet d’une entrée connue fautive, toutes deux liées par digest.

Ne revendique pas un contrôle comme réussi s’il n’a pas été exécuté selon son
contrat exact. Distingue une preuve fonctionnelle de progression d’une preuve
d’acceptation ; sans immutabilité qualifiée du candidat, du vérificateur et de
l’environnement, un résultat ne peut pas fonder G4.

## Commandes d’inspection sûres

Ces commandes sont informatives ; elles ne remplacent aucun contrôle scellé :

```sh
python3 tools/verify_state.py
rg --files
rg -n 'state_version' 495/project.json
shasum -a 256 495/changes/INC-0002/requirements.json
```

`tools/verify_state.py` compare les manifestes, le magasin d’objets, les
approbations et la liaison au profil. Il vit dans le dépôt qu’il inspecte : ce
n’est pas un objet de contrôle scellé et il ne vaut aucune preuve de gate.

Avant d’annoncer une validation, indique la commande exacte réellement
exécutée et sa portée. L’absence de commande de test reste une absence de
preuve, jamais un succès implicite.

## Contenu écrit

Dans les commentaires, commits, titres et descriptions de PR, et issues,
décris le comportement du code en termes techniques, jamais le processus qui
l’a produit.

- Aucune référence à un chantier, ticket, lot, phase de planification ou repère
  interne tel que `chantier #24`, `Lot 3`, `(P1)`, `D12` ou `design 6.8`.
- Aucune métadonnée de session ou de planification : tour de revue, session,
  plan ou PR ayant conduit au changement.
- Aucune attribution à une IA et aucun trailer `Co-Authored-By`.

Préférer par exemple « un déploiement générique par synchronisation et
redémarrage n’expose pas le digest de l’image active » à une formulation fondée
sur l’historique du travail.

Rédige la documentation destinée au projet en français, sauf lorsqu’une
interface, une convention ou le fichier voisin impose une autre langue.

## Commits et PR

Les commits suivent exactement :

```text
<type>: <description>
```

Types autorisés : `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`,
`ci`.

Une PR décrit le comportement modifié, les invariants concernés, les contrôles
effectivement exécutés et les limites restantes. Elle ne prétend pas qu’un
artefact, une preuve ou une approbation est applicable sans en donner la
référence exacte.

## Critères de fin

Avant de remettre un changement :

- vérifie que chaque fichier modifié était autorisé et non scellé ;
- vérifie la syntaxe et la cohérence des formats touchés ;
- contrôle les digests et références affectés sur les octets exacts ;
- exécute uniquement les contrôles autorisés et disponibles ;
- rapporte honnêtement les contrôles non exécutés et les preuves manquantes ;
- laisse les historiques, objets scellés et modifications sans rapport intacts.
