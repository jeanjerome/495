# Présentation de 495

495 est un harnais d’agents de code qui vise à automatiser le développement
assisté par IA tout en le rendant plus facile à comprendre et à contrôler.
L’utilisateur exprime un besoin ; 495 lance la clarification puis orchestre des
agents comme Codex, Claude Code ou un agent local jusqu’à la vérification et
l’intégration du changement.

Les contrôles en amont (*feedforward*) cadrent ce que l’agent tente en
sélectionnant notamment son contexte, ses outils et ses permissions. Les
contrôles en retour (*feedback*) observent le candidat et lui fournissent des
diagnostics précis à corriger. Chaque agent s’exécute dans une sandbox et remet
à l’orchestrateur une réponse JSON conforme au schéma de l’opération.

Une exécution utile doit notamment permettre de répondre simplement à ces
questions : quelle demande est traitée, quelles exigences s’appliquent, quels
agents et outils sont intervenus, quels fichiers ont été considérés, quels
contrôles ont été exécutés et quel résultat ont-ils produit ?

Le nom vient de la constante de Kaprekar pour les nombres à trois chiffres : en
réordonnant puis en soustrayant leurs chiffres, le calcul atteint 495. Cette
image évoque une progression guidée par des règles explicites ; elle ne promet
ni déterminisme du code produit, ni convergence automatique.

Le projet privilégie désormais les parcours utilisateur réels. Les modèles de
domaine, les protocoles d’adaptateurs ou la persistance ne seront introduits
que lorsqu’une fonctionnalité observable en aura besoin. Avant de concevoir leur
implémentation interne dans 495, ses contributeurs examinent les clients,
harnais d’agents de code et composants open source qui fournissent déjà le
comportement recherché. Cette règle ne s’applique pas à l’architecture des
applications confiées à 495.

Le cycle d’un changement reste structuré par les états `clarifying`,
`specifying`, `designing`, `implementing`, `verifying`, `accepted`,
`integrating` et `integrated`. Les gates G0 à G5 rendent leurs passages
explicites. Cette structure décrit le parcours du produit ; elle n’impose pas à
elle seule une architecture complexe ni un document distinct par état.

495 prolonge [CodeServo](https://github.com/jeanjerome/codeservo), qui a déjà
exploré l’implémentation par agents, la vérification, le feedback et la revue.
Il en reprend les comportements utiles sans importer par défaut sa plateforme
expérimentale, sa métrologie détaillée et ses mécanismes de preuve. Il élargit
ensuite cette boucle à la clarification, la spécification, la conception,
l’acceptation et l’intégration.

Les agents peuvent utiliser les prompts, skills, hooks et autres outils
disponibles dans leur environnement. Une exigence obligatoire ne peut
cependant pas être ignorée ni déclarée satisfaite sur la seule affirmation de
l’agent qui a produit le changement.

La CLI constitue la première interface. Une TUI ou une interface web pourra
ensuite exposer les mêmes actions avec une expérience centrée sur l’objectif de
l’utilisateur : apporter un changement à sa base de code, suivre son
avancement, répondre aux blocages et examiner le résultat.
