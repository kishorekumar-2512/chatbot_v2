"""
backend/query_intelligence.py — updated for real 234-table intern_db schema.

Layer 1: Query Understanding
- Intent classification (COUNT/LIST/AGGREGATE/TOP_N/TREND/COMPARE/EXISTS)
- Entity extraction mapped to real table names
- SQL skeleton builder
- Filter hint injection
"""

import re
from typing import Optional

# ── Intent patterns ───────────────────────────────────────────────────────────
INTENT_PATTERNS = {
    "COUNT":     [r"\bhow many\b", r"\bcount\b", r"\btotal number\b", r"\bnumber of\b", r"\bhow much\b"],
    "TOP_N":     [r"\btop \d+\b", r"\bbottom \d+\b", r"\bmost\b", r"\bleast\b", r"\bhighest\b",
                  r"\blowest\b", r"\bbest\b", r"\bworst\b", r"\branked\b", r"\blargest\b", r"\bsmallest\b"],
    "TREND":     [r"\bover time\b", r"\bby month\b", r"\bby week\b", r"\bby day\b", r"\btrend\b",
                  r"\bhistory\b", r"\bper month\b", r"\bgrowth\b", r"\bmonthly\b", r"\bweekly\b",
                  r"\bdaily\b", r"\bover the last\b", r"\blast \d+ days\b", r"\blast \d+ months\b"],
    "AGGREGATE": [r"\baverage\b", r"\bavg\b", r"\bsum\b", r"\btotal\b", r"\bminimum\b",
                  r"\bmaximum\b", r"\bmin\b", r"\bmax\b", r"\bper customer\b", r"\bper device\b"],
    "COMPARE":   [r"\bcompare\b", r"\bvs\b", r"\bversus\b", r"\bdifference\b",
                  r"\bmore than\b", r"\bless than\b", r"\bgreater\b", r"\bexceed\b"],
    "EXISTS":    [r"\bis there\b", r"\bare there\b", r"\bdoes .+ have\b",
                  r"\bhas .+ any\b", r"\bexist\b", r"\bany device\b", r"\bany user\b"],
    "LIST":      [],  # fallback
}

INTENT_SQL_HINTS = {
    "COUNT":     "Return a single number using COUNT(). Use COUNT(DISTINCT id) to avoid duplicates.",
    "TOP_N":     "Use ORDER BY metric DESC LIMIT N. Always GROUP BY the entity first.",
    "TREND":     "Use DATE_TRUNC('month', timestamp_col) or similar. GROUP BY time period. ORDER BY period ASC.",
    "AGGREGATE": "Use SUM/AVG/MAX/MIN with GROUP BY. Round numeric results with ROUND(...,2).",
    "COMPARE":   "GROUP BY the comparison dimension. Show the metric value for each group.",
    "EXISTS":    "Use COUNT() > 0 or EXISTS() subquery. Return a meaningful count or boolean-like result.",
    "LIST":      "SELECT relevant columns. Use DISTINCT to avoid duplicates. Add ORDER BY for readability.",
}


def classify_intent(question: str) -> str:
    q = question.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        if intent == "LIST":
            continue
        for pattern in patterns:
            if re.search(pattern, q):
                return intent
    return "LIST"


