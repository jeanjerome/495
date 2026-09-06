# Conception : configuration et vérification réutilisables

## Portée

Ce document porte la conception du premier incrément du
[plan global](../plan-global.md#1-rendre-la-configuration-et-la-vérification-réutilisables) :
un dépôt peut être préparé pour 495, puis un candidat déjà présent peut être
vérifié sans invoquer un agent.

Il décrit une cible de conception. Aucun des comportements ci-dessous n’est
disponible tant que l’[état de l’implémentation](../../implementation.md) ne le
dit pas. La commande actuelle reste celle décrite dans la
[conception du premier incrément](../00-parcours-vertical/conception.md).

L’incrément ajoute deux commandes orientées usage, `495 verify` et
`495 configure`, et conserve l’invocation actuelle. Il n’introduit ni état de
workflow, ni boucle de correction, ni second client, ni persistance.

## Composants examinés

Aucune dépendance nouvelle n’est envisagée. Les composants qui portent déjà le
comportement recherché sont réutilisés :

| Besoin | Composant | Ce qui est réutilisé |
| --- | --- | --- |
| identifier un candidat par rapport à une référence | Git, via `workspace` | `rev-parse`, `merge-base`, `diff`, `ls-files`, déjà employés pour l’observation du candidat |
| exécuter un contrôle confiné | `codex sandbox`, via `CodexSandboxControlRunner` | profils `:read-only` et `:workspace`, refus réseau, déjà éprouvés sur macOS |
| valider une réponse d’agent | `jsonschema`, déjà verrouillée | même validateur que la réponse du parcours avec agent |
| proposer une configuration | `codex exec` en `--sandbox read-only` | même client, même flux JSONL, schéma de réponse propre à l’opération |
| borner les sorties d’un processus | bibliothèque standard (`threading`, `subprocess`) | lecteurs de flux bornés autour du `Popen` existant |

Un fait a été vérifié sur cette machine avec Codex CLI `0.153.3` sous macOS :
`codex sandbox -P :read-only --sandbox-state-disable-network -- /bin/echo`
réussit avec un `CODEX_HOME` vide pour lequel `codex login status` répond
« Not logged in ». La vérification directe peut donc réutiliser le runner
sandboxé sans authentification auprès d’un fournisseur. Le même essai montre
que Codex écrit sur `stderr` un avertissement lorsqu’il refuse de créer ses
alias de `PATH` sous un répertoire temporaire ; ce texte peut apparaître dans
les diagnostics des contrôles et ne constitue pas un échec.

Le lanceur `tools/run_bootstrap.py` reste un outil du dépôt 495. Il n’est pas
fusionné avec la vérification applicative : ses manifestes de fichiers, son
héritage d’environnement et son absence de sandbox répondent à un autre besoin.

## Décisions

| Besoin | Décision | Motif |
| --- | --- | --- |
| désigner le candidat | l’arbre de travail comparé à une référence Git, `HEAD` par défaut | reprend l’observation existante sans inventer une seconde notion de candidat |
| référence acceptée | tout commit résoluble, qui doit être `HEAD` ou un ancêtre de `HEAD` | un candidat signifie « ce que l’arbre de travail ajoute à la référence », pas un écart entre deux branches |
| absence de candidat | issue `no_candidate`, code `4`, aucun contrôle lancé | un verdict n’a de sens que rattaché à un candidat identifié |
| commandes | sous-commandes `verify`, `configure` et `change` ; la forme sans sous-commande reste un alias de `change` | la CLI gagne des commandes orientées usage sans casser l’invocation documentée |
| contrat par défaut | `495.json` à la racine du dépôt cible | `configure` l’enregistre à cet endroit ; un chemin explicite reste possible |
| proposition de configuration | produite par Codex en lecture seule, restituée sans écriture | l’agent propose, l’utilisateur décide, 495 valide et écrit sur action explicite |
| écriture du contrat | sous-commande `write` distincte, refus d’écraser sans `--overwrite` | l’enregistrement et le remplacement sont deux effets distincts |
| timeout non attesté | `null` dans la réponse de l’agent, complété seulement par `--timeout-seconds` ; sans cette option, le contrôle n’est pas borné | ni l’agent ni 495 n’inventent une borne ; l’essai réel a montré qu’un dépôt n’atteste presque jamais un délai |
| exécutabilité | résolution de chaque exécutable et sonde des profils sandbox avant tout contrôle | un outil absent est une précondition manquante, pas un candidat défavorable |
| bornes des sorties | préfixe de 4 MiB par flux, troncature signalée par des champs dédiés | mémoire et taille du résultat bornées ; le texte capturé reste verbatim |
| sorties JSON | un document par exécution, indenté, UTF-8, clés triées | lisible par un humain qui relit une proposition ; le contenu ne change pas |
| codes de sortie | table unique dérivée de l’issue | le JSON reste l’autorité détaillée ; le code sert à l’automatisation |

## Commandes

### `495 verify`

```sh
495 verify [--repository .] [--contract <dépôt>/495.json] [--baseline HEAD]
```

| Option | Rôle |
| --- | --- |
| `--repository` | racine du dépôt Git cible ; répertoire courant par défaut |
| `--contract` | contrat de l’application cible ; `495.json` à la racine par défaut |
| `--baseline` | référence Git de l’état de départ ; `HEAD` par défaut |

La commande n’exige ni demande, ni `CODEX_HOME`, ni authentification. Elle
accepte un dépôt modifié : c’est précisément ce qu’elle vérifie.

### `495 configure`

```sh
495 configure propose  [--repository .] --codex-home <répertoire> [--agent-timeout-seconds 900] [--timeout-seconds <secondes>]
495 configure validate [--repository .] [--contract <dépôt>/495.json]
495 configure write    [--repository .] --proposal <fichier> [--contract <dépôt>/495.json] [--overwrite]
```

`propose` inspecte le dépôt avec Codex et restitue une proposition sans rien
écrire. `validate` contrôle un contrat déjà présent. `write` valide la
proposition relue par l’utilisateur puis l’enregistre.

### `495 change` et compatibilité

```sh
495 change --repository <dépôt> --contract <contrat> --codex-home <répertoire> --request-file <demande> [--agent-timeout-seconds 900]
```

L’invocation actuelle, sans sous-commande, conserve ses options et les codes
`0` à `3` de la table ci-dessous. Elle est traitée comme `495 change` lorsque
le premier argument commence par `--` ; `495 --help` affiche donc l’aide de
`change`, tandis que `495 -h` et `495` sans argument affichent l’aide
générale. `tools/run_change.py` continue de déléguer à la même CLI.

Trois écarts par rapport au comportement actuel sont assumés :

- le document JSON est écrit indenté au lieu de compact ; un lecteur qui le
  charge comme JSON ne voit aucune différence ;
- un contrat présent mais non conforme produit l’issue `configuration_invalid`
  au lieu d’`execution_impossible`, avec le même code `2` ;
- un exécutable de contrôle introuvable est détecté avant l’intervention de
  l’agent et produit `execution_impossible`, code `2`, au lieu d’un contrôle
  défavorable constaté après une intervention qui a consommé du quota.

Le document de `change` gagne par ailleurs les champs communs décrits plus
bas ; aucun champ existant n’est retiré ni renommé.

## Désignation du candidat

495 résout la référence avec
`git rev-parse --verify --end-of-options <référence>^{commit}` et conserve le
commit obtenu. Un nom de branche, un tag, une expression comme `HEAD~2` ou un
identifiant abrégé sont acceptés ; une référence irrésoluble produit
`execution_impossible`.

La référence doit être `HEAD` ou un ancêtre de `HEAD`, vérifié avec
`git merge-base --is-ancestor`. Sinon, l’exécution est impossible et le
diagnostic suggère de désigner la base de fusion. Cette règle garantit que le
candidat représente les modifications ajoutées à la référence, commits compris,
et non l’écart entre deux lignes de développement.

Le candidat est ensuite observé comme aujourd’hui : différence entre la
référence et l’arbre de travail, indexée ou non, plus les fichiers non suivis et
non ignorés. Son digest incorpore le commit de référence, le patch suivi et le
contenu non suivi. Avec la référence par défaut, le candidat est le travail non
commité ; avec une référence antérieure, il inclut les commits intermédiaires.

Le résultat rapporte la référence telle que demandée, le commit résolu et le
commit courant de `HEAD`, afin qu’un lecteur distingue ce qui est commité de ce
qui ne l’est pas.

## Absence de candidat

`verify` lit le contrat, prépare l’environnement et applique les préconditions
des contrôles décrites dans [Valider](#valider) avant d’observer le candidat.
Un contrat absent ou invalide, un exécutable introuvable ou une sandbox
indisponible sont donc rapportés avec leur issue propre, même lorsque l’arbre
de travail est identique à la référence.

Lorsque ces préconditions tiennent et que l’arbre de travail ne diffère pas de
la référence, `verify` restitue l’issue `no_candidate` avec le code `4`. Le
document est celui d’un `verify` ordinaire : `candidate` vaut `null`, `checks`
et `violations` sont vides, et `limitations` contient une phrase qui rappelle
la référence résolue et indique qu’une référence antérieure, par exemple
`HEAD~1`, permet de vérifier un candidat déjà commité. Aucun contrôle n’est
lancé : les contrôles produiraient un verdict sur la référence elle-même, ce
qui n’est pas une vérification de candidat. Le code `4` signifie ainsi que tout
était prêt mais qu’il n’y avait rien à vérifier.

Le parcours `change` conserve son comportement : l’absence de candidat après
l’intervention reste un `agent_failed` avec le code `3`, car elle constate
l’échec de l’intervention demandée.

## Codes de sortie

Le code de sortie est dérivé de l’issue par une table unique :

| Code | Issue | Commandes concernées |
| --- | --- | --- |
| `0` | `candidate_verified`, `proposal_ready`, `configuration_valid`, `configuration_written` | toutes |
| `1` | `candidate_failed` | `verify`, `change` |
| `2` | `execution_impossible`, `configuration_invalid` | toutes |
| `3` | `agent_failed` | `change`, `configure propose` |
| `4` | `no_candidate`, `no_checks_detected` | `verify`, `configure propose` |

`execution_impossible` couvre les préconditions et capacités manquantes :
dépôt absent ou sans `HEAD`, référence irrésoluble ou hors lignée, contrat
absent ou illisible, exécutable introuvable, sandbox indisponible, fichier de
contrat existant sans `--overwrite`, chemin de contrat hors du dépôt pour
`write`, option de commande invalide comme un timeout d’agent non positif.

`configuration_invalid` est produit exactement lorsque le fichier de contrat
existe, se lit, et échoue à la validation de format décrite dans
[Valider](#valider) : JSON invalide, champs, version, variables, noms,
commandes, timeouts ou profils. Toute autre erreur produit
`execution_impossible`. Les deux partagent le code `2` ; `error.kind` conserve
ses valeurs actuelles à titre de diagnostic et n’intervient pas dans le choix
de l’issue.

Le code `4` signale que l’exécution s’est déroulée correctement mais qu’il n’y
avait rien à vérifier ou rien à proposer. Une CI qui l’obtient sait que le
verdict est absent, pas défavorable.

## Documents JSON

Chaque commande écrit un seul document JSON sur sa sortie standard, indenté de
deux espaces, en UTF-8, clés triées, terminé par un saut de ligne. Seules les
erreurs d’usage d’argparse précèdent ce document sur la sortie d’erreur. Les
digests continuent d’être calculés sur la sérialisation compacte existante.

### Champs communs

| Champ | Contenu |
| --- | --- |
| `version` | `1` |
| `command` | `verify`, `change`, `configure propose`, `configure validate` ou `configure write` |
| `outcome` | l’issue de la table des codes de sortie |
| `error` | présent seulement pour `execution_impossible` et `configuration_invalid` : `kind` et `message` |
| `limitations` | limites connues de l’exécution ; absent du document d’exécution impossible |
| `output_limit_bytes` | borne appliquée à chaque flux capturé ; absent du document d’exécution impossible |

### Résultat de `verify`

```json
{
  "version": 1,
  "command": "verify",
  "outcome": "candidate_verified",
  "reference": "HEAD",
  "baseline": "b076e290…",
  "head": "b076e290…",
  "contract_digest": "sha256:…",
  "environment": {"inherited": ["PATH"], "missing": ["LANG"]},
  "runner": {"name": "codex-sandbox", "version": "codex-cli 0.153.3"},
  "output_limit_bytes": 4194304,
  "candidate": {"baseline": "b076e290…", "digest": "sha256:…", "files": []},
  "checks": [],
  "violations": [],
  "limitations": []
}
```

`candidate`, `checks`, `violations` et `candidate_after_checks` conservent la
forme produite aujourd’hui par `change`. Chaque contrôle rapporte son nom, sa
commande, son profil sandbox, son code, sa durée, son timeout, ses sorties et
les champs de troncature décrits plus bas. Lorsqu’un contrôle modifie l’état Git
visible, la suite est interrompue, la violation est rapportée et
`candidate_after_checks` décrit l’état constaté.

### Résultat de `change`

Le document actuel conserve tous ses champs et reçoit `command`, `reference`
(toujours `HEAD`), `head`, `runner`, `output_limit_bytes` et `limitations`.
Les blocs `checks`, `violations` et `candidate` sont produits par la même
opération de vérification que `verify`, ce qui rend le critère de fin du plan
observable : même verdict et mêmes diagnostics, appelés seuls ou après une
intervention.

### Résultats de `configure`

`propose` restitue :

| Champ | Contenu |
| --- | --- |
| `baseline` | commit `HEAD` au moment de l’inspection |
| `client_version`, `environment`, `agent` | mêmes blocs que `change` ; `agent.sandbox.filesystem` vaut `read-only` |
| `contract` | le contrat proposé, conforme au format consommé par `verify` ; `null` exactement lorsque l’issue n’est pas `proposal_ready` |
| `evidence` | objet indexé par nom de contrôle proposé ; chaque valeur est la chaîne fournie par l’agent qui cite le fichier ou la convention attestant le contrôle |
| `questions` | les choix que l’agent n’a pas pu trancher |
| `commands` | objet indexé par nom de contrôle proposé ; chaque valeur est le chemin absolu de l’exécutable résolu, ou `null` lorsqu’il est introuvable |
| `violations` | liste de chaînes ; contient notamment toute modification du dépôt constatée après l’inspection, qui produit `agent_failed` |

`validate` et `write` restituent `contract_path`, relatif à la racine du dépôt,
`contract_digest`, `environment`, `runner` et `commands`. Ce dernier a la même
forme que dans `propose`, sans valeur `null` puisqu’un exécutable introuvable
interrompt ces deux commandes. `write` ajoute `overwritten`, vrai seulement
lorsqu’un fichier a été remplacé sur demande.

### Résultat d’exécution impossible

Le document minimal actuel, `error`, `outcome` et `version`, gagne `command`.
Il reste valable même lorsque l’erreur survient avant toute observation.

## Configuration

### Proposer

`configure propose` exige un `CODEX_HOME` dédié et authentifié, comme `change`.
Il vérifie que le chemin est la racine d’un dépôt Git avec un `HEAD`, mais
n’exige pas un dépôt propre. Il observe le candidat par rapport à `HEAD` avant
et après l’inspection ; une différence est rapportée comme violation et produit
`agent_failed`, car un agent qui écrit dans le dépôt malgré la lecture seule
n’est pas digne de confiance pour proposer une configuration. Une réponse
`blocked` produit également `agent_failed`, comme pour `change`.

Le client est invoqué avec les mêmes options que `change`, sauf
`--sandbox read-only`, un prompt propre à l’opération et un schéma de réponse
propre à l’opération. L’environnement transmis se limite à `PATH`, à l’identité
du client et aux chemins temporaires : l’agent lit le dépôt, il n’exécute pas
les contrôles.

Le prompt demande à l’agent de ne proposer que des commandes attestées par le
dépôt lui-même : scripts, cibles de `Makefile`, manifestes de paquets,
configuration de CI, instructions du `README` ou du fichier d’instructions du
dépôt. Chaque contrôle cite son attestation. Un choix que le dépôt ne permet pas
de trancher devient une question, jamais une valeur inventée. L’agent choisit
`read-only` sauf lorsqu’il constate que la commande écrit dans l’espace de
travail. Il ne donne un `timeout_seconds` que lorsque le dépôt l’atteste, par
exemple dans sa configuration d’intégration continue, et `null` sinon ; 495
complète ces contrôles avec la valeur de `--timeout-seconds` lorsqu’elle est
passée, et les laisse sans borne de durée sinon, en le signalant dans
`limitations`.

Le schéma de réponse contient :

- `status`, avec `completed` ou `blocked` ;
- `summary`, une chaîne ;
- `checks`, une liste d’objets `name`, `command`, `timeout_seconds`, entier
  ou `null`, `filesystem` et `evidence` ;
- `environment`, une liste de noms de variables ;
- `questions` et `limitations`, des listes de chaînes.

Tous les champs sont obligatoires et les champs inconnus refusés. 495 construit
le contrat à partir de `checks` et `environment`, puis le passe dans la
validation ordinaire du contrat. Une proposition qui la viole, par exemple un
nom dupliqué ou une variable ressemblant à un secret, produit `agent_failed`
avec le diagnostic ; 495 ne la corrige pas silencieusement. Une réponse
`completed` sans aucun contrôle produit `no_checks_detected`.

La proposition n’est jamais une preuve. Les exécutables sont résolus à titre
d’information et le document rappelle que l’utilisateur reste responsable de la
pertinence des contrôles.

### Valider

`configure validate` et la phase de validation de `write` appliquent, sans
authentification :

1. la lecture du fichier et la validation du format déjà implémentée : champs
   exacts, version, variables, noms uniques, commandes, timeouts, profils ;
2. la résolution de l’exécutable de chaque contrôle : un premier argument
   contenant un séparateur de chemin est résolu relativement à la racine du
   dépôt et doit être un fichier exécutable ; sinon il est cherché dans le
   `PATH` de l’environnement filtré, ou dans `os.defpath` lorsque le contrat
   ne transmet pas `PATH` ; cette résolution est celle de 495, pas celle de
   `codex sandbox`, et sert de précondition, non de preuve d’exécutabilité ;
3. la sonde des profils sandbox déjà implémentée, pour chaque profil employé.

Un échec du point 1 produit `configuration_invalid`. Un échec des points 2 ou
3 produit `execution_impossible`, car le contrat peut être correct sur une autre
machine. Ces mêmes contrôles sont exécutés par `verify` avant l’observation du
candidat et par `change` avant l’intervention de l’agent, de sorte qu’un outil
absent ne soit jamais présenté comme un candidat défavorable.

Le jeton `{python}` du lanceur de bootstrap n’existe pas dans le contrat d’une
application cible ; les commandes y sont littérales.

### Enregistrer

`configure write` lit une proposition produite par `propose`, éventuellement
modifiée par l’utilisateur, et en extrait le champ `contract`. Une proposition
est reconnue par un objet JSON dont `command` vaut `configure propose`,
`version` vaut `1` et `contract` est un objet ; tout autre fichier, y compris
une proposition dont `contract` vaut `null`, produit `execution_impossible`
sans écriture. Le contrat extrait passe ensuite par la validation décrite dans
[Valider](#valider), avec les mêmes issues. Après validation complète, le
contrat est écrit indenté, en UTF-8, avec des clés triées.

Le chemin cible doit être situé dans le dépôt, afin qu’une autre personne
puisse le cloner et lancer les mêmes contrôles. Sans `--overwrite`, le fichier
est créé en mode exclusif ; un fichier existant produit `execution_impossible`
sans lecture ni modification de son contenu. Avec `--overwrite`, le nouveau
contenu est écrit dans un fichier temporaire du même répertoire puis renommé
atomiquement. 495 ne crée aucun commit.

Un contrat écrit à la main sans passer par `propose` est pris en charge par
`validate` ; `write` n’accepte que des propositions, pour ne pas confondre les
deux formats.

## Opérations avec et sans Codex

| Opération | Binaire `codex` | `CODEX_HOME` authentifié | Réseau et quota |
| --- | --- | --- | --- |
| `verify` | requis pour `codex sandbox` | non | non |
| `configure validate` | requis pour la sonde des profils | non | non |
| `configure write` | requis pour la sonde des profils | non | non |
| `configure propose` | requis | oui | oui, annoncé dans la documentation |
| `change` | requis | oui | oui, comme aujourd’hui |

Les opérations sans authentification n’appellent jamais `codex login status`.
Elles fournissent au runner sandboxé un `CODEX_HOME` jetable créé sous le `HOME`
temporaire, comme aujourd’hui. Le critère de fin du plan, vérifier un projet
indépendant de Python sans authentification, est satisfait par `verify` dès
lors que `codex` est installé.

## Bornes des sorties

`execute_process` capture chaque flux dans un lecteur dédié qui conserve les
premiers `4 194 304` octets et continue de vider le flux jusqu’à sa fermeture,
en comptant les octets écartés. Le processus n’est donc jamais bloqué sur un
tube plein, et la terminaison du groupe de processus après timeout reste
inchangée : les lecteurs se terminent lorsque les descripteurs se ferment.

La stratégie est un préfixe : le début de la sortie est conservé, le reste est
écarté. Aucun marqueur n’est inséré dans le texte capturé. Le texte est décodé
en UTF-8 après suppression d’une éventuelle séquence multi-octets incomplète en
fin de préfixe, avec remplacement des octets invalides restants.

Chaque résultat de processus rapporte, pour `stdout` et `stderr` :

| Champ | Contenu |
| --- | --- |
| `stdout`, `stderr` | texte conservé |
| `stdout_bytes`, `stderr_bytes` | nombre total d’octets émis |
| `stdout_truncated`, `stderr_truncated` | vrai lorsque des octets ont été écartés |

Ces champs traversent la frontière JSON dans chaque contrôle. Le bloc `agent`
reçoit les quatre champs de comptage et de troncature, mais continue de ne pas
restituer le texte du flux JSONL : il ne contient pas de champ `stdout`,
comme aujourd’hui. La borne est une constante unique de 495, rappelée par
`output_limit_bytes` ; elle n’est pas configurable dans cet incrément.

Le flux JSONL du client est soumis à la même borne. Un flux tronqué ne permet
pas de confirmer la fin du tour : il est rapporté comme `events_error` et
produit `agent_failed`, le candidat restant inspectable. Cette limite est
documentée ; un traitement incrémental du flux n’est pas introduit tant qu’un
usage réel ne dépasse pas la borne.

## Responsabilités extraites de `change.run_change`

Le flux monolithique actuel est découpé en opérations composables. Les modules
existants conservent leur rôle ; les nouvelles frontières sont les suivantes.

| Responsabilité | Aujourd’hui | Cible |
| --- | --- | --- |
| lecture et digest du contrat | inline dans `run_change` | `contract.load_contract(path)` retourne le contrat validé et son digest ; `contract.write_contract` porte l’écriture exclusive ou atomique |
| environnement filtré et `HOME` temporaire | `inherited_environment` et bloc `with` dans `run_change` | module `environment` : un gestionnaire de contexte crée les chemins temporaires hors du dépôt, filtre les variables et rapporte les noms présents et absents |
| racine Git, propreté, référence | `validate_repository` | `workspace.repository_root`, `workspace.require_clean` et `workspace.resolve_baseline`, qui résout la référence, vérifie la lignée et retourne le commit et `HEAD` |
| préconditions des contrôles | `validate_profiles` appelé par `run_change` | `verification.validate_controls` : résolution des exécutables puis sonde des profils, appelée avant l’agent dans `change` et avant l’observation du candidat dans `verify` |
| exécution des contrôles sur un candidat | boucle dans `run_change` | `verification.run_checks` : exécution séquentielle, comparaison du digest après chaque contrôle, arrêt à la première violation, retour des blocs `checks`, `violations`, `candidate_after_checks` et de l’issue |
| vérification directe | absente | `verification.verify_candidate` : `validate_controls`, puis observation du candidat, puis `no_candidate` ou `run_checks` |
| proposition, validation et écriture du contrat | absentes | module `configuration` : construction du prompt et du schéma de proposition, conversion de la réponse en contrat, validation complète, écriture |
| prompt et schéma d’une intervention | `codex.agent_prompt` et `AGENT_RESPONSE_SCHEMA` fixés dans le client | `AgentClient.invoke` reçoit le prompt, le schéma de réponse et le profil de fichiers ; `change` et `configuration` composent leur propre intervention |
| version du runtime des contrôles | absente | `ControlRunner.version` ; l’adaptation Codex réutilise `codex --version` |
| codes de sortie | retournés par `run_change` | table `EXIT_CODES` dans `cli`, dérivée de l’issue ; les opérations retournent seulement leur document |
| sérialisation des résultats | `canonical_bytes` compact | `serialization.result_bytes` indenté pour la sortie standard et les fichiers écrits ; `canonical_bytes` reste réservé aux digests |
| assemblage Codex | `composition.run_codex_change` | `composition` ajoute `verify_with_codex_sandbox`, `propose_with_codex` et `validate_with_codex_sandbox`, sans autre client |

`run_change` conserve son enchaînement : dépôt propre, contrat, environnement,
version et authentification du client, préconditions des contrôles,
intervention, observation, vérification. Il n’en porte plus les détails.

L’interface `AgentClient` s’élargit d’un prompt, d’un schéma et d’un profil
parce que deux opérations réelles l’exigent maintenant. Elle ne prétend pas
davantage couvrir un second client.

## Tests

### Unitaires

- `process` : sortie standard volumineuse, sortie d’erreur volumineuse,
  émission simultanée des deux flux au-delà de la borne, timeout avec flux
  volumineux, sortie ordinaire non tronquée, séquence UTF-8 coupée à la borne,
  conservation du code de sortie et de la durée.
- `workspace` : résolution de `HEAD`, d’un identifiant abrégé, d’une branche,
  d’un tag et de `HEAD~1` ; référence irrésoluble ; référence hors lignée ;
  candidat vide avec `HEAD` ; candidat commité avec une référence antérieure ;
  dépôt modifié accepté par la vérification et refusé par `change`.
- `contract` : chargement et digest ; écriture exclusive ; refus d’un fichier
  existant sans lecture ; remplacement atomique avec `--overwrite` ; chemin
  hors du dépôt refusé.
- `verification` avec doubles injectés : candidat vérifié ; contrôle
  défavorable ; timeout ; plusieurs contrôles exécutés dans l’ordre déclaré ;
  arrêt après un contrôle qui modifie le candidat ; exécutable introuvable
  avant tout contrôle ; sonde sandbox en échec.
- `configuration` : réponse valide convertie en contrat avec attestations ;
  réponse invalide ; réponse `blocked` rapportée comme `agent_failed` ;
  réponse sans contrôle ; proposition violant la validation du contrat ;
  résolution des exécutables ; fichier qui n’est pas une proposition refusé
  par `write`.
- `cli` : table des codes de sortie ; forme sans sous-commande interprétée
  comme `change` ; `--help` en premier argument affichant l’aide de `change` ;
  sérialisation indentée d’un document d’erreur ; timeout d’agent non positif
  rapporté comme `execution_impossible`.

### Intégration CLI

Avec un dépôt Git temporaire et le double de Codex existant, étendu pour
accepter `--sandbox read-only` et un schéma de proposition :

- `verify` : succès ; contrôle défavorable ; absence de candidat avec code
  `4`, `candidate` à `null` et indication dans `limitations` ; arbre propre
  avec exécutable introuvable rapporté comme `execution_impossible` ;
  `--baseline` désignant un commit antérieur ; référence hors lignée ;
  contrat absent ; contrat invalide rapporté comme `configuration_invalid` ;
  exécutable introuvable ; sortie standard
  contenant un seul document JSON et sortie d’erreur vide ; aucun appel à
  `login status`.
- `configure validate` : contrat valide ; contrat invalide ; sandbox
  indisponible.
- `configure propose` : proposition restituée sans écriture ; dépôt inchangé
  après l’inspection ; dépôt modifié après l’inspection rapporté comme
  `agent_failed` ; réponse invalide ; absence de contrôle détectable.
- `configure write` : écriture depuis une proposition ; refus d’écraser ;
  remplacement avec `--overwrite` ; proposition invalide non écrite ; contrat
  écrit relu par `validate` puis utilisé par `verify`.
- compatibilité : l’invocation actuelle et `495 change` produisent le même
  document ; `tools/run_change.py --help` reste fonctionnel ; les tests
  existants de `change` conservent leurs attentes, qui ne dépendent ni de la
  sérialisation compacte ni de l’issue d’un contrat invalide.

### Bout en bout

Deux essais manuels, consignés dans l’état de l’implémentation :

1. sans authentification : un dépôt cible sans Python, par exemple un projet
   dont le contrôle est un script shell, reçoit un contrat écrit à la main,
   passe `configure validate`, subit une modification de fichier, puis obtient
   un verdict favorable et un verdict défavorable de `verify` avec un
   `CODEX_HOME` vide ;
2. avec Codex authentifié, après annonce du besoin de réseau et de quota :
   `configure propose` sur ce même dépôt, relecture de la proposition,
   `configure write`, puis `change` pour confirmer que le parcours avec agent
   produit les mêmes blocs de contrôle que `verify`.

## Limites assumées

- seul `codex sandbox` exécute les contrôles ; `codex` doit être installé même
  sans authentification ;
- la référence doit appartenir à la lignée de `HEAD` ;
- la troncature conserve un préfixe, pas la fin d’une sortie ;
- un flux JSONL tronqué met le parcours avec agent en échec ;
- la proposition de configuration dépend d’un client authentifié ; sans lui,
  le contrat est écrit à la main puis validé ;
- aucun résultat n’est conservé et aucun état de workflow n’est introduit.

## Questions ouvertes

Aucune question ne bloque l’implémentation. Les choix suivants sont pris par
défaut et révocables avec une justification :

- `495.json` comme nom du contrat par défaut, à la racine du dépôt cible ;
- le code `4` pour « rien à vérifier » et « rien à proposer » ;
- le préfixe plutôt que le début et la fin de la sortie.
