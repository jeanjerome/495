# Expression de besoins

**495 doit embarquer des bibliothèques et des ressources méthodologiques, piloter des environnements de développement interchangeables et rester indépendant de la technologie des applications.**

**La séparation structurante est la suivante.**

| Partie                        | Responsabilité                                                                             | Dépendances                                                     |
| ----------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| **495**                       | Organiser le travail, préparer le contexte de l’IA, gérer les gates, conserver les preuves | Bibliothèques embarquées dans sa distribution                   |
| **Application cible**         | Spécifications, conception, code, tests et configuration de build                          | Technologies propres au projet                                  |
| **Environnement d’exécution** | Exécuter les agents, builds et contrôles                                                   | Local existant ou distant, derrière un adaptateur               |
| **Fournisseur d’IA**          | Produire ou examiner des propositions                                                      | Adaptateur interchangeable ; aucun CLI propriétaire obligatoire |

Une application Java ne doit donc pas utiliser des tests Python parce que 495 est écrit en Python. Et un utilisateur ne doit pas installer OPA, Witness, Harbor et Dagger pour lancer 495.

Il reste une contrainte matérielle : compiler une application Java nécessite un environnement Java **quelque part**. On considèrera que l'environnement de développement est à la charge du projet et non de 495. De même, un simple sous-processus ou un worktree Git ne constitue pas une isolation de sécurité.

Je retiendrais donc : **aucun outil supplémentaire obligatoire sur le poste pour le noyau de 495 ; des capacités d’exécution explicitement fournies par l’environnement choisi.**

**Pour couvrir le cycle de développement, la base pertinente devient Agilité + BDD + développement piloté par les spécifications.**

Ces approches sont complémentaires :

| Approche                           | Apport à 495                                            | Ce qu’elle ne remplace pas             |
| ---------------------------------- | ------------------------------------------------------------- | -------------------------------------- |
| **Agilité**                        | Petits incréments, feedback rapide, adaptation du besoin      | Des critères d’acceptation précis      |
| **BDD / Example Mapping**          | Clarification collaborative des règles, exemples et questions | La conception technique                |
| **Gherkin**                        | Expression structurée de comportements observables            | Leur implémentation en tests           |
| **Spec-driven development**        | Artefacts explicites servant d’entrée aux agents              | La vérification de leur justesse       |
| **ADR et conception par contrats** | Décisions argumentées et interfaces explicites                | Les contrôles de l’architecture réelle |
| **TDD et tests de propriétés**     | Boucles de vérification pendant l’implémentation              | La validation du besoin utilisateur    |

