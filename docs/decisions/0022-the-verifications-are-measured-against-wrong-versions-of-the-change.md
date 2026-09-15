# 0022. The verifications are measured against wrong versions of the change, and one that reports success on such a version credits no requirement

- Status: accepted
- Date: 2026-09-14

## Context

0002 measures every verification a behaviour requirement leans on against one other version
of the tree: the base, carrying the change's test files. That pair answers "does this command
report something else without the change?" and nothing else. It has one mutant to work with,
the absence of the change, and 0019 already named what that misses: a test that fails on the
base because the code it calls is not there yet has been seen missing its target, never
observing its behaviour, and its assertions may be worth nothing. `satisfied` therefore means
"the command passed on the change and reported something else without it" — which is what
the README says, and less than a reader hears in the word.

The gap is the one the test-library catalogue names `mutation`: the suite's ability to detect
a deliberate alteration of the code it covers. The catalogue recommends a tool per technology
(mutmut, Stryker, cargo-mutants, gremlins, pitest) and the profile reports whether the project
measures the role, but a tool the project has not adopted measures nothing, and running a full
mutation campaign on every iteration is not something a run can afford.

## Decision

After the control runs and before the reviewers, `checks.mutation.mutate` measures the
verifications against wrong versions of the change itself, and records one `mutation_check`
evidence per version.

`core/mutation.py` is pure and writes the mutants; `core/diff.py` reads the lines they are
written on, and the coverage check of 0023 reads them the same way. `added_lines(diff)` reads
the lines the change adds with the number they have in the version under review, counting hunk
lines so that a line of content is never read as a header. `code_lines(diff, commands)` keeps
the lines that are in a source file of a technology the catalogue covers, that are not
comments, and that are not the instrument — a file `looks_like_a_test` recognises, or one a
`test` verification's command names whole (`names_the_file`), which is how a project whose
tests are a script the commands run (`./scripts/check.sh repeat`) is read, and which leaves
`calc.py` a source file when the command runs `tests/test_calc.py`; a linter's or a build's
command is not read this way, since it names the source a mutant is written on.
`plan_mutants(diff, limit, commands)` offers each remaining line to seven textual operators: a comparison inverted (`<` for `<=`, `==` for `!=`), an
`and` turned into an `or`, an operand sign flipped (`+` for `-`, `*` for `/`), a boolean
literal flipped, a numeric constant moved by one, a statement whose whole effect is one call
dropped, a `return` short-circuited to the language's neutral value. The cap is spread over
the files the change touches — one mutant per changed line, the files taken in turn, then a
second per line — rather than spent on the first lines it meets. `mutated_source(text, m)`
writes one mutant, and writes nothing when the line is no longer the one the diff showed.

The engine runs them in a detached worktree of the evaluated commit. The commands run against
a mutant are every verification of the specification that reported success on the change and
that the calibration did not find blind — whatever requirement it carries and whatever kind it
is — ordered by what each took on the change, the cheapest first; one slower than
`budget.mutant_command_max_s` is left out with a warning, since the check costs one run per
mutant. The first command that fails settles the mutant: one report is enough to say the
evidence tells the change from this wrong version of it. A mutant no command reported is
charged to every `behaviour` requirement resting on one of those commands, which is what the
evidence's `requirement_ids` hold; `passed` says whether a command reported it.
`budget.max_mutants` (default 5) caps the campaign, and 0 leaves it out.

`decide.assess` reads a mutant no command reported as it reads a weakened suite (0021): the
commands passed on the change and pass they did, but they also passed on a version of the
change that is wrong in a stated way, so they do not demonstrate the requirement. It is
`undetermined`, with the passing commands and the mutant as its reason, listed under
`uncredited`; a failing verification or an evidenced finding still makes the requirement
`violated`, as for any requirement. The reviewers receive the fact "Wrong versions of the
change, and what the verifications reported"; `correctness` is asked whether the alteration
changes the behaviour the requirement states, and `test_quality` to name the verification and
quote the assertion that should have caught it.

## Consequences

- `satisfied` now also means: the commands named reported the wrong versions of the change
  that the harness wrote. It still does not mean the code is right, and a killed mutant is a
  statement about one line, not about the change.
- A surviving mutant never becomes a correction request. A mutant may be equivalent to the
  line it replaces — a constant no behaviour depends on, a branch reached by no input the
  requirement names — and no test can kill it; only a reader tells an equivalent mutant from
  a hole in the tests. Sending it to the producer as a defect was rejected for that reason:
  it would send it to write a test for a behaviour nobody asked for. The requester rules at
  the undetermined gate, with the reviewers' account in front of them.
- The operators are textual and read one line at a time: they fire only where an operator is
  surrounded by whitespace, which leaves `a<b` and generic brackets alone, and they know
  nothing of the grammar, so a mutant may not compile. A mutant that does not compile is
  reported by every command and reads as killed — the wasted run is the cost, and the
  conclusion stays true. Parsing each language instead was rejected: a parser per technology
  is the tool the catalogue already names, and the point of this check is to hold where the
  project has adopted none.
- A call whose name reads as reporting (log, print, echo, console) is not dropped: removing
  one changes nothing anyone observes and would produce a survivor per logging line.
- Running only the commands of the requirement whose line was altered was rejected, although
  it is what a per-requirement reading would do: the harness does not know which requirement
  a line serves, and a specification that divides one file between two requirements would
  then report a mutant of R1's line that R2's test reports as a survivor of R1. What a mutant
  asks is whether the evidence the run rests on, taken together, tells the change from a
  wrong version of it; the price is that a weak test whose gap another command covers is not
  reported, which is the same direction 0002 takes when a comparison cannot be made cleanly.
- Cost: at most `max_mutants` × (commands that passed) command runs per iteration, each
  bounded by twice `mutant_command_max_s`, and fewer in practice since the first report ends
  the mutant and the cheapest command runs first. Nothing is run when no command passed on
  the change, or when no `behaviour` requirement rests on one. The check is skipped entirely
  when the calibration found an instrument at fault, since the run stops on that and what a
  blind command lets through describes the command.
- A project that measures the `mutation` role with its own tool declares it as a verification
  naming that `CatalogueRole` (0014), and the tool enters through a proposal. This check does
  not replace it: it reads the diff, not the code base, and a few mutants, not all of them.

## Where in the code

- `harness495/core/mutation.py`: `candidates`, `Mutant`, `plan_mutants`, `mutated_source`, the
  operator tables; the reading of the diff they work from is `core/diff.py` (`AddedLine`,
  `added_lines`, `names_the_file`, `code_lines`), shared with the coverage check (0023).
- `harness495/core/models/evidence.py::EvidenceKind.mutation_check`;
  `harness495/core/models/config.py`: `Budget.max_mutants`, `Budget.mutant_command_max_s`.
- `harness495/core/engine/checks/mutation.py`: `mutation_watchers`, `mutate`, `run_mutant`.
- `harness495/core/engine/checks/sequence.py`: the `mutation` stage of `SEQUENCE` and the gate
  `instrument_is_readable` it waits on.
- `harness495/core/engine/engine.py::_review`: the fact given to the reviewers.
- `harness495/core/decide.py::assess` (`let_through`).
- `harness495/core/context.py::render_mutation_reading`.
- `harness495/core/prompts.py`: the sentences of `PERSPECTIVES["correctness"]` and
  `PERSPECTIVES["test_quality"]`.
- `harness495/interfaces/tui/reading.py::mutation_checks`, `views/checks.py`.
- `tests/features/mutation.feature` with `tests/test_mutation_scenarios.py`.