# ── Entity extraction — real table keywords from intern_db ────────────────────
TABLE_KEYWORDS = {
    # Core entities
    "managed_device":              ["device", "computer", "laptop", "desktop", "machine", "endpoint",
                                    "workstation", "server", "pc", "agent machine"],
    "managed_user":                ["user", "employee", "person", "staff", "username", "who",
                                    "member", "account"],
    "customer":                    ["customer", "client", "company", "organisation", "account",
                                    "tenant", "org"],
    # Agent
    "agent_info":                  ["agent", "agent status", "heartbeat", "online", "offline",
                                    "agent version", "enrolled", "agent active"],
    "agent_command_audit":         ["command", "command audit", "command sent", "command history"],
    "agent_command_queue":         ["command queue", "pending command", "queued command"],
    "agent_settings":              ["agent settings", "agent config", "tray", "log retention"],
    "alerts":                      ["alert", "alarm", "notification", "device alert"],
    "alert_policies":              ["alert policy", "alert rule", "alert configuration"],
    "alert_criteria":              ["alert criteria", "alert threshold", "alert condition"],
    # Device hardware
    "device_info":                 ["processor", "cpu", "ram", "memory", "disk", "storage",
                                    "intel", "amd", "device model", "hardware", "free ram",
                                    "total ram", "hard disk", "processor speed", "free space"],
    "device_operating_system_info":["os", "operating system", "windows version", "os name",
                                    "os build", "os architecture", "mac os", "linux", "os version"],
    "device_network_map":          ["ip address", "mac address", "subnet", "domain controller",
                                    "network map", "ip", "mac"],
    "device_warranty":             ["warranty", "warranty expiry", "warranty status", "warranty type"],
    "device_location":             ["location", "gps", "latitude", "longitude", "address",
                                    "where is the device"],
    "device_uptime":               ["uptime", "downtime", "boot time", "shutdown", "power event"],
    "device_uptime_daily_summary": ["availability", "daily uptime", "availability percentage"],
    "device_scan_status":          ["scan status", "last scan", "scan success", "scan fail"],
    "device_patch_summary":        ["patch summary", "missing patch count", "installed patch count"],
    # Security
    "device_antivirus":            ["antivirus", "av", "protection status", "virus", "defender"],
    "device_bitlocker":            ["bitlocker", "encryption", "drive encryption", "encrypted"],
    "device_firewall":             ["firewall", "firewall status", "firewall profile"],
    "device_firewall_mac":         ["mac firewall", "macos firewall", "stealth mode"],
    "device_file_vault_mac":       ["filevault", "file vault", "mac encryption"],
    "device_certificate":          ["certificate", "ssl certificate", "expired certificate"],
    "application_control_violations":["violation", "blocked app", "policy violation",
                                      "application control", "blocked software"],
    # Patches
    "device_installed_patch":      ["installed patch", "patch installed", "applied patch"],
    "device_missing_patch":        ["missing patch", "unpatched", "patch missing", "not patched"],
    "device_patch":                ["patch status", "patch deployment", "patch result"],
    "org_patch":                   ["patch", "hotfix", "update", "KB number", "security patch",
                                    "critical patch", "patch severity", "mandatory patch"],
    # Software
    "software":                    ["software", "application", "app", "program", "tool",
                                    "installed software"],
    "software_version":            ["software version", "version", "version name"],
    "software_version_managed_device":["installed software", "software installed on device",
                                       "software deployment", "installation count"],
    "prohibited_software":         ["prohibited software", "banned software", "blocked software"],
    "software_category":           ["software category", "software type"],
    "smetering_usage_raw":         ["software usage", "application usage", "used software",
                                    "who used", "usage duration", "run count"],
    "smetering_device_summary":    ["software usage per device", "device usage summary"],
    "smetering_aggregate_org_summary":["software metering total", "total software usage"],
    # Licenses
    "license_details":             ["license", "licence", "license cost", "license purchased",
                                    "compliance", "compliant", "reseller"],
    "license_validity":            ["license expiry", "license key", "activation date",
                                    "expiry date", "renewal date"],
    "license_details_managed_device":["device license", "license per device"],
    "license_details_managed_users":  ["user license", "license per user"],
    # Groups & policies
    "zecure_group":                ["group", "device group", "target group", "dynamic group",
                                    "static group"],
    "zecure_group_managed_devices":["devices in group", "group members", "group device"],
    "policy":                      ["policy", "configuration policy", "policy name"],
    "profiles":                    ["profile", "configuration profile", "policy profile"],
    "target":                      ["target", "deployment target", "policy target"],
    # Users
    "user_logon_history":          ["login", "logon", "logoff", "sign in", "last login",
                                    "failed login", "login history", "who logged in"],
    "managed_user_account_info":   ["department", "job title", "locked account", "disabled user",
                                    "password expired", "last logon time", "manager"],
    "device_system_users":         ["local user", "local admin", "administrator", "local account",
                                    "locked user", "system user"],
    # Remote
    "session":                     ["session", "remote session", "remote support", "RDP"],
    "live_session":                ["live session", "active session", "current session"],
    "agent_command_audit":         ["command sent", "command executed", "remote command"],
    # Deployments
    "deployment":                  ["deployment", "deploy", "software deployment", "package deploy"],
    "deployment_managed_device":   ["deployment status", "which device has deployment"],
    "script_policy":               ["script", "PowerShell", "bash script", "script name"],
    # Hardware details
    "processor_details":           ["cpu cores", "clock speed", "processor cores", "hyper-threading"],
    "disk_drive_details":          ["physical disk", "disk size", "disk drive"],
    "logical_disk_details":        ["drive letter", "C drive", "partition", "free disk space"],
    "network_adapter_details":     ["network adapter", "NIC", "DHCP", "network bandwidth"],
    "hardware_bios":               ["BIOS", "BIOS version", "BIOS release"],
    "device_driver":               ["driver", "device driver", "driver version", "driver status"],
    "battery_details":             ["battery", "battery capacity", "battery status"],
    # Android/mobile
    "android_device":              ["android", "mobile", "android device", "MDM", "battery level"],
    "mobile": ["mobile", "android", "phone", "tablet"],
    # Asset
    "asset_total_summary":         ["total assets", "asset summary", "asset count", "total devices"],
    "asset_device_summary":        ["device count", "device type summary", "laptop count", "server count"],
    "asset_os_summary":            ["OS count", "windows count", "mac count", "linux count"],
    "asset_manufacturer":          ["manufacturer", "Dell", "HP", "Lenovo", "Apple", "brand"],
    "device_warranty":             ["warranty", "expired warranty", "warranty end"],
    # Subscriptions/billing
    "subscriptions":               ["subscription", "active subscription", "purchased devices"],
    "invoices":                    ["invoice", "billing", "invoice amount"],
    "payments":                    ["payment", "transaction", "paid"],
    "plans":                       ["plan", "subscription plan", "max devices"],
    # Compliance
    "managed_device_compliance_map":["compliance score", "compliance status", "compliant device"],
}

