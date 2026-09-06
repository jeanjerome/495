# Conception du premier incrément vertical

## Portée

Ce document porte la conception de la capacité de 495 décrite dans le
[parcours utilisateur](../../parcours-utilisateur.md#premier-incrément-vertical). Il
fixe les choix appliqués par la commande applicative ;
[l’état de l’implémentation](../../implementation.md) reste l’autorité sur ce qui est
effectivement disponible et validé.

La solution retient un seul parcours et un seul client : une commande reçoit
une demande et un dépôt Git local, invoque Codex CLI une fois, observe le
candidat, exécute les contrôles déclarés par l’application cible et écrit le
résultat JSON sur sa sortie standard.

## Décisions

| Besoin | Décision | Motif |
| --- | --- | --- |
| client réel | composer `codex exec` comme sous-processus | son interface non interactive, son schéma de sortie et sa sandbox couvrent le besoin observé sans reconstruire un agent |
| contrôles applicatifs | composer `codex sandbox` pour chaque commande | la sandbox du tour agent ne couvre pas les processus lancés ensuite par 495 |
| interface de 495 | installer la commande `495` depuis un paquet `src/` | le parcours est désormais un comportement applicatif et non un outil de développement du dépôt |
| configuration cible | lire un contrat JSON explicite fourni à la commande | les contrôles appartiennent à l’application cible et aucune découverte implicite n’est nécessaire |
| résultat de l’agent | fournir un JSON Schema à Codex puis revalider le JSON dans 495 | la contrainte appliquée par le client ne remplace pas la validation à la frontière du harnais |
| identité du candidat | comparer l’arbre de travail Git à son `HEAD` initial | la déclaration de l’agent n’est pas une preuve de ses effets |
| artefacts du harnais | utiliser un répertoire temporaire extérieur au dépôt cible | le flux JSONL, le dernier message et le schéma ne doivent pas apparaître dans le candidat |
| persistance | ne conserver aucun rapport par défaut | la restitution immédiate suffit au premier parcours ; le candidat reste dans le dépôt cible |

495 n’introduit donc ni SDK de modèle, ni boucle agent interne, ni second
client, ni implémentation propre de Seatbelt. L’adaptation porte sur
l’interface de processus réellement utilisée, sans recopier le fonctionnement
interne de Codex.

## Frontières applicatives

Le paquet `harness495` porte le comportement du produit. Son module `change`
conduit le cas d’usage à travers deux capacités explicites : `AgentClient` pour
obtenir un candidat et `ControlRunner` pour lui appliquer les feedbacks de
l’application cible. Codex CLI et `codex sandbox` fournissent les seules
adaptations actuelles de ces interfaces.

L’observation Git appartient à une frontière `workspace`, distincte de la
réponse de l’agent. La CLI ne contient que la traduction des arguments, des
codes de sortie et du document JSON. Cette séparation permet de remplacer une
intégration observable sans faire dépendre l’orchestration de ses options de
processus ; elle ne préjuge pas de l’architecture d’applications confiées à
495.

## Interface de commande

La commande est :

```sh
uv run 495 \
  --repository /chemin/vers/application \
  --contract /chemin/vers/application/495.json \
  --codex-home /chemin/vers/un/codex-home-dedie \
  --request-file /chemin/vers/demande.md
```

Les quatre chemins sont explicites. Le répertoire Codex dédié doit être déjà
authentifié ; 495 ne copie, ne déplace et ne renouvelle aucun secret. La demande
n’est pas placée dans les arguments de `codex`, mais transmise sur son entrée
standard. La sortie standard de 495 contient un unique document JSON final,
diagnostics des processus compris. Seules les erreurs d’usage de la commande
précèdent ce document sur la sortie d’erreur.

Le code de sortie distingue au minimum :

- `0` : candidat présent et tous les contrôles favorables ;
- `1` : candidat présent avec au moins un contrôle défavorable ou expiré ;
- `2` : précondition ou configuration invalide ;
- `3` : client en échec, interrompu ou réponse agent invalide.

Le JSON reste l’autorité détaillée : le seul code de sortie ne suffit pas à
interpréter le résultat.

Le lanceur `tools/run_change.py` délègue à cette même CLI pour conserver la
compatibilité avec les premières utilisations du parcours.

## Contrat de l’application cible

Le contrat ne décrit que ce qui appartient à l’application :

```json
{
  "version": 1,
  "environment": ["PATH", "LANG"],
  "checks": [
    {
      "name": "tests",
      "command": ["uv", "run", "pytest"],
      "timeout_seconds": 300,
      "filesystem": "workspace-write"
    }
  ]
}
```

Une commande est une liste d’arguments non vide et n’est jamais interprétée par
un shell. Les noms sont uniques, les timeouts sont strictement positifs et les
champs inconnus sont refusés. `filesystem` accepte d’abord `read-only` et
`workspace-write`, que 495 traduit respectivement vers les profils Codex
`:read-only` et `:workspace`.

`environment` énumère les seules variables héritées par les commandes de
l’agent et les contrôles, en plus d’un `HOME` et d’un répertoire temporaire
propres à l’exécution. Les noms et les variables absentes sont annoncés avant
l’appel, mais leurs valeurs ne sont jamais écrites dans le résultat. Une chaîne
d’outils qui dépend d’autres variables doit les déclarer explicitement. Les
noms contenant `KEY`, `SECRET` ou `TOKEN` sont refusés : la transmission d’un
secret n’appartient pas à ce premier incrément.

Le premier incrément n’accorde pas d’accès réseau aux contrôles. Une application
qui doit télécharger des dépendances les prépare avant le parcours ou reçoit un
diagnostic de capacité manquante. Les permissions appliquées et le nom du
runtime sont répétés dans le résultat.

## Invocation de l’agent

Après les préconditions, 495 exécute directement une commande équivalente à :

```text
codex exec --json --ephemeral --ignore-user-config
  --strict-config --config approval_policy="never"
  --config skills.bundled.enabled=false
  --config shell_environment_policy.inherit=all
  --config shell_environment_policy.include_only=<noms-autorisés>
  --config shell_environment_policy.ignore_default_excludes=false
  --config sandbox_workspace_write.network_access=false
  --sandbox workspace-write -C <dépôt>
  --output-schema <artefact-temporaire>
  --output-last-message <artefact-temporaire> -
```

Le processus reçoit une durée maximale et appartient à un groupe que 495 peut
terminer entièrement. Sa sortie JSONL est lue comme un flux d’événements ; son
code de sortie, ses diagnostics et l’usage annoncé sont conservés dans le
résultat. Les événements inconnus ne font pas échouer l’exécution, mais 495 ne
leur attribue aucun sens.

Même avec `--ephemeral`, la version testée crée des caches, une configuration et
des fichiers d’état opérationnels dans `CODEX_HOME`. 495 ne les assimile pas à
son historique, ne les publie pas et ne les efface pas dans un répertoire fourni
par l’utilisateur. Un `CODEX_HOME` jetable peut être supprimé par son
propriétaire après l’exécution.

`--ignore-user-config` écarte le `config.toml` utilisateur, mais pas à lui seul
toutes les racines de skills. 495 exécute donc le client avec le `CODEX_HOME`
dédié indiqué par l’utilisateur, un `HOME` temporaire et les skills système
groupées désactivées. Les instructions et skills du dépôt restent disponibles
par les mécanismes du client. Cette combinaison est vérifiée avec Codex CLI
`0.153.3`. Si une autre version empêche 495 de distinguer le contexte du dépôt
des skills utilisateur, l’invocation doit s’arrêter au lieu d’annoncer une
isolation fictive.

495 ajoute seulement la demande, le contrat de réponse et les limites du
parcours ; il ne copie pas le dépôt dans le prompt. La politique d’environnement
des commandes de l’agent reprend uniquement la liste explicite du contrat et
les chemins temporaires, mais pas `CODEX_HOME`. Cette combinaison utilise les
options décrites dans la
[référence de configuration Codex](https://developers.openai.com/codex/config-reference#shell_environment_policyinherit).
Aucun hook propre à 495 n’est introduit dans cet incrément.

La réponse minimale de l’agent contient :

- `status`, avec `completed` ou `blocked` ;
- `summary`, une chaîne ;
- `questions`, une liste de chaînes ;
- `limitations`, une liste de chaînes.

Tous les champs sont obligatoires et les champs inconnus sont refusés. Cette
réponse décrit l’intention de l’agent, jamais l’identité du candidat ni le
verdict des contrôles.

La validation utilise
[`jsonschema`](https://github.com/python-jsonschema/jsonschema), version `4.26`
au moment du verrouillage. Cette implémentation stable sous licence MIT prend en
charge Python 3.12 et évite qu’un validateur manuel diverge du schéma transmis
au client ; ses dépendances transitives sont conservées dans `uv.lock`.

## Observation du candidat

Avant l’appel, 495 exige un dépôt propre et un `HEAD` résoluble, puis conserve
l’identifiant de ce commit. Après l’appel, il interroge Git sans modifier
l’index. Un candidat existe lorsque l’état suivi, indexé ou non, ou les fichiers
non suivis diffèrent de cet état initial.

L’identité calculée comprend le commit initial, le statut Git de chaque chemin
et un digest du contenu présent, ou un marqueur de suppression. Les chemins
ignorés par Git ne font pas partie du candidat. Les chemins annoncés par l’agent
peuvent être rapportés comme information, mais ne remplacent jamais cette
observation.

Un client en échec peut avoir laissé un candidat partiel. 495 le signale et le
laisse inspectable, mais ne lance pas les contrôles et ne le présente pas comme
vérifié.

## Exécution des contrôles

Chaque contrôle est exécuté une fois, séquentiellement, avec son répertoire de
travail fixé à la racine cible. 495 appelle `codex sandbox` avec le profil
correspondant, recueille le code de sortie, la durée, le timeout, `stdout` et
`stderr`, et termine le groupe de processus lorsqu’il dépasse sa limite.

Certains outils écrivent des caches ou produits de compilation. Ils peuvent le
faire sous `workspace-write`, mais l’état Git visible doit rester celui du
candidat observé. 495 compare cet état avant et après chaque contrôle. Toute
modification visible est rapportée comme violation et empêche le verdict
« candidat vérifié » ; 495 ne supprime pas silencieusement ces fichiers.

Cette règle permet le premier parcours sans fabriquer une copie de travail ou
un conteneur. Si des applications réelles ont besoin de contrôles qui modifient
l’état visible, ce besoin observable justifiera ensuite un workspace isolé.

## Résultat restitué

Le document final contient au minimum :

- une version de format et une issue parmi `candidate_verified`,
  `candidate_failed`, `agent_failed` et `execution_impossible` ;
- le digest de la demande et le commit initial ;
- le client, sa version, les permissions annoncées, son code de sortie, son
  éventuel timeout, sa réponse validée et son usage ;
- le digest du candidat et ses chemins observés, y compris lorsqu’il est
  partiel ;
- chaque contrôle avec sa commande, son profil, son code, sa durée, son timeout
  et ses diagnostics ;
- les violations et limites connues.

Les diagnostics peuvent contenir des informations sensibles produites par les
outils de l’application. Ils sont restitués à l’utilisateur local mais ne sont
ni publiés ni persistés automatiquement.

## Contrôles de l’implémentation

Les tests automatisés utilisent un exécutable Codex double dans des dépôts Git
temporaires pour couvrir les réponses valides et invalides, l’absence de
candidat, les modifications partielles, les codes non nuls et les timeouts. Un
double de sandbox couvre de manière déterministe les contrôles favorables,
défavorables, bloqués et les diagnostics.

Un essai séparé avec le client réel démontre l’intégration sans devenir un test
ordinaire : il nécessite une authentification, du réseau, du temps et un quota.
L’[essai initial](etat-de-l-art.md#premier-essai-de-codex-cli) confirme déjà la
découverte d’une skill de projet, la sortie structurée, l’observation Git et les
trois issues d’un contrôle. L’essai du runner intégré vérifie en plus les
permissions d’environnement et de réseau sur macOS ; les doubles rendent les
réponses invalides et les échecs reproductibles sans appel de modèle.

## Limites assumées

- seul Codex CLI est pris en charge ;
- l’état initial doit être propre et posséder un commit ;
- une seule intervention d’agent est exécutée ;
- les contrôles sont séquentiels et ne déclenchent aucune correction ;
- les hooks, la reprise, les commits, la publication et la conservation d’un
  historique restent hors périmètre ;
- les sorties sont capturées en mémoire sans limite de taille propre ;
- la disponibilité de `codex`, de ses deux commandes et des profils attendus est
  vérifiée, mais 495 ne les installe pas et ne remplace pas leur sandbox ;
- un `CODEX_HOME` dédié et déjà authentifié est requis pour ne pas confondre
  l’identité nécessaire au client avec les personnalisations de son utilisateur.
