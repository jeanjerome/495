# ADR-0006 — Profil `self-hosting-bootstrap`

Révision 6. Son état d'approbation n'est pas inscrit ici : il est mutable et vit dans `495/approvals.json`.

La révision 5 faisait de `TMPDIR` le répertoire du vérificateur, alors que le contrôle d'imports doit y écrire son rapport et que G4 exige ce même répertoire non modifiable. Les deux exigences étaient incompatibles : en lecture seule le rapport ne peut pas être créé ; inscriptible, le vérificateur peut être remplacé transitoirement malgré l'immutabilité annoncée.

## Contexte

Le lot A doit produire du code avant qu'un worker qualifié existe : celui-ci relève des lots D et E. Or `SRC-DESIGN §6.8` exige, pour le profil standard, un worker autorisé capable de protéger le contrôleur et le vérificateur, et interdit de descendre silencieusement au sous-processus local. G2 est donc bloquée pour ce profil.

Une exception au sens de `§3.6` serait incorrecte : ce mécanisme ne couvre qu'un défaut de baseline identifié, avec signature et portée. L'absence d'isolation et de séparation du vérificateur est une obligation technique dure, et §3.6 pose que ces obligations n'ont pas de bouton « forcer le succès ».

`REQ-11`, scellée, interdit de modifier le profil d'un incrément après sa création. Ce profil ne peut donc pas être appliqué rétroactivement à `INC-0002`, né sous `standard`.

## Décision

Un profil `self-hosting-bootstrap`, distinct de `standard`, applicable aux incréments qui construisent 495 avant l'existence d'un worker autorisé.

### Statut normatif et liaison

Tant qu'aucun type d'artefact `policy` n'existe, **cette décision est la définition normative du profil**. En conséquence :

- toute création d'incrément sous ce profil lie le nom `self-hosting-bootstrap` à la référence complète de cette décision : `artifact_id`, `revision`, `kind`, `schema_version`, `digest` ;
- toute décision de gate d'un tel incrément porte ce digest comme `policy_digest`, et non `null` ;
- une nouvelle révision de cette décision ne s'applique à aucun incrément déjà créé : celui-ci reste lié au digest sous lequel il est né.

Le nom seul n'a aucune valeur exécutoire. Un incrément qui ne cite pas le digest n'est pas sous ce profil.

### Exécution

L'exécution locale en Python 3.12 est un **choix explicite du profil**, pas un repli silencieux. Le vérificateur s'exécute dans le même espace que le code vérifié.

**L'interpréteur n'est jamais résolu par recherche dans `PATH`.** Le contrat d'exécution scellé à G2 enregistre :

| Champ | Contenu |
| --- | --- |
| Chemin | Chemin absolu de l'interpréteur, résolu une seule fois |
| Version | `sys.version`, `sys.implementation` et l'architecture de la plateforme |
| Identité | Digest du fichier exécutable désigné par ce chemin |
| Environnement approuvé | Manifeste complet de l'environnement Python : chaque fichier sous le préfixe de l'interpréteur, avec son digest, plus l'exécutable lui-même |

Le digest du lanceur ne suffit pas : la bibliothèque standard, `unittest`, `ast` ou une bibliothèque dynamique peuvent changer sans que l'exécutable bouge.

**Une fermeture relevée sur une seule exécution de référence ne suffit pas davantage.** Un contrôle ultérieur peut charger d'autres fichiers, et le code testé peut modifier `sys.modules` ou les attributs `__file__`. Une collecte effectuée uniquement depuis le processus qui charge le candidat n'est donc pas autoritative.

L'autorité vient du **manifeste de l'environnement complet**, calculé hors de toute exécution du candidat. Il est comparé au contrat avant chaque actuation.

À cela s'ajoute une observation par exécution, produite par un **lanceur scellé extérieur au candidat**, matérialisé depuis sa référence approuvée comme le vérificateur d'imports : il relève la fermeture effectivement chargée et la compare à l'ensemble autorisé par le contrat. Un fichier absent du manifeste, un digest différent, ou une fermeture manquante rendent le résultat **inutilisable** — jamais `PASS`.

