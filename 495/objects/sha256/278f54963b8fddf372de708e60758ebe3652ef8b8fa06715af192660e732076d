# INC-0003 — conception du noyau du domaine

Conception du module `domain` de `SRC-DESIGN §5.1`, sous le profil
`self-hosting-bootstrap`.

Produit sous la tentative `ATT-INC-0003-0003`, contrat de phase
`INC-0003/contract-conception` r1. Le verdict de gate et le scellement de ce
document lui sont extérieurs.

## 1. Périmètre

Ce document alloue les vingt exigences d'`INC-0002/requirements` r7 à des
composants, fixe leurs interfaces, énonce les risques et arrête la stratégie de
test. Il ne fixe ni le dispositif hôte, ni le contrat d'implémentation, ni le
plan de contrôles : ces trois artefacts sont produits séparément sous le même
contrat de phase.

### 1.1 Sources normatives

| Référence | Révision | Digest | Apport |
| --- | --- | --- | --- |
| `INC-0001/design` | 1 | `sha256:48aaff9a…c07567` | Architecture interne, types d'artefacts, gates |
| `INC-0002/requirements` | 7 | `sha256:f503f829…b622c92` | Vingt exigences, quatre-vingt-dix-huit critères, vocabulaire clos |
| `INC-0003/proposal` | 1 | `sha256:c0533feb…13307c6` | Périmètre repris et portée d'un résultat |
| `ADR-0001` | 4 | `sha256:ceb08516…5b55a55e` | Sort de la tentative sur les onze arêtes de retour |
| `ADR-0002` | 5 | `sha256:0e876614…872c4f7` | Automate de la tentative, motifs et déclencheurs |
| `ADR-0003` | 1 | `sha256:71b40bb6…ccd286` | Sept arêtes de clôture, phases terminales |
| `ADR-0004` | 1 | `sha256:968d032b…911ea8` | `domain` ne dépend d'aucun autre module |
| `ADR-0005` | 2 | `sha256:5c69fb74…8c20dc7e` | Douze commandes, liaison des vingt-cinq arêtes |
| `ADR-0006` | 6 | `sha256:7ac71f73…0e52ed2` | Profil, contrôles, cardinalités déclarées |

Les digests complets figurent dans `inputs` du contrat de phase. Les formes
abrégées ci-dessus servent la lecture ; elles ne sont pas des références.

### 1.2 Hors périmètre

`evaluate_gate` de `§5.2` réduit des faits en verdict : cette réduction
appartient au module `policy`, pas à `domain`. Ce périmètre définit le **type**
`GateDecision` et les données qu'il transporte, jamais la fonction qui le
produit. De même, le journal, les objets et la concurrence de `§5.5`
appartiennent à `infrastructure` et `application`.

`ADR-0004` fixe uniquement les arêtes sortantes de `domain`. Le graphe complet
des six modules reste ouvert et n'est pas décidé ici.

## 2. Composants

Un unique paquet, `src/domain/`, sans sous-paquet. Chaque module y est un
fichier plat ; aucune arête sortante vers un autre paquet du projet
(`ADR-0004`, REQ-20).

| Module | Responsabilité | Exigences portées |
| --- | --- | --- |
| `vocabulary.py` | Les ensembles clos et les tables scellées, en constantes gelées | REQ-05, REQ-06, REQ-10, REQ-14 |
| `outcomes.py` | Résultat d'une opération : acceptation ou refus motivé, sans exception de contrôle de flux | REQ-01, REQ-02, REQ-07, REQ-12 |
| `references.py` | `ArtifactRef`, `Approval`, `ApprovalRegistry`, leurs fabriques et l'applicabilité d'une approbation | REQ-01, REQ-02, REQ-16 |
| `revisions.py` | Suite des révisions d'un `artifact_id` | REQ-03 |
| `sealing.py` | Digest des octets bruts, registre des artefacts scellés | REQ-04, REQ-16 |
| `phases.py` | Table des vingt-cinq arêtes et résolution d'une arête visée | REQ-07, REQ-09 |
| `attempts.py` | Automate de la tentative, motifs, déclencheurs | REQ-08, REQ-13 |
| `links.py` | Types de liens, acyclicité de `depends_on` | REQ-14, REQ-15 |
| `invalidation.py` | Fonction pure d'obsolescence | REQ-17 |
| `state.py` | Agrégat d'incrément : phase, statut, tentatives, candidat et décision courants, registres, intention d'intégration | REQ-06, REQ-11, REQ-12 |
| `commands.py` | Les douze commandes, leur enveloppe, leurs préconditions et leur application | REQ-07, REQ-09, REQ-10, REQ-11, REQ-12 |

REQ-18, REQ-19 et REQ-20 ne sont portées par aucun module : ce sont des
propriétés du paquet entier, vérifiées par analyse statique (§6.3) et par
bornage du candidat (§6.4).

### 2.1 Style imposé par les exigences

**Immutabilité réelle des valeurs.** REQ-12 exige qu'un refus laisse l'état
final identique, digests compris (AC-12-5). `dataclass(frozen=True)` gèle les
attributs, **pas les objets derrière eux** : un champ annoté `Mapping[...]` reste
un `dict` mutable que l'appelant peut conserver et modifier après construction.
`types.MappingProxyType` ne corrige rien, puisque c'est une vue sur ce même
`dict`.

Toute collection portée par une structure du domaine est donc un `tuple` de
paires, trié par clé, avec des fonctions de lecture au niveau du module :

```
@dataclass(frozen=True, slots=True)
class RevisionHistory:
    entries: tuple[tuple[str, int], ...]      # (artifact_id, dernière révision), trié
```

Le tri rend la représentation canonique : deux histoires de même contenu sont
égales et ont le même `hash`. Rien ne peut muter le contenu après construction,
et l'invariance d'un refus se vérifie par identité d'objet — oracle plus fort
que l'égalité structurelle.

**Pureté.** Aucune fonction du paquet n'ouvre de fichier, de socket ni de
sous-processus, et ne lit l'horloge ou l'environnement. L'heure, les budgets
consommés et les expirations arrivent en faits explicites, conformément à
`§5.2`. C'est la condition pour que REQ-18 soit une propriété statique et non un
contrôle d'exécution.

`hashlib` est la seule dépendance de bibliothèque standard du paquet qui ne soit
pas purement langagière (§3.3). Elle n'ouvre rien : elle est absente de la liste
d'entrées/sorties de §6.3, et son usage est compatible avec AC-18-1 comme avec
AC-18-2.

**Refus valué.** Un refus est une valeur retournée, jamais une exception. Une
exception ne se prête pas à l'énumération exhaustive des quatre-vingt-un couples
de phases, et AC-07-4 exige de distinguer deux motifs de refus dans le
*résultat*.

### 2.2 Ordre de dépendance interne

`ADR-0004` interdit les arêtes **sortantes** de `domain` ; il ne dit rien de
l'ordre interne. Cet ordre est une contrainte de conception, non une exigence
scellée, et il est fixé ici pour que le graphe interne soit acyclique.

| Niveau | Modules | Peut importer |
| --- | --- | --- |
| 0 | `vocabulary` | rien |
| 1 | `outcomes` | niveau 0 |
| 2 | `references` | niveaux 0 à 1 |
| 3 | `revisions`, `sealing`, `links`, `invalidation`, `phases`, `attempts` | niveaux 0 à 2 |
| 4 | `state` | niveaux 0 à 3 |
| 5 | `commands` | niveaux 0 à 4 |

Un import n'est autorisé que vers un niveau strictement inférieur : le graphe
est acyclique par construction, sans qu'aucun test de cycle soit nécessaire.

Trois cycles étaient possibles et sont écartés par des choix explicites :

| Cycle possible | Cause | Choix retenu |
| --- | --- | --- |
| `outcomes ↔ phases` | `Accepted` portait une arête de transition | `Accepted` ne porte que sa valeur ; l'arête se relit dans `TRANSITIONS` |
| `phases ↔ commands` | `TransitionEdge` nomme la commande qui la porte | `CommandName` est défini dans `vocabulary`, pas dans `commands` |
| `phases ↔ attempts` | L'agrégat portait à la fois la phase et les tentatives | L'agrégat est `state.py`, au-dessus des deux ; `attempts` ignore `Phase` |

Toutes les énumérations closes — `Phase`, `OperationalStatus`, `CommandName`,
`ArtifactKind`, `CloseReason`, `LinkType`, `AttemptPhase`, `AttemptStateName`,
`FinishReason`, `EdgeKind`, `ChangeKind`, `Gate`, `GateVerdict` — vivent donc
en niveau 0.

Le contrôle `imports` construit déjà le graphe interne pour AC-20-1 ; il vérifie
cet ordre au passage. C'est un contrôle de conception ajouté, pas la
vérification d'une exigence scellée, et le plan de contrôles le déclare comme
tel.

### 2.3 Ce que Python ne garantit pas

Une annotation de type n'est pas vérifiée à l'exécution, et
`dataclass(frozen=True)` n'empêche pas d'appeler le constructeur avec n'importe
quoi. Aucune propriété de ce document n'est donc « garantie par le type ».

Trois invariants souvent présentés comme structurels sont ici distingués selon
ce qui les tient réellement :

