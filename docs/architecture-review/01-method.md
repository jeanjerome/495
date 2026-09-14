# Method

The review is built from two skill collections, taking from each what the other lacks.

| | |
|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) | A vocabulary for module shape, a discipline for naming the domain, and a report form built around before/after |
| [obra/superpowers](https://github.com/obra/superpowers) | Team-review practice: evidence before claims, severity calibration, and the rules that keep a test honest |

Neither is applied whole. What each contributes, and what was left, is stated below — the choices
are part of the deliverable.

## The vocabulary

From `codebase-design`. Used exactly, throughout, with no substitution.

| Term | Meaning here | Not |
|---|---|---|
| **Module** | Anything with an interface and an implementation, at any scale: a function, a class, a package | unit, component, service |
| **Interface** | Everything a caller must know to use the module correctly — the signature, but also invariants, ordering, error modes, required configuration | API, signature |
| **Implementation** | What is inside the module | |
| **Depth** | Leverage at the interface: how much behaviour a caller or a test can exercise per unit of interface it must learn | |
| **Deep** / **shallow** | A lot of behaviour behind a small interface / an interface nearly as complex as what it hides | |
| **Seam** | A place where behaviour can be altered without editing in that place; where a module's interface lives | boundary |
| **Adapter** | A concrete thing satisfying an interface at a seam. A role, not a substance | |
| **Leverage** | What callers get from depth: more capability per unit of interface learned | |
| **Locality** | What maintainers get from depth: change, bugs and verification concentrate in one place | |

Three principles from the same source do most of the work in this review:

- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through.
  If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. Wanting to test
  *past* an interface is a signal the module is the wrong shape.
- **One adapter means a hypothetical seam; two means a real one.** A seam nothing varies across is
  indirection.

And one distinction the review leans on heavily, because it settles the central question:

> A deep module can have **internal seams** — private to its implementation, used by its own tests —
> as well as the **external seam** at its interface.

495's engine is deep at its external seam and has no internal ones. That is a different diagnosis
from "the file is too big", and it points at a different remedy.

## The two axes

From `code-review`. Findings are kept on separate axes so neither masks the other:

- **Structure** — does the code hold its shape? Module depth, seam placement, what a change costs
  to make, what the suite measures.
- **Contract** — does the code do what the repository says it does? `AGENTS.md` invariants,
  `docs/decisions/` records, `docs/architecture.md`.

A finding on one axis is not reranked against the other. Code that follows every documented
invariant and is unmaintainable fails Structure and passes Contract; both readings are worth having
separately.

The same skill supplies a **smell baseline** (Fowler, *Refactoring* ch. 3) that applies where a
repository documents nothing. Two rules bind it, both kept: **the repo overrides** — a documented
495 invariant always wins over the baseline — and **every smell is a labelled judgement call**,
never a hard violation. Three of the baseline smells earn a place in this review, by name:
Shotgun Surgery, Repeated Switches, Divergent Change.

## Severity

From `requesting-code-review`. Calibrated, not inflated: not everything is Critical.

| | |
|---|---|
| **Critical** | Wrong behaviour reaches a requester, or evidence the harness reports is not what it measured |
| **Important** | A defect with no path to a wrong verdict today, but which costs correctness or velocity as the code grows |
| **Minor** | Worth doing; nothing depends on it |

Deepening candidates carry a **recommendation strength** instead — `Strong`, `Worth exploring`,
`Speculative` — because they are proposals, not defects.

## The evidence rule

From `verification-before-completion`, which states it as an iron law:

> No completion claims without fresh verification evidence.

Applied to a review rather than to a task, it reads: **no finding without the measurement that
produced it.** Every claim in these documents names the command, the `file:line`, or the coverage
figure behind it. Where a claim is an inference rather than a measurement, it says so.

This is not borrowed decoration. It is 495's own first invariant — `docs/decisions/0001` accepts a
change only on evidence the harness measured itself — turned on the harness.

## What was left

**From mattpocock/skills.** `improve-codebase-architecture` renders its output as a self-contained
HTML file in the OS temp directory, with Tailwind and Mermaid from CDNs. Rejected: the artifact
asked for lives in the repository, the repository's medium is Markdown, and a review that vanishes
with `$TMPDIR` cannot be cited by a later commit. The card *form* is kept in
[04-deepening.md](04-deepening.md) — files, problem, solution, wins, before/after, strength badge —
with ASCII where the original uses SVG.

`domain-modeling` prescribes a root `CONTEXT.md`. The glossary in [05-language.md](05-language.md)
follows its format and rules, but its placement is left to the requester: a file at the root of 495
is a context pointer with a cost, and `AGENTS.md` is already the index.

**From obra/superpowers.** The register is not kept. Iron laws in capital letters, `<HARD-GATE>`
blocks, rationalization tables and "your human partner" belong to a skill steering an agent at
runtime, not to a document a person reads. 495's own prose — `AGENTS.md`, the ADRs — is measured and
declarative; these documents match it.

Its `test-driven-development` skill is not applied, because 495 already implements a stronger and
*measured* version of the same rule. Where the skill says "delete code written before its test",
`docs/decisions/0020` has the test designer write the tests in an intervention of its own, before
the producer, on a tree where the behaviour does not exist; the harness commits them and fails any
version of the change that modifies one. The skill asks an agent to be honest. 495 removes the
opportunity. Nothing to import.

What *is* taken from that skill is `writing-good-tests.md`, whose two principles cut directly at
what this review found: **every test names the break it catches**, and **every test exercises the
real thing**. Its mutation check — mentally mutate the production code, at least one test should
fail — is the reading behind finding F2.

`subagent-driven-development` supplies the shape of [06-plan.md](06-plan.md): tasks right-sized so
that each ends in an independently testable deliverable, and a reviewer could reject one while
approving its neighbour.

## Relation to `docs/etude-harnais-495.md`

The étude measures what the harness does, against a reference model of agent harnesses, as gaps
`E01`..`E61`. This review measures how the harness is built. They meet in exactly two places, and
this review does not re-open either:

- **`E46`** — no property or mutation testing on 495 itself — already names the libraries
  (Hypothesis, mutmut) and the targets (`scope._match`, `verification.failure_signature`,
  `decide.assess`). Findings F1 and F2 here are two specific things mutation testing would have
  caught; they are evidence for `E46`, not a second entry.
- **`E45`** — the repository not applying 495's own principles to itself — is marked resolved, and
  rightly so: `AGENTS.md`, `docs/architecture.md` and `docs/decisions/` all exist. But its
  §7.5 table carries one observation that resolving the entry did not resolve:

  > `engine.py` fait 2 475 lignes et concentre phases, décisions, calibration, fusion et intégration

  That observation has no id of its own, no priority, no effort and no remedy, and the file has
  since grown by 52,5 %. It is the subject of [04-deepening.md](04-deepening.md).

New entries are proposed, never written: assigning an `E` id is the requester's act, and
`docs/etude-harnais-495.md` is untouched by this review. [06-plan.md](06-plan.md) states which
findings would warrant one.