Cette observation par exécution détecte, elle ne garantit pas : elle s'exécute dans le processus qui charge le candidat, et le profil le déclare. Elle complète le manifeste d'environnement, elle ne le remplace pas.

Les composants que la plateforme ne permet pas d'énumérer sont **déclarés comme non couverts** par le manifeste, plutôt qu'omis en silence.

Un changement de l'un de ces champs produit un nouveau contrat et invalide les preuves qui en dépendaient.

**Chaque variable d'environnement reçoit une valeur fixée par le contrat**, et l'environnement ne contient rien d'autre :

| Variable | Valeur |
| --- | --- |
| `PATH` | Vide. Toute commande est désignée par un chemin absolu |
| `PYTHONPATH` | Chemin absolu enregistré au contrat |
| `PYTHONHASHSEED` | `0` |
| `PYTHONDONTWRITEBYTECODE` | `1` |
| `TMPDIR` | `<output_root>`, défini ci-dessous |

Une variable autorisée sans valeur fixée serait une entrée non déterminée : le profil n'en admet aucune.

### Trois espaces disjoints

Un espace unique ne peut pas être à la fois immuable et inscriptible. Le profil en distingue trois, sans recouvrement :

| Espace | Contenu | Modifiable pendant l'exécution |
| --- | --- | --- |
| `<cand>` | Le candidat | Non, pour les contrôles d'acceptation |
| `<verifier_root>` | Lanceur scellé et vérificateurs matérialisés depuis leurs références approuvées | Non |
| `<output_root>` | Rapports, sorties et fichiers temporaires | Oui — c'est le seul espace inscriptible |

`<output_root>` est **initialement vide**, situé hors de `<cand>` et de `<verifier_root>`, et soumis à quatre règles :

- `TMPDIR` vaut `<output_root>` ; aucun temporaire n'est écrit ailleurs ;
- il est **inclus dans le bornage des écritures** : c'est un espace autorisé, pas un espace ignoré ;
- il est **exclu de `PYTHONPATH`** ;
- il ne fournit **aucun code chargé par un contrôle**. Un contrôle qui importerait depuis son propre répertoire de sortie exécuterait ce qu'il vient d'y écrire.

Sans cette séparation, écrire un rapport exigerait un vérificateur inscriptible, donc remplaçable pendant l'exécution par le code qu'il contrôle.

### Contrôles

Chaque contrôle est un manifeste approuvé au sens de §6.5 : `argv` en liste, répertoire de travail borné, environnement fixé, timeout, parseur et résultats attendus. Quatre valeurs sont liées par le contrat d'exécution avant lancement : `<py>`, `<cand>`, `<verifier_root>` et `<output_root>`.

**`unittest` sort avec succès lorsqu'il ne découvre aucun test.** Un code de sortie nul n'est donc jamais un résultat suffisant : chaque contrôle déclare un inventaire attendu et le compare à ce qui a réellement été exécuté.

| Champ | `unit` | `enumeration` | `imports` |
| --- | --- | --- | --- |
| `argv` | `[<py>, -B, -m, unittest, discover, -s, <cand>/tests/unit, -t, <cand>, -p, test_*.py, -v]` | `[<py>, -B, -m, unittest, discover, -s, <cand>/tests/enumeration, -t, <cand>, -p, test_*.py, -v]` | `[<py>, -B, <verifier_root>/check_imports.py, --src, <cand>/src, --report, <output_root>/imports.json]` |
| Répertoire de travail | `<cand>` | `<cand>` | `<verifier_root>` |
| Exécution | Une seule. Aucune reprise, aucune répétition | Une seule | Une seule |
| Parseur | Code de sortie ; **sortie lue sur `stderr`**, où le runner `unittest` écrit ; `Ran (\d+) tests` ; identifiants extraits de la sortie verbeuse ; `skipped`, `expected failures`, `unexpected successes` | Idem, plus les lignes `COVERAGE <domaine> <couvert>/<déclaré>` sur `stderr` | Rapport JSON lu au chemin absolu passé à `--report` |
| Résultats attendus | Sortie 0 ; décompte égal à l'inventaire déclaré ; ensemble des identifiants égal à l'inventaire déclaré ; **zéro `skipped`, zéro `expected failure`, zéro `unexpected success`** | Idem, et pour chaque domaine déclaré `couvert == déclaré` | Sortie 0 ; verdict `PASS` pour REQ-18, REQ-19 et REQ-20 ; **ensemble des fichiers analysés égal à l'ensemble attendu dérivé du manifeste du candidat** ; chaque entrée du rapport porte le chemin relatif et le digest du fichier contrôlé |

