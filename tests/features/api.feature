Feature: An HTTP interface over the store of runs
  The same documents the command line prints, served over HTTP so that a run can be created,
  watched and answered from somewhere else. A run advances in a thread of the server's own, so
  the caller polls the run document rather than holding a request open; the events are read from
  an offset, so a watcher catches up rather than re-reading. What the interface refuses it
  refuses with the code that says which side was wrong: 400 for a request missing what it needs,
  404 for a run that does not exist.

  Background:
    Given a project served over HTTP, with the fake agents behind it

  Scenario: A run is created, watched, answered and read back over HTTP
    When GET "/health" is asked
    Then it answers 200, and says it is ok
    When a run is posted with the intent "add subtract"
    Then it answers 201
    When the run is waited for until it stops on a question
    Then the question is "approve_spec"
    When GET the run's events from offset 0 is asked
    Then it answers 200, holding a "decision.requested" event
    When the answer "approve" is posted to the run
    Then it answers 200
    When the run is waited for until it is delivered
    Then the run is delivered, and accepted
    When GET the run's report is asked
    Then it answers 200, and the report has a title
    When GET "/runs" is asked
    Then it answers 200, naming that run first
    When GET "/schema/run" is asked
    Then it answers 200, with properties
    When a run is posted with no intent at all
    Then it answers 400, naming "intent"
    When GET "/runs/run-nope" is asked
    Then it answers 404
