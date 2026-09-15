Feature: The home page speaks for the store, and acts on the row under the cursor
  `495 watch` with no run named opens on the store rather than on a run: the header, the band
  and the listing all speak for the store, and the pipeline strip — eight stops of one run — is
  not drawn at all. Reading a row is not opening it, so the card beside the listing follows the
  cursor while the run opened behind the page stays open; every control offered acts on the row
  the cursor is on, never on the run opened last. A rule about what is on screen holds of both
  renderings or it is not a rule, so each is stated of the flowed content `--print` writes and
  of the screen the terminal draws.

  # ------------------------------------------------------- the page is about the store

  # Getting here by opening a run and pressing `l` used to be a different screen from getting
  # here without: what is open is a latch nothing lowers, so the chrome went on naming the run
  # opened last — its status, its question, its pipeline — above a cursor standing elsewhere.
  Scenario Outline: The home page speaks for no run, reached <arrival> and <how>
    Given a store holding a run that asks and a delivered run
    And the home page reached <arrival>
    When the page is <how>
    Then the page stands at home, showing the listing
    And the chrome says "no run is open"
    And the chrome counts "2 runs"
    And the chrome names no run of the store, and no stop of one
    And nothing on the page puts the question to the requester

    Examples:
      | arrival                  | how     |
      | without opening anything | printed |
      | without opening anything | drawn   |
      | after a run was opened   | printed |
      | after a run was opened   | drawn   |

  Scenario Outline: The card names the run the cursor is on, <how>
    Given a store holding a run that asks and a delivered run
    When the page is <how>
    Then the body names "run-0"
    When the cursor moves down one, and the page is <how>
    Then the body names "run-1", and says "delivered"
    And nothing was opened

    Examples:
      | how     |
      | printed |
      | drawn   |

  Scenario Outline: Opening a row gives the chrome back for that row, <how>
    Given a store holding a run that asks and a delivered run
    When the cursor moves down one
    And the row under the cursor is opened
    Then the run "run-1" is open, at the stop it stands at
    When the page is <how>
    Then the header names "run-1", and the band under it says "delivered"
    When the listing is opened again
    Then the cursor is still on the row that is open

    Examples:
      | how     |
      | printed |
      | drawn   |

  # Identity, then what it needs, then what it holds. Without a line under the identity the
  # band's own frame opened one row under the last row of the header, and five lines read as
  # one block instead of two things in a hierarchy.
  Scenario Outline: The header is closed by a rule, whether it speaks for <subject>, <how>
    Given a store holding a run that asks and a run with something to act on
    And <subject> as the subject of the page
    When the page is <how>
    Then the third line is a rule the full width of the screen
    And the fourth line is air

    Examples:
      | subject   | how     |
      | the store | printed |
      | the store | drawn   |
      | a run     | printed |
      | a run     | drawn   |

  # ------------------------------------------------------- what the page offers

  # The run that was opened last used to keep the controls, so `d` answered a question three
  # rows above the cursor — and the footer offered it while the card described another run.
  Scenario: A control on the home page acts on the row under the cursor
    Given a store holding a run that asks and a run with something to act on, on a surface that may act
    When the run that asks is opened, and the listing is opened again
    Then the surface can answer, the cursor being on the run that asked
    When the cursor moves down one
    Then the cursor is on "run-1", and the run open behind the page is still "run-0"
    And the surface cannot answer
    And the footer offers "m" and "i", and not "d"
    And the controls offered are: m merge the branch, i check a ref, c new run

  Scenario: A surface that only reads offers nothing on the home page either
    Given a store holding a run that asks and a delivered run
    When what the page offers is read
    Then the surface offers no control
    And the footer offers only: ↑↓, enter, n, ?, q

  # ------------------------------------------------------- moving from a page that is at no stop

  Scenario: A key that names a stop opens the row it is a stop of
    Given a store holding a run that asks and a delivered run
    When the cursor moves down one
    And the stop "spec" is asked for
    Then the run "run-1" is open, at the stop "spec"

  Scenario: A relative move needs a stop to move from
    Given a store holding a run that asks and a delivered run
    When the next stop, the previous stop and the filter are asked for in turn
    Then the page stayed at home, with nothing opened

  # ------------------------------------------------------- what the band says of a store

  Scenario: What the band names is where the catch-up key puts the cursor
    Given a store holding a delivered run and a run that asks
    When the band of the store is read
    Then it is toned "ask", saying "waiting on you"
    And it offers "n", and counts "2 runs"
    When the catch-up key is pressed
    Then the cursor stands on a run that is asking something

  Scenario: A store where nothing asks anything still says something about itself
    Given a store holding a delivered run alone
    When the band of the store is read
    Then it is toned "good", offering no key

  Scenario: A run nothing is advancing leaves the store idle
    Given a store holding a producing run alone
    When the band of the store is read
    Then it is toned "ask", saying "idle"

  Scenario: A question outranks a run that already ended
    Given a store holding a failed run and a run that asks
    When the band of the store is read
    Then it says "waiting on you"

  # ------------------------------------------------------- a store with nothing, and one with too much

  Scenario: A store emptied under the surface still has a page
    Given an empty store, on a surface that may act
    When the page is drawn
    Then nothing is in focus
    And the only control offered is: c new run
    And the page says "no run yet" and "no project"
    When opening, answering, starting, catching up and going to a stop are all asked for
    Then the page stayed at home, with nothing opened

  Scenario: A store too long for the screen is windowed around the cursor
    Given a store holding 30 runs
    When the cursor moves down 20 rows
    And the page is drawn 30 rows high
    Then the body says "21 of 30, showing"
    And the body names "run-20", and not "run-00"