**Aucun élément d'`argv` ne contient de référence de variable.** Sans shell, `$TMPDIR` resterait une chaîne littérale et créerait un fichier de ce nom. `<py>`, `<cand>`, `<verifier_root>` et `<output_root>` sont des **chemins absolus liés par le contrat avant lancement**, jamais des variables développées à l'exécution.

Le contrôle `imports` s'exécute dans `<verifier_root>` : un `--src` relatif y désignerait `<verifier_root>/src` et non le candidat. Ses deux chemins sont donc absolus et liés explicitement.

**Aucun test ignoré dans un contrôle obligatoire.** Un `skip`, même déclaré, reste dans l'inventaire et dans le décompte `Ran N` : `unittest` sortirait à zéro sans avoir exécuté l'obligation. Les trois compteurs `skipped`, `expected failure` et `unexpected success` doivent donc valoir zéro.

Un contrôle optionnel non applicable est **retiré du plan avant exécution**, conformément à §6.4, et non neutralisé par un `skip` à l'exécution. Il ne doit pas disparaître a posteriori.

**Le contrôle d'imports démontre sa couverture.** Un ensemble de modules « non vide » réussirait après n'avoir analysé qu'un fichier. L'ensemble attendu est dérivé du manifeste du candidat — tous les fichiers Python sous `<cand>/src` — et comparé à l'ensemble effectivement analysé. Un écart dans un sens ou dans l'autre est un `FAIL` : un fichier attendu non analysé comme un fichier analysé hors périmètre. Chaque entrée du rapport porte le chemin relatif et le digest du fichier contrôlé, ce qui lie le rapport aux octets vérifiés.

Un décompte nul, un inventaire différent de celui déclaré, ou un domaine dont la couverture est inférieure au déclaré rendent le contrôle `FAIL`. Un rapport absent ou mal formé le rend `ERROR`, jamais `PASS`.

**Observations propres à l'énumération exhaustive.** Les oracles du lot A portent sur des domaines finis. Chaque test d'énumération émet sa couverture, et le contrôle exige l'égalité avec la cardinalité déclarée :

| Domaine | Cardinalité déclarée |
| --- | --- |
| Phases | 9 |
| Couples de phases | 81 |
| Arêtes de transition | 25 |
| Statuts opérationnels | 5 |
| Commandes | 12 |
| Types d'artefacts | 13 |
| Types de liens | 6 |
| Motifs de clôture | 5 |
| États de tentative | 3 |
| Couples d'états de tentative | 9 |
| Motifs de terminaison | 6 |
| Conditions d'entrée de tentative | 5 |
| Conditions de sortie de tentative | 5 |
| Règles d'invalidation | 6 |

Ces cardinalités proviennent du requirement set scellé. Un écart signale soit un test manquant, soit une dérive du vocabulaire : dans les deux cas le contrôle échoue.

Aucun exécuteur de tests tiers. `unittest` et `ast` appartiennent à la bibliothèque standard : sous un profil sans isolation, toute dépendance tierce ajouterait une surface non vérifiable. Aucun générateur aléatoire : les domaines sont finis et énumérés.

Les racines de découverte sont **disjointes** : `tests/unit` ne contient pas `tests/enumeration`, faute de quoi le premier contrôle exécuterait le second et un unique échec serait compté deux fois.

