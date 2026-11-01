# 👻 Ghost Data Still Exists — Data Deletion Auditor

**Submission for the HackerRank Orchestrate October 2026 hackathon challenge "Ghost Data Still Exists".**

This project is a rule-based data deletion auditor. It reads a deletion request and every piece of
evidence attached to it (SQL dumps, JSON records, log files, text notes) and decides whether the
deletion really happened — or whether "ghost data" is still lurking in profiles, search indexes,
support threads, exports, caches, analytics, or backups.

## Why it matters

A system can report *"deletion complete"* while personal information still exists:

- data can survive in **logs, support attachments, exports, search indexes, caches and backups**;
- **synchronization and restoration** processes can silently recreate deleted data;
- a "Complete" status in the request record is just a claim — only **evidence** proves deletion.

Privacy regulations (GDPR, CCPA and similar) require real, verifiable erasure. This auditor checks
the evidence instead of trusting the claim.

## What it does

For every deletion request it returns **exactly one** status:

| Status | Meaning |
| --- | --- |
| `COMPLETE` | The evidence verifies that every resource reached its required end state. |
| `INCOMPLETE` | Data remains, a recreation risk is active, or the evidence cannot prove complete deletion. |
| `NOT_APPLICABLE` | The request text never actually asks for deletion. |

It also generates an ordered **FINDING → REMEDIATION → VERIFICATION** plan for every case, stored
as JSON in the output.

> **Honest note:** this is a deterministic, rule-based Python program. It does **not** call an LLM
> or any paid external AI service. Every decision comes from explicit, explainable rules.

## How it works (`code/main.py`)

1. **`load_all_evidence()`** — turns SQL dumps, JSON files, logs and plain-text notes into a common
   format: one "observation" per resource per evidence file, each with a timestamp.
2. **`resolve_identifiers()`** — collects the user's current *and* historical emails, phones and IDs
   from `user_identities.csv` and `user_audit_log.csv`, so a renamed email address is still caught.
3. **`is_deletion_request()`** — checks the request text (several languages) for deletion wording.
   If deletion was never requested, the case is `NOT_APPLICABLE`.
4. **`audit_case()`** — keeps only the latest observation per resource taken at or before the audit
   time (`audit_at`). The *reported* deletion status is deliberately ignored — only evidence counts.
5. **`plan_resource()`** — applies the per-resource deletion rules: delete profiles / search
   indexes / exports / caches, redact shared support threads and tombstones, anonymize analytics,
   keep audit records, disable active data flows, and block restorable backups.
6. **Decision** — any `FINDING` ⇒ `INCOMPLETE`. A case with **no evidence at all** is also
   `INCOMPLETE`: missing evidence is never treated as proof that nothing remains.
7. **`run()`** — writes `output.csv` with the exact submission schema
   (`case_id,deletion_status,steps_json`), sorted by case number, one row per request (518 rows).

## Evaluation results (32 labelled sample cases)

| Metric | Result |
| --- | --- |
| Status accuracy | **71.9 %** (23 of 32) |
| Exact step-list match | 9.4 % |
| Step precision | 63.6 % |
| Step recall | 43.5 % |
| Ordering of matched steps | **100 %** |

Field accuracy (position-aligned): `phase` 93.9 %, `evidence_id` 77.9 %, `state` 71.8 %,
`operation` 67.9 %, `system_id` 62.6 %, `resource_id` 61.8 %.

Full report: [`code/evaluation/evaluation_report.md`](code/evaluation/evaluation_report.md).

**Main known errors:** a few truly-`COMPLETE` cases were judged `INCOMPLETE` because extra
resources were flagged, and evidence inside images/PDFs is not read.

## Project structure

```text
ghost_data_auditor/
├── README.md                       ← this page
├── requirements.txt                ← standard library only (pandas used by the evaluator)
├── output.csv                      ← generated submission: 518 rows, official schema
├── interview_guide.md              ← interview preparation notes
├── log.txt                         ← run session log
├── usage_report.md                 ← AI/external-usage declaration
└── code/
    ├── main.py                     ← the auditor (all logic lives here)
    ├── README.md                   ← short technical description of the code
    ├── requirements.txt
    ├── tests.py                    ← 8 small, readable tests
    ├── interview_guide.md
    └── evaluation/
        ├── main.py                 ← scores output against the 32 labelled samples
        └── evaluation_report.md    ← measured results
```

> The official challenge dataset is **not** included in this repository — it belongs to the
> hackathon. Place it in a `dataset/` folder next to `code/` to run the pipeline yourself.

## How to run

```bash
# 1. Install dependencies (only pandas for the evaluator; the auditor uses the standard library)
pip install -r requirements.txt

# 2. Put the official dataset in a folder named "dataset" next to "code/"
#    dataset/
#    ├── deletion_requests.csv
#    ├── ... (evidence files from the challenge)

# 3. Run the auditor — writes output.csv (518 rows)
python code/main.py

# 4. Score against the 32 labelled sample cases
python code/evaluation/main.py

# 5. Run the tests
python code/tests.py
```

It also runs fine in VS Code: open the folder, open `code/main.py`, and press the ▶ *Run Python
File* button.

## Design decisions (and why)

1. **Evidence over claims** — the reported deletion status is never trusted on its own; only
   observations in evidence files can prove deletion.
2. **Missing evidence ⇒ `INCOMPLETE`** — the absence of proof is not proof of absence, so every
   unevidenced case stays conservative.
3. **Latest observation wins** — resources are judged on the newest evidence at or before
   `audit_at`, mirroring how a real deletion pipeline evolves over time.
4. **Historical identities resolved** — old emails/phones/IDs are collected so renamed users can't
   escape the audit.
5. **Explainable JSON plans** — every finding links to an ordered remediation and verification
   step, so a reviewer can trace exactly *why* a case failed.

## Limitations

- Images and PDFs are **not** read (no OCR), so evidence inside them is missed.
- Deletion intent is detected with keywords, so unusual wording can be misjudged.
- Resource-to-rule mapping relies on ID prefixes; unknown prefixes default to "delete".
- Exact step-list matching is low (9.4 %) because the generated step lists often omit resources
  the official answers include.

## Authorship

The code was written with the help of an AI coding assistant (Lovable) and reviewed, understood,
and prepared for presentation by the author. The full honest statement is in
[`usage_report.md`](usage_report.md), and the interview preparation notes are in
[`interview_guide.md`](interview_guide.md).
