Feature: Deciding on a change from the evidence measured on it
  A requirement is satisfied only by a verification that ran on the change and passed,
  violated only by a failed verification or by a reviewer finding that cites an observation,
  undetermined otherwise; undetermined blocks acceptance. A correction request states what is
  not demonstrated and what was observed, never the remedy.

  # ------------------------------------------------------- what a verification is worth

  Scenario: A requirement whose only verification is insufficient stays undetermined
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And the verification V2 is a review marked insufficient
    And V1 passed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the requirement R2 is undetermined
    And the outcome is undetermined

  Scenario: A failed verification violates its requirement and asks for a correction
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 failed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the outcome is reject
    And the requirement R2 is violated
    And a correction request names R2

  Scenario: One failing verification asks for one correction naming every requirement it carries
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V1
    And a requirement R3 verified by the test V1
    And a requirement R4 verified by the test V1
    And V1 failed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then exactly one correction request says "not demonstrated"
    And a correction request names R1,R2,R3,R4
    And no correction request says "make verification pass"

  # ------------------------------------------------------- what a reviewer's claim is worth

  Scenario: A reviewer finding that cites no observation does not violate the requirement
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change with a major finding on R1 citing ""
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  Scenario: A reviewer finding that cites an observation violates the requirement
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change with a major finding on R1 citing "file.py:3"
    When the harness assesses the change
    Then the requirement R1 is violated
    And the outcome is reject

  Scenario: A reviewer assessing a requirement as violated without a finding leaves it undetermined
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change assessing R1 as violated without any finding
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And the requirement R2 is satisfied
    And the outcome is undetermined
    And no correction request names R1

  Scenario: An unsupported violated assessment weighs no more than an undetermined answer
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change assessing R1 as violated without any finding
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  Scenario: A violated assessment backed by a finding that cites an observation violates the requirement
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change assessing R1 as violated with a major finding citing "file.py:3"
    When the harness assesses the change
    Then the requirement R1 is violated
    And the outcome is reject
    And a correction request names R1

  Scenario: A change no reviewer read stays undetermined however its verifications reported
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    When the harness assesses the change
    Then the outcome is undetermined

  Scenario: A review the harness discarded weighs nothing
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a discarded reviewer rejected the change with a blocker titled "x" citing "y"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the outcome is accept

  Scenario: A blocker finding attached to no requirement rejects the change
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change with a blocker titled "secret committed" citing ".env:1"
    When the harness assesses the change
    Then the outcome is reject
    And a correction request says "secret committed"

  # ------------------------------------------------------- what the correction carries

  Scenario: A correction request carries the claim and the observation, never the remedy
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change with a major finding on R1 whose remedy is "change `return a + b` to `return a - b` on line 8", title "subtract adds instead of subtracting" and observation "calc.py:8 `return a + b`"
    When the harness assesses the change
    Then the correction request for R1 says "subtract adds instead of subtracting"
    And the correction request for R1 says "calc.py:8"
    And the correction request for R1 does not say "return a - b"

  Scenario: A failed scope check rejects the change whatever the reviewers said
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2
    And V1 passed on the change
    And V2 passed on the change
    And the scope check failed saying "outside allowed paths: x"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the outcome is reject
    And a correction request says "[scope]"

  # ------------------------------------------------------- an instrument blind to the change

  Scenario: A verification that fails without the change as well is charged to nothing
    Given a requirement R1 verified by the test V1
    And the verification V1 is faulty because "fails identically on the base version"
    And V1 failed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And the outcome is undetermined
    And there is no correction request
    And an instrument fault names V1
    And the reason for R1 says "fails identically on the base version"

  Scenario: A finding that rests on a verification blind to the change is set aside
    Given a requirement R1 verified by the test V1
    And the verification V1 is faulty because "fails identically on the base version"
    And V1 failed on the change
    And a reviewer rejected the change assessing R1 as violated with a major finding citing "ev-1 [FAIL] for V1: exit 1 (expected 0)"
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And there is no correction request
    And the reason for R1 says "set aside"

  Scenario: A finding that stands on the code itself is unaffected by a blind verification
    Given a requirement R1 verified by the test V1
    And the verification V1 is faulty because "fails identically on the base version"
    And V1 failed on the change
    And a reviewer rejected the change with a major finding on R1 titled "wrong operator" citing "calc.py:8 `return a + b`"
    When the harness assesses the change
    Then the requirement R1 is violated
    And a correction request says "wrong operator"

  # ------------------------------------------------------- the control run, and what it is not

  Scenario: A control run on the base version does not make a passing verification unexecuted
    Given a requirement R1 verified by the test V1
    And V1 passed on the change
    And a control run of V1 on the base version exited 1
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the reason for R1 does not say "not executed"

  Scenario: A control run never stands in for the verification it checks
    Given a requirement R1 verified by the test V1
    And V1 failed on the change
    And a control run of V1 on the base version exited 1
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is violated
    And a correction request says "not demonstrated"

  # ------------------------------------------------------- success the change did not earn

  Scenario: Success a command reports either way is not success the change earned
    Given a requirement R1 verified by the test V1
    And the verification V1 is vacuous because "passes on the base version as well"
    And V1 passed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And the outcome is undetermined
    And R1 is uncredited, naming V1
    And there is no correction request

  Scenario: The same command still shows that what worked goes on working
    Given a non-regression requirement R1 verified by the test V1
    And the verification V1 is vacuous because "passes on the base version as well"
    And V1 passed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept
    And nothing is uncredited

  Scenario: A command that never passes shows nothing at all, not even non-regression
    Given a non-regression requirement R1 verified by the test V1
    And the verification V1 is broken because "passes on the base version as well"
    And V1 failed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And an instrument fault names V1
