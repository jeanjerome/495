# État de l’implémentation

## Disposition du dépôt

| Élément | Décision | Motif |
| --- | --- | --- |
| `README.md` | Conservé et raccourci | Point d’entrée pour comprendre et utiliser le dépôt |
| `docs/principes-et-contraintes.md` | Conservé | Autorité sur les règles techniques |
| `docs/parcours-utilisateur.md` | Ajouté | Workflow de référence, usages visés et expérience utilisateur |
| `docs/chantiers/plan-global.md` | Ajouté | Ordre des capacités futures et impacts attendus sur l’architecture applicative |
| `docs/etat-de-l-art.md` | Ajouté | Comparaison durable des clients, harnais et runtimes examinés |
| `docs/chantiers/00-parcours-vertical/etat-de-l-art.md` | Ajouté | Étude ciblée et essais du premier parcours vertical |
| `docs/chantiers/00-parcours-vertical/conception.md` | Ajouté | Choix d’intégration appliqués au premier parcours vertical |
| `docs/chantiers/01-configuration-verification/conception.md` | Ajouté | Conception de l’incrément en cours ; ses commandes `verify` et `configure` sont implémentées, les bornes de taille des sorties ne le sont pas |
| `docs/reprise-de-codeservo.md` | Ajouté | Comportements hérités de CodeServo et simplification attendue |
| `docs/implementation.md` | Conservé | Description du comportement réellement disponible |
| `docs/presentation.md` | Conservé et raccourci | Présentation du but et du nom du projet |
| `pyproject.toml` | Ajouté | Déclaration standard du projet Python et de ses dépendances |
| `uv.lock` | Ajouté | Résolution reproductible de l’environnement Python |
| `.python-version` | Ajouté | Sélection de Python 3.12 par `uv` |
| Documents dédiés au domaine, aux gates, à la persistance, aux adaptateurs et à l’orchestrateur | Supprimés | Ils imposaient des composants avant les comportements et intégrations réels |
| `495/` | Supprimé | Archive redondante avec l’historique Git |
| `bootstrap/runs/` | Supprimé | Résultats anciens sans rôle dans l’état courant |
| `bootstrap/contract.json` | Conservé et simplifié | Configuration facultative d’une exécution liée à des fichiers |
| `tools/run_bootstrap.py` | Conservé et simplifié | Contrôles propres au dépôt 495 |
| `src/harness495/` | Ajouté | Paquet applicatif portant le parcours, ses interfaces et ses adaptateurs |
| `tests/` | Ajouté | Vérification du paquet et du lanceur avec des dépôts temporaires |
| `tools/run_change.py` | Conservé comme compatibilité | Délègue à la CLI du paquet sans porter de comportement applicatif |
| `tools/verify_state.py` | Supprimé | Ne contrôlait que l’archive retirée |
| `src/domain/`, `src/validation/` et `src/policy/` | Supprimés | Modèle fermé conçu avant un usage réel |
| `src/persistence/` | Supprimé | Infrastructure sur mesure sans consommateur réel |
| `src/csap/` et `src/application/` | Supprimés | Protocole simulé et orchestration sans intégration réelle |

## Comportement disponible

`tools/run_bootstrap.py` offre deux commandes pour contrôler 495 lui-même :

- `validate` valide une configuration et résout les fichiers qu’elle désigne ;
- `run` exécute les contrôles et retourne un code de sortie favorable seulement
  si toutes les commandes réussissent et si les entrées restent stables.

L’option `--report` de `run` conserve le résultat. Sans cette option, le
lanceur n’écrit aucun historique d’exécution.

Les commandes documentées passent par `uv run`. `uv` sélectionne Python 3.12,
crée si nécessaire un environnement `.venv` ignoré par Git et le synchronise
avec `uv.lock`. Le paquet `harness495`, construit avec `uv_build`, installe la
commande utilisateur `495`.

