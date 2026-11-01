"""Score the auditor on the 32 labelled samples (status, step, field and sequence accuracy)."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as auditor  # noqa: E402

KEY_FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def load(path):
    return {r["case_id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


def step_key(s):
    return tuple(s[k] for k in KEY_FIELDS)


def evaluate(pred_path, gold_path):
    pred, gold = load(pred_path), load(gold_path)
    status_ok = exact = seq_ok = tp = n_pred = n_gold = 0
    field_hits = {k: 0 for k in KEY_FIELDS}
    aligned = 0
    for cid, g in gold.items():
        p = pred[cid]
        status_ok += p["deletion_status"] == g["deletion_status"]
        gs, ps = json.loads(g["steps_json"]), json.loads(p["steps_json"])
        gk, pk = [step_key(s) for s in gs], [step_key(s) for s in ps]
        exact += gk == pk
        n_pred += len(pk); n_gold += len(gk)
        tp += len(set(gk) & set(pk))
        common = [k for k in pk if k in set(gk)]
        seq_ok += common == [k for k in gk if k in set(pk)]
        for a, b in zip(gs, ps):
            aligned += 1
            for k in KEY_FIELDS:
                field_hits[k] += a[k] == b[k]
    n = len(gold)
    print(f"cases={n} status_acc={status_ok/n:.1%} exact_steps={exact/n:.1%} "
          f"step_precision={tp/max(n_pred,1):.1%} step_recall={tp/max(n_gold,1):.1%} sequence_acc={seq_ok/n:.1%}")
    print("field accuracy (position-aligned):", {k: f"{v/max(aligned,1):.1%}" for k, v in field_hits.items()})


if __name__ == "__main__":
    out = Path("/tmp/sample_pred.csv")
    auditor.run("sample_deletion_requests.csv", out)
    evaluate(out, auditor.DATA / "sample_output.csv")
