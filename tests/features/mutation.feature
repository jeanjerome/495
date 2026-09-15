Feature: The verifications are measured against wrong versions of the change
  A command that reports something else without the change observes it; that does not make it
  constrain it. The harness alters one line of the diff at a time — a comparison inverted, an
  operand sign flipped, a constant moved, a call dropped, a return short-circuited — and runs
  every command that passed on the change against each wrong version. One report settles a
  mutant; a mutant none of them reported leaves the behaviour requirements resting on those
  commands undetermined until the requester rules, since the line may be one no test looks at,
  or the alteration may leave the behaviour as it was, and only a reader tells the two apart.

  # ------------------------------------------------------------------ the mutants

  Scenario Outline: A line the change adds is altered the way a mistake would alter it
    Given a diff of "<file>" that adds the line "<line>"
    When the harness plans the mutants
    Then a <operator> mutant writes "<mutated>"

    Examples:
      | file      | line              | operator   | mutated           |
      | calc.py   | if a < b:         | comparison | if a <= b:        |
      | calc.py   | if a >= b:        | comparison | if a > b:         |
      | calc.py   | if a and b:       | connector  | if a or b:        |
      | calc.py   | return a - b      | arithmetic | return a + b      |
      | calc.py   | return a - b      | return     | return None       |
      | calc.py   | retries = 3       | constant   | retries = 4       |
      | calc.py   | enabled = True    | boolean    | enabled = False   |
      | calc.py   | notify(user)      | call       | pass              |
      | app.ts    | return total;     | return     | return null;      |
      | main.go   | if a < b {        | comparison | if a <= b {       |
      | deploy.sh | retries=3         | constant   | retries=4         |

  Scenario: A line of a test file is the instrument, and altering it measures nothing
    Given a diff of "tests/test_calc.py" that adds the line "    assert add(2, 3) == 5"
    When the harness plans the mutants
    Then no mutant is planned

  Scenario: A file a test command names is the instrument too, whatever it is called
    Given the project runs its tests with "./scripts/check.sh repeat"
    And a diff of "scripts/check.sh" that adds the line "expect_exit 2"
    When the harness plans the mutants
    Then no mutant is planned

  Scenario: A source file whose name a test file's name holds is not the instrument
    Given the project runs its tests with "pytest tests/test_calc.py"
    And a diff of "calc.py" that adds the line "retries = 3"
    When the harness plans the mutants
    Then a constant mutant writes "retries = 4"

  Scenario: A file no test command names is the source the mutants are written on
    Given the project runs its tests with "./scripts/check.sh repeat"
    And a diff of "scripts/greeter.sh" that adds the line "repeat=1"
    When the harness plans the mutants
    Then a constant mutant writes "repeat=2"

  Scenario: A line of a file no operator reads is left alone
    Given a diff of "README.md" that adds the line "The default is 3 retries."
    When the harness plans the mutants
    Then no mutant is planned

  Scenario: A comment carries no behaviour to alter
    Given a diff of "calc.py" that adds the line "    # retries = 3"
    When the harness plans the mutants
    Then no mutant is planned

  Scenario: An operator with no space around it is not read as one, so a type annotation stays as it is
    Given a diff of "calc.py" that adds the line "def add(a: int, b: int) -> int:"
    When the harness plans the mutants
    Then no mutant is planned

  Scenario: A call that only reports is not dropped, since dropping it changes nothing anyone observes
    Given a diff of "calc.py" that adds the line "    logger.info(result)"
    When the harness plans the mutants
    Then no mutant is planned

  Scenario: The cap is spread over the files the change touches rather than spent on the first
    Given a diff that adds "    return a - b" to "calc.py" and "    return x * y" to "geom.py"
    When the harness plans at most 2 mutants
    Then the mutants alter "calc.py" and "geom.py"

  Scenario: No mutant is planned when none is allowed
    Given a diff of "calc.py" that adds the line "    return a - b"
    When the harness plans at most 0 mutants
    Then no mutant is planned

  # ------------------------------------------------------------------ writing one

  Scenario: A mutant replaces the line the diff showed, and nothing else
    Given the file "calc.py" holding "def f(a, b):\n    return a - b\n"
    And a mutant replacing line 2 "    return a - b" with "    return a + b"
    When the harness writes the mutant
    Then the file reads "def f(a, b):\n    return a + b\n"

  Scenario: A mutant whose line is no longer where the diff put it is not written
    Given the file "calc.py" holding "def f(a, b):\n    return a * b\n"
    And a mutant replacing line 2 "    return a - b" with "    return a + b"
    When the harness writes the mutant
    Then the file is left as it was

  # ------------------------------------------------------------------ the decision

  Scenario: A verification that reports success on a wrong version of the change credits nothing
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And a mutant no verification reported, naming R1, saying "m1 calc.py:9 (arithmetic) `return a - b` -> `return a + b`: passed by R1 (V1)"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And the reason for R1 says "on a wrong version of it: m1 calc.py:9 (arithmetic)"
    And the outcome is undetermined
    And a requirement was not credited: "R1: no command told the change from a wrong version of it"

  Scenario: A mutant a verification reported changes nothing
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And a mutant V1 reported
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  Scenario: A failing verification decides the requirement, whatever the mutants showed
    Given a behaviour requirement R1 verified by the test V1
    And V1 failed on the change
    And a mutant no verification reported, naming R1, saying "m1 calc.py:9 (arithmetic) `return a - b` -> `return a + b`: passed by R1 (V1)"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is violated
    And the outcome is reject

  # ------------------------------------------------------------------ through the engine

  Scenario: A test that constrains the line it watches reports every wrong version of it
    Given the sample project
    When a change run walks the workflow
    Then a mutant of iteration 1 was reported: "(arithmetic) `return a - b` -> `return a + b`"
    And a mutant of iteration 1 was reported: "(return) `return a - b` -> `return None`"
    And every wrong version of the change was reported
    And the requirement R1 is satisfied
    And the run ends delivered

  Scenario: A wrong version of the change every command passes leaves the requirement undetermined
    Given the sample project
    And the only test of the new behaviour checks "subtract(5, 0) == 5"
    When a change run walks the workflow
    Then a mutant of iteration 1 went unreported: "(arithmetic) `return a - b` -> `return a + b`"
    And a mutant of iteration 1 was reported: "(return) `return a - b` -> `return None`"
    And the requirement R1 is undetermined
    And the run's reason for R1 says "so did every command watching the change, on a wrong version of it"
    And the "correctness" reviewer's prompt says "Wrong versions of the change, and what the verifications reported"
    And the "test_quality" reviewer's prompt says "`return a - b` -> `return a + b`"
    And the run awaits the requester on an undetermined verdict
    When the requester accepts the risk with the note "the scenario asks for 5 - 3 and 3 - 5; the test written for it checks neither"
    Then the run ends delivered
    And the requirement R1 is undetermined
    And the report says "mutation_check"

  Scenario: A change no command reports success on is not measured against a mutant
    Given the sample project
    And the producer gets the behaviour wrong once
    When a change run walks the workflow
    Then no wrong version of the change was measured
    And a mutant of iteration 2 was reported: "(arithmetic) `return a - b` -> `return a + b`"
    And the run ends delivered

  Scenario: A file a linter names is still the source the mutants are written on
    Given the sample project
    And a lint verification that names "calc.py"
    When a change run walks the workflow
    Then a mutant of iteration 1 was reported: "(arithmetic) `return a - b` -> `return a + b`"
    And the run ends delivered

  Scenario: The requester can leave the mutation check out
    Given the sample project
    And the mutation check is allowed no mutant
    When a change run walks the workflow
    Then no wrong version of the change was measured
    And the requirement R1 is satisfied
    And the run ends delivered

  # ------------------------------------------------------------------ the check on its own

  Scenario: A command slower than a mutant run is worth is left out, and said to be
    Given a version under review whose change adds a line of source
    And a test command V1 that passed in 300s, which the requirement R1 leans on
    When the mutation check measures the version
    Then no wrong version of the change was written
    And the run warns "what it lets through is not measured"

  Scenario: A repository no throwaway worktree can be added to leaves the check unmade
    Given a version under review whose change adds a line of source
    And a test command V1 that passed in 1s, which the requirement R1 leans on
    And the project the run works on is no git repository
    When the mutation check measures the version
    Then no wrong version of the change was written
    And the run warns "cannot measure the verifications against wrong versions"

  Scenario: A mutant whose line is no longer where the diff put it is not applied
    Given a version under review whose change adds a line of source
    And a test command V1 that passed in 1s, which the requirement R1 leans on
    And a mutant naming a line the file does not carry
    When the harness runs that wrong version
    Then no command was run against it
    And the mutant reading says "the line is not where the diff put it; not applied"
    And the mutant charges no requirement

  Scenario: A command the wrong version timed out under is counted as having reported it
    Given a version under review whose change adds a line of source
    And a test command V1 that passed in 1s, which the requirement R1 leans on
    And a mutant of the line the change adds
    And V1 times out on the wrong version
    When the harness runs that wrong version
    Then the mutant reading says "V1 reported it (timed out)"
    And the mutant charges no requirement

  Scenario: A mutant run the requester stopped puts the file back as the change wrote it
    Given a version under review whose change adds a line of source
    And a test command V1 that passed in 1s, which the requirement R1 leans on
    And a mutant of the line the change adds
    And the requester asked the run to stop
    When the harness runs that wrong version
    Then the run stops rather than reading the wrong version
    And the file the mutant altered is as the change wrote it
