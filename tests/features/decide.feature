Feature: Deciding on a change from the evidence measured on it
  A requirement is satisfied only by a verification that ran on the change and passed,
  violated only by a failed verification or by a reviewer finding that cites an observation,
  undetermined otherwise; undetermined blocks acceptance.

  Background:
    Given a requirement R1 verified by the test V1
    And a requirement R2 verified by the test V2

  Scenario: A requirement whose only verification is insufficient stays undetermined
    Given the verification V2 is a review marked insufficient
    And V1 passed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the requirement R2 is undetermined
    And the outcome is undetermined

  Scenario: A failed verification violates its requirement and asks for a correction
    Given V1 passed on the change
    And V2 failed on the change
    And a reviewer accepted the change
    When the harness assesses the change
    Then the outcome is reject
    And the requirement R2 is violated
    And a correction request names R2

  Scenario: A reviewer finding that cites no observation does not violate the requirement
    Given V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change with a major finding on R1 citing ""
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  Scenario: A reviewer finding that cites an observation violates the requirement
    Given V1 passed on the change
    And V2 passed on the change
    And a reviewer rejected the change with a major finding on R1 citing "file.py:3"
    When the harness assesses the change
    Then the requirement R1 is violated
    And the outcome is reject
