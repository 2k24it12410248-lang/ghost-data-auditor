"""
Ghost Data Still Exists - deletion auditor (rule-based, no LLM).

Pipeline:
 1. load request + identity + rule CSVs
 2. collect "observations" (one snapshot of one resource in one evidence file)
    from SQL, JSON, log, and text evidence
 3. for every case: resolve the user's current + historical identifiers,
    find observations that mention them, keep the latest one per resource
    taken at or before audit_at
 4. decide what each resource needs (delete / redact / anonymize / retain /
    disable flow / block restore) and whether it is already done
 5. write ordered FINDING -> REMEDIATION -> VERIFICATION steps to output.csv
"""
import csv
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"

# Operation order inside each phase, copied from problem_statement.md.
OPERATION_ORDER = [
    "REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
]
PHASE_OF = {op: ("FINDING" if op.startswith("REPORT") else "VERIFICATION" if op.startswith("VERIFY") else "REMEDIATION")
            for op in OPERATION_ORDER}
STATE_OF = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}
PII_FIELDS = {"email", "phone", "full_name", "display_name", "email_hash", "requester_email", "requester_name",
              "requester_phone", "owner_email", "owner_phone", "customer_email", "name"}
DELETION_WORDS = ["delet", "eras", "remov", "close my account", "supprim", "elimin", "lösch", "losch",
                  "cancel my account", "forget", "close", "suppression", "verified", "deleted", "excluir", "verwijder", "cancell", "削除", "삭제"]
NON_DELETION_HINTS = ["do not delete", "don't delete", "not delete", "keep my account", "update my",
                      "change my", "copy of my data", "export of my data", "download"]


def read_csv(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- system guess
def system_for(resource_id, hint=""):
    """Map a resource id prefix to the owning system (ids are consistent across evidence)."""
    prefixes = {"tombstone_": "identity_service", "account_": "account_service", "search_": "search_service", "support_": "support_platform",
                "analytics_": "analytics_platform", "export_": "export_service", "data_flow_": "integration_service",
                "backup_": "backup_service", "audit_record_": "security_service", "marketing_": "marketing_platform",
                "cache_": "cache_service", "telemetry_": "telemetry_service", "email_log_": "email_service",
                "legal_": "legal_service", "attachment_": "support_platform"}
    for prefix, system in prefixes.items():
        if resource_id.startswith(prefix):
            return system
    return hint or "unknown_service"


# ---------------------------------------------------------- evidence loaders
def add_obs(store, file_id, time, resource_id, fields, present=True):
    store.append({"file_id": file_id, "time": time or "", "resource_id": resource_id,
                  "fields": {k: v for k, v in fields.items()}, "present": present})


def load_sql(path, file_id, captured_at, store):
    """Execute the SQL snapshot in memory and turn every row into an observation."""
    db = sqlite3.connect(":memory:")
    db.executescript(path.read_text(encoding="utf-8"))
    tables = [r[0] for r in db.execute("select name from sqlite_master where type='table'")]
    for table in tables:
        cursor = db.execute(f"select * from {table}")
        cols = [c[0] for c in cursor.description]
        if "resource_id" not in cols:
            continue
        for row in cursor:
            rec = dict(zip(cols, row))
            add_obs(store, file_id, rec.get("updated_at") or captured_at, rec["resource_id"], rec)


def walk_json(node, file_id, time, store):
    """Recursively find dicts with a resource_id; inherit the nearest timestamp."""
    if isinstance(node, dict):
        time = node.get("observed_at") or node.get("captured_at") or node.get("updated_at") or time
        if "resource_id" in node:
            flat = {}
            for k, v in node.items():
                if isinstance(v, dict):
                    flat.update(v)
                elif not isinstance(v, list):
                    flat[k] = v
            gone = node.get("status_code") == 404 or ("profile" in node and node["profile"] is None) \
                or str(node.get("status", "")).upper() in ("NOT_FOUND", "DELETED", "ABSENT")
            add_obs(store, file_id, time, node["resource_id"], flat, present=not gone)
        for v in node.values():
            if isinstance(v, (dict, list)):
                walk_json(v, file_id, time, store)
    elif isinstance(node, list):
        for item in node:
            walk_json(item, file_id, time, store)


KV = re.compile(r'(\w+)=("[^"]*"|\S+)')


def load_log(path, file_id, store):
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "resource_id=" not in line:
            continue
        fields = {k: v.strip('"') for k, v in KV.findall(line)}
        fields = {k: (None if v == "null" else v) for k, v in fields.items()}
        time = line.split(" ", 1)[0]
        text = line.lower()
        gone = "not_found" in text or "status=404" in text or "rows=0" in text or "found=false" in text
        add_obs(store, file_id, time, fields["resource_id"], fields, present=not gone)


def load_text(path, file_id, store):
    # handover format: time | system | resource | category | state | identifier
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip(" -") for p in line.split("|")]
        if len(parts) >= 6:
            state = parts[4].upper()
            add_obs(store, file_id, parts[0], parts[2],
                    {"category": parts[3], "state": state, "identifier": parts[5]},
                    present=state not in ("NOT_FOUND", "DELETED", "ABSENT"))


