---
license: apache-2.0
pretty_name: BudgieScribe held-out evaluation sets
language:
  - fr
  - en
task_categories:
  - text2text-generation
tags:
  - asr
  - speech-to-text
  - text-normalization
  - inverse-text-normalization
  - dictation
  - evaluation
size_categories:
  - 1K<n<10K
configs:
  - config_name: fr
    data_files: "fr/*.jsonl"
  - config_name: en
    data_files: "en/*.jsonl"
---

# BudgieScribe held-out evaluation sets

The synthetic held-out sets every [BudgieScribe](https://huggingface.co/flowcorp-ch/BudgieScribe-Nano)
build is scored on. Deterministic generators
([github.com/alexxxcoelho/budgie-scribe](https://github.com/alexxxcoelho/budgie-scribe),
`scribe/generateurs/gen_*.py`, fixed seeds) start from the **value**, so the
expected output is known to the character and scoring is exact string
comparison — no judge. Each generator writes 8 % of what it produces into a
held-out slice, by family, never seen in training. These files are that slice.

| Language | File | Axis | Cases |
|---|---|---|---:|
| fr | `fr/heldout_forme.jsonl` | Formatting blocks (lists, emails, addresses) | 635 |
| fr | `fr/heldout_correction.jsonl` | Speaker self-corrections | 476 |
| fr | `fr/heldout_itn.jsonl` | Inverse text normalization (numbers, amounts, dates, times, phones) | 797 |
| fr | `fr/heldout_compo.jsonl` | Composition: 2–3 adjacent numbers in one sentence | 319 |
| fr | `fr/heldout_cor_itn.jsonl` | Self-correction × number in one sentence | 238 |
| en | `en/heldout_forme.jsonl` | Formatting blocks | 634 |
| en | `en/heldout_correction.jsonl` | Speaker self-corrections | 474 |
| en | `en/heldout_itn.jsonl` | Inverse text normalization | 798 |
| en | `en/heldout_compo.jsonl` | Composition | 319 |
| en | `en/heldout_cor_itn.jsonl` | Self-correction × number | 237 |

## Row format

One JSON object per line:

```json
{"id": "itn-00005", "file": "itn-telephone", "source": "itn", "lang": "fr",
 "held_out": true,
 "styling": "semi-formal", "structure": "prose", "context": "general",
 "control": "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]",
 "dirty": "tu peux m'appeler au zéro six douze trente-quatre cinquante-six soixante-dix-huit",
 "clean": "Tu peux m'appeler au 06 12 34 56 78."}
```

`dirty` is what an ASR engine produces; `clean` is the expected output;
`control` is the line the model receives above the transcript (see
[FORMAT.md](https://github.com/alexxxcoelho/budgie-scribe/blob/main/FORMAT.md)).
`file` carries the family (`itn-telephone`, `frm-liste`, …) the benches
report by.

## Scoring a build

```bash
hf download flowcorp-ch/BudgieScribe-eval --repo-type dataset --local-dir eval
export SCRIBE_LANG=fr SCRIBE_TRAVAIL=$PWD/eval
python scribe/bancs/eval_synth.py <checkpoint-dir | base | base:mini> eval/fr/heldout_forme.jsonl
```

or, on Hugging Face Jobs, `hf/jobs/eval.py --model <repo> --lang fr` from the
code repository, which runs every file of the language. Reported per axis:
exact matches, and for numbers **wrong value** separately from wrong
formatting.

## Personal data

Nothing here comes from a recording or a person. Every string is generated
from templates and random values. Before publication the sets were passed
through the project's PII scanner (`scribe/pipeline/pii_scan.py`); the e-mail
domains the generators use (`gmail.com`, `outlook.fr`, `free.fr`, …) were
replaced on both sides of each pair by RFC 2606 reserved domains
(`example.com`, `example.org`, `example.net`) so that no plausible real
address is distributed. Phone numbers are random digit strings in the
national formats; any match with a real number is coincidental. The
published model tables were measured on the sets before the domain swap;
the swap changes the spoken domain only, and a re-run is expected to differ
by at most a few cases on the e-mail families.

## License

Apache 2.0, like the generators that produce them.