**Écritures dans le candidat.** Deux formes existent, et elles n'ouvrent pas les mêmes gates.

| Forme | Énoncé | Gates ouvertes |
| --- | --- | --- |
| Immutabilité | Candidat, vérificateur et environnement approuvé sont **non modifiables pendant l'exécution** : montage en lecture seule ou snapshot immuable équivalent | Contrôles de progression **et** contrôles d'acceptation |
| Détection | **Aucune modification persistante observée** : le manifeste du candidat est comparé avant et après chaque contrôle | Contrôles de progression **uniquement** |

**La détection ne suffit pas pour G4.** Un contrôle peut modifier le code, tester la version modifiée, puis restaurer les octets d'origine : les manifestes avant et après coïncident alors que le candidat scellé n'a jamais été exécuté. Le résultat ne porterait pas sur le candidat précis qu'exige G4, et INV-07 pose que le candidat accepté est le candidat vérifié.

Sous la forme « détection », les résultats sont donc des **contrôles de progression** au sens de §6.8. Ils alimentent le feedback, ils ne fondent aucune acceptation.

Si l'hôte n'offre aucun mécanisme d'immutabilité qualifié, **G4 reste `INDETERMINATE`** sous ce profil. C'est une conséquence assumée : le profil permet de construire et de mesurer avant qu'un worker existe, il ne permet pas d'accepter sans immutabilité.

G2 peut alors ouvrir une tentative **limitée aux contrôles de progression**, en enregistrant cette limite dans le contrat.

L'apparition ultérieure d'un mécanisme d'immutabilité est un **changement d'environnement**, non une extension du contrat existant : nouveau contrat, nouvelle tentative si nécessaire, et réévaluation de G2 avant qu'une preuve soit utilisable à G4. Les résultats obtenus sans immutabilité ne changent pas de statut du fait que le mécanisme existe ensuite.

`-B` et `PYTHONDONTWRITEBYTECODE` suppriment les `__pycache__` ; tout fichier temporaire est écrit sous `<output_root>`, hors du candidat et du vérificateur. Ces mesures réduisent le risque ; elles ne valent immutabilité sous aucune des deux formes.

**Le vérificateur d'imports est un objet de contrôle scellé**, avec son propre digest, conservé dans le magasin d'objets. Il est matérialisé depuis la référence approuvée dans le répertoire du vérificateur, jamais lu depuis le dépôt qu'il vérifie, et son digest est vérifié avant et après l'exécution. Un vérificateur vivant dans le candidat serait modifiable par le code qu'il contrôle.

### Preuve admissible des interdictions dures

Le profil interdit le réseau et les écritures hors périmètre tout en déclarant l'absence d'isolation. Une promesse, ou l'absence d'incident observé, ne satisfait pas une obligation dure.

**G2 exige une observation enregistrée du dispositif hôte.** Elle porte sur trois points :

| Point | Contenu exigé |
| --- | --- |
| Identité du dispositif | Nom, version et digest de sa configuration effective |
| Refus du réseau | Qualification différentielle contre un **pair contrôlé**, décrite ci-dessous |
| Bornage des écritures | Soit le dispositif borne l'ensemble des chemins inscriptibles, soit une surface couvrant réellement cet ensemble est identifiée, décrite ci-dessous |

En l'absence de cette observation, **G2 reste `INDETERMINATE`** avec la raison `MISSING_EVIDENCE`. L'approbation humaine ne remplace pas une capacité technique : elle porte sur des références, pas sur l'existence d'un mécanisme.

#### Qualification du refus réseau

Une tentative sortante « refusée » ne prouve rien : elle peut viser un port fermé, un hôte inexistant ou une route absente. Elle ne démontre pas l'action du dispositif, et ne dit rien des connexions entrantes.

La qualification est **différentielle**, contre un pair contrôlé dont on maîtrise l'état :

1. Sans la règle, le pair est démontré **joignable** — ce qui établit que le pair, la route et le test fonctionnent.
2. Avec la règle, le même pair est démontré **inaccessible**.

