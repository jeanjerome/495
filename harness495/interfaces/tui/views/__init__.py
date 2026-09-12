"""One builder per stop of the pipeline, plus the two views that are not stages.

Every stage view has the same shape — headline · list · detail — so the eye learns one screen
and then reads six more for free. All of them take a :class:`ViewContext` and return a
:class:`StageContent`; none of them knows about the shell that draws it.
"""

from collections.abc import Callable

from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.views.change import build_change
from harness495.interfaces.tui.views.checks import build_checks
from harness495.interfaces.tui.views.decision import ask_decision, decision_panel
from harness495.interfaces.tui.views.deliver import build_deliver
from harness495.interfaces.tui.views.help import help_view
from harness495.interfaces.tui.views.integration import build_integration
from harness495.interfaces.tui.views.intent import ask_intent
from harness495.interfaces.tui.views.log import build_log
from harness495.interfaces.tui.views.profile import build_profile
from harness495.interfaces.tui.views.review import build_review
from harness495.interfaces.tui.views.runs import build_runs
from harness495.interfaces.tui.views.spec import build_spec
from harness495.interfaces.tui.views.verdict import build_verdict

#: The stage views, by the name the pipeline gives that stop.
STAGE_VIEWS: dict[str, Callable[[ViewContext], StageContent]] = {
    "profile": build_profile,
    "spec": build_spec,
    "change": build_change,
    "checks": build_checks,
    "review": build_review,
    "verdict": build_verdict,
    "deliver": build_deliver,
    "integration": build_integration,
}

__all__ = [
    "STAGE_VIEWS",
    "StageContent",
    "ViewContext",
    "ask_decision",
    "ask_intent",
    "build_log",
    "build_runs",
    "decision_panel",
    "help_view",
]
