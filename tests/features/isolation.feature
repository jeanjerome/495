Feature: A run works in a tree of its own, and one engine advances it at a time
  Every agent 495 calls works in a worktree under the cache, never in the checkout the requester
  works in, and the harness makes the commits there itself. A file the run finds changed outside
  that worktree is an escape: the intervention that made it is tampered, the evidence says so,
  and the run stops rather than committing what it cannot account for. A reviewer that writes is
  the same fault read from the other side — the verdict is discarded, since a reviewer that
  changed the change did not review it. Across processes, the run directory carries the claim of
  whoever is advancing the run: a second engine is refused rather than joined, and a run that
  stops on a question gives the claim back so another terminal can answer it.

  Background:
    Given a project 495 can work in

  Scenario: The worktree is outside the project, and a producer that reaches out of it is caught
    Given the producer also writes into the project's own checkout
    When the run is created
    Then the worktree is outside the project, and the run says where it is
    When the run is carried out
    Then the run failed, saying what it found changed
    And the evidence holds a failed integrity check
    And the producer's intervention is recorded as tampered
    And what the producer wrote in the checkout is left there for inspection

  Scenario: A reviewer that writes has its verdict discarded
    Given the reviewers write into the tree they are reading
    When the run is carried out
    Then every review is discarded
    And every reviewer's intervention is recorded as tampered
    And the run stops on an "undetermined" question
    And the worktree carries no trace of what the reviewers wrote

  Scenario: A run being advanced elsewhere is refused, not joined
    Given another process holds the claim on the run
    When carrying the run out is attempted
    Then it is refused as busy, and the run stands where it was
    When the claim is given up and the run is carried out
    Then the run is delivered

  Scenario: The claim is given back when the run stops on a question
    Given approval is not automatic
    When the run is carried out
    Then the run stops on an "approve_spec" question
    And nothing holds the claim on the run