L'écart entre les deux exécutions est la preuve ; aucune des deux prise isolément ne l'est. Les deux observations sont enregistrées avec leurs digests.

Le profil interdit **tout** accès réseau, en émission comme en réception. Une famille laissée « non couverte » contredirait cette interdiction : elle resterait une voie ouverte présentée comme fermée.

Chaque famille disponible sur l'hôte est donc soit **qualifiée dans les deux directions**, soit **démontrée indisponible** pour les processus concernés — la démonstration d'indisponibilité étant elle-même une observation enregistrée, non une affirmation.

Une voie réseau disponible mais non qualifiée laisse **G2 `INDETERMINATE`**. Le profil ne connaît pas de troisième issue : il n'existe pas de famille réseau tolérée sans preuve.

#### Bornage des écritures

Déclarer une racine intégralement comparée ne prouve pas que le processus ne peut écrire ailleurs. La comparaison du seul candidat ne détecte que ses modifications persistantes, et rien hors de lui.

Deux formes sont admissibles :

| Forme | Exigence |
| --- | --- |
| Bornage | Le dispositif borne l'**ensemble des chemins inscriptibles** par le processus. L'ensemble est énuméré et sa qualification enregistrée. `<output_root>` en fait partie ; `<cand>` et `<verifier_root>` en sont exclus pour les contrôles d'acceptation |
| Couverture | Une surface est identifiée qui **couvre réellement tout l'ensemble inscriptible**, pas seulement le candidat. Sa racine et son étendue sont déclarées, et l'argument de couverture est explicite |

La seconde forme est plus faible et le déclare : elle détecte, elle n'empêche pas. Elle n'ouvre que les contrôles de progression. Une surface qui ne couvre pas tout l'ensemble inscriptible ne satisfait aucune des deux formes, et laisse G2 `INDETERMINATE`.

### Ce que le profil ne garantit pas

- Aucune garantie d'isolation du processus auteur, de protection du magasin de contrôle, ni de séparation du vérificateur — les trois capacités de §6.8 sont déclarées absentes.
- Aucune preuve opposable à un tiers. L'identité locale n'est pas authentifiée, conformément à §1.
- Un résultat obtenu sous ce profil est une **preuve fonctionnelle de bootstrap**. Il n'est jamais une preuve d'isolation ni de séparation du vérificateur.

### Interdictions

Ces interdictions portent sur **toute actuation sous ce profil** — processus auteur, contrôles et outils auxiliaires — et non sur la seule exécution des contrôles. Ce sont des obligations dures :

- tout accès réseau, en émission comme en réception ;
- tout secret, toute référence de secret, toute variable d'environnement hors du tableau ci-dessus ;
- tout contrôle privé au sens de §6.8 : sous ce profil, l'ensemble des contrôles est public ;
- tout effet externe : publication, poussée, appel sortant, écriture hors des chemins autorisés.

### Périmètre et violation

Les chemins autorisés en écriture sont déclarés par le contrat d'exécution de chaque incrément. Le candidat est capturé après arrêt confirmé des processus auteurs. Le profil ne prétend pas empêcher une modification concurrente : il prétend la détecter par comparaison de manifeste.

Une écriture constatée hors des chemins autorisés fait échouer G3. Ce `FAIL` ne termine pas la tentative à lui seul — `AC-13-7` l'interdit. La violation **atteint la règle d'arrêt du contrat** : après réconciliation de l'état constaté, elle produit l'observation `definitive_failure`, qui est le déclencheur de terminaison de la tentative au sens d'ADR-0002. Aucune correction n'est possible sous le même contrat.

### Qualification des contrôles

Un contrôle n'est utilisable qu'après qualification fonctionnelle sur **deux cas au moins** : une entrée connue conforme qu'il accepte, et une entrée connue non conforme qu'il rejette. Un contrôle qui n'a jamais échoué sur une entrée fautive n'est pas qualifié, et son résultat favorable ne vaut rien.

