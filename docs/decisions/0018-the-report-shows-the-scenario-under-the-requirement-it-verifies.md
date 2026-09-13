# 0018. The report shows, under each requirement, the scenario that verifies it and what its command reported

- Status: accepted
- Date: 2026-09-13

## Context

A test to create is stated as a scenario the requester approves (0016), written by the producer
in the form the project's scenario runner dictates (0017), and compared by the `test_quality`
reviewer against the requirement and the test. The report of a run, the Markdown restitution
`495 report` renders and `deliver` writes under `artifacts/`, listed the requirements in one
table and the verifications in another: a status per requirement, a description per
verification, and no trace of the steps the requester approved. To check that the behaviour
observed is the behaviour asked for, the reader opened the specification for the steps and the
evidence for the result, and put the two together by verification id.

## Decision

Under the requirements table, the report carries one section per requirement that leans on at
least one verification stated as a scenario. The section is headed by the requirement's id,
status and statement. Under it, each such verification is one line, id, kind, role and whether
it was to create, followed by what the verification reported, then the scenario as a fenced
Gherkin block: `Scenario:` with the verification's description as its title, then the steps as
`BehaviourScenario.lines()` gives them.

What the verification reported is read as the decision reads it (0001): the last
`command_result` of the current iteration for that verification, so `PASS` or `FAIL` with the
command's summary and the evidence id, `not run on the evaluated commit` when there is none. A
control run on the base version and a baseline run carry the same verification id and are
left out. A verification the harness found to report the same with and without the change
(`broken`, `vacuous`) is stated as such with its rationale, whatever its command result on the
evaluated commit, since that result is neither proof nor defect (0002).

A requirement none of whose verifications carries a scenario has no section: its row in the
table says all the run knows about it, and a run whose verifications are all existing suites
gets no empty headings.

## Consequences

- The reader checks the requirement against the scenario and the scenario against what its
  command reported in one place, in the words the requester approved. The report says what
  the decision saw, not more: a scenario shown as `PASS` is one the decision could credit, and
  a scenario shown as reporting the same either way is one it could not.
- The observation line is a restatement of the evidence, not a second judgement. Its rule
  (current iteration, `command_result`, last one) is the rule of `decide.assess`; a change to
  one is a change to the other.
- A requirement with a scenario reads as a section; one without reads as a row. Giving every
  requirement a section, with a sentence saying no scenario was stated, was rejected: it
  repeats the table and buries the scenarios among headings that say nothing.
- The JSON form of the report (`--format json`) is the run document and is unchanged: the
  scenario is already on the verification.
- Cost: a report grows by one section per requirement with a scenario, each a few lines and
  one fenced block.

## Where in the code

- `harness495/core/report.py::_scenario_sections`, `_observed`, called from `render_markdown`
  after the requirements table.
- `tests/features/report.feature` with `tests/test_report_scenarios.py`.
