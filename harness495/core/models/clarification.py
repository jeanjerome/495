"""The decisions taken before the specification: the questions, the answers and the rounds.

``Clarification`` is what the phase leaves on the run, round by round, with the questions
nobody was asked kept rather than dropped. ``DecisionTaken`` is how the specification carries
one of those decisions, so that the artifact the requester approves states what it was written
under.
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from harness495.core.models.base import StrictModel, utcnow
from harness495.core.models.enums import DecisionMaker


class ClarifyOption(StrictModel):
    """One answer a question offers, and what taking it does to the specification.

    ``consequence`` is the whole point of the option: which requirement appears or disappears,
    which verification changes kind. An option that states none says nothing about what is
    being decided, and its question is dropped rather than put to the requester.
    """

    key: str
    label: str
    consequence: str = ""


class ClarifyQuestion(StrictModel):
    """One decision the intent leaves open, as the clarifier puts it.

    ``checked`` is what the clarifier read or ran to reach ``recommended``: a question whose
    answer is in the repository then shows as one, in front of the requester, instead of
    resting on the prompt. The harness completes ``options`` with ``other``, which takes a
    note, so that the tree never forces a false choice.
    """

    id: str
    title: str
    body: str = ""
    options: list[ClarifyOption] = Field(default_factory=list)
    recommended: str = ""
    checked: list[str] = Field(default_factory=list)

    def option(self, key: str) -> ClarifyOption | None:
        for o in self.options:
            if o.key == key:
                return o
        return None


class ClarifyAnswer(StrictModel):
    """What was decided on one question, and by whom.

    ``recommended`` says whether the answer is the one the clarifier advised, and ``taken_by``
    whether the requester chose it or the harness took it on their behalf under
    ``--auto-approve``; the report shows both, because they are not the same record.
    """

    question_id: str
    question: str
    option: str
    label: str = ""
    note: str = ""
    recommended: bool = False
    taken_by: DecisionMaker = DecisionMaker.human
    answered_at: dt.datetime = Field(default_factory=utcnow)

    @property
    def statement(self) -> str:
        """The decision in one sentence, as the later roles read it."""
        chosen = self.label or self.option
        return f"{self.question} — {chosen}" + (f": {self.note}" if self.note else "")


class ClarifyRound(StrictModel):
    """One intervention of the clarification: the frontier it returned, and the answers.

    ``dropped`` names what the harness took out of the round and why — a question already
    settled, one with fewer than two options, one whose option states no consequence. The
    round holds only what was actually put to the requester.
    """

    n: int
    intervention_id: str
    questions: list[ClarifyQuestion] = Field(default_factory=list)
    answers: list[ClarifyAnswer] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    asked_at: dt.datetime = Field(default_factory=utcnow)

    def question(self, qid: str) -> ClarifyQuestion | None:
        for q in self.questions:
            if q.id == qid:
                return q
        return None


class Clarification(StrictModel):
    """The decisions taken before the specification, round by round.

    ``open_questions`` are the ones the last round returned and nobody was asked: the round cap
    was reached, so the frontier was not empty when the phase ended. They are recorded rather
    than dropped, so that the specifier states an assumption knowing it stands on a question
    that was never put.
    """

    rounds: list[ClarifyRound] = Field(default_factory=list)
    open_questions: list[ClarifyQuestion] = Field(default_factory=list)
    complete: bool = False
    stopped_at_cap: bool = False

    @property
    def answers(self) -> list[ClarifyAnswer]:
        return [a for r in self.rounds for a in r.answers]

    def answered(self, question: ClarifyQuestion) -> ClarifyAnswer | None:
        """The answer a question already has, matched on its id or on its words.

        Both, because the clarifier chooses the ids: the same decision can come back under a
        new id, and a fresh decision can reuse one. Either match settles it.
        """
        title = normalise_question(question.title)
        for a in self.answers:
            if a.question_id == question.id or normalise_question(a.question) == title:
                return a
        return None

    @property
    def rounds_answered(self) -> int:
        return sum(1 for r in self.rounds if r.answers)

    @property
    def says_anything(self) -> bool:
        """Whether the phase left the later roles something to read.

        A round that came back with an empty frontier settled nothing and left nothing: telling
        the specifier that no decision was taken is not a fact, it is a blank section.
        """
        return bool(self.answers or self.open_questions)


def normalise_question(text: str) -> str:
    """A question reduced to its words, for telling one already answered from a new one."""
    return " ".join(text.lower().split()).strip(" ?.:;!")


class DecisionTaken(StrictModel):
    """One requester's decision as the specification carries it: what was asked, what was
    chosen among what was offered, and who chose.

    Kept on the specification rather than read back from the run, so that the artifact the
    requester approves and the reviewers are given states the decisions it was written under.
    """

    question: str
    options: list[str] = Field(default_factory=list)
    choice: str
    note: str = ""
    taken_by: DecisionMaker = DecisionMaker.human


class ClarifyReply(StrictModel):
    """One answer as the requester gives it: which option, and the note an ``other`` needs."""

    question_id: str
    option: str
    note: str = ""


class DecisionAnswer(StrictModel):
    """What an interface hands back when it has put a pending decision to the requester.

    ``answers`` is empty for every decision that is one question; a ``clarify`` round carries
    one reply per question of the round.
    """

    choice: str
    note: str = ""
    answers: list[ClarifyReply] = Field(default_factory=list)
