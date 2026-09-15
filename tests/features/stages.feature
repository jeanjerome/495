Feature: The eight stops a run walks, and the one it is standing at
  The surface is a pipeline of eight stops, and the status of a run says which one it stands at.
  A run stopped on a question stands at the stop that raised the question, not at a ninth stop
  called "waiting": `awaiting_decision` says that the run stopped, and the question says where.
  Delivery ends what the harness can do alone — every stop before the integration is walked, and
  the integration waits on a merge that is the requester's to make.

  Scenario Outline: A run whose status is <status> stands at the stop "<stop>"
    Given a run whose status is "<status>"
    When the stop it stands at is read
    Then it is "<stop>"

    Examples:
      | status    | stop        |
      | created   | profile     |
      | specified | spec        |
      | producing | change      |
      | verifying | checks      |
      | reviewing | review      |
      | reviewed  | verdict     |
      | accepted  | deliver     |
      | delivered | integration |

  Scenario: A question is shown at the stop that raised it
    Given a run stopped on an "approve_spec" question
    When the stop it stands at is read
    Then it is "spec"
    And the stop "spec" is blocked
    And the stop "checks" is still to walk
    And the stop "profile" is done

  Scenario: A delivered run leaves every stop walked and stands at the integration
    Given a run whose status is "delivered"
    When the stop it stands at is read
    Then it is "integration"
    And every stop before the integration is done
    And the stop "integration" is blocked, waiting on a merge rather than working