| Invariant | Ce qui le tient | Force |
| --- | --- | --- |
| `Approval.target` n'est pas un chemin (AC-16-3) | La fabrique `build_approval` revalide les cinq champs de la cible et refuse avec `INVALID_APPROVAL_TARGET` ce qui n'est pas une `ArtifactRef` | Fabrique + test ; le constructeur direct reste atteignable |
| `attempt_id` ne change jamais (AC-13-1) | `start_attempt` l'attribue ; `transition` le recopie sans le prendre en paramètre | Fabrique + signature + test sur l'historique |
| `contract_ref` ne change jamais (AC-13-9) | `transition` **n'a aucun paramètre de contrat** : il n'existe aucun chemin d'appel qui en fournisse un autre | Signature — genuinement structurel |

Seul le troisième tient sans test, parce qu'il repose sur l'absence d'un
paramètre et non sur une vérification. Les deux premiers sont tenus par une
fabrique sanctionnée et par le test qui l'accompagne. Le document n'emploie
« structurel » que pour le troisième cas.

Les fabriques `build_ref`, `build_approval` et `start_attempt` sont les seules
voies de construction sanctionnées. Le plan de contrôles peut ajouter une
vérification statique qu'aucun appel direct au constructeur de ces trois types
n'existe hors de sa fabrique ; cette vérification n'est exigée par aucun critère
scellé.

## 3. Interfaces

### 3.1 `outcomes.py`

Le type de la valeur produite et celui de l'état conservé en cas de refus sont
**distincts**. Les confondre serait impossible à typer : `build_ref` ne peut pas
placer une `ArtifactRef` dans un refus, puisque c'est précisément ce qu'elle n'a
pas pu construire, et `validate` conserve un `IncrementState` alors qu'elle
produit une `Command`.

```
@dataclass(frozen=True, slots=True)
class Accepted[T]:
    value: T

@dataclass(frozen=True, slots=True)
class Refused[S]:
    code: RefusalCode
    subject: str
    state: S
    details: tuple[str, ...] = ()

type Outcome[T, S] = Accepted[T] | Refused[S]
```

`S` vaut `None` lorsqu'il n'existe aucun état antérieur à conserver — c'est le
cas de `build_ref`, de `build_approval` et de `create_increment`. Les signatures
complètes :

| Fonction | Type de retour |
| --- | --- |
| `build_ref` | `Outcome[ArtifactRef, None]` |
| `build_approval` | `Outcome[Approval, None]` |
| `create_increment` | `Outcome[IncrementState, None]` |
| `record_revision` | `Outcome[RevisionHistory, RevisionHistory]` |
| `seal` | `Outcome[SealRegistry, SealRegistry]` |
| `record` | `Outcome[ApprovalRegistry, ApprovalRegistry]` |
| `add_link` | `Outcome[LinkGraph, LinkGraph]` |
| `start_attempt` | `Outcome[AttemptState, tuple[AttemptState, ...]]` |
| `transition` | `Outcome[AttemptState, AttemptState]` |
| `well_formed` | `Outcome[Command, None]` |
| `validate` | `Outcome[Command, IncrementState \| None]` |
| `apply_command` | `Outcome[IncrementState, IncrementState]` |

`subject` nomme l'élément unique en cause : le champ manquant, la référence, la
précondition violée. Le refus n'est pas une chaîne libre — `code` est énuméré,
`subject` est un identifiant.

`details` porte ce qu'un identifiant unique ne peut pas transporter. AC-15-2
exige les nœuds du cycle détecté dans l'ordre de parcours, le premier répété en
dernière position. `MALFORMED_COMMAND` l'utilise aussi, sans exigence scellée
supplémentaire, pour porter la forme attendue. Dans les autres refus, `details`
est vide.

#### Codes de refus et critères couverts

```
class RefusalCode(StrEnum):
    MISSING_FIELD, UNKNOWN_KIND, SYMBOLIC_REVISION,
    NON_CONSECUTIVE_REVISION, SEALED_ARTIFACT, DIGEST_MISMATCH,
    UNKNOWN_LINK_TYPE, DEPENDENCY_CYCLE,
    STATE_VERSION_MISMATCH, UNKNOWN_TRANSITION,
    PRECONDITION_UNSATISFIED, INTEGRATED_REQUIRES_NEW_INCREMENT,
    PROFILE_IMMUTABLE, UNKNOWN_ATTEMPT_TRANSITION,
    MISSING_FINISH_REASON, RUNNING_ATTEMPT_CONFLICT,
    MALFORMED_COMMAND, INVALID_APPROVAL_TARGET
```

Chaque code est rattaché aux critères qu'il sert. Aucun code n'est déclaré sans
emploi, et la table est comparable mécaniquement au requirement set scellé.

| Code | Critères couverts |
| --- | --- |
| `MISSING_FIELD` | AC-01-2, AC-01-3 |
| `UNKNOWN_KIND` | AC-05-2 |
| `SYMBOLIC_REVISION` | AC-02-1, AC-02-2, AC-02-3 |
| `NON_CONSECUTIVE_REVISION` | AC-03-3, AC-03-4 |
| `SEALED_ARTIFACT` | AC-04-1, AC-04-3 |
| `DIGEST_MISMATCH` | AC-16-5 |
| `UNKNOWN_LINK_TYPE` | AC-14-2 |
| `DEPENDENCY_CYCLE` | AC-15-1, AC-15-2, AC-15-4 |
| `UNKNOWN_TRANSITION` | AC-07-3, AC-10-6 |
| `PRECONDITION_UNSATISFIED` | AC-07-2, AC-10-1, AC-10-2, AC-10-4, AC-12-6 |
| `INTEGRATED_REQUIRES_NEW_INCREMENT` | AC-09-1, AC-09-3, AC-10-5 |
| `PROFILE_IMMUTABLE` | AC-11-1, AC-11-2, AC-11-3 |
| `UNKNOWN_ATTEMPT_TRANSITION` | AC-13-5 |
| `MISSING_FINISH_REASON` | AC-13-6 |
| `RUNNING_ATTEMPT_CONFLICT` | AC-13-14 |
| `MALFORMED_COMMAND` | AC-12-1, AC-12-6 |
| `INVALID_APPROVAL_TARGET` | AC-16-3 |
| `STATE_VERSION_MISMATCH` | **Aucun** — enveloppe de `§5.5`, sans critère scellé correspondant |

`PRECONDITION_UNSATISFIED` couvre plusieurs critères parce que c'est `subject`
qui les distingue : la clôture sans motif, le motif hors ensemble et l'effet
externe non réconcilié sont trois préconditions nommées de `CloseIncrement`.

AC-09-3 exige que le refus indique qu'un nouvel incrément est nécessaire. Cette
indication est un **code énuméré**, pas une phrase : lorsque la phase de départ
est `integrated`, le refus porte `INTEGRATED_REQUIRES_NEW_INCREMENT` plutôt que
le générique `UNKNOWN_TRANSITION`. Les deux restent des refus sans mutation, si
bien qu'AC-07-3 est satisfait pendant qu'AC-09-3 gagne son remède.

`Accepted` ne porte pas l'arête appliquée : `outcomes` resterait alors lié à
`phases` (§2.2). L'arête se relit dans `TRANSITIONS` à partir du couple de
phases.

### 3.2 `references.py`

```
@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str ; revision: int ; kind: ArtifactKind
    schema_version: str ; digest: str

@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str ; actor: str ; role: str
    target: ArtifactRef ; scope: str ; decision: ApprovalDecision

@dataclass(frozen=True, slots=True)
class ApprovalRegistry:
    entries: tuple[Approval, ...]        # append-only, dans l'ordre d'enregistrement

def build_ref(**fields) -> Outcome[ArtifactRef, None]
def build_approval(**fields) -> Outcome[Approval, None]
def approval_applies(approval: Approval, target: ArtifactRef) -> bool
def record(registry: ApprovalRegistry, approval: Approval) -> Outcome[ApprovalRegistry, ApprovalRegistry]
def approvals_for(registry: ApprovalRegistry, target: ArtifactRef) -> tuple[Approval, ...]
```

`build_ref` accepte toute référence portant les cinq champs, avec un `kind`
appartenant à `vocabulary.artifact_kinds` (AC-01-1). Il refuse l'omission d'un
des cinq champs en nommant le champ
(`MISSING_FIELD`), refuse un `kind` hors des treize valeurs (`UNKNOWN_KIND`) et
refuse une `revision` non entière — `latest` comprise, nommément
(`SYMBOLIC_REVISION`). Le type accepte un entier ; la validation rejette `bool`,
que Python considère comme entier.

`build_approval` **ne peut pas reconnaître la provenance de sa cible.** Un
objet construit directement par le constructeur de `ArtifactRef` est
indiscernable d'un objet issu de `build_ref` : rien ne le marque. La fabrique ne
revendique donc aucune provenance.

Ce qu'elle fait est vérifiable : elle **revalide les cinq champs** de la cible
avec le même prédicat que `build_ref`, et propage le code obtenu — `MISSING_FIELD`,
`UNKNOWN_KIND` ou `SYMBOLIC_REVISION` — avec `subject` préfixé `target.`. Une
cible qui n'est pas du tout une `ArtifactRef` — une chaîne, un chemin de
fichier — est refusée avec `INVALID_APPROVAL_TARGET` et `subject = "target"`.
C'est ce refus qui porte AC-16-3.

