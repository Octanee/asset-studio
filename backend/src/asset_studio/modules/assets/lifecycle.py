"""The asset-version lifecycle state machine (Asset-Lifecycle, T-01 to T-13).

Pure rules with no database access, so they can be tested exhaustively.
"""

from dataclasses import dataclass
from typing import Literal, get_args

StateName = Literal[
    "generated",
    "processing",
    "processing_failed",
    "awaiting_review",
    "approved",
    "rejected",
    "published",
    "archived",
    "deleted",
]
STATES: tuple[str, ...] = get_args(StateName)
# Who may run a transition. "decider" = the user, or MCP when the project allows it (RULE-005).
Policy = Literal["user", "decider", "system", "user_or_system"]

ARCHIVABLE: frozenset[str] = frozenset(
    {"generated", "awaiting_review", "approved", "rejected", "published", "processing_failed"}
)


@dataclass(frozen=True)
class Transition:
    id: str
    action: str
    sources: frozenset[str]
    target: str | None  # None = "the state before archiving" (T-12)
    policy: Policy
    reason_required: bool = False


TRANSITIONS: dict[str, Transition] = {
    t.action: t
    for t in [
        Transition("T-02", "start_processing", frozenset({"generated"}), "processing", "system"),
        Transition(
            "T-03", "processing_succeeded", frozenset({"processing"}), "awaiting_review", "system"
        ),
        Transition(
            "T-04", "processing_failed", frozenset({"processing"}), "processing_failed", "system"
        ),
        Transition(
            "T-04R",
            "retry_processing",
            frozenset({"processing_failed"}),
            "processing",
            "user_or_system",
        ),
        Transition("T-05", "approve", frozenset({"awaiting_review"}), "approved", "decider"),
        Transition("T-06", "reject", frozenset({"awaiting_review"}), "rejected", "decider"),
        Transition("T-07", "reopen", frozenset({"rejected"}), "awaiting_review", "user"),
        Transition(
            "T-08",
            "withdraw",
            frozenset({"approved"}),
            "awaiting_review",
            "user",
            reason_required=True,
        ),
        Transition("T-09", "publish", frozenset({"approved"}), "published", "decider"),
        Transition("T-10", "republish", frozenset({"published"}), "published", "user"),
        Transition("T-11", "archive", ARCHIVABLE, "archived", "user"),
        Transition("T-12", "restore", frozenset({"archived"}), None, "user"),
        Transition("T-13", "delete", frozenset({"rejected", "archived"}), "deleted", "user"),
    ]
}

# Actions a client may request through POST /versions/{id}/transitions.
ClientAction = Literal[
    "approve", "reject", "reopen", "withdraw", "archive", "restore", "retry_processing"
]


def actor_allowed(policy: Policy, actor: str, *, mcp_can_decide: bool) -> bool:
    if policy == "system":
        return actor == "system"
    if policy == "user_or_system":
        return actor in ("user", "system")
    if policy == "decider":
        return actor == "user" or (actor == "mcp" and mcp_can_decide)
    return actor == "user"
