Feature: The command line is 495's own surface on a project and its runs
  Every command reads or advances state that is already on disk, and says what it did in one of
  two registers: a terminal rendering for a person, or a JSON document under `--json` for
  whatever reads it next. The exit code carries the same answer as the document — 0 when there
  is nothing left to decide, 3 when the run stopped on a question, 4 when a ref does not carry
  what the run delivered, 1 when there is nothing to talk about — so a script never has to parse
  prose to know what happened.

  Background:
    Given a project the CLI can work in

  # ------------------------------------------------------- what the machine can be asked

  Scenario: The command line names the version it is
    When the command "--version" is run
    Then it exits 0, saying "495"

  Scenario: The project is profiled as a document
    When the command "--json profile" is run
    Then it exits 0
    And the document names the command "test", and a base commit

  Scenario: The shape of a persisted document is printed on request
    When the command "schema spec" is run
    Then it exits 0
    And the document has a "requirements" property

  Scenario: What the machine offers is reported before a run needs it
    When the command "--json doctor" is run
    Then it exits 0
    And the document names the sandboxes

  Scenario: Initialising a project writes the two files a run reads
    When the command "init" is run
    Then it exits 0
    And ".495/config.toml" is in the project
    And ".495/project.toml" declares a scope

  # ------------------------------------------------------- carrying a run from the terminal

  Scenario: A run stopped for approval exits 3, and one answer carries it to delivery
    When a run is created with "--agent claude_code:fake --sandbox host"
    And the command "--json run <id>" is run
    Then it exits 3, awaiting the "approve_spec" question
    When the command "--json decide <id> approve" is run
    Then it exits 0, the run delivered and accepted

  Scenario: What a delivered run holds is read back from the terminal
    Given a run carried to delivery from the terminal
    When the command "--json status <id>" is run
    Then the first requirement is satisfied
    When the command "--json list" is run
    Then the listing names that run, and no other
    When the command "report <id>" is run
    Then the report has a title and an interventions section
    When the command "--json events <id>" is run
    Then the events name "run.delivered"
    When the run document is validated
    Then it exits 0, saying "valid"
    When the run is exported
    Then it exits 0, and the archive is there

  Scenario: A run that does not exist is named as such, rather than answered for
    When the command "--json status run-nope" is run
    Then it exits 1, the document saying "not found"

  # ------------------------------------------------------- the eighth stop from the terminal

  # A ref nobody merged into is the run standing where it delivered, not a rejection: the
  # command says so and exits clean. A moved ref carrying something else does not.
  Scenario: The integration state is read, changed by a merge, and read again
    Given a run carried to delivery from the terminal
    When the command "--json check-integration <id>" is run
    Then it exits 0, the state "unmerged"
    When the command "--json merge <id>" is run
    Then it exits 0, the state "landed"
    When the command "--json check-integration <id>" is run
    Then it exits 0, the state "landed"
    When the branch is put back and moved on without it
    And the command "--json check-integration <id>" is run
    Then it exits 4, the state "differs"
    When the command "--json cleanup <id>" is run
    Then it exits 0

  # ------------------------------------------------------- evaluating, and stopping

  Scenario: An existing change is evaluated from the terminal, and the run can be stopped
    Given the change is in the working tree
    When it is evaluated from the terminal
    Then it exits 0, an evaluate run accepted
    When the command "--json stop <id>" is run
    Then it exits 0, and a stop is on file for the run

  # ------------------------------------------------------- reading the specification

  Scenario: The specification is read from the terminal, as a document and as text
    Given a run stopped for approval
    When the command "--json spec <id>" is run
    Then it exits 0
    And the specification names R1 and R2, and says where it is written
    When the command "spec <id>" is run
    Then it exits 0, printing "R1", "not approved" and "calc.subtract"

  # ------------------------------------------------------- how a question is printed

  # Every option says what it does to the run, not just what it is called; and the
  # requirements are laid out once, by the decision, rather than twice.
  Scenario: A printed question says what each answer does, and lays the requirements out once
    Given a run that reached its iteration limit on a version the reviewer rejected
    When the command "run <id>" is run
    Then it exits 3
    And the output says "Raises the limit by one"
    And the output says "stay on disk"
    And the output names R1 once, under "where each requirement stands"
    And the output says "outstanding corrections"
