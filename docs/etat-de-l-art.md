# État de l’art du premier incrément

## Objet

Ce document examine les clients d’agents, harnais de code et runtimes qui
portent déjà tout ou partie du
[premier incrément vertical](parcours-utilisateur.md#premier-incrément-vertical).
Il sert d’entrée à sa conception. Les comparaisons décrivent les composants
externes ; les sections d’essai consignent les comportements observés par le
runner 495.

L’examen porte sur les besoins suivants :

- invoquer un agent réel sans interface interactive ;
- limiter son contexte, ses outils et ses permissions ;
- obtenir un résultat structuré ;
- observer un candidat indépendamment de la déclaration de l’agent ;
- exécuter les contrôles de l’application cible sous une limite de temps et
  dans un environnement confiné ;
- distinguer les échecs du client, du contrat de sortie et des contrôles ;
- réutiliser un composant maintenu sans importer un harnais concurrent complet.

Les documentations, sources et tests liés ci-dessous ont été consultés le
6 septembre 2026. Les interfaces de ces outils évoluent rapidement ; leur
version et leur comportement devront être vérifiés par des essais exécutables
avant intégration.

## Environnement disponible

Deux clients adaptés sont déjà installés sur la machine étudiée :

| Client | Version observée | Mode non interactif | Sortie contrainte |
| --- | --- | --- | --- |
| Codex CLI | `0.153.3` | `codex exec` | `--output-schema`, `--json`, `--output-last-message` |
| Claude Code | `2.1.261` | `claude --print` | `--output-format json`, `--json-schema` |

Cette présence réduit le coût d’un premier essai mais ne vaut ni sélection
définitive, ni preuve de compatibilité. L’examen initial des interfaces n’a
appelé aucun modèle ; l’essai ciblé décrit plus bas a ensuite invoqué Codex dans
un dépôt jetable.

## Candidats directs

### Codex CLI

Codex fournit une commande non interactive dédiée. Son interface accepte un
répertoire de travail, un mode de sandbox, un schéma de sortie, un flux JSONL
et un mode éphémère. Ces options sont visibles dans le
[code de la CLI](https://github.com/openai/codex/blob/main/codex-rs/exec/src/cli.rs)
et dans le
[SDK TypeScript](https://github.com/openai/codex/blob/main/sdk/typescript/src/exec.ts).
Un [test d’intégration](https://github.com/openai/codex/blob/main/codex-rs/exec/tests/suite/output_schema.rs)
vérifie que le schéma est transmis à l’API comme sortie structurée stricte.

La commande
[`codex sandbox`](https://github.com/openai/codex/blob/main/codex-rs/README.md#experimenting-with-the-codex-sandbox)
applique le sandbox propre à la plateforme à un processus arbitraire, sans
lancer un agent. Elle peut donc être étudiée pour exécuter les contrôles du
candidat sous la même famille de politiques que les commandes de l’agent. Sur
Linux, l’implémentation actuelle préfère Bubblewrap, ajoute `no_new_privs` et
seccomp et conserve Landlock comme solution de repli explicite ; ces choix et
leurs limites sont décrits dans le
[code du sandbox Linux](https://github.com/openai/codex/blob/main/codex-rs/linux-sandbox/README.md).
Sur macOS, le client utilise Seatbelt.

Le projet est open source sous
[licence Apache-2.0](https://github.com/openai/codex/blob/main/docs/license.md).
Son implémentation et ses tests peuvent donc être inspectés pour chaque
comportement dont 495 dépend.

Limites à vérifier :

- `--output-schema` contraint la réponse du modèle, mais 495 doit aussi valider
  lui-même le document qu’il consomme ; le runner le fait avec le même schéma ;
- le format JSONL est un flux d’événements propre au client, distinct du contrat
  métier minimal de 495 ;
- la sandbox du tour agent ne couvre pas un contrôle lancé ensuite par un
  processus ordinaire de 495 ; ce contrôle doit passer par `codex sandbox` ou
  par un autre runtime confiné ;
- les configurations personnelles peuvent ajouter du contexte ou modifier les
  permissions ; `--ephemeral`, `--ignore-user-config`, les profils et les règles
  chargées doivent être évalués explicitement plutôt que combinés par défaut.
  En particulier, le
  [chargeur de skills](https://github.com/openai/codex/blob/main/codex-rs/core-skills/src/loader.rs)
  possède des racines utilisateur distinctes de la configuration : ignorer
  `config.toml` ne démontre donc pas que les skills utilisateur sont absentes.

### Claude Code

Claude Code offre également une interface directement exploitable. Le
[mode non interactif](https://code.claude.com/docs/en/headless) fournit un code
de sortie, un résultat JSON ou JSONL et une sortie validée par JSON Schema. Il
permet aussi de borner les tours et le budget. Les options `--bare`,
`--setting-sources`, `--tools`, `--allowedTools`, `--disallowedTools` et
`--no-session-persistence` donnent des leviers pour maîtriser le contexte et
les capacités chargées.

Sa [sandbox documentée](https://code.claude.com/docs/en/sandboxing) utilise
Seatbelt sur macOS et Bubblewrap sur Linux et WSL2. Elle impose les restrictions
du shell à ses processus descendants, mais pas aux outils de fichiers, hooks,
MCP ou processus lancés en dehors de la session. Le mode strict doit en outre
transformer l’indisponibilité du sandbox en échec et interdire les reprises non
sandboxées.

Anthropic publie séparément
[`@anthropic-ai/sandbox-runtime`](https://github.com/anthropics/sandbox-runtime),
ou `srt`, sous licence Apache-2.0. Ce CLI et cette bibliothèque peuvent confiner
un processus arbitraire avec Seatbelt, Bubblewrap et seccomp ainsi qu’un proxy
réseau. Ils pourraient donc couvrir les contrôles applicatifs indépendamment
du client choisi. Le projet se présente toutefois comme une *research preview* :
son interface et sa configuration ne sont pas encore stables.

Le dépôt public de Claude Code ne contient pas l’implémentation du client et sa
[licence](https://github.com/anthropics/claude-code/blob/main/LICENSE.md) réserve
les droits. 495 peut tester son interface publique, mais pas auditer son
fonctionnement avec la même profondeur que Codex.

Limites à vérifier :

- `--bare` retire notamment les hooks, LSP, plugins et la découverte automatique
  de `CLAUDE.md` ; il ne convient donc pas si les instructions ou skills du
  projet font partie du contexte voulu ;
- les permissions logiques et la sandbox du shell sont deux frontières
  différentes ; un outil autorisé n’est pas nécessairement confiné par
  Seatbelt ou Bubblewrap ;
- la configuration doit refuser explicitement une exécution non confinée plutôt
  que compter sur les valeurs par défaut du poste ;
- les contrôles lancés après la session nécessitent `srt` ou un autre runtime.

## Harnais et runtimes comparés

| Projet | Comportements utiles à 495 | Écart avec le premier incrément |
| --- | --- | --- |
| [Docker Agent](https://github.com/docker/docker-agent) | Exécution sans TUI et JSON, hooks, permissions, faux et enregistrements d’appels, sandbox Docker ; Apache-2.0 | Constitue déjà un harnais complet et appelle les fournisseurs de modèles plutôt que les clients Codex ou Claude Code installés ; le sandbox exige Docker Desktop. |
| [OpenHands](https://github.com/OpenHands/OpenHands) | SDK Python, événements, workspaces locaux ou distants et runtime Docker ; noyau MIT | Plateforme et runtime beaucoup plus larges que le parcours local retenu ; utilise ses propres agents et accès aux modèles. |
| [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | Boucle très courte `modèle → action → observation`, limites de pas, coût et temps, trajectoire JSON ; MIT | Construit son propre agent au-dessus des API de modèles et inclut déjà la boucle de correction, hors périmètre du premier incrément. |
| [SWE-ReX](https://github.com/SWE-agent/SWE-ReX) | Interface Python de commandes, timeouts, sessions persistantes et backends Docker ou distants ; MIT | Son exécution locale n’est pas sandboxée et ses backends isolés apportent une infrastructure destinée notamment aux évaluations massives. |
| [Aider](https://github.com/Aider-AI/aider) | Sélection du contexte par fichiers et carte du dépôt, suivi Git, lint et tests avec retour des erreurs ; Apache-2.0 | Agent complet appelé directement via les API de modèles, commits automatiques par défaut et absence de frontière OS native identifiée. |
| [OpenCode](https://github.com/anomalyco/opencode) | Mode `run`, architecture client-serveur, LSP et permissions `allow`/`ask`/`deny` ; MIT | Les permissions observées contrôlent les outils, mais ne constituent pas à elles seules une sandbox OS ; l’outil appelle les modèles plutôt que les clients retenus. |

Les sources particulièrement instructives sont :

- la [boucle principale de mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py),
  qui sépare le modèle de l’environnement avec très peu d’abstractions ;
- les [options de lint et de test d’Aider](https://github.com/Aider-AI/aider/blob/main/aider/website/assets/sample.aider.conf.yml),
  qui réinjectent les diagnostics défavorables dans la conversation ;
- le [runtime Docker d’OpenHands](https://github.com/OpenHands/docs/blob/main/openhands/usage/architecture/runtime.mdx),
  qui traite commandes et observations comme une frontière indépendante de
  l’agent ;
- le [CLI de Docker Agent](https://github.com/docker/docker-agent/blob/main/cmd/root/run.go),
  qui sépare exécution directe, sortie JSON, cassettes de test et sandbox ;
- la [documentation des permissions d’OpenCode](https://opencode.ai/docs/tools/),
  qui illustre la différence entre autoriser un outil et confiner le processus
  qu’il lance ;
- le [tutoriel de SWE-ReX](https://swe-rex.com/latest/usage/), qui indique
  explicitement que son backend local exécute sans sandbox.

## Enseignements réutilisables

### Composer les clients au lieu de reconstruire un agent

Codex et Claude Code portent déjà la boucle d’outils, les instructions de
projet, les skills, les hooks, les permissions, les appels de modèle et les
formats de sortie. Le premier incrément de 495 n’a pas besoin d’introduire un
SDK de modèle, un registre d’outils ni une boucle agent interne. Une invocation
de processus bornée suffit comme première frontière, tant que ses entrées,
sorties et effets sont observés par 495.

### Séparer résultat déclaré et résultat observé

Les sorties structurées servent à connaître le statut, le résumé, les questions
et les limites annoncées. Elles ne doivent pas devenir l’autorité sur les
fichiers modifiés ni sur la réussite des contrôles. Git identifie le candidat et
495 exécute les contrôles déclarés par l’application cible.

### Réutiliser un sandbox de processus

La sandbox native du client est préférable pour les commandes qu’il lance. Les
contrôles exécutés ensuite ont besoin de la même propriété observable, pas
nécessairement du même mécanisme. `codex sandbox` et `srt` montrent qu’un runner
de processus réutilisable existe déjà sur macOS et Linux. 495 doit décrire la
politique, vérifier son application et recueillir les refus ; il ne doit pas
générer lui-même des profils Seatbelt, Bubblewrap, Landlock ou seccomp dans le
premier incrément.

### Garder les diagnostics natifs

Les harnais étudiés conservent les codes de sortie et observations brutes, puis
en extraient ce qui est utile à la boucle. 495 doit donc structurer le verdict
et les références sans normaliser prématurément les formats de tous les
compilateurs, linters ou runners de tests.

### Tester les frontières avec des doubles et un vrai client

Les cassettes de Docker Agent et les environnements interchangeables de
mini-SWE-agent et SWE-ReX confirment qu’un double déterministe est utile pour les
timeouts, sorties invalides et échecs. Il ne remplace pas l’essai de bout en
bout avec la version réelle du client et sa sandbox.

## Orientation pour la conception

Codex CLI est le premier candidat à éprouver : il est installé, open source,
inspectable, non interactif, capable de produire une sortie contrainte et
accompagné d’un runner de processus sandboxé. Claude Code doit rester le second
candidat concret, car son interface publique couvre le même parcours et fera
apparaître les différences qu’une éventuelle abstraction devra réellement
absorber.

Avant de retenir l’interface de cette intégration, un essai minimal dans un
dépôt jetable doit confirmer :

1. les fichiers et configurations réellement chargés par chaque mode Codex ;
2. la forme des événements, du dernier message et des codes de sortie ;
3. le comportement d’un schéma valide et d’un schéma impossible à satisfaire ;
4. la distinction entre échec technique, refus de sandbox et fin normale sans
   candidat ;
5. les lectures, écritures, accès réseau et variables effectivement visibles à
   l’agent ;
6. l’exécution d’un contrôle favorable, défavorable et bloqué par timeout avec
   `codex sandbox` ;
7. la possibilité d’utiliser les instructions et skills du dépôt sans charger
   les personnalisations utilisateur sans rapport.

Si ces essais contredisent une propriété nécessaire, la conception comparera
le même parcours avec Claude Code et `srt` avant d’ajouter un mécanisme propre à
495.

## Premier essai de Codex CLI

Un essai de bout en bout a été exécuté le 6 septembre 2026 avec Codex CLI
`0.153.3`, dans un dépôt Git jetable distinct de 495. Le dépôt contenait une
instruction `AGENTS.md`, une skill de projet sous `.agents/skills/`, un schéma
JSON et un contrôle déterministe. L’invocation utilisait `codex exec` avec :

- un répertoire de travail explicite ;
- `--ephemeral` et `--ignore-user-config` ;
- le sandbox `workspace-write` ;
- un schéma fourni par `--output-schema` ;
- le flux d’événements `--json` et le dernier message écrit séparément.

L’agent a découvert et lu la skill du dépôt, puis créé uniquement le fichier
demandé. Le dernier message était un objet JSON conforme au schéma, et le flux
JSONL distinguait le démarrage du tour, les messages, les commandes, leurs
codes de sortie et la consommation. Git montrait deux fichiers non suivis : le
candidat créé par l’agent et le dernier message que la commande avait écrit dans
le dépôt pour cet essai. Le contrôle de l’application cible confirmait
indépendamment le contenu exact du candidat.

Le flux rapportait `47 825` jetons d’entrée, dont `31 232` en cache, pour `218`
jetons de sortie. Cette mesure inclut davantage que les seuls fichiers visibles
du petit dépôt ; elle justifie que 495 conserve l’usage annoncé par le client et
vérifie ultérieurement l’effet de chaque source de contexte au lieu d’assimiler
un dépôt minimal à un contexte minimal.

Le même contrôle a ensuite été lancé comme processus autonome avec
`codex sandbox` et le profil `:read-only` :

| Situation | Observation |
| --- | --- |
| contrôle favorable | code `0` et diagnostic de succès |
| contrôle défavorable | code `7` et diagnostic d’erreur conservé |
| contrôle bloqué | processus interrompu par l’appelant après une seconde |
| tentative d’écriture | code `1` et `Operation not permitted` |

Le timeout n’est pas fourni par `codex sandbox` lui-même : il appartient au
processus qui pilote la commande, lequel doit aussi terminer le groupe de
processus. Le refus d’écriture confirme le confinement du contrôle testé, sans
prouver encore sa politique de lecture, de réseau ou d’environnement.

Deux précautions d’intégration se dégagent de l’essai :

- la sortie finale, le flux d’événements et les rapports de 495 doivent être
  écrits hors de l’arbre de travail cible afin de ne pas être confondus avec le
  candidat observé par Git ;
- la validation du JSON par le client ne dispense pas 495 de parser et valider
  indépendamment la réponse avant de lui attribuer un sens métier.

L’essai confirme donc les points 1, 2 et 6 de la liste précédente pour le mode
testé, ainsi que la disponibilité d’une skill de projet et le refus d’écriture
en lecture seule. Il ne montre pas que les autres skills utilisateur étaient
absentes ; le volume d’entrée renforce au contraire la nécessité de mesurer
cette frontière. Restent aussi à éprouver un schéma impossible, les échecs
techniques et la fin sans candidat, les autres modes de chargement, ainsi que
les frontières de lecture, de réseau et d’environnement. Ces cas se prêtent en
majorité à des doubles déterministes ; les propriétés propres au client ou au
sandbox exigent un nouvel essai réel ciblé.

### Essai du runner intégré

Le runner 495 issu de cette conception a ensuite exécuté le même type de dépôt
jetable avec Codex CLI `0.153.3` sur macOS. Une première invocation contenant
une option placée au mauvais niveau a produit un code client `2`, aucun candidat
et aucun contrôle ; 495 l’a restituée comme `agent_failed` avec le diagnostic
natif. Après correction par une valeur de configuration prise en charge, le
parcours complet a produit :

- une réponse agent conforme au JSON Schema et un code client `0` ;
- un unique fichier candidat observé et digéré indépendamment par Git ;
- un contrôle cible sous le profil `:read-only`, avec code `0` et diagnostic ;
- l’issue `candidate_verified`, sans violation ni commit.

La skill du dépôt imposait aussi l’exécution d’un script avant de créer le
candidat. Ce script a vérifié que `CODEX_HOME` était absent de l’environnement
des commandes de l’agent, que `HOME` et `TMPDIR` désignaient l’espace jetable et
qu’une connexion réseau locale échouait avec `Operation not permitted`. Un
processus distinct lancé par `codex sandbox` avec
`--sandbox-state-disable-network` a observé le même refus réseau pour les
contrôles.

Le client a rapporté `49 989` jetons d’entrée, dont `36 736` en cache, et `263`
jetons de sortie pour ce scénario. Les fonctions sans rapport — applications,
navigateurs, hooks, génération d’images, multi-agent, plugins, snapshot du shell
et suggestions d’outils — étaient explicitement désactivées. Cette consommation
montre que limiter les fichiers, skills et capacités ne permet pas de déduire à
elle seule la taille de tout le contexte interne du client ; 495 doit continuer
à rapporter la mesure plutôt que promettre un volume.

Cet essai, complété par les cas déterministes de réponse invalide, absence de
candidat, client non nul, contrôle défavorable, mutation par un contrôle et
timeouts, satisfait les critères observables du premier incrément sur la
plateforme testée. Il ne démontre pas encore la portée exacte des lectures de la
sandbox ni le comportement Linux.
