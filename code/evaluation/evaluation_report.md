# Evaluation Report

Measured on the 32 labelled sample cases:
```
wrote 32 rows to /tmp/sample_pred.csv
cases=32 status_acc=71.9% exact_steps=9.4% step_precision=63.6% step_recall=43.5% sequence_acc=100.0%
field accuracy (position-aligned): {'phase': '93.9%', 'system_id': '62.6%', 'resource_id': '61.8%', 'operation': '67.9%', 'state': '71.8%', 'evidence_id': '77.9%'}
```

Main errors: some COMPLETE cases judged INCOMPLETE because extra resources were flagged; image/PDF evidence not read.
