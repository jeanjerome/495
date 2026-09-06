# Présentation de 495

495 vise à automatiser le développement assisté par IA tout en le rendant plus
facile à comprendre et à contrôler. L’utilisateur exprime un besoin ; 495 lance
la clarification puis orchestre des agents comme Codex, Claude Code ou un agent
local jusqu’à la vérification et l’intégration du changement.

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
que lorsqu’une fonctionnalité observable en aura besoin.

Le cycle d’un changement reste structuré par les états `clarifying`,
`specifying`, `designing`, `implementing`, `verifying`, `accepted`,
`integrating` et `integrated`. Les gates G0 à G5 rendent leurs passages
explicites. Cette structure décrit le parcours du produit ; elle n’impose pas à
elle seule une architecture complexe ni un document distinct par état.

Les agents peuvent utiliser les prompts, skills, hooks et autres outils
disponibles dans leur environnement. Une exigence obligatoire ne peut
cependant pas être ignorée ni déclarée satisfaite sur la seule affirmation de
l’agent qui a produit le changement.

La CLI constitue la première interface. Une TUI ou une interface web pourra
ensuite exposer les mêmes actions avec une expérience centrée sur l’objectif de
l’utilisateur : apporter un changement à sa base de code, suivre son
avancement, répondre aux blocages et examiner le résultat.
