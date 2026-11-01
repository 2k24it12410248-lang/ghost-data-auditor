# Ghost Data Still Exists — Data Deletion Auditor

## What it solves
A system can say "deletion complete" while personal data still sits in profiles, search indexes,
support tickets, exports, analytics, caches or backups — and syncs or restores can bring it back.
This tool reads each deletion request plus its evidence files and decides, for every request:

- `COMPLETE` — evidence shows every resource is in its required end state
- `INCOMPLETE` — data remains, a recreation risk is active, or nothing proves deletion
- `NOT_APPLICABLE` — the text never asks for deletion

It also writes ordered FINDING -> REMEDIATION -> VERIFICATION steps as JSON.

**Honest note:** this is a rule-based Python program. It does not call an LLM or any paid API.

## How it works (`main.py`)
1. `load_all_evidence()` turns SQL dumps, JSON, logs and text notes into "observations"
   (one snapshot of one resource in one evidence file, with a timestamp).
2. `resolve_identifiers()` collects the user's current and old emails/phones/ids from
   `user_identities.csv` and `user_audit_log.csv` (so renamed emails are still caught).
3. `is_deletion_request()` checks the request text (several languages) for deletion words.
4. `audit_case()` keeps the latest observation per resource taken at or before `audit_at`.
   The reported status is ignored — only evidence counts.
5. `plan_resource()` applies the deletion rules: delete profiles/search/exports/caches,
   redact shared support threads and tombstones, anonymize analytics, keep audit records,
   disable active data flows, block restorable backups.
6. Any FINDING => `INCOMPLETE`. No evidence at all => `INCOMPLETE` (missing evidence is not proof).
7. `run()` writes `output.csv` (`case_id,deletion_status,steps_json`), sorted by case number.

## Run
```
pip install -r requirements.txt   # standard library only
python code/main.py               # writes output.csv (518 rows)
python code/evaluation/main.py    # scores against the 32 labelled samples
python code/tests.py              # 8 small tests
```

## Results (32 labelled samples, measured)
Status accuracy 71.9%, step precision 63.6%, step recall 43.5%, exact step lists 9.4%,
ordering of matched steps 100%. See `evaluation/evaluation_report.md`.

## Limitations
- Images and PDFs are not read (no OCR), so evidence inside them is missed.
- Keyword detection of deletion intent can misjudge unusual wording.
- Resource-to-rule mapping uses id prefixes; unknown prefixes default to "delete".
- Step lists often miss resources the official answers include, so exact match is low.
