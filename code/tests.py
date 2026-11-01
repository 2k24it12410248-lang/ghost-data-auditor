"""Simple tests for the deletion auditor. Run: python code/tests.py"""
import csv
import json
import main as auditor


def obs(rid, fields, present=True, file_id="evidence_1", time="2026-09-01T00:00:00Z"):
    return {"resource_id": rid, "fields": fields, "present": present, "file_id": file_id, "time": time}


def test_deleted_profile_is_verified_absent():
    # Evidence shows the profile is gone -> only a verification step, no fix needed.
    finding, fix, verify = auditor.plan_resource(obs("account_1", {}, present=False), "account_1")
    assert (finding, fix, verify) == (None, None, "VERIFY_RECORD_ABSENT")


def test_remaining_profile_must_be_deleted():
    # Profile still holds the email -> report it, delete it, then verify.
    plan = auditor.plan_resource(obs("account_1", {"email": "a@b.com"}), "account_1")
    assert plan == ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")


def test_not_a_deletion_request():
    # Asking to update a phone number is not a deletion -> NOT_APPLICABLE.
    assert auditor.is_deletion_request("Please update my phone number") is False
    assert auditor.is_deletion_request("Please delete my account") is True
    assert auditor.is_deletion_request("Je demande la suppression du compte") is True


def test_active_sync_is_recreation_risk():
    # An enabled sync can recreate deleted data -> disable it.
    plan = auditor.plan_resource(obs("data_flow_1", {"enabled": "true"}), "data_flow_1")
    assert plan == ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED")


def test_restorable_backup_is_recreation_risk():
    plan = auditor.plan_resource(obs("backup_1", {"restore_allowed": "1"}), "backup_1")
    assert plan == ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED")


def test_audit_record_is_retained():
    # Security audit records are legally retained, so we only verify they exist.
    plan = auditor.plan_resource(obs("audit_record_1", {"email": "a@b.com"}), "audit_record_1")
    assert plan == (None, None, "VERIFY_RECORD_PRESENT")


def test_no_evidence_is_not_proof_of_deletion():
    # Missing evidence must never become COMPLETE.
    case = {"case_id": "case_x", "email": "nobody@nowhere.test", "audit_at": "2026-09-01T00:00:00Z",
            "request_text": "Please delete my account"}
    status, steps = auditor.audit_case(case, [], [], [])
    assert status == "INCOMPLETE" and steps == []


def test_output_file_is_valid():
    rows = list(csv.DictReader(open(auditor.ROOT / "output.csv", encoding="utf-8")))
    ids = [r["case_id"] for r in rows]
    assert len(rows) == 518 and len(set(ids)) == 518
    assert set(rows[0].keys()) == {"case_id", "deletion_status", "steps_json"}
    for r in rows:
        assert r["deletion_status"] in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")
        json.loads(r["steps_json"])


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)} tests passed")
