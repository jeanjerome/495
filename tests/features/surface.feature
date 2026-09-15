Feature: Every stop of the run surface renders what the run holds
  `495 watch` is eight stops of one run, each drawing what the run document already holds and
  nothing else. Reading is not driving: opening a stop, moving the cursor and flowing the page
  leave the run exactly as they found it, and a surface over a snapshot offers nothing to press
  at all. At any width the content fits — below 136 columns the detail goes under the list
  rather than beside it, below 92 the mark goes — and nothing ever scrolls sideways.

  Scenario: Every stop of a delivered run renders, naming the run and the pipeline
    Given a run carried to delivery, open on the surface
    When every stop is rendered
    Then every one of them names the run
    And every stop of a run carries the pipeline strip, the home page excepted

  Scenario: The last stop names what was produced and what is left to do
    Given a run carried to delivery, open on the surface
    When the "deliver" stop is rendered
    Then it says "nothing has been merged"
    And it names the branch the change is on
    And it names the command that prints the report

  Scenario: The checks stop shows every command the specification named
    Given a run carried to delivery, open on the surface
    When the "checks" stop is rendered
    Then every verification of the specification is named

  Scenario: The ledger carries every requirement and where it stands
    Given a run carried to delivery, open on the surface
    When the "verdict" stop is rendered
    Then every requirement is named, with the status it stands at

  Scenario: The cursor moves the detail beside the list
    Given a run carried to delivery, open on the surface
    When the "spec" stop is rendered
    And the cursor moves down one
    Then the cursor stands on the second row
    And the stop renders differently from before

  Scenario: A narrow terminal never scrolls sideways
    Given a run carried to delivery, open on the surface
    When every stop is rendered at 80 columns
    Then no line is wider than 80 columns

  Scenario: Rendering a run never advances it
    Given a run carried to delivery, open on the surface
    When every stop is rendered
    Then the run document is what it was before

  Scenario: A recorded output is read back from the store
    Given a run carried to delivery, open on the surface
    When the output of the first command that recorded one is asked for
    Then it comes back

  Scenario: An output the store no longer holds reads as nothing rather than raising
    Given a run carried to delivery, open on the surface
    When the output of an evidence pointing at a file that is gone is asked for
    Then nothing comes back

  Scenario: A surface over a snapshot renders, and offers nothing to press
    Given a surface over a snapshot of one run
    When the "profile" stop is rendered
    Then something was drawn
    And the surface offers no control, and nothing to start
    And asking it to start a run is refused
