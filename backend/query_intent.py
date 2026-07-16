"""
Detect COUNT vs LIST intent and the target entity (user, device, etc.).
Injects mandatory SQL patterns into the LLM prompt and validates generated SQL
so count/list pairs stay consistent (same JOIN path, correct DISTINCT target).
"""

import re
from dataclasses import dataclass
from enum import Enum


class QueryMode(str, Enum):
    COUNT = "count"
    LIST = "list"
    OTHER = "other"


class EntityType(str, Enum):
    USER = "user"
    DEVICE = "device"
    CUSTOMER = "customer"
    SOFTWARE = "software"
    UNKNOWN = "unknown"


@dataclass
class QueryIntent:
    mode: QueryMode
    entity: EntityType
    hint: str


_COUNT_WORDS = re.compile(
    r"\b(count|how many|number of|total|how much|what is the count)\b", re.I
)
_LIST_WORDS = re.compile(
    r"\b(list|show|display|give me|get|name|names|who are|which are)\b", re.I
)
_USER_WORDS = re.compile(r"\b(user|users|username|usernames|employee|employees|people)\b", re.I)
_DEVICE_WORDS = re.compile(
    r"\b(device|devices|machine|machines|endpoint|endpoints|computer|laptop|server)\b", re.I
)
_CUSTOMER_WORDS = re.compile(r"\b(customer|customers|client|clients|organization)\b", re.I)
_SOFTWARE_WORDS = re.compile(r"\b(software|application|applications|app|apps|program)\b", re.I)


def _detect_mode(question: str) -> QueryMode:
    q = question.lower()
    has_count = bool(_COUNT_WORDS.search(q))
    has_list = bool(_LIST_WORDS.search(q))

    # "which user having X" without count words → list
    if has_count:
        return QueryMode.COUNT
    if has_list or re.search(r"\bwhich\b", q):
        return QueryMode.LIST
    return QueryMode.OTHER


def _detect_entity(question: str) -> EntityType:
    q = question.lower()
    # Order matters — "user" before "device" when both appear
    if _USER_WORDS.search(q):
        return EntityType.USER
    if _DEVICE_WORDS.search(q):
        return EntityType.DEVICE
    if _CUSTOMER_WORDS.search(q):
        return EntityType.CUSTOMER
    if _SOFTWARE_WORDS.search(q):
        return EntityType.SOFTWARE
    return EntityType.UNKNOWN


def _build_hint(mode: QueryMode, entity: EntityType, question: str) -> str:
    q = question.lower()
    needs_device_join = any(
        w in q
        for w in (
            "platform", "windows", "linux", "mac", "processor", "cpu", "intel",
            "ram", "memory", "agent", "inactive", "active", "device_name",
        )
    )
    needs_software_join = any(w in q for w in ("installed", "software", "application"))

    lines = [
        "════════════════════════════════════════",
        "MANDATORY QUERY INTENT (follow exactly)",
        "════════════════════════════════════════",
    ]

    if mode == QueryMode.COUNT and entity == EntityType.USER:
        lines += [
            "Intent: COUNT users.",
            "- SELECT must be: COUNT(DISTINCT mu.username) AS user_count",
            "- MUST match list row count — list uses SELECT DISTINCT mu.username, so count the same column.",
            "- NEVER use COUNT(DISTINCT mu.id) — many user ids share the same username in this database.",
            "- NEVER use COUNT(DISTINCT md.id) — that counts devices, not users.",
            "- NEVER use COUNT(*) or COUNT without DISTINCT.",
            "- FROM managed_user mu",
        ]
        if needs_device_join and not needs_software_join:
            lines.append(
                "- JOIN managed_device md ON md.customer_id = mu.customer_id"
            )
            lines.append(
                "- Do NOT JOIN device_info unless the question filters by processor/RAM/hardware."
            )
        lines.append(
            "- A LIST query for the same question must use the IDENTICAL FROM, JOIN, and WHERE."
        )

    elif mode == QueryMode.LIST and entity == EntityType.USER:
        lines += [
            "Intent: LIST users.",
            "- SELECT must be: SELECT DISTINCT mu.username",
            "- NEVER select md.device_name or md.id for a user question.",
            "- FROM managed_user mu",
        ]
        if needs_device_join and not needs_software_join:
            lines.append(
                "- JOIN managed_device md ON md.customer_id = mu.customer_id"
            )
            lines.append(
                "- Do NOT JOIN device_info unless the question filters by processor/RAM/hardware."
            )
        lines.append(
            "- A COUNT query for the same question must use the IDENTICAL FROM, JOIN, and WHERE."
        )

    elif mode == QueryMode.COUNT and entity == EntityType.DEVICE:
        lines += [
            "Intent: COUNT devices.",
            "- SELECT must be: COUNT(DISTINCT md.id) AS device_count",
            "- NEVER use COUNT(*) across joins.",
            "- FROM managed_device md",
        ]
        if "processor" in q or "intel" in q or "cpu" in q or "ram" in q:
            lines.append(
                "- JOIN device_info di ON di.managed_device_id = md.id"
            )
        if "agent" in q:
            lines.append(
                "- JOIN agent_info ai ON ai.managed_device_id = md.id"
            )
        lines.append(
            "- LIST device queries must use the same FROM/JOIN/WHERE with SELECT DISTINCT md.device_name."
        )

    elif mode == QueryMode.LIST and entity == EntityType.DEVICE:
        lines += [
            "Intent: LIST devices.",
            "- SELECT must be: SELECT DISTINCT md.device_name (add md.platform only if needed).",
            "- FROM managed_device md",
        ]
        if "processor" in q or "intel" in q or "cpu" in q or "ram" in q:
            lines.append(
                "- JOIN device_info di ON di.managed_device_id = md.id"
            )
        if "agent" in q:
            lines.append(
                "- JOIN agent_info ai ON ai.managed_device_id = md.id"
            )
        lines.append(
            "- COUNT device queries must use the same FROM/JOIN/WHERE with COUNT(DISTINCT md.id)."
        )

    elif mode == QueryMode.COUNT and entity == EntityType.CUSTOMER:
        lines += [
            "Intent: COUNT customers.",
            "- SELECT: COUNT(DISTINCT id) FROM customer",
            "- No unnecessary JOINs.",
        ]

    elif mode == QueryMode.LIST and entity == EntityType.CUSTOMER:
        lines += [
            "Intent: LIST customers.",
            "- SELECT DISTINCT columns from customer table only.",
        ]

    else:
        lines.append(
            "If counting an entity use COUNT(DISTINCT primary_key). "
            "If listing use SELECT DISTINCT. COUNT and LIST for the same topic "
            "must share identical FROM, JOIN, and WHERE clauses."
        )

    return "\n".join(lines)