La commande `495` offre trois sous-commandes, `change`, `verify` et
`configure`, cette dernière avec les opérations `propose`, `validate` et
`write`. Une invocation dont le premier argument commence par `--` est traitée comme
`change`, ce qui préserve la forme historique ; `495 --help` affiche donc
l’aide de `change`, tandis que `495 -h` et `495` sans argument affichent l’aide
générale avec le code `0`. Chaque sous-commande écrit un seul document JSON sur
la sortie standard, indenté de deux espaces, en UTF-8, avec des clés triées et
un saut de ligne final ; les digests continuent d’être calculés sur la
sérialisation compacte. Seules les erreurs d’usage d’argparse sont écrites sur
la sortie d’erreur.

`495 change` expose le premier parcours vers une application cible. Elle
exige une demande dans un fichier, la racine d’un dépôt Git propre avec un
`HEAD`, un contrat cible et un `CODEX_HOME` dédié. Elle exécute une intervention
de `codex exec`, observe l’état Git obtenu, puis lance chaque contrôle avec
`codex sandbox`. La demande est transmise au client par l’entrée standard et
les commandes sont toujours des listes d’arguments sans shell.

Le runner crée ses schémas, réponses intermédiaires et répertoires personnels
temporaires hors du dépôt cible. Il fournit au processus Codex uniquement les
variables nommées par le contrat, son identité dédiée et ces chemins
temporaires. La politique des commandes de l’agent exclut `CODEX_HOME`, refuse
les noms ressemblant à des clés, secrets ou jetons, et désactive le réseau du
sandbox `workspace-write`. Les personnalisations utilisateur et skills
personnelles ne sont pas chargées ; les instructions et skills du dépôt restent
disponibles.

`495 verify` expose l’opération de vérification sans agent,
`verify_candidate`, que `verify_with_codex_sandbox` assemble avec le runner
`codex sandbox`. Ses options sont `--repository`, le répertoire courant par
défaut, `--contract`, `495.json` à la racine du dépôt par défaut, et
`--baseline`, `HEAD` par défaut. Elle vérifie un candidat déjà présent : l’écart entre l’arbre
de travail et une référence Git explicite, `HEAD` par défaut. La référence est
résolue avec `git rev-parse --verify --end-of-options <référence>^{commit}` et
doit être `HEAD` ou un ancêtre de `HEAD` ; une référence irrésoluble ou hors
lignée rend l’exécution impossible avant tout contrôle. Le dépôt peut être
modifié, puisque c’est cet écart qui est vérifié ; le parcours `495` conserve
en revanche l’exigence d’un dépôt propre avant l’intervention de l’agent.

L’opération lit le contrat, prépare l’environnement filtré, résout
l’exécutable de chaque contrôle et sonde les profils sandbox avant d’observer
le candidat. Lorsque l’arbre de travail est identique à
la référence, elle restitue l’issue `no_candidate` sans lancer de contrôle, avec
`candidate` à `null` et une limitation qui rappelle la référence résolue et
suggère une référence antérieure comme `HEAD~1`. Sinon, chaque contrôle est
exécuté une fois dans l’ordre déclaré, le candidat est observé de nouveau après
chacun et une modification de l’état Git visible interrompt la suite avec une
violation. Le document restitué porte `command`, `reference`, `baseline`,
`head`, `contract_digest`, `environment`, `candidate`, `checks`, `violations` et
`limitations`. Cette opération n’a besoin ni d’un `CODEX_HOME` utilisateur ni
d’une authentification : le runner reçoit un `CODEX_HOME` jetable sous le
`HOME` temporaire et `codex login status` n’est jamais appelé. Le binaire
`codex` reste requis pour les profils sandbox.

La résolution des exécutables, `verification.validate_controls`, est
appliquée par `verify`, par `change` avant l’intervention de l’agent et par
`configure validate` et `configure write`. Un premier argument contenant un
séparateur de chemin est résolu par rapport à la racine du dépôt et doit
désigner un fichier exécutable ; sinon il est cherché dans le `PATH` de
l’environnement filtré, ou dans `os.defpath` lorsque le contrat ne transmet pas
`PATH`. Un exécutable introuvable rend l’exécution impossible avant tout
contrôle, de sorte qu’un outil absent ne soit jamais présenté comme un
candidat défavorable. Cette résolution est celle de 495 : elle sert de
précondition, non de preuve que `codex sandbox` pourra lancer la commande.

