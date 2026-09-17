# contrib/ — dictation pairs contributed by pull request

One file per contributor and month, one language per folder:
`contrib/<fr|en>/<handle>-<YYYY-MM>.jsonl`. The full procedure, the row
format and what happens to your pairs afterwards are in
[CONTRIBUTING.md §1](../CONTRIBUTING.md#1-data-dictation-pairs).

Every pull request that touches this folder runs
`scribe/pipeline/verifier_contribution.py` (format, coherence, duplicates,
personal data, structural invariants) and posts the report in the checks;
a maintainer then reads the pairs. Once merged, the folder is mirrored to the
public `flowcorp-ch/BudgieScribe-contrib` dataset. Training runs select an
explicit dataset revision and file glob, so accepted data is available without
silently changing an already recorded run.

`fr/exemple-2026-09.jsonl` and `en/example-2026-09.jsonl` are templates: copy
one, keep its shape, replace its content. They are excluded from training.