Comme le note §2.3, c'est la fabrique et son test qui tiennent cet invariant,
pas l'annotation : le constructeur direct d'`Approval` reste atteignable.

`approval_applies` retourne vrai si et seulement si les cinq champs sont égaux.
Il en découle qu'une approbation de la révision n ne vaut pas pour la révision
n+1 (AC-16-1) et que deux artefacts d'octets identiques sous deux `artifact_id`
distincts restent deux cibles (AC-16-2).

**AC-16-4 exige un état conservé, pas une affirmation.** « L'approbation sur la
révision n reste lisible après création de la révision n+1 » porte sur un
registre qui doit exister. `ApprovalRegistry` est donc modélisé : un `tuple`
d'approbations, append-only, porté par l'agrégat. `record` n'y ajoute qu'en
queue et ne retire jamais ; `approvals_for` filtre par égalité des cinq champs.
Après `seal` de la révision n+1, `approvals_for(registry, ref_n)` retourne
toujours l'approbation de la révision n : c'est l'oracle d'AC-16-4, vérifié sur
des séquences construites de scellements et d'enregistrements.

`RecordApproval` appartient donc au groupe des commandes dont l'effet est
modélisé (§3.4), et non au groupe validé sans effet.

### 3.3 `revisions.py` et `sealing.py`

```
# revisions.py
@dataclass(frozen=True, slots=True)
class RevisionHistory:
    entries: tuple[tuple[str, int], ...]        # trié par artifact_id

def next_revision(history: RevisionHistory, artifact_id: str) -> int
def record_revision(history, artifact_id, revision: int) -> Outcome[RevisionHistory, RevisionHistory]
```

`next_revision` vaut 1 pour un `artifact_id` inconnu (AC-03-1) et `last + 1`
sinon. `record_revision` accepte exactement `last + 1` (AC-03-2) et refuse
toute autre valeur avec `NON_CONSECUTIVE_REVISION`, **y compris supérieure**
(AC-03-3) : un saut créerait un trou, ce qu'AC-03-4 interdit. La suite acceptée
sur un `artifact_id` est donc exactement `1..k`, sans trou ni répétition, ce qui
est la formulation de l'oracle de REQ-03.

```
# sealing.py
def digest_bytes(raw: bytes) -> str          # "sha256:" + sha256(raw).hexdigest()

@dataclass(frozen=True, slots=True)
class SealRegistry:
    entries: tuple[tuple[str, int, ArtifactRef], ...]    # trié par (artifact_id, revision)

def seal(registry, ref: ArtifactRef, raw: bytes) -> Outcome[SealRegistry, SealRegistry]
def digest_of(registry, artifact_id: str, revision: int) -> str | None
```

**AC-16-5 — le digest couvre les octets exacts.** Transporter un digest opaque
ne prouve rien : un producteur fautif transmettrait le digest d'une
re-sérialisation, et le domaine l'accepterait sans le savoir. `seal` reçoit donc
les **octets bruts** et refuse avec `DIGEST_MISMATCH` si
`digest_bytes(raw) != ref.digest`.

`digest_bytes` est une fonction pure de `bytes` vers `str`. Elle n'ouvre aucun
fichier : la lecture des octets appartient à l'appelant, hors du domaine.
REQ-18 interdit les entrées/sorties, pas le calcul ; `hashlib` n'apparaît dans
aucune des deux listes de §6.3. Le contrôle d'AC-16-5 devient donc interne au
domaine et testable, au lieu d'être délégué à la bonne conduite d'un producteur.

`seal` refuse avec `SEALED_ARTIFACT` toute écriture sur un couple
`(artifact_id, revision)` déjà présent, quel que soit le digest proposé
(AC-04-1), et retourne le registre reçu sans copie (AC-04-3). Le registre est
append-only : après le scellement de la révision n+1, l'entrée de la révision n
est toujours présente et `digest_of` y retourne la même valeur (AC-04-2).

L'oracle de REQ-04 porte sur *toute séquence d'opérations* : le test
correspondant applique des séquences construites de scellements et de tentatives
de modification, puis compare chaque digest à celui observé au scellement.

### 3.4 `phases.py`, `state.py` et `commands.py`

```
# vocabulary.py
class GateVerdict(StrEnum):       # PASS, FAIL, INDETERMINATE

# phases.py
@dataclass(frozen=True, slots=True)
class TransitionEdge:
    origin: Phase ; target: Phase ; command: CommandName
    gate: Gate | None ; kind: EdgeKind
    terminates_current_attempt: FinishReason | None
    extra_precondition: str | None

TRANSITIONS: tuple[TransitionEdge, ...]     # 25 entrées, indexées par (origin, target)

def edge_between(origin: Phase, target: Phase) -> TransitionEdge | None

# state.py
@dataclass(frozen=True, slots=True)
class DecisionReason:
    code: str ; obligation: str ; evidence: tuple[ArtifactRef, ...]

@dataclass(frozen=True, slots=True)
class IntegrationIntent:
    candidate: ArtifactRef ; destination: str ; reconciled: bool

@dataclass(frozen=True, slots=True)
class IntegrationReconciliation:
    candidate: ArtifactRef ; destination: str ; receipt: ArtifactRef

@dataclass(frozen=True, slots=True)
class GateDecision:
    decision_id: str ; gate: Gate ; verdict: GateVerdict
    engine_version: str ; policy_digest: str ; input_bundle_digest: str
    expected_state_version: int ; candidate: ArtifactRef | None
    reasons: tuple[DecisionReason, ...]
    reconciliation: IntegrationReconciliation | None

@dataclass(frozen=True, slots=True)
class IncrementState:
    increment_id: str ; revision: int
    phase: Phase ; status: OperationalStatus ; profile: str
    attempts: tuple[AttemptState, ...]
    other_unreconciled_external_effect: bool
    expected_destination: str | None
    current_candidate: ArtifactRef | None
    current_gate_decision: GateDecision | None
    integration_intent: IntegrationIntent | None
    sealed: SealRegistry ; revisions: RevisionHistory
    approvals: ApprovalRegistry

def with_status(state, status: OperationalStatus) -> IncrementState
def has_unreconciled_external_effect(state: IncrementState) -> bool
```

**`with_phase` n'existe pas comme opération publique.** Remplacer librement la
phase contournerait `TRANSITIONS` et les préconditions, c'est-à-dire REQ-07 tout
entier. Il n'existe pas non plus de fonction `_apply_edge` importable :
`apply_command` remplace `phase` directement dans son étape d'effet, uniquement
avec la cible de l'arête retournée par `intended_edge` dans le même appel. Aucun
appel sanctionné ne peut donc fournir une phase ou une arête arbitraire.

`with_status` reste public : aucune règle scellée ne contraint les transitions
de statut, et aucune des douze commandes ne le modifie (§3.4).

**Conséquence sur l'oracle de REQ-06.** AC-06-3 — changer le statut laisse la
phase inchangée — se vérifie sur les quarante-cinq couples (phase, statut) par
`with_status`. AC-06-4 — changer la phase laisse le statut inchangé — ne peut
plus se vérifier sur les quatre-vingt-un couples, puisque soixante-seize d'entre
eux ne sont pas applicables. Il se vérifie sur les **vingt-cinq arêtes acceptées
× cinq statuts**, soit cent vingt-cinq cas, en constatant que `status` est
identique avant et après `apply_command`.

Ces cent vingt-cinq cas sont un test **unitaire**, pas un domaine
d'énumération : `ADR-0006` en scelle quatorze, et la conception n'en ajoute pas
un quinzième.

**`state_version` n'appartient pas à l'incrément.** Le compteur est un compteur
de *projet* : `495/project.json` n'en porte qu'un, avancé par toute commande
appliquée quel que soit l'incrément visé. Le loger dans `IncrementState` serait
faux, et rendrait `CreateIncrement` invérifiable puisqu'elle ne dispose d'aucun
incrément préexistant où le lire.

La version d'état arrive donc en **fait explicite**, conformément à `§5.2` :
chaque fonction la reçoit en paramètre. Son avancement appartient au contrôleur,
qui détient le compteur ; `domain` la compare, il ne l'incrémente pas.

`GateDecision` reprend les données de `SRC-DESIGN §5.2`. Pour G5, elle peut en
outre transporter le fait explicite de réconciliation établi depuis le reçu
d'intégration ; le domaine compare ce fait à l'intention, il ne lit pas le reçu.
Une décision est dite
**courante** lorsqu'elle est la dernière appliquée, que son candidat éventuel
égale `current_candidate` et qu'aucune commande invalidante n'est intervenue.
`SubmitCandidate` remplace `current_candidate` et efface
`current_gate_decision` ; `ApplyGateDecision` est la seule commande qui renseigne
ce dernier. Un seul champ porte la décision courante : deux faits G4 `PASS` et
`FAIL` ne peuvent donc pas coexister.

`has_unreconciled_external_effect` retourne vrai si
`other_unreconciled_external_effect` est vrai ou si `integration_intent` existe
avec `reconciled == false`. Les préconditions de retour et de clôture utilisent
ce prédicat, jamais l'un des deux champs isolément.