`495 configure propose` expose `propose_configuration`, que
`propose_with_codex` assemble avec le client Codex. L’opération exige la
racine d’un dépôt Git avec un `HEAD`, accepte un dépôt modifié et exige,
comme `change`, un `CODEX_HOME` dédié et authentifié ; l’appel contacte le
service Codex et peut consommer un quota. Le client est invoqué avec les mêmes
options que `change`, sauf `--sandbox read-only`, un prompt propre à
l’opération et un schéma de réponse propre à l’opération,
`PROPOSAL_RESPONSE_SCHEMA` du module `configuration`. L’environnement transmis
se limite à `PATH`, à `CODEX_HOME` et aux chemins temporaires. Le prompt
demande de ne proposer que des commandes attestées par le dépôt lui-même, de
citer cette attestation dans `evidence`, de transformer tout choix
indécidable en question, de ne donner un `timeout_seconds` que lorsque le
dépôt l’atteste et `null` sinon, et de choisir `read-only` sauf écriture
constatée. La réponse contient `status`, `summary`, `checks`, `environment`,
`questions` et `limitations`, tous obligatoires, sans champ inconnu.

495 construit le contrat à partir de `checks` et `environment`, sans le
corriger. Les contrôles dont le timeout vaut `null` reçoivent la valeur de
l’option `--timeout-seconds` lorsqu’elle est passée ; sans elle, ils restent
sans borne de durée. Dans les deux cas, `limitations` nomme ces contrôles et
l’origine de leur timeout, car ni l’agent ni 495 n’inventent ce délai. Le
contrat passe ensuite par la validation ordinaire. Le candidat
est observé par rapport à `HEAD` avant et après l’inspection ; une différence
est rapportée comme violation. Le document restitué porte `baseline`,
`client_version`, `environment`, `agent`, `contract`, `evidence`,
`questions`, `commands`, `violations` et `limitations`. `contract` vaut `null`
exactement lorsque l’issue n’est pas `proposal_ready` ; `evidence` associe
chaque nom de contrôle à la chaîne fournie par l’agent ; `commands` associe
chaque nom à l’exécutable résolu, ou à `null` lorsqu’il est introuvable, à
titre d’information. `limitations` rappelle toujours que la proposition
n’atteste ni la pertinence ni l’exécutabilité des contrôles. Un client expiré,
non nul, un flux JSONL invalide, une réponse non conforme, une réponse
`blocked`, un dépôt modifié pendant l’inspection ou une proposition qui viole
le format du contrat produisent `agent_failed` avec le diagnostic dans
`violations`. Une réponse `completed` sans contrôle produit
`no_checks_detected`, avec les questions de l’agent et une limitation qui
renvoie vers un contrat écrit à la main. Rien n’est écrit dans le dépôt.

`495 configure validate` expose `validate_configuration` : lecture et
validation du format du contrat, résolution des exécutables, puis sonde des
profils sandbox, sans authentification. `495 configure write` expose
`write_configuration` : le fichier passé par `--proposal` doit être un objet
JSON dont `command` vaut `configure propose`, `version` vaut `1` et `contract`
est un objet ; tout autre fichier, y compris une proposition dont `contract`
vaut `null`, rend l’exécution impossible sans écriture. Le contrat extrait
subit la même validation que `validate`, puis est écrit indenté, en UTF-8,
avec des clés triées, par `contract.write_contract`. Le chemin cible doit être
situé dans le dépôt. Sans `--overwrite`, le fichier est créé en mode exclusif
et un fichier existant rend l’exécution impossible sans être lu ni modifié ;
avec `--overwrite`, le contenu est écrit dans un fichier temporaire du même
répertoire puis renommé atomiquement. Les deux opérations restituent
`contract_path`, relatif à la racine du dépôt, `contract_digest`,
`environment`, `runner`, avec le nom du runner et la sortie de
`codex --version`, et `commands`, sans valeur `null` ; `write` ajoute
`overwritten`, vrai seulement lorsqu’un fichier a été remplacé sur demande.
Aucun commit n’est créé.

