Feature: The lines the change adds are crossed with what the verifications execute
  A command that reports something else without the change observes it; a command that reports
  a wrong version of one of its lines constrains that line. Neither says anything about a line
  no command ever runs, since a command that never executes a line reports the same thing
  whatever that line says. The project's own coverage tool answers that, so the harness runs
  the test commands once more under it and crosses the report with the diff. A line the report
  holds with no hit on it is a line the evidence rests on without ever running, and it leaves
  the behaviour requirements resting on those commands undetermined until the requester rules:
  the line may carry behaviour no requirement states, and only a reader tells that from a hole
  in the tests.

  # ------------------------------------------------------------------ the reports

  Scenario Outline: The report each engine writes says which lines of a file ran
    Given a "<format>" report '<text>'
    When the harness reads the report
    Then it says line <ran> of "<file>" ran and line <missed> did not

    Examples:
      | format        | text                                                                                  | file        | ran | missed |
      | lcov          | SF:/work/src/calc.ts\nDA:4,2\nDA:7,0\nend_of_record                                    | /work/src/calc.ts | 4 | 7 |
      | coverage.json | {"files": {"calc.py": {"executed_lines": [4], "missing_lines": [7]}}}                  | calc.py     | 4   | 7      |
      | go profile    | mode: set\nexample.com/m/calc.go:4.20,5.3 1 3\nexample.com/m/calc.go:7.2,7.10 1 0       | example.com/m/calc.go | 4 | 7 |

  Scenario: Cobertura names the file on the class and counts a line with its hits
    Given a "xml" report '<coverage><packages><package><classes><class filename="scripts/greet.sh"><lines><line number="4" hits="2"/><line number="7" hits="0"/></lines></class></classes></package></packages></coverage>'
    When the harness reads the report
    Then it says line 4 of "scripts/greet.sh" ran and line 7 did not

  Scenario: JaCoCo names a package and a source file and counts the instructions covered
    Given a "xml" report '<report><package name="com/example"><sourcefile name="Math.java"><line nr="4" mi="0" ci="12"/><line nr="7" mi="3" ci="0"/></sourcefile></package></report>'
    When the harness reads the report
    Then it says line 4 of "com/example/Math.java" ran and line 7 did not

  Scenario: A report in no format the harness reads says nothing rather than something wrong
    Given a "lcov" report 'not a coverage report at all'
    When the harness reads the report
    Then the report holds no line

  # ------------------------------------------------------------------ the crossing

  Scenario: A line the report holds with no hit is a line no verification executed
    Given a diff of "calc.py" that adds a line at line 2
    And a report where line 2 of "calc.py" ran 0 time(s)
    When the harness crosses the change with the report
    Then line 2 of "calc.py" was executed by no verification

  Scenario: A line the report holds with a hit is a line the verifications executed
    Given a diff of "calc.py" that adds a line at line 2
    And a report where line 2 of "calc.py" ran 3 time(s)
    When the harness crosses the change with the report
    Then every line the change adds was executed

  Scenario: A line the report holds no statement on is neither executed nor missed
    Given a diff of "calc.py" that adds a line at line 2
    And a report where line 5 of "calc.py" ran 1 time(s)
    When the harness crosses the change with the report
    Then every line the change adds was executed
    And no file is named as one the tool did not instrument

  Scenario: A file the tool did not instrument is named as such and charges nothing
    Given a diff of "calc.py" that adds a line at line 2
    And a report where line 2 of "other.py" ran 0 time(s)
    When the harness crosses the change with the report
    Then every line the change adds was executed
    And "calc.py" is named as a file the tool did not instrument

  Scenario: A report naming the file otherwise than the diff does names the same file
    Given a diff of "calc.py" that adds a line at line 2
    And a report where line 2 of "/tmp/worktree/calc.py" ran 0 time(s)
    When the harness crosses the change with the report
    Then line 2 of "calc.py" was executed by no verification

  Scenario: A test file is the instrument, and what it executes of itself measures nothing
    Given a diff of "tests/test_calc.py" that adds a line at line 2
    And a report where line 2 of "tests/test_calc.py" ran 0 time(s)
    When the harness crosses the change with the report
    Then every line the change adds was executed

  # ------------------------------------------------------------------ the command

  Scenario Outline: The project's own test command is rewritten to write a report
    Given a project measuring the coverage role of "<technology>" with "<tool>"
    And a test command "<command>"
    When the harness instruments the command
    Then the instrumented command holds "<holds>"

    Examples:
      | technology            | tool                | command                                         | holds                                        |
      | python                | coverage.py         | .venv/bin/python -m pytest -q                    | -m coverage run --source=. -m pytest         |
      | python                | coverage.py         | .venv/bin/pytest tests/                          | .venv/bin/coverage run --source=. -m pytest  |
      | javascript/typescript | @vitest/coverage-v8 | ./scripts/with-deps.sh node_modules/.bin/vitest run | --coverage.reportsDirectory=.495-coverage |
      | go                    | go test -cover      | go test ./...                                    | -coverprofile=.495-coverage/cover.out        |
      | rust                  | cargo-llvm-cov      | cargo test --all-features                        | cargo llvm-cov --lcov --output-path          |
      | java/kotlin           | jacoco              | ./mvnw -q -B test                                | org.jacoco:jacoco-maven-plugin:report        |
      | shell                 | kcov                | shellspec                                        | shellspec --kcov                             |

  Scenario: A command the harness cannot rewrite is left as the project wrote it
    Given a project measuring the coverage role of "javascript/typescript" with "@vitest/coverage-v8"
    And a test command "npm run test"
    When the harness instruments the command
    Then no instrumented command is derived

  Scenario: A project whose coverage role nothing measures is not instrumented
    Given a project measuring the coverage role of "python" with nothing
    And a test command ".venv/bin/python -m pytest -q"
    When the harness instruments the command
    Then no instrumented command is derived

  # ------------------------------------------------------------------ the decision

  Scenario: A verification that never executed a line of the change credits nothing
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And a line no verification executed, naming R1, saying "1 of the 4 line(s) the change adds were executed by no verification (V1 under coverage.py): calc.py:12 `raise ValueError(msg)`"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And the reason for R1 says "did not run every line the change adds: 1 of the 4 line(s)"
    And the outcome is undetermined
    And a requirement was not credited: "R1: no verification executed every line the change adds"

  Scenario: A coverage check that executed every line changes nothing
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And a coverage check V1 passed
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  Scenario: A failing verification decides the requirement, whatever the coverage showed
    Given a behaviour requirement R1 verified by the test V1
    And V1 failed on the change
    And a line no verification executed, naming R1, saying "1 of the 4 line(s) the change adds were executed by no verification (V1 under coverage.py): calc.py:12 `raise ValueError(msg)`"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is violated
    And the outcome is reject

  # ------------------------------------------------------------------ through the engine

  Scenario: A change whose every line the tests run is measured as such
    Given the sample project measuring its coverage
    When a change run walks the workflow
    Then the coverage check of iteration 1 passed
    And the coverage check of iteration 1 says "executed the"
    And the requirement R1 is satisfied
    And the run ends delivered

  Scenario: A line of the change no test reaches leaves the requirement undetermined
    Given the sample project measuring its coverage
    And the change carries a guard no test reaches
    When a change run walks the workflow
    Then the coverage check of iteration 1 failed
    And the coverage check of iteration 1 says "raise ValueError"
    And the requirement R1 is undetermined
    And the run's reason for R1 says "did not run every line the change adds"
    And the "correctness" reviewer's prompt says "Lines of the change no verification executed"
    And the "test_quality" reviewer's prompt says "raise ValueError"
    And the run awaits the requester on an undetermined verdict
    When the requester accepts the risk with the note "the guard is asked for by the convention, and no requirement states it"
    Then the run ends delivered
    And the requirement R1 is undetermined
    And the report says "coverage_check"

  Scenario: A project that measures no coverage role is not instrumented
    Given the sample project
    When a change run walks the workflow
    Then no coverage was measured
    And the requirement R1 is satisfied
    And the run ends delivered

  Scenario: The requester can leave the coverage check out
    Given the sample project measuring its coverage
    And the coverage check is allowed no command
    When a change run walks the workflow
    Then no coverage was measured
    And the requirement R1 is satisfied
    And the run ends delivered
