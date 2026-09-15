Feature: Landing a delivered change in the checkout the requester works in
  495 writes to that checkout on one command and no other: until it is asked, the change waits
  on a branch of its own. The ask names one of four shapes, each leaving a history it states in
  advance, and the same command reads back what landed — by the files rather than by the
  commit, since two of the four copy the change instead of moving it. A precondition that does
  not hold is a refusal and never a repair: an unclean tree is not stashed, a conflict is not
  resolved, a branch already carrying the change is not given it twice, and each refusal leaves
  the repository exactly where it was found.

  # ------------------------------------------------------- the shape the history takes

  Scenario: A fast-forward makes the branch the verified commit and adds nothing else
    Given a run carried to delivery
    When the delivery is integrated by fast-forward
    Then the checkout stands at the verified commit
    And the history carries a merge commit: no
    And the run records the integration as "fast-forward"
    And the run reads as landed
    And integrating a second time is refused, saying "already contains"

  Scenario: A fast-forward is refused once the branch has gone somewhere of its own
    Given a run carried to delivery
    And the branch has moved on since
    When the delivery is integrated by fast-forward
    Then the integration is refused, saying "fast-forwarded"
    And the run records no integration

  # Three shapes of one act, told apart by what the history keeps and what the check finds.
  # The two that copy the change rather than move it leave the verified commit out of the
  # branch, which is the reading a hand-made cherry-pick produces too — and why identical file
  # contents, not the commit, are what say the right thing landed.
  Scenario Outline: Integrating by <how> leaves the history it promises
    Given a run carried to delivery
    And the branch has moved on since
    When the delivery is integrated by <how>
    Then the files of the checkout are those of the verified commit
    And the checkout contains the verified commit: <contains>
    And the run records the integration as "<how>"
    And the run reads as landed
    And the history carries a merge commit: <merge>
    And the last commit subject starts with "<subject>"
    And what the branch had of its own is still there

    Examples:
      | how    | contains | merge | subject                               |
      | rebase | no       | no    | 495 iteration 1: add subtract to calc |
      | squash | no       | no    | add subtract to calc                  |
      | merge  | yes      | yes   | Merge branch '495/                    |

  # git resolves the committer before it squashes, though a squash writes no commit of its
  # own: a checkout on a machine that names nobody would refuse the act rather than the commit
  # that follows it. 495 names itself for the squash as it does for the commit.
  Scenario: A squash goes through on a machine that names nobody
    Given a run carried to delivery
    And the branch has moved on since
    And the machine names nobody to git
    When the delivery is integrated by squash
    Then the files of the checkout are those of the verified commit
    And the last commit subject starts with "add subtract to calc"

  Scenario: A squash says where the evidence for it is
    Given a run carried to delivery
    And the branch has moved on since
    When the delivery is integrated by squash
    Then the commit message names the verified commit and the run

  # ------------------------------------------------------- what the check records

  Scenario: The check records the name the ref has, not where the requester stood
    Given a run carried to delivery
    When the delivery is integrated by fast-forward
    Then the check names "main" as the branch it landed in
    And the check records the commit "main" stands at

  Scenario: A ref that resolves to no branch keeps the name it was given
    Given a run carried to delivery
    And the checkout stands on a detached HEAD
    When the integration of "HEAD" is checked
    Then the check names "HEAD" as the branch it landed in

  Scenario: A ref nobody merged into carries neither the commit nor the files
    Given a run carried to delivery
    When the integration of "HEAD" is checked
    Then the check finds neither the commit nor the files

  Scenario: A branch merged by hand is found to carry the change, and is measured again
    Given a run carried to delivery
    And the branch was merged into the checkout by hand
    When the integration of "HEAD" is checked, running the verifications again
    Then the check finds the commit and the files
    And the verifications passed on the checkout

  Scenario: The worktree a run held is removed on request
    Given a run carried to delivery
    When the worktree of the run is cleaned up
    Then nothing is left of the worktree

  # ------------------------------------------------------- what a refusal leaves behind

  Scenario: A merge that conflicts leaves the repository where it was
    Given a run carried to delivery
    And the checkout carries a subtract of its own
    When the delivery is integrated by merge
    Then the integration is refused, saying "nothing was changed"
    And the checkout stands where it stood
    And no merge was left half-made
    And the checkout is clean

  Scenario: A tree with uncommitted work is refused rather than stashed
    Given a run carried to delivery
    And the checkout has uncommitted work
    When the delivery is integrated by fast-forward
    Then the integration is refused, saying "uncommitted changes"
    And the uncommitted work is still there
