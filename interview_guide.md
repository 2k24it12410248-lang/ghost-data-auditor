# Interview Guide

## 60-second introduction
"Companies often mark a deletion request as done while personal data still lives in search
indexes, support tickets, exports or backups. I built a Python auditor that ignores the reported
status and looks only at evidence. It parses SQL, JSON, log and text evidence, links records to
the user through current and past identifiers, keeps the latest snapshot of each resource at audit
time, and applies the deletion rules. It outputs COMPLETE, INCOMPLETE or NOT_APPLICABLE plus ordered
finding, fix and verification steps. It is rule-based, with no LLM, and scores about 72% status
accuracy on the 32 labelled samples."

## Code walk-through
1. Read CSVs -> 2. turn evidence into observations -> 3. find the user's identifiers ->
4. check it is a deletion request -> 5. latest observation per resource before audit_at ->
6. `plan_resource` picks finding/fix/verify per rule -> 7. status + sorted steps -> 8. write CSV.

## Five design decisions
1. **Ignore reported status** — the challenge is exactly that reports can lie.
2. **Missing evidence = INCOMPLETE** — absence of proof is not proof of absence.
3. **Use the snapshot at audit time** — later evidence did not exist when the audit happened.
4. **Follow old identifiers** — data tied to a previous email is still the user's data.
5. **Plain rules, no LLM** — explainable, free, deterministic, easy to test.

## Ten likely questions
1. *Why not an LLM?* Rules are explainable and reproducible; an LLM could help read free text later.
2. *How is NOT_APPLICABLE decided?* Keyword check for deletion words in several languages.
3. *What counts as recreation risk?* An enabled data flow (sync) or a backup allowed to restore.
4. *Why keep audit records?* Rules require retaining security audit logs; we verify they exist.
5. *How do you order steps?* By phase, then the official operation order, then system and resource.
6. *How do you handle email changes?* The audit log maps old emails/phones to the same user.
7. *How did you validate?* Schema checks on 518 rows, 8 unit tests, and an evaluator on 32 samples.
8. *Biggest weakness?* Step recall (~44%) — some resources are missed, and images/PDFs aren't read.
9. *Why sort cases numerically?* Output order must follow case ids.
10. *How would you improve it?* Add OCR, map every resource prefix to its rule, study missed samples.

## Limitations / future work
No OCR; keyword intent detection; prefix-based rule mapping; low exact-step match.