La qualification est enregistrée avec le contrôle, avec les digests des deux entrées.

### Autorité

G2 et G4 exigent une approbation humaine explicite, sur la référence exacte du contrat et du candidat. Aucun jugement de modèle ne se substitue à cette approbation sous ce profil.

### Extinction

Le kit de conformité CSAP ne qualifie pas l'isolation : §9 pose qu'un worker respectant la forme du protocole n'est pas automatiquement qualifié pour son niveau d'isolation, et que cette qualification est séparée.

L'extinction exige donc, **cumulativement** :

| Condition | Source |
| --- | --- |
| Un worker implémentant CSAP 1.0, ayant passé le kit de conformité | §9 |
| Isolation du processus auteur, qualifiée séparément | §6.8 |
| Protection du magasin de contrôle, qualifiée séparément | §6.8 |
| Séparation du vérificateur, qualifiée séparément | §6.8 |
| Compatibilité du worker avec la toolchain des incréments concernés — Python 3.12 pour le lot A | §6.3, capacités déclarées au `describe` |

Un worker isolé mais incapable d'exécuter Python 3.12 ne permettrait aucune requalification : la capacité d'isolation et la capacité d'exécution sont deux conditions distinctes.

Aucune date n'est fixée : une échéance calendaire n'apporterait rien tant que ces conditions ne sont pas remplies, et créerait une pression à déclarer conforme ce qui ne l'est pas.

**Sort des incréments ouverts à l'extinction.** Aucun nouvel incrément ne peut être créé sous ce profil, et **aucune nouvelle tentative ne peut être créée** dans un incrément existant. Une opération déjà active peut seulement être arrêtée ou réconciliée ; le travail restant est repris sous le profil `standard`, dans un nouvel incrément puisque `REQ-11` interdit le changement de profil.

### Requalification

Les résultats obtenus sous ce profil sont **réévalués sous le profil standard** avant toute revendication d'auto-hébergement conforme. Cette réévaluation réexécute les contrôles sur un worker qualifié et compare les verdicts. Un incrément accepté sous `self-hosting-bootstrap` ne devient pas conforme au profil standard par le seul fait que ce dernier existe ensuite.

## Conséquences

- `INC-0002` ne peut pas adopter ce profil. Il sera clos avec le motif `superseded`, sans que son G1 soit réécrit ni invalidé.
- Un nouvel incrément reprend son objectif sous ce profil, en liant son digest.
- G4 n'est franchissable sous ce profil que si l'hôte fournit un mécanisme d'immutabilité qualifié. À défaut, le profil permet de construire et de mesurer, pas d'accepter.
- Le vocabulaire des profils compte au moins trois valeurs. `standard` est mentionné par §3.5 ; `exploration` existe déjà en §3.1 et porte la clôture d'`INC-0001` ; `self-hosting-bootstrap` s'y ajoute. Le registre des profils doit énumérer les trois.
- Les décisions de gate cessent de porter `policy_digest: null` pour les incréments concernés.

## Relation au profil standard

Cette décision **complète** la conception ; elle ne remplace aucune obligation du profil standard, qui reste intact et applicable. Le lien est informatif au sens de §4.4 : `related_to`, non `supersedes`. Un lien `supersedes` entraînerait l'invalidation des obligations de §3.5, ce que le texte ci-dessus contredit expressément.

## Limite de modélisation

`SRC-DESIGN §4.2` fixe treize types d'artefacts et `REQ-05`, scellée, refuse tout type absent de cet ensemble. Aucun ne correspond à un profil de workflow, alors que §3.1, §3.5, §3.6 et §5.3 s'y réfèrent constamment.

Rattacher le profil à un `check_plan` serait incorrect : le profil gouverne toutes les gates et précède ce plan. Cette décision sert donc de définition normative transitoire, selon la convention de liaison énoncée plus haut, jusqu'à l'introduction d'un type `policy`. La question reste ouverte sous `Q-15` et ne bloque pas le noyau du domaine.
