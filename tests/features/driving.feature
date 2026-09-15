Feature: Driving a run from the surface
  The surface is the workflow, so what it can do is measured the way what it shows is measured:
  against a real store walked by the agents behind it, rather than against a stand-in for the
  engine. An intent typed here becomes a run that walks to delivery on its own. A run another
  process is advancing is watched rather than joined — every control is withdrawn except the
  stop, which is how one terminal reaches another's run — and the driver does one thing at a
  time. Leaving the surface asks the run it was advancing to stop first, because the engine
  lives in this process and quitting without stopping it kills an agent mid-turn.

  # ------------------------------------------------------- from an intent

  Scenario: An intent typed here becomes a run that walks to delivery
    Given a surface that may drive the sample project
    When the intent "add subtract to calc" is typed in
    Then the run is delivered
    And the run records the surface as where the intent came from
    And it stands at the integration, the stop the harness cannot walk alone
    And there is nothing to answer, and nothing to start

  Scenario: An existing change can be evaluated from here
    Given a surface that may drive the sample project
    When the intent "subtract must work" is typed in, over the working tree
    Then the run is an evaluate run of "WORKTREE"

  # ------------------------------------------------------- what the opening question asks

  Scenario: A run that writes its own change is asked for an intent and nothing else
    Given a console that answers what is typed at it
    When "make the deploy command idempotent" is typed, then enter
    Then the intent taken is "make the deploy command idempotent", over nothing
    And the question said "495 writes it" and "it already exists"
    And the question never showed "<base>..<head>", which the ordinary path never sees

  Scenario: A change that already exists is asked which one, the working tree by default
    Given a console that answers what is typed at it
    When "subtract must work" is typed, then "evaluate", then enter
    Then the intent taken is "subtract must work", over "WORKTREE"

  Scenario: A ref is asked for only where one is meant
    Given a console that answers what is typed at it
    When "subtract must work" is typed, then "evaluate", then "commit", then "main..mine"
    Then the intent taken is "subtract must work", over "main..mine"

  Scenario: An empty intent opens nothing
    Given a console that answers what is typed at it
    When nothing at all is typed
    Then nothing is opened

  # ------------------------------------------------------- start, pause, answer

  Scenario: A created run is started by one key
    Given a surface that may drive the sample project
    And a run created but not started, open on the surface
    When what the surface offers for it is read
    Then it offers "start", as the key "s", and the band says so too
    When the start control is pressed
    Then the run is delivered

  Scenario: Pausing asks the run to stop wherever it is being driven from
    Given a surface that may drive the sample project
    And a run created but not started, open on the surface
    When the run is asked to pause
    Then a stop is on file for it
    When the run is started
    Then the run is paused or delivered, the flag being read by whichever engine walks it next

  Scenario: A question answered here lets the run carry on
    Given a surface that may drive the sample project, where approval is not automatic
    And a run created but not started, open on the surface
    When the run is started
    Then the run stopped on a question
    And it offers "answer", as the key "d", and there is nothing to start
    And the stop "spec" is blocked
    When the question is answered "approve"
    Then the run is delivered

  # ------------------------------------------------------- two terminals

  Scenario: A run advanced elsewhere is watched, not joined
    Given a surface that may drive the sample project
    And a run created but not started, open on the surface
    And another process holding the claim on it
    When what the surface offers for it is read
    Then the surface knows the run is held, and offers nothing to start
    And the controls offered are: p pause the run, c new run
    And the band says the run is being advanced elsewhere
    And neither answering nor checking a ref is offered
    And the stop is offered, which is how one terminal reaches another's run
    When the start control is pressed
    Then nothing was started, and the surface says to act on it there
    And the run stands where it was

  Scenario: The driver does one thing at a time
    Given a surface that may drive the sample project
    And two runs created but not started
    When both of them are started
    Then the second was refused, the surface naming the first
    And the second run stands where it was

  # ------------------------------------------------------- leaving

  Scenario: Leaving the surface pauses the run it was advancing
    Given a surface whose engine holds a run until it is asked to stop
    And a run created but not started, open on the surface
    When the run is started, and the surface is left
    Then nothing is working any more
    And a stop is on file for it
