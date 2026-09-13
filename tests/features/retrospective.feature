Feature: A retrospective states what a run showed about each tool, for the catalogue
  A run measures the tools of a host project each time a verification naming a catalogue
  role runs on the change and on the base version. The retrospective reads those
  measurements back from the run document and says, per technology, role and tool, whether
  the tool proved itself, posed a problem, or showed nothing, with each measurement in words
  and the Markdown row the catalogue takes with the run as its source. The catalogue is
  written by hand from those rows, never by a command.

  Scenario: A tool whose report differs with and without the change is proven
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "property" with the command "pytest tests/test_props.py"
    And in iteration 1 "V1" passed on the change and failed on the base version
    When the harness writes the retrospective
    Then the observation on "property" of "python" names the tools "hypothesis"
    And that observation is "proven"
    And that observation counts 1 verdict, 0 contradictions and 0 faults
    And that observation reads "V1, iteration 1: passes with the change and fails without it"
    And that observation's row is a recommended entry citing the run

  Scenario: A tool that contradicted the agent is proven, and the contradiction is counted
    Given a run on a Python project measuring "static" with "ruff"
    And the verification "V1" of the run measures the role "static" with the command "ruff check ."
    And in iteration 1 "V1" failed on the change and passed on the base version
    And in iteration 2 "V1" passed on the change and passed on the base version
    When the harness writes the retrospective
    Then that observation is "proven"
    And that observation counts 0 verdicts, 1 contradiction and 0 faults
    And that observation reads "V1, iteration 1: fails with the change and passes without it, contradicting the agent"
    And that observation's row says "measured the role in 2 run(s) of 1 verification(s), contradicted the agent 1 time(s)"

  Scenario: A tool that fails identically with and without the change is faulty, with a row for the Rejected table
    Given a run on a Python project measuring "mutation" with "mutmut"
    And the verification "V1" of the run measures the role "mutation" with the command "mutmut run"
    And in iteration 1 "V1" failed on the change and on the base version, and the harness recorded the fault
    When the harness writes the retrospective
    Then that observation is "faulty"
    And that observation counts 0 verdicts, 0 contradictions and 1 fault
    And that observation reads "V1, iteration 1: fails identically with and without the change (exit 2)"
    And that observation's row is a rejected row citing the run
    And that observation's row says "| Python | mutation | mutmut | V1, iteration 1: fails identically with and without the change (exit 2) |"

  Scenario: A tool that timed out is faulty
    Given a run on a Python project measuring "fuzzing" with "atheris"
    And the verification "V1" of the run measures the role "fuzzing" with the command "python fuzz.py"
    And in iteration 1 "V1" timed out on the change
    When the harness writes the retrospective
    Then that observation is "faulty"
    And that observation reads "V1, iteration 1: timed out"

  Scenario: A tool whose command the requester replaced is faulty, and the replacement is stated
    Given a run on a Python project measuring "mutation" with "mutmut"
    And the verification "V1" of the run measures the role "mutation" with the command "mutmut run"
    And in iteration 1 "V1" failed on the change and on the base version, and the harness recorded the fault
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    When the harness writes the retrospective
    Then that observation is "faulty"
    And that observation reads "V1, iteration 1: failed on both versions and the requester replaced its command (`mutmut run` by `mutmut run --paths-to-mutate src`)"

  Scenario: A tool that reports the same success on both versions shows nothing
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "property" with the command "pytest tests/test_props.py"
    And in iteration 1 "V1" passed on the change and passed on the base version
    When the harness writes the retrospective
    Then that observation is "inconclusive"
    And that observation reads "V1, iteration 1: passes with and without the change, showing nothing about the tool"
    And that observation brings no row

  Scenario: A passing report with nothing to read it against shows nothing
    Given a run on a Python project measuring "types" with "mypy"
    And the verification "V1" of the run measures the role "types" with the command "mypy src"
    And in iteration 1 "V1" passed on the change and was not run on the base version
    When the harness writes the retrospective
    Then that observation is "inconclusive"
    And that observation reads "V1, iteration 1: passes with the change; not measured on the base version"

  Scenario: A passing report read against the run before any change is a verdict
    Given a run on a Python project measuring "types" with "mypy"
    And the verification "V1" of the run measures the role "types" with the command "mypy src"
    And the command of "V1" passed on the base version before any change
    And in iteration 1 "V1" passed on the change and was not run on the base version
    When the harness writes the retrospective
    Then that observation is "proven"
    And that observation reads "V1, iteration 1: passes with the change, as on the base version before it"

  Scenario: A tool that failed before any change and fails on the change is faulty
    Given a run on a Python project measuring "types" with "mypy"
    And the verification "V1" of the run measures the role "types" with the command "mypy src"
    And the command of "V1" failed on the base version before any change
    And in iteration 1 "V1" failed on the change and was not run on the base version
    When the harness writes the retrospective
    Then that observation is "faulty"
    And that observation reads "V1, iteration 1: fails with the change as it did on the base version before any change (exit 1)"

  Scenario: A tool the catalogue already recommends gets a further source, not a new entry
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "property" with the command "pytest tests/test_props.py"
    And in iteration 1 "V1" passed on the change and failed on the base version
    When the harness writes the retrospective
    Then that observation is a further source for an entry the catalogue recommends

  Scenario: A tool the catalogue does not recommend yields an entry to admit
    Given a run on a Python project measuring "security" with "bandit"
    And the verification "V1" of the run measures the role "security" with the command "bandit -r src"
    And in iteration 1 "V1" failed on the change and passed on the base version
    When the harness writes the retrospective
    Then that observation is "proven"
    And that observation is an entry the catalogue does not have

  Scenario: A verification without a role brings nothing to the catalogue
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V2" of the run has no role and the command "pytest"
    And in iteration 1 "V2" passed on the change and failed on the base version
    When the harness writes the retrospective
    Then the retrospective makes no observation

  Scenario: A verification of a role nothing measures brings nothing to the catalogue
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "mutation" with the command "mutmut run"
    And in iteration 1 "V1" failed on the change and on the base version, and the harness recorded the fault
    When the harness writes the retrospective
    Then the retrospective makes no observation

  Scenario: The retrospective reads the same each time it is written
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "property" with the command "pytest tests/test_props.py"
    And in iteration 1 "V1" passed on the change and failed on the base version
    When the harness writes the retrospective
    And the harness writes the retrospective again
    Then both retrospectives make the same observations

  Scenario: The retro command saves the retrospective under the run and shows the rows
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "property" with the command "pytest tests/test_props.py"
    And in iteration 1 "V1" passed on the change and failed on the base version
    And the run is saved in the project's store
    When the requester runs "495 retro run-retro"
    Then the retrospective of the run is saved under it
    And the output shows "rows for docs/test-libraries.md, source: retrospective"
    And the output shows "a further source for the entry the python table already recommends"
    And the output shows "| property | hypothesis | recommended | retrospective"

  Scenario: The retro command says so when the run showed nothing about the tools
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V2" of the run has no role and the command "pytest"
    And in iteration 1 "V2" passed on the change and failed on the base version
    And the run is saved in the project's store
    When the requester runs "495 retro run-retro"
    Then the output shows "no verification naming a catalogue role was measured"

  Scenario: The retrospective in JSON carries each observation with its row
    Given a run on a Python project measuring "property" with "hypothesis"
    And the verification "V1" of the run measures the role "property" with the command "pytest tests/test_props.py"
    And in iteration 1 "V1" passed on the change and failed on the base version
    And the run is saved in the project's store
    When the requester runs "495 --json retro run-retro"
    Then the JSON output lists an observation on "property" of "python" with the verdict "proven"

  Scenario: The schema of the retrospective document is published
    Given a run on a Python project measuring "property" with "hypothesis"
    When the requester runs "495 schema retrospective"
    Then the output shows "ToolObservation"