Le code de sortie est dérivé de l’issue par une table unique, `EXIT_CODES` du
module `cli` : `0` pour `candidate_verified`, `proposal_ready`,
`configuration_valid` et `configuration_written`, `1` pour
`candidate_failed`, `2` pour `execution_impossible` et
`configuration_invalid`, `3` pour `agent_failed`, `4` pour `no_candidate` et
`no_checks_detected`. Un contrat présent mais non conforme, y compris le
contrat extrait d’une proposition modifiée, lève `ConfigurationError` et
produit l’issue `configuration_invalid` ; toute autre erreur d’exécution
produit `execution_impossible`. Le document d’erreur contient `command`,
`error`, `outcome` et `version` ; `error.kind` conserve son rôle de
diagnostic.

## Architecture applicative

Le paquet `harness495` sépare les frontières démontrées par le premier
parcours :

- `change` conduit le cas d’usage sans contenir les détails de la CLI ;
- `verification` exécute les contrôles sur un candidat observé, applique les
  préconditions des contrôles et porte l’opération de vérification sans
  agent, réutilisée par `change` ;
- `configuration` compose le prompt et le schéma d’une proposition, convertit
  la réponse en contrat, valide un contrat présent et l’enregistre sur action
  explicite ;
- `environment` prépare les chemins temporaires hors du dépôt et filtre les
  variables transmises ;
- `composition` assemble ces cas d’usage avec les composants Codex disponibles ;
- `agent` définit les capacités attendues d’un client d’agent, qui reçoit le
  prompt, le schéma de réponse et le profil de fichiers de chaque opération,
  et `codex` les adapte à Codex CLI ;
- `controls` définit l’exécution des feedbacks et fournit l’adaptation à
  `codex sandbox` ;
- `workspace` identifie la racine du dépôt, sa propreté et la référence de
  départ, puis observe le candidat Git indépendamment des déclarations de
  l’agent ;
- `contract`, `serialization`, `process` et `errors` portent les mécanismes
  partagés par ces frontières ;
- `cli` transforme les arguments et les erreurs en résultat de commande.

Les interfaces `AgentClient` et `ControlRunner` rendent les dépendances des
cas d’usage explicites. `AgentClient.invoke` reçoit un prompt, un schéma et un
profil de fichiers parce que deux opérations réelles, `change` et
`configure propose`, l’exigent ; l’interface ne prétend pas davantage couvrir
un second client ou un autre runtime : seule l’adaptation Codex est
implémentée et vérifiée. `tools/run_change.py` appelle la même CLI pour préserver
les usages existants.

## Configuration du lanceur de contrôles

`bootstrap/contract.json` utilise quatre champs :

| Champ | Rôle |
| --- | --- |
| `version` | Version du format de configuration |
| `files` | Motifs relatifs des fichiers liés au résultat |
| `checks` | Nom, commande et timeout de chaque contrôle |
| `report_directory` | Destination utilisée uniquement avec `--report` |

Chaque motif de `files` doit correspondre à au moins un fichier. Les doublons
sont éliminés dans le manifeste. Le digest du candidat est calculé à partir du
chemin, de la taille et du SHA-256 de chaque fichier.

Une commande est une liste d’arguments exécutée directement, sans shell. Le
jeton `{python}` désigne l’interpréteur qui exécute le lanceur. Le processus
hérite de l’environnement et utilise la racine du dépôt comme répertoire de
travail.

## Contrat de l’application cible

Le contrat reçu par la commande `495` contient exactement `version`,
`environment` et `checks`. `environment` énumère les variables ordinaires que
495 peut transmettre ; `HOME`, `TMPDIR`, `CODEX_HOME` et les noms contenant
`KEY`, `SECRET` ou `TOKEN` sont refusés.

Chaque contrôle possède un nom unique, une commande non vide, un timeout
strictement positif ou `null`, auquel cas sa durée n’est pas bornée, et un
accès fichiers `read-only` ou `workspace-write`. Ces
deux valeurs utilisent respectivement les profils Codex `:read-only` et
`:workspace`. Le runner ajoute une interdiction réseau explicite à chaque
invocation.

## Résultat du lanceur de contrôles

Une commande réussit lorsque son code de sortie vaut zéro avant le timeout. En
cas d’échec, ses sorties standard et d’erreur sont affichées et peuvent être
conservées dans le rapport.

