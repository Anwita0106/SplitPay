"""SplitPay AI agent — an orchestration layer, never a source of financial truth.

    User message
        -> intent parsing (deterministic fast-path) OR local Ollama tool-calling loop
        -> validated tool call
        -> deterministic backend service (GroupService / BalanceService / DraftService ...)
        -> PostgreSQL
        -> reply text rendered from backend data

Guarantees enforced HERE (and covered by tests):

* Groups are resolved ONCE, to a UUID, by `group_service.resolve_group`. Names are
  only ever a search phrase. Two groups with the same name are never guessed
  between — the user gets a clarification with selectable options.
* People are resolved against the real membership of the resolved group. "you",
  "me", "myself" and the user's own name are the SAME person and collapse into one
  participant. Unknown names are an error — no user is ever invented.
* Every balance sentence comes from `balance_service` (the one canonical balance
  engine) and is phrased for humans ("Anwita owes you ₹1200") — never a signed number.
* The agent has NO tool that writes to expenses / settlements. Writes are only
  *prepared* as server-side drafts (`draft_service`); the user's explicit click on
  POST /ai/drafts/{id}/confirm is the only thing that performs them.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.agent import (
    Clarification,
    ClarificationOption,
    ExpenseDraft,
    SettlementDraft,
)
from app.services import draft_service
from app.services.balance_service import GroupBalances, format_inr, get_group_balances, position_status
from app.services.group_service import (
    GroupChoice,
    GroupResolutionError,
    list_user_groups,
    members_of,
    normalize_text,
    resolve_group,
)
from app.services.settlement_service import coerce_amount

logger = logging.getLogger(__name__)

SELF_ALIASES = {"you", "yourself", "me", "myself", "i", "self", "my"}
ALL_ALIASES = {"everyone", "everybody", "all", "all of us", "us", "everyone else", "the group", "the whole group", "group"}


# ---------------------------------------------------------------------------
# Result / error types
# ---------------------------------------------------------------------------
@dataclass
class AgentResult:
    reply: str
    used_tools: list[str] = field(default_factory=list)
    mode: str = "deterministic"
    expense_draft: Optional[ExpenseDraft] = None
    settlement_draft: Optional[SettlementDraft] = None
    clarification: Optional[Clarification] = None


class ToolError(Exception):
    """A problem the user can act on (unknown member, ambiguous group, impossible settlement...)."""

    def __init__(self, message: str, clarification: Optional[Clarification] = None):
        super().__init__(message)
        self.message = message
        self.clarification = clarification


def _clarification(question: str, choices: list[GroupChoice]) -> Clarification:
    return Clarification(
        question=question,
        options=[ClarificationOption(label=c.label(), group_id=c.id) for c in choices],
    )


def _choices_from(groups: list[dict]) -> list[GroupChoice]:
    return [
        GroupChoice(id=g["id"], name=g["name"], member_names=g["member_names"], created_at=g["created_at"])
        for g in groups
    ]


def _to_tool_error(exc: Exception) -> ToolError:
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, GroupResolutionError):
        clar = _clarification(exc.message, exc.choices) if exc.choices else None
        return ToolError(exc.message, clar)
    if isinstance(exc, DomainError):
        return ToolError(str(exc.detail))
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        msg = str(errors[0].get("msg", "That request isn't valid.")) if errors else "That request isn't valid."
        return ToolError(msg.removeprefix("Value error, "))
    if isinstance(exc, ValueError):
        return ToolError(str(exc))
    raise exc


@dataclass
class Run:
    """Mutable state for one chat turn."""

    db: Session
    user: User
    context_group_id: Optional[UUID] = None
    used_tools: list[str] = field(default_factory=list)
    expense_draft: Optional[ExpenseDraft] = None
    settlement_draft: Optional[SettlementDraft] = None
    clarification: Optional[Clarification] = None


# ---------------------------------------------------------------------------
# People resolution (the "Anwi" / "You" / "Me" fix)
# ---------------------------------------------------------------------------
def resolve_person(raw: str, user: User, members: list[User], group_name: str) -> User:
    """
    Map a phrase to exactly one REAL member of the group.

    'you', 'me', 'myself' and the user's own name all mean the current user, so
    ["Anwi", "You", "me"] collapses to one person downstream. A first name matches a
    full name ("Anwita" -> "Anwita Sharma") only when that is unambiguous.
    """
    key = normalize_text(str(raw))
    if not key:
        raise ToolError("A participant name was empty.")
    if key in SELF_ALIASES or key == normalize_text(user.name):
        return user

    exact = [m for m in members if normalize_text(m.name) == key]
    candidates = exact or [m for m in members if set(key.split()) <= set(normalize_text(m.name).split())]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(m.name for m in candidates)
        raise ToolError(f"More than one member of {group_name} matches “{raw}” ({names}). Please use the full name.")
    roster = ", ".join(m.name for m in members)
    raise ToolError(f"I couldn't find “{raw}” in {group_name}. Members: {roster}.")


def _dedupe(users: list[User]) -> list[User]:
    seen: set[UUID] = set()
    out: list[User] = []
    for u in users:
        if u.id not in seen:  # stable DB identity, not object identity or spelling
            seen.add(u.id)
            out.append(u)
    return out


def parse_amount(raw: Any) -> Decimal:
    text = re.sub(r"(?i)(₹|rs\.?|inr|rupees?)", "", str(raw)).strip()
    return coerce_amount(text)


# ---------------------------------------------------------------------------
# Read tools (all data comes from the deterministic services)
# ---------------------------------------------------------------------------
def _names(members: list[User]) -> dict[UUID, str]:
    return {m.id: m.name for m in members}


def _position_dict(snapshot: GroupBalances, user: User, group_id: UUID, group_name: str, names: dict[UUID, str]) -> dict[str, Any]:
    """Human-readable position of `user` in one group. No signed numbers leave this function."""
    owed_to_you = [(names.get(d.from_user, "Someone"), d.amount) for d in snapshot.owed_to(user.id)]
    you_owe = [(names.get(d.to_user, "Someone"), d.amount) for d in snapshot.owed_by(user.id)]
    receivable = [f"{n} owes you {format_inr(a)} in {group_name}." for n, a in owed_to_you]
    payable = [f"You owe {n} {format_inr(a)} in {group_name}." for n, a in you_owe]
    return {
        "group_id": str(group_id),
        "group_name": group_name,
        "status": position_status(snapshot.position(user.id)),  # OWED | OWES | SETTLED
        "owed_to_you": [{"person": n, "amount": f"{a:.2f}", "display": format_inr(a)} for n, a in owed_to_you],
        "you_owe": [{"person": n, "amount": f"{a:.2f}", "display": format_inr(a)} for n, a in you_owe],
        "receivable_statements": receivable,
        "payable_statements": payable,
        "statements": receivable + payable or [f"You're all settled up in {group_name}."],
    }


def tool_list_groups(run: Run, args: dict) -> dict[str, Any]:
    groups = list_user_groups(run.db, run.user)
    return {"groups": [{"id": str(g["id"]), "name": g["name"], "members": g["member_names"]} for g in groups]}


def tool_my_balances(run: Run, args: dict) -> dict[str, Any]:
    results = []
    for g in list_user_groups(run.db, run.user):
        snapshot = get_group_balances(run.db, g["id"])  # fresh from PostgreSQL, never the cache
        names = _names(members_of(run.db, g["id"]))
        results.append(_position_dict(snapshot, run.user, g["id"], g["name"], names))
    return {"user": run.user.name, "groups": results}


def _resolve(run: Run, args: dict) -> Any:
    return resolve_group(
        run.db,
        run.user,
        group_id=args.get("group_id"),
        group_name=args.get("group_name"),
        context_group_id=run.context_group_id,
    )


def tool_group_summary(run: Run, args: dict) -> dict[str, Any]:
    group = _resolve(run, args)
    members = members_of(run.db, group.id)
    names = _names(members)
    snapshot = get_group_balances(run.db, group.id)
    expenses = (
        run.db.query(Expense).filter(Expense.group_id == group.id).order_by(Expense.created_at.desc()).limit(20).all()
    )
    return {
        "group": {"id": str(group.id), "name": group.name},
        "members": [{"id": str(m.id), "name": m.name} for m in members],
        "you": _position_dict(snapshot, run.user, group.id, group.name, names),
        "everyone": [
            f"{names.get(d.from_user, 'Someone')} owes {names.get(d.to_user, 'someone')} {format_inr(d.amount)}."
            for d in snapshot.debts
        ]
        or ["Everyone is settled up."],
        "recent_expenses": [
            {
                "description": e.description,
                "amount": format_inr(e.total_amount),
                "paid_by": names.get(e.paid_by, "Unknown"),
                "date": e.created_at.date().isoformat(),
            }
            for e in expenses
        ],
    }


def tool_spending(run: Run, args: dict) -> dict[str, Any]:
    per_group = []
    total_paid = Decimal("0")
    total_share = Decimal("0")
    expense_count = 0
    for g in list_user_groups(run.db, run.user):
        expenses = run.db.query(Expense).filter(Expense.group_id == g["id"]).all()
        ids = [e.id for e in expenses]
        paid = sum((Decimal(e.total_amount) for e in expenses if e.paid_by == run.user.id), Decimal("0"))
        share = Decimal("0")
        if ids:
            rows = (
                run.db.query(ExpenseSplit.amount)
                .filter(ExpenseSplit.expense_id.in_(ids), ExpenseSplit.user_id == run.user.id)
                .all()
            )
            share = sum((Decimal(r[0]) for r in rows), Decimal("0"))
        total_paid += paid
        total_share += share
        expense_count += len(expenses)
        per_group.append(
            {
                "group_id": str(g["id"]),
                "group_name": g["name"],
                "expenses": len(expenses),
                "you_paid": format_inr(paid),
                "your_share": format_inr(share),
            }
        )
    return {
        "total_paid": format_inr(total_paid),
        "total_share": format_inr(total_share),
        "expense_count": expense_count,
        "groups": per_group,
    }


def tool_settlements(run: Run, args: dict) -> dict[str, Any]:
    rows = (
        run.db.query(Settlement)
        .filter((Settlement.from_user == run.user.id) | (Settlement.to_user == run.user.id))
        .filter(Settlement.status.in_(["COMPLETED", "PROCESSING", "PENDING"]))
        .order_by(Settlement.created_at.desc())
        .limit(20)
        .all()
    )
    ids = {r.from_user for r in rows} | {r.to_user for r in rows}
    names = {u.id: u.name for u in run.db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    return {
        "settlements": [
            {
                "from": names.get(r.from_user, "Unknown"),
                "to": names.get(r.to_user, "Unknown"),
                "amount": format_inr(r.amount),
                "status": r.status,
                "method": r.method,
                "date": r.created_at.date().isoformat(),
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Draft-preparing tools (still read-only w.r.t. expenses / settlements)
# ---------------------------------------------------------------------------
def tool_prepare_expense(run: Run, args: dict) -> dict[str, Any]:
    group = _resolve(run, args)
    members = members_of(run.db, group.id)
    assumptions: list[str] = []

    split_type = str(args.get("split_type") or "EQUAL").upper()
    if split_type != "EQUAL":
        raise ToolError("I can only prepare equal splits. For exact amounts or percentages, use the Add Expense form.")

    raw_names = [n for n in (args.get("participant_names") or []) if str(n).strip()]
    if not raw_names or any(normalize_text(str(n)) in ALL_ALIASES for n in raw_names):
        participants = list(members)
        assumptions.append(f"Split equally among all {len(members)} members of {group.name}.")
    else:
        participants = _dedupe([resolve_person(n, run.user, members, group.name) for n in raw_names])

    paid_raw = args.get("paid_by_name")
    if paid_raw and normalize_text(str(paid_raw)):
        payer = resolve_person(paid_raw, run.user, members, group.name)
    else:
        payer = run.user
        assumptions.append("Paid by you.")

    description = " ".join(str(args.get("description") or "").split())[:255] or "Expense"
    amount = parse_amount(args.get("total_amount"))

    draft = draft_service.prepare_expense_draft(
        run.db, run.user, group=group, description=description, total_amount=amount,
        payer=payer, participants=participants, assumptions=assumptions,
    )
    run.expense_draft = draft
    return {
        "draft_prepared": True,
        "note": "Draft only — nothing is saved until the user presses Confirm.",
        "group": group.name,
        "paid_by": payer.name,
        "shares": [{"person": p.name, "amount": format_inr(p.amount)} for p in draft.participants],
    }


def _pair_limit(snapshot: GroupBalances, from_user: User, to_user: User) -> Decimal:
    """Largest amount `from_user` can currently settle with `to_user` (backend numbers only)."""
    for d in snapshot.debts:
        if d.from_user == from_user.id and d.to_user == to_user.id:
            return d.amount
    return min(-snapshot.position(from_user.id), snapshot.position(to_user.id))


def tool_prepare_settlement(run: Run, args: dict) -> dict[str, Any]:
    group = _resolve(run, args)
    members = members_of(run.db, group.id)
    from_user = resolve_person(args.get("from_name", ""), run.user, members, group.name)
    to_user = resolve_person(args.get("to_name", ""), run.user, members, group.name)
    if from_user.id == to_user.id:
        raise ToolError("The payer and the receiver must be different people.")

    raw_amount = args.get("amount")
    if raw_amount in (None, "", "all", "full"):
        snapshot = get_group_balances(run.db, group.id, include_in_flight=True)
        amount = _pair_limit(snapshot, from_user, to_user)
        if amount <= 0:
            raise ToolError(f"{from_user.name} doesn't currently owe {to_user.name} anything in {group.name}.")
    else:
        amount = parse_amount(raw_amount)

    draft = draft_service.prepare_settlement_draft(
        run.db, run.user, group=group, from_user=from_user, to_user=to_user, amount=amount
    )
    run.settlement_draft = draft
    return {
        "draft_prepared": True,
        "note": "Draft only — nothing is recorded until the user presses Confirm.",
        "group": group.name,
        "from": from_user.name,
        "to": to_user.name,
        "amount": format_inr(draft.amount),
    }


READ_TOOLS = {
    "list_groups": tool_list_groups,
    "get_my_balances": tool_my_balances,
    "get_group_summary": tool_group_summary,
    "get_spending_summary": tool_spending,
    "get_settlements": tool_settlements,
}
DRAFT_TOOLS = {
    "prepare_expense_draft": tool_prepare_expense,
    "prepare_settlement_draft": tool_prepare_settlement,
}
# Kept public so the UI / docs / tests can show which tools only read and which prepare drafts.
TOOL_KIND = {**{k: "read" for k in READ_TOOLS}, **{k: "draft" for k in DRAFT_TOOLS}}


def execute_tool(name: str, arguments: dict[str, Any], run: Run) -> dict[str, Any]:
    """Run one tool. Unknown tools are refused — there is deliberately no write/confirm tool."""
    fn = READ_TOOLS.get(name) or DRAFT_TOOLS.get(name)
    if fn is None:
        raise ToolError(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise ToolError("Tool arguments must be an object.")
    try:
        result = fn(run, arguments)
    except Exception as exc:  # noqa: BLE001 — translated (or re-raised if unexpected)
        run.db.rollback()
        raise _to_tool_error(exc) from exc
    run.used_tools.append(name)
    return result


def _run_tool_safely(name: str, arguments: dict[str, Any], run: Run) -> dict[str, Any]:
    try:
        return execute_tool(name, arguments, run)
    except ToolError as err:
        if err.clarification is not None:
            run.clarification = err.clarification
        return {"error": err.message}


# ---------------------------------------------------------------------------
# Deterministic intents
# ---------------------------------------------------------------------------
_QUESTION_START = re.compile(r"^\s*(who|what|how|when|which|where|why|did|do|does|is|are|can|could|show|list|tell)\b", re.I)
_CONFIRM_TOKENS = {
    "yes", "yep", "yeah", "yup", "confirm", "confirmed", "ok", "okay", "sure", "go", "ahead", "do", "it",
    "approve", "proceed", "please", "save", "this", "that", "the", "draft", "settlement",
}


def _is_confirmation_phrase(text: str) -> bool:
    """'yes', 'yes confirm', 'ok go ahead' ... — replies that try to confirm a draft by chat."""
    tokens = normalize_text(text).split()
    return bool(tokens) and all(t in _CONFIRM_TOKENS for t in tokens)
_SETTLE_RE = re.compile(
    r"\b(settle|settled|settling|settlement|pay\s+back|paid\s+back|paid\s+me\s+back|repay|repaid|clear\s+(?:the\s+)?(?:debt|dues?))\b", re.I
)
_EXPENSE_VERB_RE = re.compile(r"\b(paid|spent|bought|add(?:ed)?\s+(?:an?\s+)?expense|expense\s+of|split)\b", re.I)
_SPEND_RE = re.compile(r"\b(spend|spent|spending|expenses?)\b", re.I)
_BALANCE_RE = re.compile(r"\b(owe|owes|owed|balance|balances|debt|debts|dues?|settled up|pay\s+back)\b|who do i|how much", re.I)
_UNEQUAL_RE = re.compile(r"(%|percent|percentage|exact(?:ly)?|unequal|\b\d+\s*/\s*\d+\b)", re.I)
_NUMBER = r"\d[\d,]*(?:\.\d+)?"


def _first_amount(text: str) -> Optional[str]:
    m = re.search(rf"(?:₹|rs\.?\s*|inr\s*)({_NUMBER})", text, re.I) or re.search(
        rf"({_NUMBER})\s*(?:₹|rs\b|rupees?|inr\b)", text, re.I
    )
    if m:
        return m.group(1)
    m = re.search(rf"(?<![\w.]){_NUMBER}(?!\w)", text)
    return m.group(0) if m else None


def _mentioned_group_name(groups: list[dict], text: str) -> tuple[Optional[str], list[dict]]:
    """
    Find a group NAME in free text (longest full-name match wins). Returns (name, candidates).
    Identically-named groups are all candidates — resolve_group decides or asks.
    `name is None` with several candidates means genuinely different groups were mentioned.
    """
    padded = f" {normalize_text(text)} "
    hits = [g for g in groups if normalize_text(g["name"]) and f" {normalize_text(g['name'])} " in padded]
    if not hits:
        return None, []
    names = {normalize_text(g["name"]) for g in hits}
    names = {n for n in names if not any(n != o and f" {n} " in f" {o} " for o in names)}
    if len(names) > 1:
        return None, [g for g in hits if normalize_text(g["name"]) in names]
    only = next(iter(names))
    chosen = [g for g in hits if normalize_text(g["name"]) == only]
    return chosen[0]["name"], chosen


def _fallback_group_phrase(text: str) -> Optional[str]:
    """'... in Goa' / '... in the Goa Trip group' when no full group name matched."""
    m = re.search(
        r"\bin\s+(?:the\s+)?([A-Za-z0-9][\w' -]{1,40}?)(?:\s+group)?\s*(?=[.,?!]|\bsplit\b|\bequally\b|$)", text, re.I
    )
    return m.group(1).strip() if m else None


def _strip_group_mention(text: str, group_name: Optional[str]) -> str:
    if not group_name:
        return text
    pattern = rf"(?:\b(?:in|at|on|for|from|of|within)\s+)?(?:the\s+)?{re.escape(group_name)}(?:\s+group)?"
    return re.sub(pattern, " ", text, flags=re.I)


def _group_hint(groups: list[dict], text: str) -> tuple[Optional[str], bool]:
    """(name to search for, whether the message points at a specific group at all)."""
    name, candidates = _mentioned_group_name(groups, text)
    if name is None and len(candidates) > 1:
        raise ToolError(
            "Which group do you mean?", _clarification("Which group do you mean?", _choices_from(candidates))
        )
    if name is None:
        name = _fallback_group_phrase(text)
    return name, name is not None


def _resolve_group_for_text(run: Run, text: str) -> Any:
    groups = list_user_groups(run.db, run.user)
    name, _ = _group_hint(groups, text)
    try:
        return resolve_group(run.db, run.user, group_name=name, context_group_id=run.context_group_id)
    except GroupResolutionError as exc:
        raise _to_tool_error(exc) from exc


def _split_names(segment: str) -> list[str]:
    parts = re.split(r"\s*(?:,|&|\+|\band\b)\s*", segment.strip(), flags=re.I)
    return [p.strip(" .'\"") for p in parts if p.strip(" .'\"")]


# ---- expense ---------------------------------------------------------------
def _parse_expense_text(text: str) -> dict[str, Any]:
    t = " ".join(text.split())
    amount = _first_amount(t)
    payer: Optional[str] = None
    if not (re.match(r"^\s*(?:i|me)\b.*?\b(?:paid|spent|bought)\b", t, re.I) or re.match(r"^\s*(?:add|record|log)\b", t, re.I)):
        m = re.match(r"^\s*(?:hey,?\s*|note that\s*)?([A-Za-z][\w']*)\s+(?:paid|spent|bought)\b", t, re.I)
        if m and m.group(1).lower() not in {"who", "we", "he", "she", "they", "it", "please", "somebody", "someone"}:
            payer = m.group(1)
    m = re.search(r"\bpaid by\s+([A-Za-z][\w']*)", t, re.I)
    if m:
        payer = m.group(1)

    after_amount = t
    if amount:
        idx = t.find(amount)
        after_amount = t[idx + len(amount):] if idx >= 0 else t
    dm = re.search(
        r"\b(?:for|on)\s+(?:an?\s+|the\s+)?(.+?)(?=\s+(?:with|between|among|amongst|split|shared|paid|at|equally|and\s+split)\b|[.,;!?]|$)",
        after_amount, re.I,
    )
    description = dm.group(1).strip() if dm else ""
    description = description[:1].upper() + description[1:] if description else "Expense"

    participants: list[str] = []
    include_self = False
    pm = re.search(
        r"\b(with|between|among|amongst|shared by|split by|split with|split between)\s+(.+?)"
        r"(?=\s*(?:[.;!?]|\bsplit\b|\bequally\b|\bin\b|\bfor\b|\bpaid\b|\bon\b)|$)",
        after_amount, re.I,
    )
    if pm:
        participants = _split_names(pm.group(2))
        include_self = pm.group(1).lower() == "with"
    return {"amount": amount, "payer": payer, "description": description, "participants": participants, "include_self": include_self}


def _who_owes_lines(d: ExpenseDraft) -> str:
    return "\n".join(
        f"{p.name} will owe {d.paid_by_name} {format_inr(p.amount)}."
        for p in d.participants
        if p.user_id != d.expense.paid_by and p.amount > 0
    )


def _expense_reply(d: ExpenseDraft) -> str:
    split_lines = "\n".join(f"• {p.name}: {format_inr(p.amount)}" for p in d.participants)
    who_owes = _who_owes_lines(d)
    return (
        f"I've prepared an expense draft for {d.group_name}: {d.expense.description} — "
        f"{format_inr(d.expense.total_amount)}, paid by {d.paid_by_name}, split equally.\n{split_lines}"
        + (f"\n{who_owes}" if who_owes else "")
        + "\nNothing is saved yet — press Confirm to add it, or Cancel."
    )


def _intent_expense(run: Run, text: str) -> AgentResult:
    groups = list_user_groups(run.db, run.user)
    mentioned, _ = _mentioned_group_name(groups, text)
    group = _resolve_group_for_text(run, text)
    parsed = _parse_expense_text(_strip_group_mention(text, mentioned))
    if not parsed["amount"]:
        raise ToolError("How much was the expense? Please include the amount, e.g. “I paid ₹2400 for dinner in Goa Trip”.")
    if _UNEQUAL_RE.search(re.sub(_NUMBER, "", text)) and not re.search(r"\bequal", text, re.I):
        raise ToolError("I can only prepare equal splits. For exact amounts or percentages, use the Add Expense form.")

    names = list(parsed["participants"])
    if parsed["include_self"] and not any(
        normalize_text(n) in SELF_ALIASES or normalize_text(n) == normalize_text(run.user.name) for n in names
    ):
        names = ["me"] + names  # "dinner with X" means the speaker shared it too
    tool_prepare_expense(
        run,
        {
            "group_id": str(group.id),  # from here on the UUID is the only handle used
            "description": parsed["description"],
            "total_amount": parsed["amount"],
            "split_type": "EQUAL",
            "participant_names": names,
            "paid_by_name": parsed["payer"],
        },
    )
    run.used_tools.append("prepare_expense_draft")
    d = run.expense_draft
    assert d is not None
    return AgentResult(reply=_expense_reply(d), used_tools=run.used_tools, expense_draft=d)


# ---- balances --------------------------------------------------------------
def _balance_focus(text: str) -> str:
    t = text.lower()
    if re.search(r"who\s+owes\s+me|owes\s+me|owe\s+me|owed\s+to\s+me|money\s+back|get\s+back|receiv", t):
        return "receivable"
    if re.search(r"who\s+do\s+i\s+owe|do\s+i\s+owe|i\s+owe|what\s+i\s+owe|owe\s+anyone|how\s+much\s+i\s+owe", t):
        return "payable"
    return "both"


def _intent_balance(run: Run, text: str) -> AgentResult:
    focus = _balance_focus(text)
    groups = list_user_groups(run.db, run.user)
    _, scoped = _group_hint(groups, text)
    scoped = scoped or run.context_group_id is not None
    if scoped:
        group = _resolve_group_for_text(run, text)
        entries = [tool_group_summary(run, {"group_id": str(group.id)})["you"]]
        run.used_tools.append("get_group_summary")
    else:
        entries = tool_my_balances(run, {})["groups"]
        run.used_tools.append("get_my_balances")
        if not entries:
            return AgentResult(reply="You aren't a member of any group yet.", used_tools=run.used_tools)

    lines: list[str] = []
    for e in entries:
        gname = e["group_name"]
        if focus == "receivable":
            lines += e["receivable_statements"] or [f"No one currently owes you money in {gname}."]
        elif focus == "payable":
            lines += e["payable_statements"] or [f"You don't currently owe anyone in {gname}."]
        else:
            lines += e["receivable_statements"] + e["payable_statements"] or [f"You're all settled up in {gname}."]

    if not scoped:  # one summary line instead of N identical "nothing" lines
        if focus == "receivable" and not any(e["receivable_statements"] for e in entries):
            lines = ["No one currently owes you money in any of your groups."]
        elif focus == "payable" and not any(e["payable_statements"] for e in entries):
            lines = ["You don't currently owe anyone in any of your groups."]
        elif focus == "both" and not any(e["receivable_statements"] or e["payable_statements"] for e in entries):
            lines = ["You're all settled up in every group."]
    return AgentResult(reply="\n".join(lines), used_tools=run.used_tools)


# ---- spending --------------------------------------------------------------
def _intent_spending(run: Run, text: str) -> AgentResult:
    data = tool_spending(run, {})
    run.used_tools.append("get_spending_summary")
    if data["expense_count"] == 0:
        return AgentResult(reply="There are no expenses recorded in your groups yet.", used_tools=run.used_tools)
    n = data["expense_count"]
    lines = [
        f"Across {n} expense{'s' if n != 1 else ''}, you've paid {data['total_paid']} "
        f"and your share of them is {data['total_share']}."
    ]
    lines += [
        f"• {g['group_name']}: paid {g['you_paid']}, your share {g['your_share']} ({g['expenses']} expenses)"
        for g in data["groups"] if g["expenses"]
    ]
    return AgentResult(reply="\n".join(lines), used_tools=run.used_tools)


# ---- settlement ------------------------------------------------------------
def _settlement_reply(d: SettlementDraft) -> str:
    return (
        f"Settlement draft for {d.group_name}: {d.from_name} → {d.to_name}, {format_inr(d.amount)}.\n"
        "This records that the money was paid outside SplitPay. Nothing is recorded yet — press Confirm, or Cancel."
    )


def _intent_settlement(run: Run, text: str) -> AgentResult:
    groups = list_user_groups(run.db, run.user)
    hint, explicit = _group_hint(groups, text)
    if explicit or run.context_group_id is not None or len(groups) == 1:
        group = _resolve_group_for_text(run, text)
    else:
        # No group named: only groups where this user actually has something to settle are candidates.
        open_groups = []
        for g in groups:
            snap = get_group_balances(run.db, g["id"], include_in_flight=True)
            if snap.owed_to(run.user.id) or snap.owed_by(run.user.id):
                open_groups.append(g)
        if not open_groups:
            return AgentResult(reply="You don't have anything to settle right now — you're all settled up.", used_tools=run.used_tools)
        if len(open_groups) > 1:
            raise ToolError(
                "Which group do you want to settle in?",
                _clarification("Which group do you want to settle in?", _choices_from(open_groups)),
            )
        run.context_group_id = open_groups[0]["id"]  # unambiguous: resolved by UUID, not by name
        group = resolve_group(run.db, run.user, context_group_id=run.context_group_id)

    members = members_of(run.db, group.id)
    snapshot = get_group_balances(run.db, group.id, include_in_flight=True)
    body = _strip_group_mention(text, hint or group.name)
    body_norm = normalize_text(body)

    # Who is the other party?
    others = _dedupe([
        m for m in members
        if m.id != run.user.id and re.search(rf"\b{re.escape(normalize_text(m.name).split()[0])}\b", body_norm)
    ])
    if len(others) > 1:
        raise ToolError("Please settle with one person at a time — who do you mean? " + ", ".join(m.name for m in others))
    if len(others) == 1:
        counterparty = others[0]
    else:
        related = {d.from_user for d in snapshot.owed_to(run.user.id)} | {d.to_user for d in snapshot.owed_by(run.user.id)}
        if not related:
            return AgentResult(
                reply=f"You don't have anything to settle in {group.name} — you're all settled up.", used_tools=run.used_tools
            )
        if len(related) > 1:
            roster = ", ".join(m.name for m in members if m.id in related)
            raise ToolError(f"Who do you want to settle with in {group.name}? ({roster})")
        counterparty = next(m for m in members if m.id in related)

    # Direction: the wording first ("X owes me", "I owe X", "I paid X"), backend balances otherwise.
    first = re.escape(normalize_text(counterparty.name).split()[0])
    if re.search(rf"\b{first}\s+(owes|owe|paid|pays)\b", body_norm) and re.search(r"\b(me|us)\b", body_norm):
        from_user, to_user = counterparty, run.user
    elif re.search(r"\bi\s+(owe|paid|pay|gave|sent)\b", body_norm) or re.search(rf"\b(pay|paid|give)\s+{first}\b", body_norm):
        from_user, to_user = run.user, counterparty
    elif any(d.from_user == counterparty.id and d.to_user == run.user.id for d in snapshot.debts):
        from_user, to_user = counterparty, run.user
    elif any(d.from_user == run.user.id and d.to_user == counterparty.id for d in snapshot.debts):
        from_user, to_user = run.user, counterparty
    else:
        return AgentResult(
            reply=f"There's nothing to settle between you and {counterparty.name} in {group.name} right now.",
            used_tools=run.used_tools,
        )

    tool_prepare_settlement(
        run,
        {
            "group_id": str(group.id),
            "from_name": from_user.name if from_user.id != run.user.id else "me",
            "to_name": to_user.name if to_user.id != run.user.id else "me",
            "amount": _first_amount(body),
        },
    )
    run.used_tools.append("prepare_settlement_draft")
    d = run.settlement_draft
    assert d is not None
    return AgentResult(reply=_settlement_reply(d), used_tools=run.used_tools, settlement_draft=d)


def _deterministic(run: Run, message: str) -> Optional[AgentResult]:
    """Return a result for well-defined intents, or None to let the model handle the message."""
    text = message.strip()
    if _is_confirmation_phrase(text):
        return AgentResult(
            reply="I can't confirm anything myself. Please press the Confirm button on the draft card — nothing is saved until you do.",
        )
    has_amount = _first_amount(text) is not None
    is_question = bool(_QUESTION_START.match(text)) or text.endswith("?")

    if _SETTLE_RE.search(text) and not re.match(r"^\s*(what|how|why)\b", text, re.I):
        return _intent_settlement(run, text)
    if has_amount and _EXPENSE_VERB_RE.search(text) and not is_question:
        return _intent_expense(run, text)
    if _SPEND_RE.search(text) and re.search(r"\b(how much|total|my|summary|so far)\b", text, re.I) and not has_amount:
        return _intent_spending(run, text)
    if _BALANCE_RE.search(text) and not has_amount:
        return _intent_balance(run, text)
    return None


# ---------------------------------------------------------------------------
# LLM path (Ollama tool calling)
# ---------------------------------------------------------------------------
TOOLS = [
    {"type": "function", "function": {"name": "list_groups",
        "description": "List the groups the current user belongs to (id, name, members).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_my_balances",
        "description": "Exact balances of the current user across ALL groups, already phrased for humans. Use for 'who owes me', 'who do I owe', 'my balance'.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_group_summary",
        "description": "Members, recent expenses and exact balances of ONE group. Pass the group name the user said; the backend resolves it to a UUID.",
        "parameters": {"type": "object", "properties": {
            "group_id": {"type": "string", "description": "Group UUID, only if you were given one"},
            "group_name": {"type": "string", "description": "Group name as the user said it"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_spending_summary",
        "description": "Totals the current user paid and their share, per group.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_settlements",
        "description": "Settlements involving the current user.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "prepare_expense_draft",
        "description": "Prepare (NOT save) an equal-split expense draft. participant_names must list everyone sharing it; 'you'/'me' mean the current user. Never invent names.",
        "parameters": {"type": "object", "properties": {
            "group_id": {"type": "string"}, "group_name": {"type": "string"},
            "description": {"type": "string"}, "total_amount": {"type": "string"},
            "split_type": {"type": "string", "enum": ["EQUAL"]},
            "participant_names": {"type": "array", "items": {"type": "string"}},
            "paid_by_name": {"type": "string"}},
            "required": ["description", "total_amount", "participant_names"]}}},
    {"type": "function", "function": {"name": "prepare_settlement_draft",
        "description": "Prepare (NOT record) a settlement draft: from_name pays to_name. Omit amount to settle the full outstanding amount between them.",
        "parameters": {"type": "object", "properties": {
            "group_id": {"type": "string"}, "group_name": {"type": "string"},
            "from_name": {"type": "string"}, "to_name": {"type": "string"}, "amount": {"type": "string"}},
            "required": ["from_name", "to_name"]}}},
]

SYSTEM_PROMPT = """You are SplitPay AI, a concise assistant inside an expense-sharing app.
Rules:
- Never invent amounts, people, groups or transactions. Answer account questions ONLY from tool results.
- Tool results contain ready-made sentences ("statements"). Repeat them; do not recalculate or rephrase amounts.
- Never mention negative numbers. Say who owes whom, e.g. "Anwita owes you ₹1200".
- You cannot save anything. prepare_expense_draft / prepare_settlement_draft only create a draft that the user must confirm with a button.
- Never claim an expense or settlement was saved.
- For 'who owes me', 'who do I owe', 'my balance' use get_my_balances (or get_group_summary when a group is named).
- Pass group NAMES as the user typed them; the backend resolves the group. If a tool reports an ambiguous or missing group, tell the user and ask.
- If required details (amount, group, who paid) are missing, ask a short question instead of guessing.
Keep answers short."""


def _draft_reply(run: Run) -> Optional[str]:
    if run.expense_draft:
        return _expense_reply(run.expense_draft)
    if run.settlement_draft:
        return _settlement_reply(run.settlement_draft)
    return None


def _llm_chat(run: Run, message: str, conversation: list[dict[str, str]]) -> AgentResult:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in conversation[-10:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"][:4000]})
    messages.append({"role": "user", "content": message})

    def finish(content: str) -> AgentResult:
        return AgentResult(
            reply=_draft_reply(run) or content,  # drafts are always described from backend data, never model text
            used_tools=run.used_tools, mode="llm", expense_draft=run.expense_draft,
            settlement_draft=run.settlement_draft, clarification=run.clarification,
        )

    try:
        with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
            for _ in range(6):
                response = client.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                    json={"model": settings.OLLAMA_MODEL, "messages": messages, "tools": TOOLS, "stream": False},
                )
                response.raise_for_status()
                msg = response.json().get("message", {})
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    return finish(msg.get("content") or "I couldn't generate a response.")
                messages.append(msg)
                for call in tool_calls:
                    fn = call.get("function", {})
                    arguments = fn.get("arguments") or {}
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}
                    result = _run_tool_safely(fn.get("name", ""), arguments, run)
                    messages.append({"role": "tool", "content": json.dumps(result, default=str)})
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Ollama unavailable: %s", exc)
        return AgentResult(
            reply=(
                "SplitPay AI isn't connected to the local model right now. Start Ollama and make sure "
                f"“{settings.OLLAMA_MODEL}” is downloaded, then try again. "
                "(Balance questions, expense drafts and settlements phrased directly still work without it.)"
            ),
            used_tools=run.used_tools, mode="llm",
        )
    return finish("I couldn't finish that request. Please try again.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def chat(
    db: Session,
    user: User,
    message: str,
    conversation: list[dict[str, str]],
    context_group_id: Optional[UUID] = None,
) -> AgentResult:
    run = Run(db=db, user=user, context_group_id=context_group_id)

    if settings.AI_DETERMINISTIC_INTENTS:
        try:
            result = _deterministic(run, message)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            err = _to_tool_error(exc)  # re-raises anything that isn't a user-actionable problem
            return AgentResult(reply=err.message, used_tools=run.used_tools, clarification=err.clarification)
        if result is not None:
            return result
    return _llm_chat(run, message, conversation)
