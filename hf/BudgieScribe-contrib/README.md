---
license: cc0-1.0
pretty_name: BudgieScribe community dictation pairs
language:
  - fr
  - en
task_categories:
  - text-generation
tags:
  - asr
  - speech-to-text
  - text-normalization
  - inverse-text-normalization
  - dictation
configs:
  - config_name: fr
    data_files: "contrib/fr/*.jsonl"
  - config_name: en
    data_files: "contrib/en/*.jsonl"
---

# BudgieScribe community dictation pairs

The public, versioned corpus of human-reviewed contributions to
[BudgieScribe](https://github.com/alexxxcoelho/budgie-scribe). Each row pairs
the raw output of an ASR engine (`dirty`) with the text the speaker meant
(`clean`). It contains text only, never audio.

## Contribute

Contributions use pull requests on the public GitHub repository so automated
checks and line-by-line human review happen before publication:

1. collect and validate pairs in Budgie Echo's **Scribe training** tab;
2. export them to `contrib/<lang>/<handle>-YYYY-MM.jsonl`;
3. open a pull request on
   [alexxxcoelho/budgie-scribe](https://github.com/alexxxcoelho/budgie-scribe);
4. CI checks format, duplicates, language consistency, structural rules and
   likely personal data; a maintainer then reads the actual changes;
5. after merge, the accepted `contrib/` tree is mirrored here.

The full rules and CLI commands are in
[CONTRIBUTING.md](https://github.com/alexxxcoelho/budgie-scribe/blob/main/CONTRIBUTING.md).
Do not open a Hub pull request directly: GitHub is the review source of truth,
and this dataset is its public mirror.

## Load a reviewed snapshot

Pin a commit hash for reproducible training:

```python
from datasets import load_dataset

fr = load_dataset(
    "flowcorp-ch/BudgieScribe-contrib",
    "fr",
    revision="<dataset-commit>",
    split="train",
)
```

BudgieScribe's Hugging Face training job can select the same snapshot and any
subset of files:

```bash
hf jobs uv run hf/jobs/train.py --flavor a10g-small --timeout 2h \
  --secrets HF_TOKEN -- \
  --lang fr --profil nano \
  --source 'flowcorp-ch/BudgieScribe-contrib@<dataset-commit>:contrib/fr/*.jsonl' \
  --out <namespace>/scribe-fr-next
```

Repeat `--source` to combine explicitly selected datasets. The private model
checkpoint receives a `selection.json` recording the resolved Hub commits,
files, row count and hashes.

## Row format and review boundary

Rows are JSONL objects with `id`, `file`, `lang`, `control`, `dirty`, `clean`
and `source`. The contribution gate rejects empty or malformed rows, duplicate
ids/transcripts, incoherent control lines and likely personal data. Automated
checks reduce risk; they do not prove that free text is anonymous. Human
review remains mandatory before merge.

## License

Contributors release accepted pairs under CC0 1.0. The contribution pull
request records consent, rights and the absence of known personal data.