Après les commandes, le lanceur recalcule les digests de la configuration et
des fichiers contrôlés. Un changement rend le résultat défavorable, car les
commandes ne se rapporteraient plus aux entrées initiales.

Un rapport contient uniquement :

- la date d’exécution ;
- le digest de la configuration ;
- le manifeste et le digest des fichiers ;
- l’interpréteur utilisé ;
- les commandes, durées, codes de sortie et timeouts ;
- le résultat global et les éventuelles violations de stabilité.

## Résultat d’un changement

La commande `495` écrit un unique document JSON sur sa sortie standard. Elle
relie le digest de la demande, le commit initial, la version du client, la
réponse de l’agent, le candidat observé, l’environnement nommé et les contrôles.
Les artefacts temporaires ne sont pas conservés.

La réponse de l’agent est contrainte et revalidée avec le même JSON Schema au
moyen de la bibliothèque `jsonschema`. Elle contient un statut, un résumé, des
questions et des limites, mais ne décide ni des chemins modifiés ni du verdict.
Le candidat est calculé à partir du diff Git et des fichiers non suivis ; son
digest incorpore le commit initial, le patch suivi et le contenu non suivi.

Les contrôles sont exécutés par la même opération que la vérification sans
agent, de sorte qu’un candidat produit par l’agent et un candidat déjà présent
reçoivent le même verdict et les mêmes diagnostics. Ils sont séquentiels. Leur
code, leur durée, leur timeout et leurs sorties sont restitués. Si un contrôle modifie l’état Git visible, 495 arrête la
suite, conserve les fichiers et signale une violation au lieu de vérifier un
candidat différent de celui qu’il avait observé.

Le document de `change` porte en outre `command`, `reference`, toujours
`HEAD`, `head` et `limitations`. Les issues sont `candidate_verified`,
`candidate_failed`, `agent_failed`, `execution_impossible` et
`configuration_invalid`. Un client non nul, bloqué ou expiré, un flux JSONL
incomplet, une réponse invalide et une absence de candidat sont distingués des
échecs des contrôles.

Le parcours complet a été exécuté avec Codex CLI `0.153.3` sur macOS. Le dépôt
d’essai a confirmé la réponse structurée, le candidat unique, le contrôle
favorable, l’absence de `CODEX_HOME` dans les commandes de l’agent et le refus
réseau de l’agent comme des contrôles. Les tests automatisés couvrent en plus
les issues défavorables sans consommer de quota.

## Comportements absents

Le projet ne fournit pas encore de passage par les états du workflow complet,
de boucle de correction, de stockage applicatif, de reprise, de mécanisme
d’approbation ni d’intégration Git. Le premier incrément ne prend en charge que
Codex CLI, un dépôt initial propre et une seule intervention.

La [conception de l’incrément en cours](chantiers/01-configuration-verification/conception.md)
est disponible pour ses commandes `verify`, `configure` et `change`. Les
bornes de taille des sorties ne sont pas implémentées : le champ
`output_limit_bytes` et les champs de troncature sont absents des documents,
et le champ `runner` n’apparaît que dans les documents de `configure validate`
et `configure write`. `495 verify` a été exécuté sur cette machine avec Codex
CLI `0.153.3`, sans `CODEX_HOME`, sur un dépôt dont l’unique contrôle est un
script shell : il a restitué `no_candidate` sur l’arbre propre,
`candidate_verified` après l’ajout du fichier attendu et `candidate_failed`
après une modification du script. Sur un dépôt du même type, une proposition
écrite à la main a ensuite été enregistrée par `configure write`, refusée une
seconde fois sans `--overwrite`, relue par `configure validate` avec
`codex-cli 0.153.3` comme version de runner, puis utilisée par `verify` pour
un verdict défavorable et un verdict favorable, le tout sans `CODEX_HOME` ni
authentification. `configure propose` a ensuite été exécuté avec Codex
authentifié sur un dépôt shell comparable, doté d’un `Makefile` dont la cible
`check` appelle le script et d’un README prescrivant `make check`. L’agent a
identifié ce contrôle, sa commande et son profil `read-only`, n’a modifié
aucun fichier et n’a exécuté aucun contrôle, mais a répondu `blocked` : le
dépôt n’indiquant aucun délai, il a refusé d’inventer `timeout_seconds` et a
posé la question. Le document a donc restitué `agent_failed`, `contract` à
`null` et la question dans `questions`. Cet essai a montré qu’un timeout
n’est presque jamais attesté par un dépôt ; le prompt demande depuis de le
laisser à `null` dans ce cas et l’option `--timeout-seconds` a été ajoutée.
Un second essai sur le même dépôt, sans `--timeout-seconds`, a restitué
`proposal_ready` en 35 secondes : un contrôle `make check` en `read-only`,
`timeout_seconds` à `null`, une attestation citant le README et le Makefile,
`gmake` résolu dans `commands`, une question sur la provenance de
`result.txt` et la limitation signalant l’absence de borne de durée. Le dépôt
est resté intact. Cette proposition a ensuite été enregistrée telle quelle par
`configure write`, relue par `configure validate`, puis utilisée par `verify`
pour un verdict défavorable puis favorable, le tout sans authentification. Le
parcours `change` n’a pas été rejoué sur ce dépôt.

