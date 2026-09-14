Feature: The answer read out of an agent's prose
  An agent CLI that drops the output schema leaves the harness a page of prose where an object
  was asked for: the clarifier's questions, the specifier's specification and a reviewer's
  verdict all arrive that way when the structured output is missing. The harness builds
  candidates out of the text — the text itself, the body of every fenced block, the span from
  the first brace to the last — and takes the largest that parses as an object. An agent that
  shows a block before its answer is showing the shape it is about to fill, and fills it in a
  block that follows, so the answer is the larger of the two; the order the candidates are built
  in says nothing about them, since the whole text comes first and the brace span last however
  the prose is laid out.

  Scenario: An answer that is nothing but the object is read as it stands
    Given the agent answered
      """
      {"verdict": "pass", "findings": []}
      """
    When the harness reads the answer out of the text
    Then the answer is
      """
      {"verdict": "pass", "findings": []}
      """

  Scenario: An answer fenced in a code block is read from the fence
    Given the agent answered
      """
      I looked at the diff and found nothing.

      ```json
      {"verdict": "pass", "findings": []}
      ```
      """
    When the harness reads the answer out of the text
    Then the answer is
      """
      {"verdict": "pass", "findings": []}
      """

  Scenario: A shape shown before the answer does not become the answer
    Given the agent answered
      """
      Here is the shape I will use:

      ```json
      {"requirements": [], "verifications": []}
      ```

      And here is the specification:

      ```json
      {"requirements": [{"id": "R1", "statement": "it subtracts"}], "verifications": []}
      ```
      """
    When the harness reads the answer out of the text
    Then the answer is
      """
      {"requirements": [{"id": "R1", "statement": "it subtracts"}], "verifications": []}
      """

  Scenario: The larger block is the answer wherever it sits
    Given the agent answered
      """
      The specification:

      ```json
      {"requirements": [{"id": "R1", "statement": "it subtracts"}], "verifications": []}
      ```

      which has the shape:

      ```json
      {"requirements": [], "verifications": []}
      ```
      """
    When the harness reads the answer out of the text
    Then the answer is
      """
      {"requirements": [{"id": "R1", "statement": "it subtracts"}], "verifications": []}
      """

  Scenario: A fence tagged jsonc is read like a fence tagged json
    Given the agent answered
      """
      The shape is {verdict, findings}:

      ```jsonc
      {"verdict": "pass", "findings": []}
      ```
      """
    When the harness reads the answer out of the text
    Then the answer is
      """
      {"verdict": "pass", "findings": []}
      """

  Scenario: An object written into the prose is read from the first brace to the last
    Given the agent answered
      """
      My verdict is {"verdict": "fail", "findings": [{"id": "F1"}]} and I stand by it.
      """
    When the harness reads the answer out of the text
    Then the answer is
      """
      {"verdict": "fail", "findings": [{"id": "F1"}]}
      """

  Scenario: Prose with no object in it carries no answer
    Given the agent answered
      """
      I could not review this change: the diff was empty and I had nothing to read.
      """
    When the harness reads the answer out of the text
    Then there is no answer

  Scenario: An answer cut off mid-object carries no answer
    Given the agent answered
      """
      ```json
      {"verdict": "pass", "findings": [{"id": "F1",
      """
    When the harness reads the answer out of the text
    Then there is no answer

  Scenario: A list is not an answer
    Given the agent answered
      """
      ```json
      [{"id": "F1"}, {"id": "F2"}]
      ```
      """
    When the harness reads the answer out of the text
    Then there is no answer

  Scenario: An empty answer carries no answer
    Given the agent answered nothing at all
    When the harness reads the answer out of the text
    Then there is no answer
