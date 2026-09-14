Feature: What a run showed about the project is put to the requester and carried to the next run
  A run settles things that outlive it: a command put in the place of one that could not
  measure anything, a rule stated by hand once the producer had already broken it, the paths
  the change was allowed to touch, a decision taken before the specification was written. The
  harness reads them back from the run document, states each one against what the project
  already declares, and keeps the requester's answer next to it. An accepted lesson is part of
  the project's criteria from the next run on and reaches the specifier as a fact; a declined
  one is never proposed again.

  Scenario: A command the requester put in the place of another is proposed as a declared command
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    When the harness reads what the run showed
    Then a lesson of kind "command" says "`mutmut run --paths-to-mutate src` measures what V1 measures, and `mutmut run` did not"
    And that lesson would declare "mutmut run --paths-to-mutate src"
    And that lesson's lines for project.toml hold "[[commands]]"
    And that lesson's lines for project.toml hold "mutmut run --paths-to-mutate src"
    And that lesson holds what the run observed about it

  Scenario: A command the project already declares is not proposed
    Given a project whose criteria declare the command "mutmut run --paths-to-mutate src"
    And a run "run-1" on it
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    When the harness reads what the run showed
    Then no lesson of kind "command" is proposed

  Scenario: An accepted command is declared for every run that follows
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    And the harness has read what the run showed
    When the requester accepts that lesson
    Then the project's criteria declare the command "mutmut run --paths-to-mutate src"
    And the criteria name the lesson as the source of that command

  Scenario: A correction the requester wrote by hand is proposed as a convention
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester corrected the change by hand with "every public function carries a docstring"
    When the harness reads what the run showed
    Then a lesson of kind "convention" says "the requester corrected the change by hand in iteration 1"
    And that lesson would declare "every public function carries a docstring"
    And that lesson's lines for project.toml hold "conventions = "

  Scenario: A reviewer's blocking finding no requirement asked about is proposed as a convention
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the "security" reviewer of "run-1" blocked the change for "a credential is committed" observed at ".env:1"
    When the harness reads what the run showed
    Then a lesson of kind "convention" says "the security reviewer blocked the change for “a credential is committed”, which no requirement asked about"
    And that lesson would declare "a credential is committed"

  Scenario: A convention the project already declares is not proposed
    Given a project whose criteria declare the convention "a credential is committed"
    And a run "run-1" on it
    And the "security" reviewer of "run-1" blocked the change for "a credential is committed" observed at ".env:1"
    When the harness reads what the run showed
    Then no lesson of kind "convention" is proposed

  Scenario: A lesson accepted in the requester's own words declares those words
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the "security" reviewer of "run-1" blocked the change for "a credential is committed" observed at ".env:1"
    And the harness has read what the run showed
    When the requester accepts that lesson as "no credential is committed to the repository"
    Then the project's criteria declare the convention "no credential is committed to the repository"
    And that lesson still says what the run observed

  Scenario: The scope a produced change stayed within is proposed as the project's scope
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the change of "run-1" was produced within "src/**, tests/**" and stayed there
    When the harness reads what the run showed
    Then a lesson of kind "allowed_path" says "the project declares no scope, so a change may touch any path that is not forbidden"
    And that lesson's lines for project.toml hold "[scope]"

  Scenario: An accepted scope bounds every run that follows
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the change of "run-1" was produced within "src/**, tests/**" and stayed there
    And the harness has read what the run showed
    When the requester accepts that lesson
    Then the project's criteria allow "src/**"
    And the project's criteria allow "tests/**"

  Scenario: A scope widened for one run alone is proposed against the one the criteria declare
    Given a project whose criteria declare the scope "src/**"
    And a run "run-1" on it
    And "run-1" was allowed "src/**, docs/**" for that run alone
    And the change of "run-1" was produced within "src/**, docs/**" and stayed there
    When the harness reads what the run showed
    Then a lesson of kind "allowed_path" says "the project declares `src/**`"
    And that lesson would declare "docs/**, src/**"

  Scenario: A run no version of which stayed inside its scope proposes none
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the specification of "run-1" allowed "src/**" and no version stayed inside it
    When the harness reads what the run showed
    Then no lesson of kind "allowed_path" is proposed

  Scenario: A decision the requester took before the specification is carried to the next one
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester decided "are errors raised or returned" with "raised"
    When the harness reads what the run showed
    Then a lesson of kind "note" says "the requester decided: are errors raised or returned — raised"
    And that lesson declares nothing

  Scenario: A decision the harness took on the requester's behalf is not a lesson
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the harness decided "are errors raised or returned" with "raised" on the requester's behalf
    When the harness reads what the run showed
    Then no lesson of kind "note" is proposed

  Scenario: A specification sent back to be written again warns the next one
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester sent the specification back with "the intent is about the parser, not the CLI"
    When the harness reads what the run showed
    Then a lesson of kind "note" says "a specification of this project was sent back to be written again: “the intent is about the parser, not the CLI”"

  Scenario: A tool the retrospective found unable to measure anything warns the next specification
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the retrospective of "run-1" found "mutmut" faulty for the "mutation" role
    When the harness reads what the run showed
    Then a lesson of kind "note" says "mutmut measures the mutation role of python here and could not report anything the change decided"

  Scenario: The same lesson read from two runs is one record naming both
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the "security" reviewer of "run-1" blocked the change for "a credential is committed" observed at ".env:1"
    And a run "run-2" on it
    And the "security" reviewer of "run-2" blocked the change for "a credential is committed" observed at ".env:4"
    When the harness reads what each run showed
    Then there is one lesson of kind "convention"
    And that lesson names the runs "run-1, run-2"
    And that lesson holds what both runs observed

  Scenario: A declined lesson keeps its reason and is not proposed again
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the "security" reviewer of "run-1" blocked the change for "a credential is committed" observed at ".env:1"
    And the harness has read what the run showed
    When the requester declines that lesson with the reason "the file is a fixture, committed on purpose"
    And the harness reads what the run showed
    Then there is one lesson of kind "convention"
    And that lesson is "declined"
    And that lesson carries the reason "the file is a fixture, committed on purpose"
    And the project's criteria declare no convention

  Scenario: Declining a lesson without a reason is refused
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the "security" reviewer of "run-1" blocked the change for "a credential is committed" observed at ".env:1"
    And the harness has read what the run showed
    When the requester declines that lesson with no reason
    Then the answer is refused with "needs a reason"
    And that lesson is "open"

  Scenario: The lessons in force are written next to the document for a person to read
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester decided "are errors raised or returned" with "raised"
    And the harness has read what the run showed
    When the requester accepts that lesson
    Then "lessons.md" holds "the requester decided: are errors raised or returned — raised"
    And "lessons.md" holds "run-1"

  Scenario: A lesson nobody has accepted is in no criteria and in no reading
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester decided "are errors raised or returned" with "raised"
    When the harness reads what the run showed
    Then "lessons.md" holds "No lesson is in force yet"

  Scenario: The retro command records what the run showed and says what awaits an answer
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    And the run is saved in the project's store
    When the requester runs "495 retro run-1"
    Then the output shows "1 lesson(s), 1 awaiting an answer"
    And the output shows "in .495/project.toml, merged into the keys already there"

  Scenario: The lessons command lists them and says how to answer
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    And the harness has read what the run showed
    When the requester runs "495 lessons"
    Then the output shows "open lesson(s): answer with 495 lessons accept|decline|defer"

  Scenario: The lessons in JSON carry what would be declared and where
    Given a project whose criteria declare nothing
    And a run "run-1" on it
    And the requester replaced the command of "V1" by "mutmut run --paths-to-mutate src"
    And the harness has read what the run showed
    When the requester runs "495 --json lessons"
    Then the JSON output lists a lesson of kind "command" whose lines hold "[[commands]]"

  Scenario: The schema of the lessons document is published
    Given a project whose criteria declare nothing
    When the requester runs "495 schema lessons"
    Then the output shows "LessonKind"

  Scenario: The lessons in force are given to the specifier as established facts
    Given the sample project
    And a lesson in force saying "the requester decided: are errors raised or returned — raised"
    When a change run walks the workflow
    Then the facts given to the specifier hold that lesson
    And the untrusted content given to the specifier does not hold it
