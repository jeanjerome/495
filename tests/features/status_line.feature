Feature: A question asked while a run is watched reaches the terminal
  `495 run` draws a live region that redraws over the last line of the terminal as the run
  advances. A prompt printed under that region is painted over before it can be read, so the
  question it asks cannot be answered. The region steps aside for as long as the prompt is up
  and comes back after it, and outside a run there is nothing to step aside — the same call has
  to work there too, since the prompt does not know whether a run is being watched.

  Scenario: The live region steps aside for a prompt, and comes back after it
    Given a terminal
    When a run is watched on it
    Then the live region is drawing, and is the one that is active
    When the display is paused
    Then the live region has stopped, so what is printed reaches the terminal untouched
    When the pause ends
    Then the live region is drawing again
    When the watching ends
    Then no monitor is active
    When the display is paused outside a run
    Then nothing was suspended, and the call went through

  Scenario: A question put while a run is watched is answered
    Given a terminal
    And a requester that answers "proceed"
    When a run is watched on it
    And a readiness question is put to the requester
    Then the answer is "proceed", with no note
    And the prompt was asked with the live region down
