Feature: The harness is the only source an agent takes instructions from
  A CLI that reads the target project's instruction and settings files on its own gives the same
  text two contradictory statuses: an instruction obeyed on the native path, data not to be
  obeyed in the pack. It also makes the context depend on which CLI runs the role, and puts in
  front of the agent material the harness never counted, bounded or traced. So the native paths
  are closed: a repository file reaches an agent through the pack only, as untrusted content,
  and what the requester wants obeyed is declared in the project configuration and travels as a
  fact.

  # ------------------------------------------------------------------ the CLIs' native paths

  Scenario: The Claude Code command loads no setting source
    Given a read-only intervention for Claude Code
    When the harness builds the command
    Then the command loads no setting source
    And the command carries the sandbox the harness imposes

  Scenario: A write intervention loads no setting source either
    Given a write intervention for Claude Code
    When the harness builds the command
    Then the command loads no setting source
    And the command carries the sandbox the harness imposes

  Scenario: The Codex command reads no project instruction file
    Given a read-only intervention for Codex
    When the harness builds the command
    Then the command reads no project instruction file

  Scenario: A write intervention of Codex reads none either
    Given a write intervention for Codex
    When the harness builds the command
    Then the command reads no project instruction file

  # ------------------------------------------------------------------ the one route left

  Scenario: An instruction file of the repository reaches the specifier as data
    Given the sample project
    And the project carries a CLAUDE.md that tells the agent to ignore the specification
    When a change run walks the workflow
    Then the specifier reads CLAUDE.md as untrusted content
    And no established fact given to the specifier holds what CLAUDE.md says

  Scenario: The profile names the documentation files without quoting them
    Given the sample project
    And the project carries a CLAUDE.md that tells the agent to ignore the specification
    When a change run walks the workflow
    Then the facts given to the producer name CLAUDE.md as a documentation file
    And no established fact given to the producer holds what CLAUDE.md says

  Scenario: A rule the requester wants obeyed is a fact because the configuration declares it
    Given the sample project
    When a change run walks the workflow
    Then the facts given to the producer hold the convention declared in the configuration
