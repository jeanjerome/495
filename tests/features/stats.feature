Feature: The runs of a project read as a series
  One run says whether one change was accepted. Read together, the runs say what this project
  keeps paying for: which command could not decide anything, how many iterations a change
  costs, what a requirement costs, which perspective finds something and which kind of
  verification most often reports the same thing with and without the change. All of it is in
  the run documents; the harness states it and decides nothing with it.

  Scenario: The runs are counted by outcome and by status
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And a run "run-2" that ended "reject" after 3 iterations
    When the harness reads the runs as a series
    Then the series counts 2 run(s)
    And the series counts 1 run(s) that ended "accept"
    And the series counts 1 run(s) that ended "reject"

  Scenario: The iterations are averaged over the runs that produced one
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And a run "run-2" that ended "reject" after 3 iterations
    And a run "run-3" that ended "reject" after 0 iterations
    When the harness reads the runs as a series
    Then the series counts 4 iteration(s), 2.0 per run produced

  Scenario: The cost is divided by the requirements the runs assessed
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And "run-1" assessed 2 requirement(s) and cost 1.0 USD
    When the harness reads the runs as a series
    Then the series states 0.5 USD per requirement assessed

  Scenario: A cost nothing could be read from leaves no cost per requirement
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And "run-1" assessed 2 requirement(s) and cost 0.0 USD
    When the harness reads the runs as a series
    Then the series states no cost per requirement

  Scenario: A command the harness recorded at fault is listed with what it cost
    Given a project with runs
    And a run "run-1" that ended "reject" after 1 iteration
    And "run-1" named the command "mutmut run" for "V1"
    And the harness recorded "V1" of "run-1" unable to tell the change from its absence
    When the harness reads the runs as a series
    Then the command "mutmut run" is listed with 1 fault(s)

  Scenario: A command the requester replaced is listed against the one it replaced
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And "run-1" named the command "mutmut run --paths-to-mutate src" for "V1"
    And the requester had replaced "mutmut run" by it
    When the harness reads the runs as a series
    Then the command "mutmut run" is listed as replaced 1 time(s)

  Scenario: The kinds of verification are ranked by how often they decided nothing
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And "run-1" carries a "test" verification that reported the same thing with and without the change
    And "run-1" carries a "review" verification the gate called insufficient
    When the harness reads the runs as a series
    Then the kind "test" counts 1 verification(s) that decided nothing
    And the kind "review" counts 1 verification(s) stated insufficient

  Scenario: What each perspective found is counted
    Given a project with runs
    And a run "run-1" that ended "reject" after 1 iteration
    And the "security" reviewer of "run-1" rejected the change and found "a credential is committed" as a blocker
    When the harness reads the runs as a series
    Then the perspective "security" counts 1 review(s), 1 rejection(s) and 1 finding(s)
    And the perspective "security" counts 1 blocker(s)

  Scenario: A finding two runs found is recurring
    Given a project with runs
    And a run "run-1" that ended "reject" after 1 iteration
    And the "security" reviewer of "run-1" rejected the change and found "a credential is committed" as a blocker
    And a run "run-2" that ended "reject" after 1 iteration
    And the "security" reviewer of "run-2" rejected the change and found "a credential is committed" as a blocker
    When the harness reads the runs as a series
    Then the perspective "security" states "2× a credential is committed" as recurring

  Scenario: A finding a reviewer repeated inside one run is one thing the project does
    Given a project with runs
    And a run "run-1" that ended "reject" after 1 iteration
    And the "security" reviewer of "run-1" rejected the change and found "a credential is committed" as a blocker
    And the "security" reviewer of "run-1" rejected the change and found "a credential is committed" as a blocker
    When the harness reads the runs as a series
    Then the perspective "security" counts 2 review(s), 2 rejection(s) and 2 finding(s)
    And the perspective "security" states nothing as recurring

  Scenario: A review the harness discarded is counted as discarded and finds nothing
    Given a project with runs
    And a run "run-1" that ended "reject" after 1 iteration
    And the review of "correctness" on "run-1" was discarded after finding "the subtraction adds"
    When the harness reads the runs as a series
    Then the perspective "correctness" counts 1 review(s), 0 rejection(s) and 0 finding(s)
    And the perspective "correctness" counts 1 discarded review(s)

  Scenario: The lessons of the project are counted by where they stand
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And a lesson of the project is "accepted" and another is "open"
    When the harness reads the runs as a series
    Then the series counts 1 lesson(s) "accepted" and 1 "open"

  Scenario: The stats command reads the store and states the series
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    And "run-1" named the command "mutmut run" for "V1"
    And the harness recorded "V1" of "run-1" unable to tell the change from its absence
    When the requester runs "495 stats"
    Then the output shows "1 run(s)"
    And the output shows "commands that could not decide"
    And the output shows "mutmut run"

  Scenario: A store with no run says so rather than stating zeroes
    Given a project with runs
    When the requester runs "495 stats"
    Then the output shows "no run recorded under"

  Scenario: The indicators in JSON carry each series
    Given a project with runs
    And a run "run-1" that ended "accept" after 1 iteration
    When the requester runs "495 --json stats"
    Then the JSON output states 1 run(s) and the kinds it read

  Scenario: The schema of the indicators is published
    Given a project with runs
    When the requester runs "495 schema stats"
    Then the output shows "PerspectiveStat"