def load_all_evidence():
    store = []
    for f in read_csv("evidence_files.csv"):
        path = DATA / f["file_path"]
        try:
            if path.suffix == ".sql":
                load_sql(path, f["file_id"], f["captured_at"], store)
            elif path.suffix == ".json":
                walk_json(json.loads(path.read_text(encoding="utf-8")), f["file_id"], f["captured_at"], store)
            elif path.suffix == ".log":
                load_log(path, f["file_id"], store)
            elif path.suffix == ".txt":
                load_text(path, f["file_id"], store)
            # PDFs and images are not parsed (no OCR); documented as a limitation.
        except Exception as error:  # one bad file must not stop the run
            print("skip", f["file_path"], error)
    return store


# ----------------------------------------------------------- identity
def resolve_identifiers(email, identities, audit_log):
    """Return (user_id, set of lowercase identifiers incl. historical values, audit ids used)."""
    email = email.lower()
    user = next((u for u in identities if u["email"].lower() == email), None)
    if user is None:  # maybe it is an old email
        hit = next((a for a in audit_log if a["old_value"].lower() == email), None)
        if hit:
            user = next((u for u in identities if u["user_id"] == hit["user_id"]), None)
    ids = {email}
    user_id = None
    if user:
        user_id = user["user_id"]
        ids |= {user["email"].lower(), user["phone"].lower(), user["email_hash"].lower(), user["name"].lower()}
        for a in audit_log:
            if a["user_id"] == user_id:
                ids |= {a["old_value"].lower(), a["new_value"].lower()}
    ids.discard("")
    return user_id, ids


def mentions_user(obs, user_id, ids):
    for key, value in obs["fields"].items():
        if value is None:
            continue
        v = str(value).lower()
        if v in ids or (user_id and v == user_id.lower() and key in ("customer_reference", "subject_reference",
                                                                         "identifier", "lookup_key")):
            return True
    return False


def has_pii(obs):
    f = obs["fields"]
    if f.get("state") in ("IDENTIFIABLE", "FOUND", "ACTIVE", "PRESENT"):
        return True
    return any(f.get(k) not in (None, "", "null") for k in PII_FIELDS)


# ------------------------------------------------------------ decision
def is_deletion_request(text):
    """True when the text asks for deletion/closure. Any deletion word wins,
    because many requests mention exports or downloads *and* ask to delete."""
    t = text.lower()
    if any(w in t for w in DELETION_WORDS):
        return True
    return False