COLUMN_VALUE_HINTS = {
    "platform":          ["windows", "linux", "macos", "mac", "android", "ios"],
    "status":            ["active", "inactive", "offline", "online", "open", "closed",
                          "pending", "resolved", "enabled", "disabled"],
    "severity":          ["critical", "high", "medium", "low"],
    "install_status":    ["installed", "failed", "pending", "uninstalled"],
    "agent_status":      ["true", "false", "active", "inactive"],
    "is_encrypted":      ["true", "false"],
    "encryption_status": ["encrypted", "not encrypted", "unknown"],
    "compliant_status":  ["compliant", "non-compliant", "in compliance", "not evaluated"],
    "upgrade_status":    ["pending", "completed", "failed", "not required"],
    "warranty_status":   ["active", "expired", "unknown"],
    "protection_status": ["enabled", "disabled", "not monitored"],
}


def extract_entities(question: str) -> dict:
    q = question.lower()
    entities = {"tables": [], "filters": {}, "time_filter": None}

    for table, keywords in TABLE_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            if table not in entities["tables"]:
                entities["tables"].append(table)

    for column, values in COLUMN_VALUE_HINTS.items():
        for val in values:
            if val in q:
                entities["filters"][column] = val
                break

    time_patterns = [
        (r"last (\d+) days?",   "days"),
        (r"last (\d+) weeks?",  "weeks"),
        (r"last (\d+) months?", "months"),
        (r"this month",         "this_month"),
        (r"this week",          "this_week"),
        (r"today",              "today"),
        (r"yesterday",          "yesterday"),
        (r"last year",          "last_year"),
    ]
    for pattern, period in time_patterns:
        m = re.search(pattern, q)
        if m:
            n = m.group(1) if "(" in pattern else "1"
            entities["time_filter"] = {"period": period, "n": n}
            break

    return entities