```
# commands.py
class TransitionArity(StrEnum):
    REQUIRED, OPTIONAL, FORBIDDEN

TRANSITION_ARITY: tuple[tuple[CommandName, TransitionArity], ...]    # 12 entrées

@dataclass(frozen=True, slots=True)
class Command:
    command_id: str
    name: CommandName
    expected_state_version: int
    payload: CommandPayload          # union scellée, une variante par commande

def well_formed(command: Command) -> Outcome[Command, None]
def intended_edge(state, command) -> Outcome[TransitionEdge | None, IncrementState]
def validate(state: IncrementState | None, command: Command,
             project_state_version: int) -> Outcome[Command, IncrementState | None]
def create_increment(command, project_state_version) -> Outcome[IncrementState, None]
def apply_command(state, command, project_state_version) -> Outcome[IncrementState, IncrementState]
```

#### Bonne formation d'une commande

Laisser `payload.target_phase` valoir `None` suffirait sinon à sortir de la
table pour une commande qui exige une transition. L'arité est donc **déclarée
par commande** et **vérifiée à l'exécution**, pas portée par les annotations.
Les commandes à deux formes ajoutent une relation entre leur discriminant et
leur cible.

| Arité | Commandes | Contrainte sur `payload.target_phase` |
| --- | --- | --- |
| `REQUIRED` | `CloseIncrement`, `ReviseIncrement`, `StartIntegration` | Non nul ; nul est refusé |
| `OPTIONAL` | `ApplyGateDecision`, `StartAttempt` | Forme déterminée par le verdict ou par la phase de tentative |
| `FORBIDDEN` | `CreateIncrement`, `ProposeArtifact`, `SealArtifact`, `RecordApproval`, `EvaluateGate`, `SubmitCandidate`, `CancelOperation` | Nul ; toute valeur est refusée |

Trois plus deux plus sept : les douze commandes ont une arité, et
l'énumération du domaine `commands` compare le cardinal de `TRANSITION_ARITY` à
douze.

`well_formed(command)` refuse avec `MALFORMED_COMMAND` dans cinq cas, chacun
nommé par `subject` :

| `subject` | Constat |
| --- | --- |
| `target_phase` | Arité `REQUIRED` et `target_phase is None` ; ou arité `FORBIDDEN` et `target_phase` non nul |
| `payload` | La variante de payload ne correspond pas à `command.name` |
| `gate` | `gate` est renseigné alors que l'arité est `FORBIDDEN` |
| `attempt_form` | `StartAttempt` dont `attempt_phase` n'est pas `implementation` et dont `target_phase` est non nul |
| `decision_form` | `ApplyGateDecision` avec `PASS` sans cible, ou avec `FAIL` / `INDETERMINATE` et une cible non nulle |

`details` porte l'arité ou la forme attendue. La concordance entre
`command.name` et la variante de payload est vérifiée à l'exécution par le type
de la variante : une annotation d'union ne l'imposerait pas.

`well_formed` ne consulte pas l'état : une commande mal formée n'est pas une
commande, et son `expected_state_version` n'est pas plus digne de foi que son
payload. C'est pourquoi cette étape précède l'enveloppe.

#### Les deux formes d'`ApplyGateDecision`

Le payload porte la `GateDecision` complète et une `target_phase` éventuelle.
La forme découle du verdict, sans consulter l'état :

| Verdict | `target_phase` | Effet possible |
| --- | --- | --- |
| `PASS` | Obligatoire | Enregistre la décision puis applique l'arête de sa gate |
| `FAIL`, `INDETERMINATE` | Interdite | Enregistre la décision ; phase et tentatives inchangées |

Cette relation est vérifiée par `well_formed` avec
`subject = "decision_form"`. Ainsi, un verdict défavorable ne peut pas fournir
la cible d'une arête, et un `PASS` ne peut pas éviter la table en omettant sa
cible. La gate comparée à l'arête est `decision.gate` : le payload ne porte pas
une seconde valeur susceptible de diverger.

`validate` exige que
`decision.expected_state_version == command.expected_state_version ==
project_state_version`, que le rapport soit encore courant, que le candidat de
G3, G4 ou G5 égale `current_candidate` et, pour un `PASS`, que l'arête résolue
porte `decision.gate`. Un G4 `FAIL` valide produit donc un fait courant
utilisable par la reprise sans franchir `verifying → accepted` ; un G4 `PASS`
valide franchit cette arête et ne peut jamais servir de fait de reprise.

#### Les deux formes de `StartAttempt`

L'arité `OPTIONAL` autorise les deux formes ; elle ne les distingue pas. Or
`Accepted(None)` et `Accepted(edge)` recouvrent ici deux opérations qui n'ont ni
les mêmes préconditions ni le même effet. Le payload porte donc
`attempt_phase: AttemptPhase` et, pour une reprise, le candidat exact.
`validate` vérifie la relation entre cette phase de tentative, l'état existant
et la décision G4 courante :

| Forme | `attempt_phase` | `target_phase` | Préconditions | Effet |
| --- | --- | --- | --- | --- |
| Ouverture | Les cinq valeurs | `None` | Contrat de phase scellé ; gate d'entrée de `attempt_entry_conditions` satisfaite si non nulle ; budget disponible | **Crée** une tentative à `running` |
| Reprise | `implementation` seulement | `implementing`, depuis `verifying` | `current_gate_decision` est un G4 `FAIL` courant sur le candidat du payload ; une tentative d'implémentation à `suspended` ; contrat inchangé | **Reprend** la tentative suspendue : `suspended → running`, aucune tentative créée |

La forme d'ouverture couvre AC-13-3 et AC-13-4 : une tentative de clarification
existe sans gate franchie, une tentative de conception après G1 et avant G2. La
forme de reprise est l'arête de correction, et le déclencheur composé
« `StartAttempt` après un G4 `FAIL`, sous le contrat inchangé » de
`attempt_state_triggers` (AC-13-15, AC-13-16).

Deux refus distincts protègent cette relation :

- une commande dont `attempt_phase` n'est pas `implementation` mais qui porte un
  `target_phase` est **mal formée** — le constat ne dépend d'aucun état, il est
  fait par `well_formed` avec `subject = "attempt_form"` ;
- une reprise demandée sans G4 `FAIL` courant, ou sans tentative d'implémentation
  à `suspended`, est refusée par `validate` avec `PRECONDITION_UNSATISFIED`, la
  précondition manquante dans `subject`.

La reprise **ne crée aucune tentative** : `start_attempt` n'est pas appelée, et
c'est `transition(attempt, running, trigger)` qui s'applique à la tentative
suspendue existante. AC-08-5 en découle — la correction ne termine pas la
tentative courante — et AC-13-10 aussi, puisque rien ne remplace les
précédentes.

#### Résolution de l'arête

**Le nom d'une commande ne détermine pas la présence d'une transition.**
`StartAttempt` porte l'arête de correction `verifying → implementing`, mais crée
aussi les tentatives de clarification, de spécification et de conception, qui ne
changent aucune phase. Un ensemble `CARRYING_COMMANDS` indexé par le nom serait
donc faux. C'est l'arité, puis le payload et la phase courante, qui décident.

`intended_edge(state, command)` n'est appelée qu'après `well_formed`. Elle
retourne
- `Accepted(None)` si `command.payload.target_phase is None` — l'arité a déjà
  garanti que cette absence est légitime pour cette commande ;
- `Accepted(edge)` si `edge_between(state.phase, target_phase)` existe **et**
  que les trois concordances ci-dessous sont vérifiées ;
- un refus sinon.

| Concordance exigée | Refus si violée |
| --- | --- |
| Le couple `(state.phase, target_phase)` figure dans `TRANSITIONS` | `UNKNOWN_TRANSITION`, ou `INTEGRATED_REQUIRES_NEW_INCREMENT` si `state.phase is integrated` |
| `edge.command == command.name` | `UNKNOWN_TRANSITION` — cette commande ne porte pas cette arête |
| Si `edge.gate is not None`, alors `command.payload.decision.gate == edge.gate` | `UNKNOWN_TRANSITION` — la décision ne porte pas sur la gate de l'arête |

Sans la deuxième concordance, un `CloseIncrement` visant `implementing` depuis
`verifying` emprunterait l'arête de correction de `StartAttempt`. Sans la
troisième, un `ApplyGateDecision` portant G3 franchirait l'arête de G0.

#### Trois groupes de commandes, trois interfaces

`apply_command` ne peut pas représenter le résultat de toutes les commandes.
`EvaluateGate` produit un rapport, `ProposeArtifact` une proposition,
`CancelOperation` une demande d'arrêt : aucun de ces registres n'existe dans
`IncrementState`, et aucun des quatre-vingt-dix-huit critères ne nomme ces trois
commandes.

`RecordApproval` en est sortie : AC-16-4 exige un état d'approbation conservé,
donc son effet est modélisé (§3.2).

`SubmitCandidate` en sort également. AC-07-8 et AC-12-2 exigent qu'un `PASS` G4
soit courant sur le candidat exact : soumettre un candidat doit donc remplacer
`current_candidate` et invalider la décision précédente, même si le registre
historique des candidats reste hors de `IncrementState`.

