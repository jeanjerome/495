Feature: The existing test suite is measured on the change
  A command that passes on the change credits a non-regression requirement only if the tests
  it ran are the tests that passed on the base. The harness reads the diff over the test files
  that existed on the base and the tally each runner prints on both versions; a test file
  deleted, a test removed or skipped, or a smaller tally, is a failed suite check that leaves
  the non-regression requirements undetermined until the requester rules, and every existing
  test the change touched is listed to the reviewers.

  # ------------------------------------------------------------------ the diff

  Scenario: A test removed from an existing test file weakens the suite
    Given a diff of "tests/test_calc.py" that removes the line "def test_add():"
    When the harness reads the suite
    Then the suite is weakened
    And the reading says "tests/test_calc.py: test(s) removed: test_add"

  Scenario: A skip marker added to an existing test file weakens the suite
    Given a diff of "tests/test_calc.py" that adds the line "@pytest.mark.skip(reason='later')"
    When the harness reads the suite
    Then the suite is weakened
    And the reading says "tests/test_calc.py: skip(s) added: @pytest.mark.skip(reason='later')"

  Scenario: A test whose definition line is edited under the same name is a modification
    Given a diff of "tests/test_calc.py" that replaces the line "def test_add():" with "def test_add():  # noqa"
    When the harness reads the suite
    Then the suite is not weakened
    And the reading says "tests/test_calc.py: modified (1 hunk(s))"

  Scenario: A test whose name changes is read as removed, since the test that passed on the base no longer runs
    Given a diff of "tests/test_calc.py" that replaces the line "def test_add():" with "def test_addition():"
    When the harness reads the suite
    Then the suite is weakened
    And the reading says "tests/test_calc.py: test(s) removed: test_add; 1 test(s) added"

  Scenario: A test added to an existing test file is listed and does not weaken the suite
    Given a diff of "tests/test_calc.py" that adds the line "def test_subtract():"
    When the harness reads the suite
    Then the suite is not weakened
    And the reading says "tests/test_calc.py: 1 test(s) added"

  Scenario: A new test file is the change's own instrument, not an existing test
    Given a diff that creates "tests/test_subtract.py" with the line "def test_subtract():"
    When the harness reads the suite
    Then the suite is not weakened
    And no existing test file is listed

  Scenario: A deleted test file weakens the suite
    Given a diff that deletes "tests/test_calc.py"
    When the harness reads the suite
    Then the suite is weakened
    And the reading says "tests/test_calc.py: deleted"

  Scenario: A test file renamed to a name the runner does not collect weakens the suite
    Given a diff that renames "tests/test_calc.py" to "docs/calc_checks.txt"
    When the harness reads the suite
    Then the suite is weakened
    And the reading says "tests/test_calc.py: renamed to docs/calc_checks.txt, which the runner does not collect"

  Scenario: A file that is not a test is not read
    Given a diff of "calc.py" that removes the line "def test_helper():"
    When the harness reads the suite
    Then the suite is not weakened
    And no existing test file is listed

  Scenario Outline: Test definitions and skips are read in the languages the catalogue covers
    Given a diff of "<file>" that removes the line "<removed>" and adds the line "<added>"
    When the harness reads the suite
    Then the reading says "<file>: <expected>"

    Examples:
      | file                     | removed                          | added                                   | expected                                                 |
      | src/calc_test.go         | func TestAdd(t *testing.T) {     | t.Skip("flaky")                         | test(s) removed: TestAdd; skip(s) added: t.Skip("flaky") |
      | src/calc.test.ts         | it('adds', () => {               | it.skip('subtracts', () => {            | test(s) removed: adds; skip(s) added: it.skip('subtracts', () => { |
      | src/lib_test.rs          | #[test]                          | #[ignore]                               | test(s) removed: 1 unnamed; skip(s) added: #[ignore]     |
      | src/test/CalcTest.java   | @Test                            | @Disabled("later")                      | test(s) removed: 1 unnamed; skip(s) added: @Disabled("later") |
      | spec/calc_spec.sh        | It 'adds two numbers'            | Skip 'not now'                          | test(s) removed: adds two numbers; skip(s) added: Skip 'not now' |
      | features/calc.feature    | Scenario: adding two numbers     | @wip                                    | test(s) removed: adding two numbers; skip(s) added: @wip |

  # ------------------------------------------------------------------ the tally

  Scenario Outline: The tally a runner prints is read as tests that ran and tests set aside
    When the harness counts the tests in "<output>"
    Then the tally is <ran> ran and <skipped> skipped by "<runner>"

    Examples:
      | output                                                              | ran | skipped | runner         |
      | 3 passed, 1 skipped, 1 xfailed in 0.04s                             | 3   | 2       | pytest         |
      | ====== 2 failed, 5 passed, 1 deselected in 0.10s ======              | 7   | 1       | pytest         |
      | Ran 4 tests in 0.002s\n\nOK (skipped=1)                             | 3   | 1       | unittest       |
      | Tests:       1 skipped, 6 passed, 7 total                           | 6   | 1       | jest           |
      | \n  5 passing (20ms)\n  1 pending\n                                 | 5   | 1       | mocha          |
      | --- PASS: TestAdd (0.00s)\n--- SKIP: TestSub (0.00s)\n--- FAIL: TestMul (0.00s) | 2 | 1 | go test    |
      | test result: ok. 4 passed; 0 failed; 1 ignored; 0 measured          | 4   | 1       | cargo test     |
      | Finished in 0.5 seconds\n8 examples, 0 failures, 2 skipped          | 6   | 2       | shellspec/rspec |
      | Tests run: 12, Failures: 0, Errors: 1, Skipped: 2                   | 10  | 2       | junit          |
      | 3 scenarios passed, 1 failed, 2 skipped                             | 4   | 2       | behave         |
      | 5 scenarios (1 skipped, 4 passed)                                   | 4   | 1       | cucumber       |

  Scenario: An output with no tally is read as none
    When the harness counts the tests in "ok  \texample.com/calc\t0.012s"
    Then no tally is read

  Scenario: A tally that shrank between the base and the change weakens the suite
    Given the base printed "4 passed in 0.03s" and the change printed "3 passed in 0.02s"
    When the harness compares the tallies for V2
    Then the comparison is weakened
    And the comparison says "V2 (pytest): 4 ran and 0 skipped on the base, 3 ran and 0 skipped on the change"

  Scenario: A tally with more tests set aside weakens the suite
    Given the base printed "4 passed in 0.03s" and the change printed "4 passed, 1 skipped in 0.02s"
    When the harness compares the tallies for V2
    Then the comparison is weakened

  Scenario: A tally that grew does not weaken the suite
    Given the base printed "4 passed in 0.03s" and the change printed "5 passed in 0.02s"
    When the harness compares the tallies for V2
    Then the comparison is not weakened

  # ------------------------------------------------------------------ the decision

  Scenario: A passing command on a weaker suite does not credit the non-regression requirement
    Given a non-regression requirement R2 verified by the test V2
    And V2 passed on the change
    And a failed suite check naming R2 saying "the suite is weaker than on the base: tests/test_calc.py: test(s) removed: test_add"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R2 is undetermined
    And the reason for R2 says "on a suite weaker than the base's: the suite is weaker than on the base: tests/test_calc.py: test(s) removed: test_add"
    And the outcome is undetermined
    And a requirement was not credited: "R2: V2 ran a suite weaker than the base's"

  Scenario: A reviewer finding that cites the removed test violates the requirement
    Given a non-regression requirement R2 verified by the test V2
    And V2 passed on the change
    And a failed suite check naming R2 saying "the suite is weaker than on the base: tests/test_calc.py: test(s) removed: test_add"
    And a reviewer rejected the change with a major finding on R2 citing "tests/test_calc.py hunk @@ -3,4 +3,0 @@ removes test_add"
    When the harness assesses the change
    Then the requirement R2 is violated
    And the outcome is reject

  Scenario: A weaker suite that no requirement names still blocks acceptance
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And a failed suite check naming no requirement saying "the suite is weaker than on the base: tests/test_calc.py: deleted"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is undetermined
    And an undetermined reason says "suite check: the suite is weaker than on the base: tests/test_calc.py: deleted"

  Scenario: A passed suite check changes nothing
    Given a non-regression requirement R2 verified by the test V2
    And V2 passed on the change
    And a passed suite check naming R2
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R2 is satisfied
    And the outcome is accept

  # ------------------------------------------------------------------ through the engine

  Scenario: A change that adds a test to an existing file passes the suite check
    Given the sample project
    When a change run walks the workflow
    Then the suite check of iteration 1 passed saying "1 existing test file(s) modified, none deleted, no test removed or skipped; V2 ran 3 test(s) on the change for 1 on the base"
    And the "spec_compliance" reviewer's prompt says "## Existing tests modified by the change"
    And the "spec_compliance" reviewer's prompt says "tests/test_calc.py: 1 test(s) added"
    And the "spec_compliance" reviewer's prompt says "V2 (pytest): 1 ran and 0 skipped on the base, 3 ran and 0 skipped on the change"
    And the run ends delivered

  Scenario: A producer that removes an existing test leaves non-regression undetermined until the requester rules
    Given the sample project
    And the producer implements the behaviour and removes the existing test "test_add"
    When a change run walks the workflow
    Then the suite check of iteration 1 failed saying "tests/test_calc.py: test(s) removed: test_add"
    And the requirement R2 is undetermined
    And the run's reason for R2 says "on a suite weaker than the base's"
    And the requirement R1 is satisfied
    And the run awaits the requester on an undetermined verdict
    And the "spec_compliance" reviewer's prompt says "tests/test_calc.py: test(s) removed: test_add"
    And the "spec_compliance" reviewer's prompt says "account for each line"
    And the producer's prompt says "Do not remove or skip an existing test"
    When the requester accepts the risk with the note "test_add is obsolete, R1 replaces add"
    Then the run ends delivered
    And the requirement R2 is undetermined
    And the report says "suite_check"

  Scenario: A producer that skips an existing test is seen by the diff and by the tally
    Given the sample project
    And the producer implements the behaviour and skips the existing test "test_add"
    When a change run walks the workflow
    Then the suite check of iteration 1 failed saying "skip(s) added: @pytest.mark.skip"
    And the suite check of iteration 1 failed saying "V2 (pytest): 1 ran and 0 skipped on the base, 1 ran and 1 skipped on the change"
    And the requirement R2 is undetermined
    And the run awaits the requester on an undetermined verdict

  Scenario: A producer that edits an existing assertion is listed to the reviewers and passes the suite check
    Given the sample project
    And the producer implements the behaviour and edits the assertion of the existing test "test_add"
    When a change run walks the workflow
    Then the suite check of iteration 1 passed saying "1 existing test file(s) modified, none deleted, no test removed or skipped"
    And the "spec_compliance" reviewer's prompt says "tests/test_calc.py: modified (1 hunk(s))"
    And the "test_quality" reviewer's prompt says "tests/test_calc.py: modified (1 hunk(s))"
    And the run ends delivered
