Feature: What the harness is to do and what the project declares load into one document
  A project carries two files under `.495/`: `config.toml`, what 495 is to do — the agents it
  may call, what it may spend, who reviews — and `project.toml`, what the project itself
  declares — the commands that check it, the conventions to obey, the paths a change may touch.
  They are read into one configuration, so that every surface of the harness reads the same
  setting from the same place, and an agent named in shorthand resolves to the same agent
  wherever it is written.

  Scenario: The two files of a project are read into one configuration
    Given a config.toml naming the agent "x" as codex "m", a budget of 2.5 dollars, the producer "x" and the reviewer "security"
    And a project.toml declaring the convention "c1", the command "lint" as "ruff check ." and the allowed path "src/**"
    When the configuration is loaded
    Then the agent "x" is a codex agent
    And the budget allows 2.5 dollars
    And the producer is "x", and the first reviewer looks at "security"
    And the project's first command is "ruff check ."
    And a change may touch "src/**"
    And the conventions are "c1"