Les trois effets non représentables restent limités à la validation :

| Groupe | Commandes | Interface |
| --- | --- | --- |
| Effet modélisé dans `IncrementState` | `ApplyGateDecision`, `CloseIncrement`, `ReviseIncrement`, `StartIntegration`, `StartAttempt`, `SealArtifact`, `RecordApproval`, `SubmitCandidate` | `well_formed`, `validate`, `apply_command` |
| Création de l'agrégat | `CreateIncrement` | `well_formed`, `validate`, `create_increment` |
| Effet non modélisé dans cet agrégat | `ProposeArtifact`, `EvaluateGate`, `CancelOperation` | `well_formed`, `validate` seulement |

Huit plus une plus trois : les douze sont couvertes par `validate`, ce qui
suffit à AC-12-1 — les douze déclarent leurs préconditions — et à AC-12-6 — le
refus nomme la précondition violée. AC-12-5, « un refus laisse l'état
strictement inchangé », est tenu par les huit premières via l'identité de
l'objet retourné, et trivialement par les trois dernières, qui ne touchent
aucun état.

`SealArtifact` appartient au premier groupe parce que son effet *est* modélisé :
il met à jour `sealed` et `revisions` de l'agrégat, par `sealing.seal` et
`revisions.record_revision`.

#### Effets atomiques sur l'agrégat

Après validation, `apply_command` construit une seule nouvelle valeur de
`IncrementState`. Les effets sur la phase, les tentatives et les faits courants
ne sont jamais appliqués séparément :

Les onze arêtes de retour se partagent exactement en dix arêtes portées par
`ReviseIncrement` et l'arête de correction portée par `StartAttempt` (AC-08-1).
Les dix premières comprennent les deux arêtes de type `return` et les huit de
type `revision` (AC-08-3).

| Commande | Effet accepté |
| --- | --- |
| `ApplyGateDecision` | Enregistre `current_gate_decision`. Une réconciliation G5 admissible remplace l'intention exacte par `reconciled=True`, quel que soit le verdict. Sur `FAIL` ou `INDETERMINATE`, ne change ni phase ni tentative. Sur `PASS`, remplace la phase par la cible de l'arête acceptée et applique l'effet de tentative détaillé ci-dessous. |
| `CloseIncrement` | Remplace la phase par `closed` et termine la tentative courante, s'il en existe une, avec `increment_closed` ; les tentatives antérieures sont recopiées sans changement (AC-10-8), comme les registres scellés. |
| `ReviseIncrement` | Sur chacune de ses dix arêtes, termine la tentative courante avec `revision_requested` (AC-08-2), ouvre la révision de travail consécutive (AC-08-8), applique l'arête acceptée et efface le candidat, la décision de gate et l'intention propres à la révision précédente ; les artefacts scellés restent inchangés (AC-08-7). |
| `StartIntegration` | Crée `IntegrationIntent(candidate, destination, reconciled=False)`, puis remplace la phase par `integrating` avec l'arête acceptée. |
| `StartAttempt` | En ouverture, ajoute la nouvelle tentative `running`. En reprise, passe la tentative d'implémentation suspendue à `running`, applique l'arête acceptée et efface le G4 `FAIL` consommé. |
| `SealArtifact` | Met à jour `sealed` et `revisions`, puis efface `current_gate_decision` si le `ChangeKind` de l'artefact invalide sa gate. Si la cible est le rapport déclaré de la tentative de revue courante, termine cette tentative avec `phase_completed` dans la même valeur d'agrégat. |
| `RecordApproval` | Remplace `approvals` par le registre append-only retourné par `record`. |
| `SubmitCandidate` | Remplace `current_candidate` par la référence immuable soumise et met `current_gate_decision` à `None`. |

Le rôle « rapport de revue » n'est pas déduit du chemin : le payload de
`SealArtifact` porte la tentative de revue et la déclaration de sortie extraite
de son contrat scellé, liée à la référence exacte de ce contrat. `validate`
compare l'identité de l'artefact à cette déclaration. Un artefact seulement
nommé « rapport » ne termine aucune tentative.

Pour un `ApplyGateDecision` avec `PASS`, la gate détermine exactement l'effet
sur la tentative :

| Gate | Effet sur les tentatives |
| --- | --- |
| G0, G1, G2 | Termine respectivement la tentative de clarification, de spécification ou de conception à `phase_completed`. |
| G3 | Passe la tentative d'implémentation `running → suspended`. |
| G4 | Ne modifie pas la tentative d'implémentation, déjà suspendue ; la tentative de revue a été terminée par le scellement de son rapport. |
| G5 | Exige une réconciliation admissible, puis passe la tentative d'implémentation `suspended → finished` avec `integration_succeeded` ; l'intention correspondante est déjà remplacée par `reconciled=True` dans le même effet atomique. |

`validate` exige la tentative et l'état attendus par cette table : tentative de
phase correspondante à `running` pour G0 à G3, implémentation à `suspended` et
revue terminée pour G4, implémentation à `suspended` et intention exacte pour
G5. Un G5 `PASS` exige en outre une réconciliation admissible. Une absence ou
un état discordant produit
`PRECONDITION_UNSATISFIED`, sans modification partielle.

Une décision G5 peut porter une réconciliation même avec `FAIL` : par exemple,
un reçu d'échec peut démontrer que l'effet externe est terminé sans autoriser
l'intégration. `validate` exige alors candidat et destination égaux à
l'intention courante et un reçu référencé ; `ApplyGateDecision` marque
l'intention réconciliée sans changer la phase ni la tentative. `ReviseIncrement`
ou `CloseIncrement` redevient ensuite applicable. Sans ce fait, un G5
défavorable laisse l'intention non réconciliée.

La commande et son verdict forment le déclencheur : un objet `GateDecision`
isolé ne termine ni ne suspend rien. Cette table rend exécutables AC-08-6,
AC-10-7, AC-13-7, AC-13-12, AC-13-13 et AC-13-15. Toute tentative antérieure
est recopiée à l'identique.

**`CreateIncrement` est à part.** Elle ne dispose d'aucun `IncrementState`
d'entrée : elle en produit un. Elle reçoit la version d'état du projet en
paramètre, comme les autres, ce qui rend son enveloppe vérifiable. Le profil est
figé par cette commande et n'est plus modifiable ensuite (REQ-11).

#### Ordre d'évaluation

`apply_command(state, command, project_state_version)` évalue dans cet ordre :

1. **Bonne formation**, par `well_formed`. Indépendante de l'état.
2. **Enveloppe.** `command.expected_state_version == project_state_version`,
   sinon `STATE_VERSION_MISMATCH`. La commande n'est pas adressée à cette
   version : rien d'autre n'est examiné.
3. **Arête visée**, par `intended_edge`. Une transition demandée mais absente ou
   discordante est refusée *quelles que soient les préconditions* (AC-07-3),
   d'où cette étape avant la suivante.
4. **Préconditions déclarées** de `command.name`, sinon
   `PRECONDITION_UNSATISFIED` avec la précondition dans `subject` (AC-07-2,
   AC-12-6).
5. **Effet** sur l'agrégat. `domain` n'avance pas le compteur de projet.

Lorsque l'arête figure dans `TRANSITIONS` et que toutes les préconditions sont
satisfaites, l'opération retourne `Accepted` avec le nouvel agrégat (AC-07-1).

`validate` s'arrête après l'étape 4 et retourne la commande. Les trois commandes
du troisième groupe n'ont pas d'étape 5.

`UNKNOWN_TRANSITION`, `PRECONDITION_UNSATISFIED` et `MALFORMED_COMMAND` sont
trois codes distincts, ce qui satisfait AC-07-4 par construction plutôt que par
convention de message.

**Ce que l'enveloppe ne couvre pas.** `§5.5` demande en outre qu'un même
`command_id` avec le même payload retourne le résultat précédent, et qu'un même
identifiant avec un payload différent soit rejeté. Cette idempotence exige le
journal et le verrou : elle appartient à `application` et `infrastructure`.
`domain` porte le champ et compare la version d'état ; il ne revendique pas
l'idempotence, qui n'est allouée à aucune exigence de ce périmètre.

`integrated` et `closed` n'apparaissent comme `origin` d'aucune entrée de
`TRANSITIONS` (AC-07-6, AC-09-2). Il n'y a donc pas de garde spéciale à écrire :
l'absence dans la table suffit, et un test d'énumération le constate sur les
quatre-vingt-un couples.

Les préconditions sont déclarées par commande, en données et non en code
dispersé :

