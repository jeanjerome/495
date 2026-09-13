Feature: The nature of a failure without the change is read before a test is believed
  A verification that passes on the change and fails without it observes the change. When
  what it reports without the change is an execution error (an import that fails, a name that
  does not exist) rather than an assertion, the test was seen missing its target, not
  observing the behaviour: it is unconfirmed. It still credits its requirement, the report
  and the reviewers say so, and the test_quality reviewer is called whenever a test is to be
  created, whether or not it is configured.

  Scenario: A test that fails without the change by an import error is unconfirmed
    Given a verification V1 that passed on the change
    And without the change it exited 1 printing
      """
      tests/test_calc.py:1: in <module>
          from calc import subtract
      E   ImportError: cannot import name 'subtract' from 'calc'
      """
    When the pair of runs is read
    Then the verification V1 discriminates
    And the verification V1 is unconfirmed
    And the rationale says "by an execution error, not by an assertion"
    And the rationale says "ImportError: cannot import name 'subtract'"

  Scenario: A test that fails without the change by an assertion is sufficient
    Given a verification V1 that passed on the change
    And without the change it exited 1 printing
      """
      def test_subtract():
      >       assert subtract(5, 3) == 2
      E       assert 8 == 2
      FAILED tests/test_calc.py::test_subtract - assert 8 == 2
      """
    When the pair of runs is read
    Then the verification V1 discriminates
    And the verification V1 is sufficient

  Scenario: A missing module in a Node runner is an execution error
    Given a verification V1 that passed on the change
    And without the change it exited 1 printing
      """
      FAIL src/calc.test.js
        ● Test suite failed to run
          Cannot find module './subtract' from 'src/calc.test.js'
      """
    When the pair of runs is read
    Then the verification V1 is unconfirmed
    And the rationale says "Cannot find module './subtract'"

  Scenario: An undefined symbol in a Go build is an execution error
    Given a verification V1 that passed on the change
    And without the change it exited 2 printing
      """
      # calc [calc.test]
      ./calc_test.go:8:9: undefined: Subtract
      FAIL	calc [build failed]
      """
    When the pair of runs is read
    Then the verification V1 is unconfirmed

  Scenario: A test that fails without the change for no recognised reason is believed
    Given a verification V1 that passed on the change
    And without the change it exited 1 printing
      """
      something went wrong
      """
    When the pair of runs is read
    Then the verification V1 discriminates
    And the verification V1 is sufficient

  Scenario: An unconfirmed verification still credits its requirement, and the reason says so
    Given a requirement R1 verified by the test V1
    And V1 is unconfirmed because "fails without the change by an execution error"
    And the verification V1 passed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the reason for R1 says "V1 (unconfirmed: fails without the change by an execution error)"
    And the outcome is accept

  Scenario: A test to create calls for the test_quality reviewer
    Given the configured reviewers are "spec_compliance, correctness"
    And a specification with a test to create
    When the reviewers for the specification are listed
    Then they are "spec_compliance, correctness, test_quality"
    And the "test_quality" reviewer runs with the agent of "spec_compliance"

  Scenario: A specification with no test to create keeps the configured reviewers
    Given the configured reviewers are "spec_compliance, correctness"
    And a specification with no test to create
    When the reviewers for the specification are listed
    Then they are "spec_compliance, correctness"

  Scenario: A configured test_quality reviewer is not added twice
    Given the configured reviewers are "test_quality, security"
    And a specification with a test to create
    When the reviewers for the specification are listed
    Then they are "test_quality, security"

  Scenario: A run whose new test names code absent from the base version says so everywhere
    Given the sample project
    When a change run walks the workflow
    Then the run ends delivered
    And the verification V1 discriminates
    And the verification V1 is unconfirmed
    And the requirement R1 is satisfied
    And the "test_quality" reviewer's prompt says "unconfirmed: fails without the change"
    And the "test_quality" reviewer's prompt says "Read that test with particular care"
    And the report says "unconfirmed: fails without the change"
