# État de l’art des clients, harnais et runtimes

## Objet

Ce document compare les clients d’agents de code, les harnais et les runtimes
d’exécution confinée qui portent déjà tout ou partie du comportement recherché
par 495. Il sert d’entrée commune aux conceptions successives et satisfait la
règle d’étude préalable des
[principes et contraintes](principes-et-contraintes.md).

Il décrit des composants externes. Les essais menés par 495 sur ces composants
et les décisions propres à un incrément appartiennent au chantier concerné,
sous `docs/chantiers/`.

L’examen a d’abord porté sur les besoins du
[premier parcours vertical](parcours-utilisateur.md#premier-incrément-vertical) :

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
avant intégration. Un incrément qui dépend d’un composant non encore éprouvé
complète cette comparaison au lieu de la refaire.

## Environnement disponible

Deux clients adaptés sont déjà installés sur la machine étudiée :

| Client | Version observée | Mode non interactif | Sortie contrainte |
| --- | --- | --- | --- |
| Codex CLI | `0.153.3` | `codex exec` | `--output-schema`, `--json`, `--output-last-message` |
| Claude Code | `2.1.261` | `claude --print` | `--output-format json`, `--json-schema` |

Cette présence réduit le coût d’un premier essai mais ne vaut ni sélection
définitive, ni preuve de compatibilité. L’examen des interfaces n’a appelé aucun
modèle ; seuls les essais consignés par un chantier ont invoqué un client dans
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

## Essais menés par 495

Cette comparaison repose sur les interfaces publiées et le code inspectable des
composants. Les comportements réellement observés par 495 sont consignés dans
le chantier qui les a provoqués :

- l’[étude ciblée du premier parcours vertical](chantiers/00-parcours-vertical/etat-de-l-art.md)
  rapporte les essais de Codex CLI `0.153.3` et de `codex sandbox` sur macOS.

Claude Code, `@anthropic-ai/sandbox-runtime` et les autres projets du tableau
n’ont pas encore été éprouvés par 495. Leur intégration éventuelle exige un
essai propre avant toute revendication.
