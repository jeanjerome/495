Feature: The chrome of the surface: the icons, the footer, the band, the strip and the mark
  Around whatever a stop is showing sit the rows that say what the screen is about: a mark at
  the top left, a band naming what the run needs, a strip of the eight stops with the one being
  walked marked on it, and a footer of the keys that do something here. Each of them is drawn
  from the run document and from the clock, and from nothing else — two surfaces refreshing at
  different rates draw the same frame at the same instant — and each is measured on what it
  paints rather than on the call that painted it.

  # ------------------------------------------------------- the icons

  Scenario: Every stop is named by an emoji of its own
    When the emoji of the eight stops are read
    Then no two stops share one
    And each of them is two cells wide

  Scenario: A terminal without emoji gets one-cell marks instead
    When the icon set is switched to ascii
    Then every mark is one cell wide

  # ------------------------------------------------------- the footer

  # Quit is put back after the trim, so a row that still held it printed it twice.
  Scenario Outline: No key is offered twice on the footer row, at <width> columns
    Given a run carried to delivery, open on the surface
    When the footer row is drawn at <width> columns
    Then "quit" is on the row once

    Examples:
      | width |
      | 80    |
      | 88    |
      | 104   |
      | 120   |
      | 150   |

  # ------------------------------------------------------- the band

  # A run can be stopped on a decision before one requirement has been weighed, and a question
  # raised elsewhere is answered elsewhere: the panel that puts it is not under this sentence.
  Scenario: A question raised at the ledger is named in the ledger's own headline
    Given a run stopped on an "acceptance" question
    When the headline of the "verdict" stop is read
    Then it says "waiting on your answer"
    And it does not say "nothing to decide"

  Scenario: A question raised elsewhere is not named in the ledger's headline
    Given a run stopped on an "approve_spec" question
    When the headline of the "verdict" stop is read
    Then it does not say "waiting on your answer"

  Scenario: Every state of the band takes a frame the rest of the surface already draws
    When the band is read for every status a run can be in
    Then each tone is one the panels take, and the theme has a frame for it

  Scenario: A frozen display never hides what the run is stopped on
    Given a snapshot surface over a run stopped on an "approve_spec" question
    When the display is frozen, and the "spec" stop is rendered
    Then the stop says "waiting on you"
    And the stop says "frozen"

  Scenario: The band offers no key the surface would refuse
    Given a snapshot surface over a run stopped on an "approve_spec" question
    When the band of the open run is read
    Then the surface cannot answer
    And the band names the stop that holds the question, rather than the key that answers it

  # The claim and the running intervention are both in the store, so idle is read there rather
  # than assumed from a status.
  Scenario: A run nothing holds is idle, on a surface that could drive it and on one that could not
    When the band of a producing run is read, on a surface that may drive and on one that may not
    Then neither says anything is working, and both say "idle"
    And the band of a run nobody started says "not started"

  # ------------------------------------------------------- the strip

  Scenario: The stop a run is moving through turns
    When the strip of a producing run is drawn with something working
    Then the turning mark is on it
    And the still glyph for the stop being walked is not
    And the stops ahead are untouched

  # A --print and an export capture one frame, and a spinner caught alone reads as a typo.
  Scenario: A still strip keeps the glyph the legend names
    When the strip of a producing run is drawn with nothing working
    Then the still glyph for the stop being walked is on it
    And the turning mark is not

  Scenario: The turning mark advances with the clock and never changes width
    When eight frames of the turning mark are read, one per redraw
    Then they are eight different frames
    And each of them is one cell wide

  # ------------------------------------------------------- the mark

  Scenario: The highlight crosses the mark once per cycle
    When the sweep of one cycle is read
    Then the cycle opens at rest, and closes at rest
    And the sweep is one continuous pass
    And the lit column only ever moves to the right
    And it starts at the first column and ends at the last

  Scenario: The mark is a pure function of the clock
    When a moment of the sweep and a moment at rest are each compared with a cycle later
    Then the moment of the sweep draws the same frame
    And the moment at rest is at rest there too

  Scenario: The highlight paints the ink, and leaves everything else at rest
    When the mark is rendered at a moment of the sweep
    Then no glyph is replaced; only the colour moves
    And the brightest column differs from the resting style
    And a hole between the glyphs keeps the resting style
    And a column the light has not reached carries no overlay at all

  Scenario: A still capture gets the whole mark
    When the mark is captured still
    Then it reads "█ █ █▀█ █▀▀" over "▀▀█ ▀▀█ ▀▀█"