def analyze_query_intent(question: str) -> QueryIntent:
    mode = _detect_mode(question)
    entity = _detect_entity(question)
    hint = _build_hint(mode, entity, question)
    return QueryIntent(mode=mode, entity=entity, hint=hint)


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower()).strip()


def _alias_for_table(sql: str, table: str) -> str | None:
    """Return alias used for a table if found."""
    m = re.search(
        rf"\b{table}\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
        re.I,
    )
    if m:
        return m.group(1).lower()
    if re.search(rf"\bFROM\s+{table}\b", sql, re.I):
        return table.lower()
    return None


def validate_query_intent(sql: str, intent: QueryIntent) -> list[str]:
    """Return validation errors when SQL doesn't match detected count/list intent."""
    if intent.mode == QueryMode.OTHER or intent.entity == EntityType.UNKNOWN:
        return []

    errors: list[str] = []
    norm = _normalize(sql)

    if intent.mode == QueryMode.COUNT and intent.entity == EntityType.USER:
        if re.search(r"count\s*\(\s*\*", norm):
            errors.append(
                "Counting users: never use COUNT(*) — use COUNT(DISTINCT mu.username)."
            )
        if re.search(r"count\s*\(\s*distinct\s+mu\.id\s*\)", norm) or re.search(
            r"count\s*\(\s*distinct\s+managed_user\.id\s*\)", norm
        ):
            errors.append(
                "User count must use COUNT(DISTINCT mu.username), not mu.id. "
                "Many user ids share the same username — counting ids gives a number "
                "much higher than the list. Use COUNT(DISTINCT mu.username) to match "
                "SELECT DISTINCT mu.username."
            )
        if re.search(r"count\s*\(\s*distinct\s+md\.id\s*\)", norm) or re.search(
            r"count\s*\(\s*distinct\s+managed_device\.id\s*\)", norm
        ):
            errors.append(
                "This question asks for USER count but SQL counts devices (md.id). "
                "Use COUNT(DISTINCT mu.username) instead."
            )
        if not re.search(r"count\s*\(\s*distinct\s+mu\.username\s*\)", norm) and not re.search(
            r"count\s*\(\s*distinct\s+managed_user\.username\s*\)", norm
        ):
            errors.append(
                "User count queries must use COUNT(DISTINCT mu.username) "
                "to match SELECT DISTINCT mu.username in list queries."
            )
        if "managed_user" not in norm and " mu " not in f" {norm} ":
            errors.append("User count queries must include the managed_user table.")

    if intent.mode == QueryMode.LIST and intent.entity == EntityType.USER:
        if not re.search(r"select\s+distinct", norm):
            errors.append("Listing users requires SELECT DISTINCT to avoid duplicate rows.")
        if re.search(r"select\s+distinct\s+md\.device_name", norm):
            errors.append(
                "This question asks for USERS but SQL lists device_name. "
                "Use SELECT DISTINCT mu.username."
            )
        if "username" not in norm and "mu." not in norm:
            errors.append(
                "User list queries should SELECT DISTINCT mu.username from managed_user."
            )

    if intent.mode == QueryMode.COUNT and intent.entity == EntityType.DEVICE:
        if re.search(r"count\s*\(\s*distinct\s+mu\.id\s*\)", norm):
            errors.append(
                "This question asks for DEVICE count but SQL counts users. "
                "Use COUNT(DISTINCT md.id)."
            )
        if re.search(r"count\s*\(\s*\*", norm):
            errors.append(
                "Device count across joins: use COUNT(DISTINCT md.id), not COUNT(*)."
            )

    if intent.mode == QueryMode.LIST and intent.entity == EntityType.DEVICE:
        if not re.search(r"select\s+distinct", norm):
            errors.append("Listing devices requires SELECT DISTINCT.")

    # Platform filters live on managed_device — device_info is only for hardware
    if "device_info" in norm and re.search(r"\bmd\.platform\b|\bmanaged_device\.platform\b", norm):
        if not re.search(r"\b(processor|ram|cpu)\b", norm):
            errors.append(
                "Platform filters use managed_device.platform only — "
                "remove unnecessary device_info JOIN."
            )

    return errors
