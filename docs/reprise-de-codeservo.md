# Reprise de CodeServo dans 495

## Relation entre les projets

[CodeServo](https://github.com/jeanjerome/codeservo) a expérimenté et
implémenté la boucle centrale des états `implementing` et `verifying` : confier
une modification à un agent, mesurer le candidat, lui transmettre les échecs,
relancer une correction, effectuer une revue et décider du résultat.

495 reprend cette expérience. Il ne s’agit ni d’une réécriture sans héritage,
ni d’un portage complet de son architecture. Le nouveau projet poursuit deux
objectifs simultanés :

- simplifier radicalement l’implémentation de cette boucle ;
- l’inscrire dans le cycle complet décrit par les
  [parcours utilisateur](parcours-utilisateur.md), du besoin initial à
  l’intégration du changement.

Le comportement utile est l’héritage. Les couches, protocoles, formats et
preuves ne le sont que lorsqu’un usage actuel les exige.

## Comportements à conserver

CodeServo fournit des bases concrètes que 495 doit préserver :

- des intégrations réelles avec Codex et Claude Code ;
- un agent chargé de produire le changement et une revue capable de relever ce
  que les contrôles exécutables ne couvrent pas ;
- des commandes du projet cible comme autorité sur les vérifications qu’elles
  exécutent ;
- une boucle de correction alimentée par les erreurs, observations et constats
  de revue ;
- une correspondance explicite entre critères d’acceptation et moyens de
  vérification ;
- un candidat identifiable auquel les résultats se rapportent ;
- une décision calculée à partir des résultats plutôt que déclarée par l’agent
  qui a modifié le code ;
- des issues distinctes lorsque le candidat échoue, réussit ou nécessite une
  décision que l’automatisation ne peut pas prendre ;
- une intégration déclenchée explicitement et vérifiée après son exécution.

Les constats expérimentaux restent également utiles : des contrôles verts ne
prouvent que ce qu’ils mesurent, une revue sémantique peut trouver des défauts
sans être reproductible, et une spécification incomplète limite davantage la
qualité qu’un modèle plus puissant ne peut la compenser.

## Complexité non reprise par défaut

CodeServo a combiné un harnais d’agents, une plateforme expérimentale et un
système de preuve détaillé. Cette combinaison a rendu chaque évolution coûteuse.
495 reste un harnais d’agents de code, mais ne reprend donc pas automatiquement :

- un profil de confinement unique appliqué indistinctement à chaque agent et à
  chaque commande, sans tenir compte de leurs besoins ;
- l’interdiction générale du réseau, des skills, des hooks, de la mémoire ou
  des outils proposés par les agents ;
- l’exigence d’un dépôt propre et d’un checkout isolé pour toute modification ;
- le gel et le digest systématiques de la tâche, de la constitution, des
  profils, des capteurs et de chaque sortie ;
- les capteurs privés conservés dans un dépôt d’état séparé ;
- le journal chaîné, les schémas de record successifs et la provenance
  exhaustive de chaque appel de modèle ;
- les générations gelées, checkpoints, protocoles préenregistrés et mécanismes
  d’auto-hébergement expérimental ;
- un adaptateur propre à chaque gestionnaire d’environnement ou format de
  résultat ;
- une couche, un port ou une taxonomie fermée avant qu’un second cas réel ne
  rende l’abstraction nécessaire.

Ces mécanismes ne sont pas tous incorrects. Les garanties qui dépassent le
socle deviennent conditionnelles : une évaluation avec capteur secret peut
exiger un profil de confinement renforcé et une preuve d’isolation ; une
exécution distante peut exiger davantage de provenance ; une interface
persistante peut exiger une base transactionnelle. Le parcours concerné doit
alors démontrer leur valeur et supporter leur coût.

## Simplification retenue

495 applique les choix suivants :

- le besoin exprimé par l’utilisateur lance `clarifying` ;
- les agents disponibles participent à toutes les étapes utiles avec leurs
  prompts, skills, hooks et outils ;
- les exigences obligatoires et leurs moyens de vérification structurent les
  gates, sans imposer un document séparé pour chaque état ;
- les commandes et formats standards du projet cible sont utilisés directement
  lorsqu’ils suffisent ;
- les commandes ordinaires peuvent utiliser l’environnement courant ; chaque
  agent et ses processus descendants utilisent une sandbox avec les seules
  permissions nécessaires à leur intervention ;
- sous Linux, le choix entre Bubblewrap, Landlock et les namespaces évalue
  aussi l’ajout d’un filtre seccomp ; sous macOS, l’étude couvre Seatbelt et les
  solutions d’isolation prises en charge ;
- le contexte de chaque agent est construit à partir de l’état courant et du
  dernier feedback, sans transmettre par défaut les informations sans rapport ;
- le résultat remis par un agent à l’orchestrateur est du JSON validé par le
  JSON Schema de l’opération ;
- Git porte le contenu et l’historique du changement ; 495 ne construit pas un
  second magasin de versions ;
- la persistance et les rapports se limitent aux informations nécessaires pour
  comprendre, reprendre ou présenter le workflow courant ;
- une première intégration d’agent reste directe ; l’interface commune est
  extraite seulement lorsqu’un autre agent révèle les différences à absorber ;
- la CLI expose d’abord le parcours complet ; une TUI ou une interface web
  réutilise ensuite les mêmes opérations.

La simplification ne doit pas réduire les exigences. Elle réduit le nombre de
mécanismes utilisés pour les porter et les vérifier.

## Extension au workflow complet

CodeServo devient une source pour la partie centrale du workflow, pas sa
frontière :

| Workflow 495 | Apport de CodeServo | Extension attendue dans 495 |
| --- | --- | --- |
| `clarifying` | La tâche était déjà rédigée avant l’exécution. | Partir de l’expression initiale et utiliser les agents pour lever les ambiguïtés. |
| `specifying` | Les critères d’acceptation alimentaient les contrôles et la revue. | Aider à produire les exigences et vérifier qu’elles couvrent tous les niveaux applicables. |
| `designing` | La constitution et la configuration existaient avant l’agent. | Faire produire et examiner une conception proportionnée au changement. |
| `implementing` | Actionneurs Codex et Claude Code, contexte, feedback et itérations. | Réutiliser ces comportements avec un contexte ciblé, un confinement explicite et moins de métrologie par défaut. |
| `verifying` | Gates, observations, cliquets et revue sémantique. | Conserver les oracles utiles et simplifier leur déclaration et leur restitution. |
| `accepted` | Verdict calculé sur le candidat. | Relier G4 à toutes les exigences du changement et aux décisions humaines réellement nécessaires. |
| `integrating` | Une commande appliquait le patch et créait un commit. | Orchestrer l’effet adapté au projet et rendre ses erreurs récupérables. |
| `integrated` | Le commit d’intégration était enregistré. | Vérifier par G5 que la destination contient bien le candidat accepté. |

## Règle de réutilisation dans 495

Le code de CodeServo est une réserve d’implémentations et de tests, pas le
squelette imposé de 495 ni l’unique source à examiner. Avant de concevoir ou de
reprendre un composant interne à 495, l’étude inclut les autres harnais d’agents
de code et outils open source qui fournissent le même comportement. Il faut
établir :

1. le parcours utilisateur courant qui en a besoin ;
2. le comportement précis à préserver ;
3. le risque concret évité ;
4. l’absence d’une solution plus directe fournie par Python, le client d’agent
   ou un projet open source maintenu ;
5. le coût de maintenance restant après retrait des garanties expérimentales.

Un composant peut être copié, extrait ou réécrit selon la solution la plus
simple. Sa structure historique ne constitue pas une contrainte de conception.