| Commande | Préconditions déclarées |
| --- | --- |
| `ApplyGateDecision` | Rapport courant ; versions de la décision, de la commande et du projet égales ; gate attendue dans la phase courante ; candidat de G3 à G5 égal à `current_candidate` ; réconciliation G5 éventuelle liée à l'intention et à un reçu ; sur `PASS`, gate égale à celle de l'arête |
| `StartIntegration` | Phase `accepted` ; décision courante G4 `PASS` sur `current_candidate` et sur le candidat du payload ; destination attendue ; `has_unreconciled_external_effect(state) == false` |
| `ReviseIncrement` | Acceptée depuis toute phase non `integrated` et non `closed` ; depuis `integrating`, exige `has_unreconciled_external_effect(state) == false` (AC-08-4, AC-12-4) |
| `StartAttempt` | Ouverture : contrat scellé, gate d'entrée satisfaite si non nulle, budget disponible. Reprise : G4 `FAIL` courant sur le candidat exact, tentative d'implémentation suspendue, contrat inchangé. |
| `CloseIncrement` | Phase non terminale ; motif présent ; motif dans `close_reasons` ; `has_unreconciled_external_effect(state) == false` ; acceptée si toutes ces conditions sont vraies et refusée sinon (AC-07-5) |
| `SealArtifact` | Format valide ; dépendances résolues ; révision consécutive ; couple non déjà scellé ; octets fournis ; pour terminer une revue, déclaration de sortie liée au contrat exact |
| `RecordApproval` | Acteur autorisé ; cible complète à cinq champs |
| `ProposeArtifact` | Révision ouverte ; type autorisé dans la phase courante |
| `EvaluateGate` | Entrées disponibles ; aucune mutation de phase |
| `SubmitCandidate` | Tentative connue ; référence complète du candidat |
| `CancelOperation` | Opération en cours |
| `CreateIncrement` | Projet et profil connus ; profil figé dès cette commande |

L'oracle positif de `CloseIncrement` parcourt les sept phases non terminales et
les cinq valeurs de `close_reasons`, avec
`has_unreconciled_external_effect(state) == false`, et exige l'acceptation des
trente-cinq cas (AC-10-3). Il s'agit d'un test unitaire croisé, pas d'un
quinzième domaine d'énumération.

AC-12-1 exige que les douze soient représentées avec leurs préconditions : la
table ci-dessus est l'inventaire, et l'énumération du domaine `commands` compare
son cardinal à douze. AC-07-8 est porté par la ligne `StartIntegration`, pas par
un commentaire. AC-12-3 est porté par un champ, non par une phrase : l'effet de
`StartIntegration` écrit `integration_intent`, une `IntegrationIntent` portant
le candidat exact, la destination et `reconciled=False`, puis remplace la phase
par `integrating` avec l'arête acceptée. C'est la représentation de
l'« événement d'intention durable » de `§5.5`. Aucun `PASS` G5 n'est produit :
G5 reste porté par `ApplyGateDecision` après réception du reçu d'intégration.

`other_unreconciled_external_effect` porte uniquement les effets externes
autres que l'intention d'intégration. Le prédicat dérivé inclut les deux
sources ; il n'existe donc pas deux booléens prétendant chacun représenter le
même fait. G5 `PASS` réconcilie l'intention exacte avant de passer à
`integrated`.

Toute demande de changement de `profile` sur un incrément existant est refusée
avec `PROFILE_IMMUTABLE`, pour tout couple (profil initial, profil visé), y
compris vers `exploration`, et sans mutation : AC-11-1, AC-11-2 et AC-11-3.

### 3.5 `attempts.py`

```
class AttemptStateName(StrEnum)   # running, suspended, finished
class FinishReason(StrEnum)       # 6 valeurs
class AttemptPhase(StrEnum)       # 5 valeurs

@dataclass(frozen=True, slots=True)
class AttemptState:
    attempt_id: str ; increment_id: str ; increment_revision: int
    attempt_phase: AttemptPhase ; contract_ref: ArtifactRef
    state: AttemptStateName ; finish_reason: FinishReason | None
    history: tuple[AttemptEvent, ...]

def start_attempt(existing: tuple[AttemptState, ...], ...) -> Outcome[AttemptState, tuple[AttemptState, ...]]
def transition(attempt: AttemptState, target: AttemptStateName,
               trigger: Trigger, reason: FinishReason | None = None) -> Outcome[AttemptState, AttemptState]
```

`increment_revision` est la révision de l'incrément, pas celle d'un artefact
(AC-13-2).

`transition` **ne prend aucun paramètre de contrat** : il recopie
`contract_ref` depuis la tentative reçue. Aucun chemin d'appel ne permet donc
d'en substituer un autre, ce qui tient AC-13-9 par la signature elle-même
(§2.3). Une reprise après suspension réutilise nécessairement la même référence
(AC-08-9). `attempt_id` suit le même chemin, avec en appui un test constatant
que tous les événements de `history` portent le même identifiant (AC-13-1).

`transition` refuse `finished` sans motif avec `MISSING_FINISH_REASON`
(AC-13-6) et n'accepte que les quatre couples de `attempt_states.transitions`,
chacun par son déclencheur déclaré (AC-13-5, AC-13-16). Les cinq autres couples
des neuf sont refusés avec `UNKNOWN_ATTEMPT_TRANSITION` ; `finished` n'a aucune
transition sortante.

**Unicité de `running`.** AC-13-14 interdit deux tentatives `running` **de
phases différentes** sur la même révision d'incrément. `start_attempt` refuse
donc avec `RUNNING_ATTEMPT_CONFLICT` si et seulement s'il existe déjà une
tentative `running` de la même révision **dont l'`attempt_phase` diffère**. Une
tentative `suspended` n'entre pas dans la comparaison, ce qui autorise la
coexistence revue / implémentation d'AC-13-17.

Le critère ne dit rien de deux tentatives `running` de la **même** phase ; la
conception n'ajoute donc pas cette interdiction. Le nombre de tentatives d'une
phase est borné ailleurs, par `limits.attempts` du contrat de phase, et non par
une règle du domaine.

**Verdicts de gate et déclencheurs.** Aucun verdict n'est à lui seul le
déclencheur d'un passage à `finished` : AC-13-7 et AC-08-6 sont satisfaits par
l'absence d'une telle entrée, non par une garde. Un verdict défavorable
participe en revanche légitimement à un déclencheur **composé** : la table
`attempt_state_triggers` porte `suspended → running` sur « `StartAttempt` après
un G4 `FAIL`, sous le contrat inchangé ». Ce qui est interdit, c'est qu'un
verdict termine une tentative par lui-même ; ce n'est pas qu'il figure dans un
déclencheur.

De même, un changement de phase ne termine jamais une tentative de son propre
fait : chaque passage à `finished` est porté par l'un des six déclencheurs
déclarés (AC-13-8).

Les six valeurs de `attempt_finish_reasons` possèdent chacune leur déclencheur
de commande ou d'observation ; chacune est donc atteignable par une transition
déclarée (AC-13-11).

### 3.6 `links.py` et `invalidation.py`

```
def add_link(graph, source, target, link_type: LinkType) -> Outcome[LinkGraph, LinkGraph]
def invalidated_by(change: ChangeKind) -> frozenset[Gate]
```

`add_link` refuse avec `UNKNOWN_LINK_TYPE` un type absent des deux ensembles
(AC-14-2), et avec `DEPENDENCY_CYCLE` toute arête `depends_on` fermant un
circuit, en retournant le graphe reçu sans mutation (AC-15-1, AC-15-4).
`details` porte les nœuds du cycle, dans l'ordre de parcours (AC-15-2). Un cycle
formé de `related_to` est accepté (AC-15-3). Les six valeurs de `LinkType` sont
toutes représentables (AC-14-1) ; le type distingue les cinq exécutoires de
l'informatif par un champ du modèle, pas par une convention de nommage
(AC-14-3).

**`ChangeKind` est un type de changement, pas un type de lien.** L'ambiguïté est
levée en énumérant les six valeurs et en les rattachant une à une aux règles
scellées :

| `ChangeKind` | Règle scellée (`change`) | `must_reevaluate` |
| --- | --- | --- |
| `MANDATORY_REQUIREMENT_OR_SCENARIO` | requirement_set ou scenario_set obligatoire | G1, G2, G3, G4, G5 |
| `DECISION_OR_INTERFACE_CONTRACT` | decision ou interface_contract | G2, G3, G4, G5 |
| `POLICY_VERIFIER_ENVIRONMENT_OR_BASELINE` | politique, vérificateur, environnement ou base | G2, G3, G4, G5 |
| `CANDIDATE` | candidat | G3, G4 |
| `DESTINATION_BRANCH_ADVANCED` | branche de destination avancée | G5 |
| `UNCONSUMED_RELATED_TO_NOTE` | note related_to non consommée | ∅ |

La sixième valeur nomme **le changement d'une note qui n'a pas été consommée**,
non le type de lien `related_to`. C'est un `ChangeKind`, du même ensemble que
les cinq autres ; `LinkType.RELATED_TO` en est distinct et vit dans un autre
ensemble clos. `invalidated_by(UNCONSUMED_RELATED_TO_NOTE)` retourne l'ensemble
vide, ce qui satisfait AC-14-4 et AC-17-3.

`invalidated_by` est pure et totale sur les six valeurs. Son oracle est la
**complétude**, pas la minimalité : le test vérifie `must_reevaluate ⊆ résultat`
pour chacune des six règles (AC-17-1), constate qu'une fonction constamment vide
échoue sur au moins une règle (AC-17-2), accepte la sur-approximation (AC-17-4)
et vérifie le déterminisme en plus, jamais seul (AC-17-5).

## 4. Allocation des exigences

