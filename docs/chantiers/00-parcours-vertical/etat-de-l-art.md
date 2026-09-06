# État de l’art du premier parcours vertical

## Objet

Ce document porte l’étude ciblée du
[premier parcours vertical](../../parcours-utilisateur.md#premier-incrément-vertical)
et les essais qui l’ont validée. La comparaison des clients, harnais et
runtimes examinés est commune aux incréments et vit dans
l’[état de l’art](../../etat-de-l-art.md) du dépôt.

L’orientation ci-dessous a précédé la
[conception](conception.md) de ce parcours ; les sections d’essai consignent
ensuite les comportements observés par le runner 495.

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