def build_time_filter(col: str, time_filter: dict) -> str:
    if not time_filter:
        return ""
    period = time_filter["period"]
    n = time_filter.get("n", "1")
    mapping = {
        "days":       f"{col} >= NOW() - INTERVAL '{n} days'",
        "weeks":      f"{col} >= NOW() - INTERVAL '{n} weeks'",
        "months":     f"{col} >= NOW() - INTERVAL '{n} months'",
        "this_month": f"DATE_TRUNC('month', {col}) = DATE_TRUNC('month', NOW())",
        "this_week":  f"DATE_TRUNC('week', {col}) = DATE_TRUNC('week', NOW())",
        "today":      f"{col}::date = CURRENT_DATE",
        "yesterday":  f"{col}::date = CURRENT_DATE - 1",
        "last_year":  f"EXTRACT(YEAR FROM {col}) = EXTRACT(YEAR FROM NOW()) - 1",
    }
    return mapping.get(period, "")


def build_sql_skeleton(intent: str, root_table: str, join_hints: str, entities: dict) -> str:
    time_hint = ""
    if entities.get("time_filter"):
        time_hint = f"-- Time filter: {build_time_filter('created_time', entities['time_filter'])}"

    skeletons = {
        "COUNT": f"""-- Fill in conditions:
SELECT COUNT(DISTINCT {root_table}.id) AS total_count
FROM {root_table}
{join_hints}
WHERE 1=1  /* add conditions */
{time_hint}""",
        "TOP_N": f"""-- Fill in metric and conditions:
SELECT {root_table}.id, /* name column */ , COUNT(*) AS metric
FROM {root_table}
{join_hints}
WHERE 1=1  /* add conditions */
{time_hint}
GROUP BY {root_table}.id  /* add name column */
ORDER BY metric DESC
LIMIT 10""",
        "AGGREGATE": f"""-- Fill in aggregate function and conditions:
SELECT /* grouping column */, /* SUM/AVG/MAX/MIN(column) */ AS metric
FROM {root_table}
{join_hints}
WHERE 1=1  /* add conditions */
{time_hint}
GROUP BY /* grouping column */
ORDER BY metric DESC""",
        "TREND": f"""-- Fill in timestamp column:
SELECT DATE_TRUNC('month', /* created_time or timestamp col */) AS period,
       COUNT(*) AS count
FROM {root_table}
{join_hints}
WHERE /* timestamp */ >= NOW() - INTERVAL '12 months'
{time_hint}
GROUP BY period
ORDER BY period ASC""",
        "LIST": f"""-- Fill in columns and conditions:
SELECT {root_table}.id, /* relevant columns */
FROM {root_table}
{join_hints}
WHERE 1=1  /* add conditions */
{time_hint}
ORDER BY {root_table}.created_time DESC""",
    }
    skeleton = skeletons.get(intent, skeletons["LIST"])
    return f"\nSQL skeleton to fill in (remove comments in final SQL):\n{skeleton}\n"


def build_query_context(question: str, schema_text: str, join_hints: str) -> dict:
    intent   = classify_intent(question)
    entities = extract_entities(question)
    hint     = INTENT_SQL_HINTS.get(intent, "")
    root_table = entities["tables"][0] if entities["tables"] else "managed_device"
    skeleton = build_sql_skeleton(intent, root_table, join_hints, entities)

    filter_hints = ""
    if entities["filters"]:
        filter_hints = "\nDetected filter values from question:\n"
        for col, val in entities["filters"].items():
            filter_hints += f"  - {col} ILIKE '%{val}%'\n"

    return {
        "intent":       intent,
        "intent_hint":  hint,
        "entities":     entities,
        "skeleton":     skeleton,
        "filter_hints": filter_hints,
        "root_table":   root_table,
    }