| Exigence | Composant | Domaine de test |
| --- | --- | --- |
| REQ-01 | `references.build_ref` | unitaire — table 5 champs × {présent, absent} |
| REQ-02 | `references.build_ref` | unitaire |
| REQ-03 | `revisions.record_revision` | unitaire — propriété sur séquences |
| REQ-04 | `sealing.seal`, `sealing.digest_of` | unitaire — propriété sur séquences |
| REQ-05 | `vocabulary.ARTIFACT_KINDS` | énumération — `artifact_kinds`, 13 |
| REQ-06 | `state.with_status`, `commands.apply_command` | énumération — `phases` 9, `operational_statuses` 5 ; unitaire — 45 couples pour AC-06-3, 25 arêtes × 5 statuts pour AC-06-4 |
| REQ-07 | `phases.TRANSITIONS`, `commands.intended_edge` | énumération — `phase_pairs` 81, `transition_edges` 25 ; unitaire pour les préconditions |
| REQ-08 | `attempts`, `phases`, `commands.apply_command` | énumération — les 11 arêtes de retour, partition 10 / 1 |
| REQ-09 | `phases.TRANSITIONS`, `outcomes` | énumération — aucune arête sortante d'`integrated` ; unitaire pour le code de remède |
| REQ-10 | `commands`, `vocabulary` | énumération — `close_reasons` 5 ; unitaire pour les refus |
| REQ-11 | `state`, `commands.create_increment` | unitaire — tout couple (profil initial, profil visé) refusé |
| REQ-12 | `commands.well_formed`, `commands.validate`, `commands.apply_command` | énumération — `commands` 12, `TRANSITION_ARITY` 12 ; unitaire pour l'invariance sur refus et les effets acceptés |
| REQ-13 | `attempts`, `commands.apply_command` | énumération — `attempt_states` 3, `attempt_state_pairs` 9, `attempt_finish_reasons` 6, `attempt_entry_conditions` 5, `attempt_exit_conditions` 5 |
| REQ-14 | `links`, `invalidation` | énumération — `link_types` 6 |
| REQ-15 | `links.add_link` | unitaire — propriété sur séquences d'ajouts, dont les nœuds du cycle |
| REQ-16 | `references.approval_applies`, `references.build_approval`, `references.ApprovalRegistry`, `sealing.digest_bytes` | unitaire — octets identiques, refus `DIGEST_MISMATCH`, lisibilité de l'approbation de n après scellement de n+1 |
| REQ-17 | `invalidation.invalidated_by` | énumération — `invalidation_rules` 6 |
| REQ-18 | paquet entier | contrôle `imports` |
| REQ-19 | paquet entier | contrôle `imports` et contrôle `manifest_scope` |
| REQ-20 | paquet entier | contrôle `imports` |

Les vingt exigences sont allouées. Aucune n'est laissée sans composant ni sans
domaine de test.

## 5. Domaines finis et cardinalités

`ADR-0006` déclare quatorze cardinalités. Chaque domaine reçoit un test
d'énumération émettant sur `stderr` une ligne
`COVERAGE <domaine> <couvert>/<déclaré>`, et le contrôle exige l'égalité.

| Domaine | Déclaré | Ce que l'énumération parcourt |
| --- | --- | --- |
| `phases` | 9 | Les neuf valeurs de `Phase`, toutes représentables (AC-06-1) |
| `phase_pairs` | 81 | Le produit `Phase × Phase`, accepté ssi dans `TRANSITIONS` |
| `transition_edges` | 25 | Les entrées de `TRANSITIONS`, chacune nommant sa commande (AC-07-7) |
| `operational_statuses` | 5 | Les cinq valeurs d'`OperationalStatus`, toutes représentables (AC-06-2) |
| `commands` | 12 | Les valeurs de `CommandName`, chacune déclarant ses préconditions |
| `artifact_kinds` | 13 | Les treize valeurs d'`ArtifactKind`, toutes représentables et sans ajout ni omission face à `SRC-DESIGN §4.2` (AC-05-1, AC-05-3) |
| `link_types` | 6 | Cinq exécutoires plus `related_to` |
| `close_reasons` | 5 | Les motifs de clôture |
| `attempt_states` | 3 | Les états de tentative |
| `attempt_state_pairs` | 9 | Le produit des états, accepté ssi dans la table des quatre transitions |
| `attempt_finish_reasons` | 6 | Les motifs, chacun avec son déclencheur unique |
| `attempt_entry_conditions` | 5 | Les cinq phases de tentative et leur gate d'entrée |
| `attempt_exit_conditions` | 5 | Les cinq sorties normales et leur motif |
| `invalidation_rules` | 6 | Les six valeurs de `ChangeKind` |

Le total des couples parcourus est `81 + 9 = 90` ; les douze autres domaines
sont des ensembles plats. Un écart dans un sens ou dans l'autre échoue : un
domaine sous-couvert signale un test manquant, un domaine sur-couvert signale
une dérive du vocabulaire.

### 5.1 Liaison de l'oracle aux octets scellés

Une table d'attendus recopiée à la main dans les tests ne prouverait que la
cohérence des tests avec eux-mêmes. Les tests d'énumération ne recopient donc
pas le vocabulaire : un module d'appui `tests/enumeration/sealed_reference.py`
lit `495/changes/INC-0002/requirements.json` relativement à la racine de
découverte, vérifie que son SHA-256 égale la constante littérale

```
sha256:f503f82932ab6f6b5c172c5d7aeabb24cdf36291e2e50c0c3a207d79bb622c92
```

et n'en dérive les ensembles attendus qu'après cette égalité. Un digest
différent échoue immédiatement, sans comparaison.

Ce module d'appui vit dans l'arborescence de test, jamais dans `src/domain/` :
la lecture de fichier qu'il effectue est interdite au paquet du domaine
(REQ-18) et ne lui est pas imputée. Son nom ne correspond pas au motif
`test_*.py` : il n'est pas collecté comme test.

## 6. Stratégie de test

### 6.1 Deux racines disjointes

```
tests/
  __init__.py
  unit/          __init__.py, test_*.py
  enumeration/   __init__.py, sealed_reference.py, test_*.py
```

`tests/unit` ne contient pas `tests/enumeration` : ce sont deux répertoires
frères. La contrainte de disjonction d'`ADR-0006` est satisfaite par la
structure, et un unique échec ne peut pas être compté deux fois.

Les deux racines étant des paquets importables depuis la racine de découverte,
`tests/__init__.py` et les deux `__init__.py` de sous-répertoire sont
nécessaires à `unittest discover -t <cand>`.

`PYTHONPATH` vaut `<cand>/src`, chemin absolu lié par le contrat
d'implémentation : `domain` est importable, `<output_root>` en est exclu, et
aucun contrôle ne charge de code depuis son répertoire de sortie.

### 6.2 Ce que chaque racine porte

`tests/unit` porte ce qui n'est pas un domaine fini : les messages de refus
nommant leur sujet, l'invariance de l'état sur refus, les propriétés sur
séquences d'opérations — révisions consécutives, stabilité des digests scellés,
acyclicité — et l'applicabilité d'une approbation.

`tests/enumeration` porte les quatorze domaines de §5, et rien d'autre.

Aucun générateur aléatoire. Les propriétés sur séquences sont vérifiées sur des
séquences énumérées ou construites explicitement, jamais tirées au sort : une
propriété qui échoue doit échouer à chaque exécution.

Aucun `skip`, aucun `expectedFailure`. Un contrôle optionnel non applicable est
retiré du plan avant exécution ; il n'est pas neutralisé à l'exécution.

L'inventaire attendu de chaque contrôle — le décompte et l'ensemble des
identifiants de test — est fixé par le plan de contrôles, pas par ce document.
Un code de sortie nul sans inventaire conforme ne vaut rien.

### 6.3 Contrôle `imports`

Vérificateur `check_imports.py`, objet de contrôle scellé, matérialisé dans
`<verifier_root>` depuis sa référence approuvée et jamais lu depuis le dépôt
qu'il vérifie. Il analyse `<cand>/src` avec `ast` et écrit son rapport sous
`<output_root>`.

| Critère | Prédicat |
| --- | --- |
| AC-18-1 | Aucun appel n'ouvre de fichier, de socket ni de sous-processus |
| AC-18-2 | Aucun import n'atteint la liste nommée d'entrées/sorties |
| AC-19-1 | La racine de tout module importé appartient à `sys.stdlib_module_names` ou au projet |
| AC-20-1 | Aucune arête sortante de `domain` vers `validation`, `policy`, `application`, `ports` ou `infrastructure` |
| AC-20-2 | Conséquence du précédent : l'ensemble des arêtes sortantes étant vide, aucun import de `domain` par l'un des cinq ne peut fermer de cycle |

La liste nommée d'AC-18-2, fixée par le plan de contrôles et liée par digest :
`socket`, `ssl`, `http`, `urllib`, `ftplib`, `smtplib`, `asyncio`, `selectors`,
`socketserver`, `xmlrpc`, `webbrowser`, `os`, `io`, `pathlib`, `shutil`,
`tempfile`, `glob`, `fileinput`, `sqlite3`, `dbm`, `shelve`, `pickle`,
`subprocess`, `multiprocessing`, `signal`, `mmap`, `fcntl`, `ctypes`,
`importlib`, plus tout SDK d'agent nommé. Les appels `open`, `eval`, `exec`,
`compile` et `__import__` sont refusés au titre d'AC-18-1. `hashlib` n'appartient
à aucune des deux listes.