def plan_resource(obs, rid):
    """Return (finding_op or None, remediation_op or None, verify_op, evidence)."""
    f = obs["fields"]
    pii = has_pii(obs) and obs["present"]
    state = str(f.get("state", "")).upper()
    if rid.startswith("audit_record_"):
        return None, None, "VERIFY_RECORD_PRESENT"          # rule_12 RETAIN
    if rid.startswith("data_flow_"):
        active = str(f.get("enabled", "")).lower() in ("1", "true") or state == "ACTIVE"
        return ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED") if active \
            else (None, None, "VERIFY_DATA_FLOW_DISABLED")
    if rid.startswith("backup_"):
        risk = str(f.get("restore_allowed", "")).lower() in ("1", "true") or state == "ACTIVE"
        return ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED") if risk \
            else (None, None, "VERIFY_RESTORE_BLOCKED")
    if rid.startswith("analytics_") or rid.startswith("telemetry_"):   # rule_07/08 ANONYMIZE
        return ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED") if pii \
            else (None, None, "VERIFY_RECORD_ANONYMIZED")
    if rid.startswith("support_") and f.get("message_excerpt"):       # rule_05 REDACT shared conversation
        return ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED") if pii \
            else (None, None, "VERIFY_RECORD_REDACTED")
    if rid.startswith("tombstone_"):  # deleted-account marker may stay, but without personal data
        return ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED") if (has_pii(obs) and obs["present"]) \
            else (None, None, "VERIFY_RECORD_REDACTED")
    # everything else (profile, search, export, cache, marketing, attachment) -> DELETE
    return ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT") if obs["present"] \
        else (None, None, "VERIFY_RECORD_ABSENT")


def audit_case(case, identities, audit_log, evidence):
    if not is_deletion_request(case["request_text"]):
        return "NOT_APPLICABLE", []
    user_id, ids = resolve_identifiers(case["email"], identities, audit_log)
    audit_at = case["audit_at"]
    latest = {}
    for obs in evidence:
        if obs["time"] and obs["time"] > audit_at:
            continue
        if not mentions_user(obs, user_id, ids):
            continue
        rid = obs["resource_id"]
        if rid not in latest or obs["time"] >= latest[rid]["time"]:
            latest[rid] = obs
    # A deleted record no longer carries identifiers, so also follow later
    # observations of the same resource id (e.g. a 404 readback).
    for obs in evidence:
        rid = obs["resource_id"]
        if rid in latest and obs["time"] <= audit_at and obs["time"] > latest[rid]["time"]:
            latest[rid] = obs

    rows = []  # (op, system, resource, evidence)
    incomplete = False
    for rid, obs in latest.items():
        system = system_for(rid)
        finding, fix, verify = plan_resource(obs, rid)
        if finding:
            incomplete = True
            rows.append((finding, system, rid, obs["file_id"]))
            rows.append((fix, system, rid, ""))
        rows.append((verify, system, rid, obs["file_id"]))
    if not latest:
        # No evidence at all: we cannot verify deletion -> conservative INCOMPLETE is not provable either;
        # report it as COMPLETE only with evidence, otherwise INCOMPLETE with no steps.
        return "INCOMPLETE", []
    status = "INCOMPLETE" if incomplete else "COMPLETE"
    if incomplete:  # future checks carry an empty evidence id
        rows = [(op, s, r, "" if PHASE_OF[op] != "FINDING" else e) for op, s, r, e in rows]
    rows.sort(key=lambda x: (["FINDING", "REMEDIATION", "VERIFICATION"].index(PHASE_OF[x[0]]),
                             OPERATION_ORDER.index(x[0]), x[1], x[2]))
    steps = [{"step_no": i + 1, "phase": PHASE_OF[op], "system_id": s, "resource_id": r,
              "operation": op, "state": STATE_OF[op], "evidence_id": e} for i, (op, s, r, e) in enumerate(rows)]
    return status, steps


def run(requests_file="deletion_requests.csv", out_path=ROOT / "output.csv"):
    identities = read_csv("user_identities.csv")
    audit_log = read_csv("user_audit_log.csv")
    evidence = load_all_evidence()
    cases = sorted(read_csv(requests_file), key=lambda c: int(c["case_id"].split("_")[1]))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for case in cases:
            status, steps = audit_case(case, identities, audit_log, evidence)
            writer.writerow([case["case_id"], status, json.dumps(steps)])
    print(f"wrote {len(cases)} rows to {out_path}")


if __name__ == "__main__":
    run()