Le BDD est particulièrement intéressant : Cucumber le présente comme un enchaînement de **découverte, formulation et automatisation**, avec des changements petits et itératifs. Cela correspond bien à un harnais qui accompagne l’IA avant et pendant le coding. [Présentation officielle du BDD](https://cucumber.io/docs/bdd/)

Je ne construirais donc pas trois grandes phases figées pour toute l’application. **Chaque incrément traverserait spécification, conception et implémentation**, avec des retours possibles et une traçabilité des modifications. Cela respecte l’adaptation continue portée par l’Agilité. [Principes du manifeste Agile](https://agilemanifesto.org/principles.html)

**Deux projets sont beaucoup plus pertinents que ceux que j’avais privilégiés : Spec Kit et OpenSpec.**

| Projet                                                          | Ce qui existe                                                               | Réutilisation envisagée dans 495                                       | Limite                                                                                 |
| --------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **[GitHub Spec Kit](https://github.com/github/spec-kit)** — MIT | Constitution, spécification, plan, tâches, instructions pour agents         | Embarquer une sélection versionnée de modèles et d’instructions              | Son workflow ne constitue pas une preuve indépendante de conformité                    |
| **[OpenSpec](https://github.com/Fission-AI/OpenSpec)** — MIT    | Propositions de changement, spécifications, conception, tâches et archivage | Réutiliser des conventions et ressources adaptées aux évolutions d’un projet | La modification libre des artefacts doit être encadrée pendant une exécution contrôlée |

Leurs licences MIT permettent la réutilisation et la redistribution avec conservation des mentions requises. **Cela ne nécessite pas de demander à l’utilisateur d’installer leurs CLI** : 495 peut distribuer les ressources sélectionnées et implémenter leur orchestration. Il faut toutefois identifier précisément les fichiers repris et leur version, plutôt que supposer une API de bibliothèque stable. [Licence Spec Kit](https://github.com/github/spec-kit/blob/main/LICENSE), [licence OpenSpec](https://github.com/Fission-AI/OpenSpec/blob/main/LICENSE)

Mon arbitrage serait :

* **Spec Kit comme point de départ pour structurer les entrées et sorties des étapes.**
* **OpenSpec comme référence pour gérer les changements et l’évolution des spécifications.**
* **Un seul workflow cohérent dans 495**, après sélection des éléments utiles.

Je ne reprendrais pas leurs conclusions d’agent comme verdicts. Une case « tâche terminée » reste une déclaration à vérifier.

**Gherkin peut devenir un format central, mais il faut distinguer lecture et exécution.**

Le [parseur officiel Gherkin](https://github.com/cucumber/gherkin), sous licence MIT, possède une implémentation Python. 495 peut l’embarquer pour :

* analyser les fichiers `.feature` ;
* extraire règles, scénarios, exemples et tags ;
* relier les scénarios aux exigences ;
* détecter des erreurs de syntaxe ;
* préparer le contexte envoyé à l’IA.

En revanche, exécuter un scénario nécessite de relier ses étapes à du code de test. C’est le rôle des *step definitions*, propres au runner choisi par le projet. [Documentation Cucumber](https://cucumber.io/docs/cucumber/step-definitions/)

| Dans 495                            | Dans l’application cible                         |
| ----------------------------------------- | ------------------------------------------------ |
| Analyse du Gherkin et traçabilité         | Implémentation des étapes de test                |
| Vérification de la présence d’un résultat | Exécution avec le runner adapté                  |
| Politique sur les scénarios non exécutés  | Démarrage de l’application et de ses dépendances |
| Conservation des preuves                  | Assertions sur le comportement réel              |

Le protocole **[Cucumber Messages](https://github.com/cucumber/messages)**, également MIT, est intéressant pour récupérer des résultats structurés sans coupler 495 au langage du runner.

Mais Gherkin ne doit pas tout absorber. Un objectif de latence, une règle de dépendance entre modules ou une décision architecturale peuvent être exprimés plus clairement dans un contrat ou un document dédié.

**Voici le workflow que je proposerais pour chaque incrément.**

| Étape           | Méthode et artefacts                                                     | Contribution de l’IA                                        | Condition de passage                                       |
| --------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------- | ---------------------------------------------------------- |
| **Clarifier**   | Objectif, périmètre, règles, exemples, questions ouvertes                | Détecter ambiguïtés, proposer contre-exemples et découpages | Questions bloquantes résolues par l’autorité compétente    |
| **Spécifier**   | Exigences identifiées, Gherkin pertinent, contraintes non fonctionnelles | Rédiger et confronter les scénarios au besoin               | Critères vérifiables et validation métier enregistrée      |
| **Concevoir**   | Composants, contrats, ADR, stratégie de test                             | Proposer des options et expliciter leurs conséquences       | Couverture des exigences et décisions importantes validées |
| **Implémenter** | Petites tâches reliées aux exigences                                     | Modifier code et tests, traiter le feedback                 | Contrôles obligatoires satisfaits sur le candidat exact    |
| **Intégrer**    | Résultats, documentation, état des spécifications                        | Préparer la synthèse et identifier les écarts               | Acceptation enregistrée ; incrément intégré ou clôturé     |

Les **ADR** permettent de conserver le contexte, les alternatives et les conséquences d’une décision sans installer un outil particulier. [Présentation et modèles ADR](https://adr.github.io/adr-templates/)

Pour les API HTTP, **OpenAPI** fournit un contrat indépendant du langage de l’application. Il s’insère naturellement dans la conception, puis dans la validation de l’implémentation. [Présentation officielle d’OpenAPI](https://www.openapis.org/what-is-openapi)

Il faut néanmoins reconnaître les limites des gates documentaires : **un parseur peut prouver qu’une spécification est bien formée, pas qu’elle exprime le bon besoin.** La validation métier et certains arbitrages de conception restent humains. 495 doit en conserver l’auteur, le périmètre et la version approuvée.

**Le socle technique embarquable peut être beaucoup plus petit.**

En conservant Python pour 495, les candidats suivants répondent mieux à tes contraintes :

| Composant                                                                  | Licence du composant    | Fonction interne                                            | Installation séparée |
| -------------------------------------------------------------------------- | ----------------------- | ----------------------------------------------------------- | -------------------- |
| **Gherkin officiel, implémentation Python**                                | MIT                     | Analyse des spécifications comportementales                 | Non                  |
| **Cucumber Messages**                                                      | MIT                     | Échange de résultats BDD                                    | Non                  |
| **[jsonschema](https://github.com/python-jsonschema/jsonschema)**          | MIT                     | Validation des contrats internes et résultats d’adaptateurs | Non                  |
| **[transitions](https://github.com/pytransitions/transitions)**            | MIT                     | Machine à états et conditions de transition                 | Non                  |
| **[cryptography](https://github.com/pyca/cryptography/blob/main/LICENSE)** | Apache-2.0 ou BSD       | Signatures, si nécessaires                                  | Non                  |
| **Bibliothèque standard Python**                                           | Fournie avec le runtime | Hashes, journalisation, stockage SQLite                     | Non                  |

« Embarqué » signifie fourni avec la distribution de 495, éventuellement avec son runtime. Cela implique de construire et vérifier les distributions pour les plateformes supportées ; pas de déléguer l’installation des dépendances à chaque utilisateur.

Les licences ci-dessus sont celles des composants consultés. La nomenclature finale devra aussi couvrir **leurs dépendances transitives et les binaires effectivement distribués**. C’est cette distribution précise qu’il faudra qualifier.

Je commencerais même sans bibliothèque dédiée à la machine à états si les transitions restent simples. `transitions` économise de la mécanique, mais ne fournit pas à elle seule la persistance atomique, les règles d’acceptation ou la reprise après incident.

**Les contrôles des applications doivent passer par un contrat d’adaptateur.**

495 demanderait des capacités comme :

* construire ;
* exécuter les tests d’acceptation ;
* vérifier l’architecture ;
* vérifier les contrats ;
* produire un candidat.

L’adaptateur du projet traduirait ces demandes en opérations adaptées à sa technologie. 495 recevrait un résultat normalisé comprenant au minimum :

| Champ                                | Utilité                                             |
| ------------------------------------ | --------------------------------------------------- |
| Identifiant du contrôle              | Savoir quelle obligation est évaluée                |
| Identifiants des exigences couvertes | Assurer la traçabilité                              |
| Digest des entrées et du candidat    | Empêcher de réutiliser un verdict sur un autre état |
| Version du vérificateur              | Identifier la méthode réellement utilisée           |
| Statut                               | Réussite, échec, erreur, non exécuté                |
| Références des preuves               | Permettre inspection et vérification                |

Les commandes et vérificateurs qui font autorité doivent provenir d’une configuration approuvée. L’agent ne doit pas pouvoir remplacer le contrôle par une commande qui retourne simplement « succès ».

Cette architecture permet aussi des tests externes indépendants du langage — par exemple contre une API — sans imposer leur technologie à l’application.

**Le gel des artefacts doit être local à une exécution, compatible avec l’évolution du produit.**

Je modifierais ici aussi le cadrage précédent :

* une spécification peut évoluer entre deux incréments ;
* une exécution utilise une version précise et approuvée ;
* une modification en cours d’exécution crée une nouvelle révision ;
* les validations dépendantes deviennent obsolètes lorsque leurs entrées changent ;
* l’historique précédent reste conservé.

Ainsi, modifier un contrat invalide les preuves qui dépendaient de son ancienne version, sans interdire l’itération.

Et il faut distinguer **le workflow de développement** du **protocole expérimental utilisé pour évaluer 495**. Le pré-enregistrement d’une campagne est utile pour une mesure scientifique ; il ne doit pas imposer une procédure de recherche à chaque fonctionnalité développée.

La conception devrait partir de quatre éléments concrets : **un workflow par incrément, des artefacts versionnés inspirés de Spec Kit/OpenSpec, un noyau embarqué de validation et de décision, et un protocole d’adaptateurs indépendant des technologies cibles.** C’est sur ces interfaces, et sur les garanties de chaque gate, que porterait l’effort spécifique de 495.