L'ensemble des fichiers attendus est dérivé du manifeste du candidat — tous les
`.py` sous `<cand>/src` — et comparé à l'ensemble effectivement analysé. Un
écart dans un sens ou dans l'autre est un `FAIL`. Chaque entrée du rapport porte
le chemin relatif et le digest du fichier contrôlé, ce qui lie le rapport aux
octets vérifiés.

Ce contrôle vérifie aussi l'ordre de dépendance interne de §2.2, qu'il construit
déjà pour AC-20-1.

### 6.4 Contrôle `manifest_scope`

AC-19-1 porte sur ce que le code importe ; **AC-19-2 porte sur ce que le
candidat déclare**. Une dépendance d'exécution déclarée mais non encore importée
échappe entièrement à l'analyse `ast` : le contrôle `imports` ne peut pas
couvrir AC-19-2.

Une liste noire de noms de fichiers de déclaration ne le peut pas davantage.
Elle ne prouverait que l'absence des motifs qu'elle nomme, et resterait muette
sur `requirements.in`, `environment.yaml`, `tox.ini`, `pdm.lock`, `pixi.toml`
ou tout format à venir. **Un oracle ouvert ne démontre pas une absence.**

Le contrôle porte donc sur une **liste blanche exacte**, liée par le contrat
d'implémentation : l'ensemble des chemins que le candidat est autorisé à
contenir.

| Constat | Verdict |
| --- | --- |
| L'ensemble des chemins du manifeste du candidat est **égal** à la liste blanche scellée | `PASS` |
| Un chemin du manifeste est absent de la liste blanche | `FAIL`, le chemin est nommé |
| Un chemin de la liste blanche est absent du manifeste | `FAIL`, le chemin est nommé |

AC-19-2 en découle : aucun fichier de déclaration de dépendance ne figure dans
la liste blanche, donc aucun ne peut être présent dans le candidat sans produire
un `FAIL`. L'oracle est **fermé** — une égalité ensembliste contre une liste
scellée — au lieu de reposer sur l'exhaustivité d'une énumération de formats.

L'ajout ultérieur d'un `pyproject.toml` légitime devient alors une révision
explicite de la liste blanche, donc du contrat, et non un ajout silencieux.

### 6.5 Qualification

Aucun des quatre contrôles n'est utilisable avant d'avoir accepté une entrée
connue conforme et rejeté une entrée connue fautive, les deux liées par digest.
Un contrôle `imports` qui n'a jamais échoué sur un fichier important `socket` ne
démontre rien ; un contrôle `manifest_scope` qui n'a jamais échoué sur un
candidat portant un chemin hors liste non plus. Les paires de qualification sont
enregistrées avec le plan de contrôles.

## 7. Risques

| Risque | Effet si réalisé | Traitement retenu |
| --- | --- | --- |
| Transcription du vocabulaire dans les tests | L'énumération ne prouve que la cohérence des tests avec eux-mêmes | Dérivation depuis les octets scellés après contrôle de digest (§5.1) |
| Immutabilité annoncée mais non tenue | Un `dict` derrière un champ gelé se mute après construction et l'invariance d'un refus devient fausse | Collections en `tuple` de paires triées ; `MappingProxyType` écarté comme simple vue (§2.1) |
| « Structurel » revendiqué pour une annotation | Une garantie inexistante serait invoquée à G4 | §2.3 distingue ce que tient une signature de ce que tient une fabrique testée |
| Digest opaque transporté sans contrôle | Un producteur fautif ferait passer le digest d'une re-sérialisation | `seal` reçoit les octets bruts et compare à `digest_bytes` (§3.3) |
| Détection d'une transition par le nom de la commande | `StartAttempt` créant une tentative initiale chercherait à tort une arête | `target_phase` du payload décide ; concordances `edge.command` et `edge.gate` exigées (§3.4) |
| `target_phase` nul comme échappatoire | Une commande à transition obligatoire sortirait de la table en omettant sa cible | `TRANSITION_ARITY` déclare l'arité des douze commandes et `well_formed` la vérifie à l'exécution (§3.4) |
| Verdict défavorable confondu avec un franchissement | Un G4 `FAIL` ferait passer la phase à `accepted`, ou ne pourrait pas être enregistré | Deux formes d'`ApplyGateDecision` : cible obligatoire sur `PASS`, interdite sinon (§3.4) |
| Décision courante détachée du candidat | Un ancien G4 `PASS` autoriserait l'intégration d'un candidat remplacé | `SubmitCandidate` remplace `current_candidate` et efface `current_gate_decision` (§3.4) |
| Changement de phase hors table | Une fonction publique acceptant une phase ou une arête arbitraire viderait REQ-07 | Remplacement de `phase` local à l'effet d'`apply_command`, après résolution et validation de l'arête (§3.4) |
| Deux formes de `StartAttempt` confondues | Une reprise créerait une tentative, ou une ouverture emprunterait l'arête de correction | `attempt_phase` au payload ; `well_formed` pour la forme, `validate` pour le fait G4 et la tentative suspendue (§3.4) |
| Effet affirmé sans champ correspondant | AC-12-3 et AC-16-4 seraient réputés satisfaits par une phrase | `integration_intent` et `ApprovalRegistry` sont des champs de l'agrégat (§3.2, §3.4) |
| Deux faits de réconciliation divergents | Une intention non réconciliée pourrait coexister avec un indicateur global faux et autoriser une clôture | Prédicat dérivé sur l'intention et les autres effets externes (§3.4) |
| Provenance d'un objet revendiquée | Une cible construite directement passerait pour validée | `build_approval` ne revendique aucune provenance et revalide les cinq champs (§3.2) |
| Effet non représentable présenté comme appliqué | Trois commandes seraient réputées appliquées alors que leurs registres n'existent pas | Trois groupes d'interfaces ; ces trois commandes n'ont que `validate`, et la limite est déclarée (§3.4, §8) |
| `sys.stdlib_module_names` varie avec l'interpréteur | AC-19-1 change de sens sans que le code bouge | Interpréteur et manifeste d'environnement liés au contrat ; un changement est un nouveau contrat |
| Import dynamique | `ast` ne voit pas l'arête et le graphe est incomplet | `importlib` et `__import__` sont refusés d'emblée plutôt que résolus |
| Oracle ouvert sur les dépendances déclarées | AC-19-2 serait réputé satisfait par une liste noire incomplète | Liste blanche exacte des chemins du candidat, liée au contrat (§6.4) |
| Préconditions non énumérables | Une couverture des 81 couples serait présentée comme une couverture totale de REQ-07 | L'énumération couvre l'appartenance à la table ; les préconditions relèvent des tests unitaires |
| Absence d'immutabilité qualifiée | Un résultat vert serait pris pour une acceptation | Résultats déclarés preuves de progression ; G4 reste `INDETERMINATE` (`ADR-0006`) |
| Absence de contrôleur et de journal | L'idempotence par `command_id` de `§5.5` serait revendiquée sans support | `domain` porte le champ et vérifie `expected_state_version` ; l'idempotence est explicitement non allouée à ce périmètre |

## 8. Limites

Cette conception ne franchit pas G2 à elle seule.

L'observation du dispositif hôte exigée par `ADR-0006` — identité et digest de
configuration, refus réseau qualifié différentiellement contre un pair
contrôlé, bornage de l'ensemble des chemins inscriptibles — n'a pas de
mécanisme choisi. En son absence, G2 reste `INDETERMINATE` avec la raison
`MISSING_EVIDENCE`. Le contrat de phase courant n'accorde aucun droit réseau et
ne permet donc pas de produire la qualification différentielle.

`Q-17` reste ouverte : aucun des six déclencheurs d'`ADR-0002` ne se déclenche
sur le scellement d'une nouvelle révision d'un contrat de phase, alors que
changer un contrat impose une nouvelle tentative.

`Q-15` reste ouverte : `§4.2` n'offre aucun type d'artefact pour un profil de
workflow, et `ADR-0006` en tient lieu à titre transitoire.

Le contrôle `manifest_scope` de §6.4 est ajouté par cette conception. `ADR-0006`
n'en nomme que trois : son introduction dans le plan de contrôles, et la liste
blanche de chemins qu'il exige du contrat d'implémentation, sont un
élargissement à approuver, non un acquis.

Trois commandes — `ProposeArtifact`, `EvaluateGate`, `CancelOperation` — ont
leurs préconditions modélisées mais **pas leurs effets**. Les registres de
propositions, de rapports de gate et d'opérations n'existent pas dans
`IncrementState` et ne sont exigés par aucun des quatre-vingt-dix-huit critères,
dont aucun ne nomme ces trois commandes. Leur modélisation appartient à un
agrégat de projet ultérieur. Rien dans ce document ne doit être lu comme les
appliquant.

`STATE_VERSION_MISMATCH` ne couvre aucun critère scellé : l'enveloppe de `§5.5`
n'a pas d'exigence correspondante dans ce périmètre. Le code existe parce que le
champ existe, non parce qu'un oracle l'impose.

Sous ce profil, un résultat vert sera une preuve fonctionnelle de bootstrap. Il
ne sera jamais une preuve d'isolation ni de séparation du vérificateur.