Le runner de bootstrap continue d’hériter de l’environnement et ne constitue
pas une sandbox. Le runner de changement délègue le confinement à la version de
Codex installée : il configure et observe cette frontière, mais ne rend pas le
système d’exploitation hermétique et ne prouve pas encore les lectures
effectivement possibles. Les diagnostics des outils peuvent contenir des
informations sensibles et sont remis localement sans persistance automatique.
Codex peut néanmoins écrire ses caches et fichiers d’état propres dans le
`CODEX_HOME` dédié, que 495 ne supprime pas lorsqu’il appartient à l’utilisateur.
Les sorties des processus sont bornées par leur timeout, mais pas encore par une
taille maximale indépendante.

## Règle d’évolution

Cette section gouverne l’évolution du harnais 495. Elle ne demande pas aux
applications cibles d’utiliser Python, `uv`, les dépendances ou l’architecture
de 495.

Avant d’introduire un composant ou une abstraction dans 495, la conception
examine les clients d’agents, les autres harnais de code et les bibliothèques
open source qui fournissent déjà le comportement recherché. Pour une décision
structurante, cette étude consulte les parties pertinentes de l’implémentation,
des tests, des garanties documentées et des limites connues. Elle compare aussi
la licence, la maintenance, les plateformes, la stabilité de l’interface et le
coût d’exploitation. La décision indique brièvement ce qui est configuré,
composé, adapté ou développé dans 495.

L’[état de l’art](etat-de-l-art.md) porte cette comparaison pour l’ensemble du
projet et l’[étude ciblée](chantiers/00-parcours-vertical/etat-de-l-art.md) du
premier parcours vertical y ajoute ses essais. Toute propriété encore incertaine
doit être confirmée par un essai sur les versions réellement intégrées.

La [conception](chantiers/00-parcours-vertical/conception.md) de ce parcours
retient Codex CLI et son runner sandboxé comme composants à adapter. Le paquet
`harness495` applique cette conception au
[premier incrément vertical](parcours-utilisateur.md#premier-incrément-vertical)
sans prétendre faire traverser au changement les états et gates du workflow
complet.

Cette intégration construit un contexte ciblé, utilise des environnements
d’exécution dont les permissions sont explicites et valide le résultat JSON
attendu. Le confinement de l’agent peut être celui du client retenu si ses
propriétés observables satisfont le besoin. Les contrôles qui exécutent le
candidat doivent bénéficier de garanties équivalentes, sans supposer qu’ils
sont couverts par la sandbox du client. 495 n’ajoute pas une couche redondante
lorsque l’environnement retenu couvre déjà le processus concerné. La CLI est la
première interface. Les modèles, adaptateurs et choix de persistance seront
dérivés de ce comportement plutôt que définis au préalable. Une dépendance
tierce peut être adoptée si elle simplifie concrètement cette fonctionnalité.

La [reprise de CodeServo](reprise-de-codeservo.md) guide l’implémentation de
`implementing` et `verifying`. Elle autorise la réutilisation ciblée de son
code et de ses tests, mais pas le portage préalable de son architecture
complète.
