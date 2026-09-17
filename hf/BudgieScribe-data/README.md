---
license: other
license_name: mixed-see-notice
pretty_name: BudgieScribe training data (private)
language:
  - fr
  - en
configs:
  - config_name: mix_fr
    data_files: "mix/pairs_mix.jsonl"
  - config_name: mix_en
    data_files: "mix/pairs_mix_en.jsonl"
---

# BudgieScribe training data — private

Everything the shipped [BudgieScribe](https://huggingface.co/flowcorp-ch/BudgieScribe-Nano)
builds were trained on, and everything needed to train the next ones (`mini`,
`standard`, `large` profiles, a new language) without the author's machine.
The code, prompts and recipe are in
[alexxxcoelho/budgie-scribe](https://github.com/alexxxcoelho/budgie-scribe)
(TRAINING.md); this repository is the data that repository refuses to hold.

**Private by license.** The French side derives from SUMM-RE (CC BY-SA 4.0):
dictation-sized units, ASR transcripts, teacher-cleaned pairs and the
paragraph pairs assembled from real units are Adapted Material and are not
redistributed (NOTICE §2 of the code repository). The English side derives
from VoxPopuli (CC0) and could be public, but is kept here by the same
project rule: one place, one visibility, no per-file exceptions to reason
about. Nothing here comes from a Budgie user or from the author's own
dictations (NOTICE §1).

## What trains what

| Language | Shipped build | Training file | Rows | Trained on | Held out | Weights (bf16, private) |
|---|---|---|---:|---:|---:|---|
| fr | `scribe-v9` | `mix/pairs_mix.jsonl` | 41,387 | 38,042 | 3,345 | `flowcorp-ch/scribe-v9` |
| en | `scribe-en-v7` | `mix/pairs_mix_en.jsonl` | 38,409 | 35,306 | 3,103 | `flowcorp-ch/scribe-en-v7` |

Both: Qwen3-0.6B, full SFT, lr 1e-5, batch 4 × accum 2, 2 epochs, max
512 tokens, bf16 autocast, ~1 h on one Radeon AI PRO R9700. `train.py`
excludes the rows with `"held_out": true` itself; a mix is given whole.
`manifest.json` at the root repeats this table with the SHA-256 and row
count of every file, and each build's `run.json` (loss curve included).

Composition of each mix, by `source`:

| `source` | fr | en | Made by |
|---|---:|---:|---|
| `itn` | 10,000 | 10,000 | `gen_itn[_en].py` — numbers, amounts, dates, times, phones, e-mails |
| `forme` | 8,000 | 8,000 | `gen_forme[_en].py` — lists, e-mail layout, counter-examples |
| `correction` | 6,000 | 6,000 | `gen_correction[_en].py` — self-corrections |
| `termes` | 4,000 | 4,000 | `[Terms:]` line, phase 3 |
| `compo` | 4,000 | 4,000 | `gen_compo[_en].py` — 2–3 numbers in one sentence |
| `coritn` | 3,000 | 3,000 | `gen_cor_itn[_en].py` — correction × number |
| `paragraphes` | 2,000 | 2,000 | `gen_paragraphes[_en].py` — from real units |
| `summre` / `voxpopuli` | 4,387 | 1,409 | real speech, ASR → teacher → adjudication |

## Layout

```
mix/pairs_mix.jsonl            fr — the file scribe-v9 was trained on
mix/pairs_mix_en.jsonl         en — the file scribe-en-v7 was trained on
manifest.json                  SHA-256, bytes, rows of every file; build → mix; run.json of each build
<lang>/pairs/                  the components of the mix, one file per generator + the real pairs
<lang>/corpus/                 units (units_*.jsonl), ASR transcripts (cohere_units_*.jsonl),
                               QC verdicts (qc_units_*.jsonl), references and jobs of the source
                               corpus, the 80-unit A/B set (eval_set_*.jsonl) no step may train on
<lang>/teacher/                raw teacher outputs (*.progress) and adjudications (*.adjudged):
                               hours of GPU, reusable as-is by teach.py
<lang>/history/                mixes and components of the previous builds (en: v1 → v6)
<lang>/builds/<build>/run.json hyperparameters and loss curve of every run, shipped or not
<lang>/logs/                   training, evaluation, GGUF, teacher and QC logs, as written
<lang>/scripts/                the overnight chains that produced the builds, unedited
<lang>/bench/                  bench outputs: evalsynth_*, generations on the A/B set, S1-mini
                               comparison, outputs on the hand-written real cases
<lang>/pii_<mix>.txt           the full pii_scan report on the mix (see below)
```

Not here, on purpose: the audio and parquet of the source corpora (15 GB,
regenerated from the Hub by `scribe/corpus/voxpopuli.py` and `summre.py`),
the weights (one private model repo per build, table above), and the
documentation (the code repository). `scribe/pipeline/archiver.py` produces
this layout from a work directory and lists what it leaves out.

## Row format

Same as [flowcorp-ch/BudgieScribe-eval](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-eval)
and [FORMAT.md](https://github.com/alexxxcoelho/budgie-scribe/blob/main/FORMAT.md):

```json
{"id": "itn-00005", "file": "itn-telephone", "source": "itn", "lang": "fr",
 "held_out": false,
 "styling": "semi-formal", "structure": "prose", "context": "general",
 "control": "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]",
 "dirty": "tu peux m'appeler au zéro six douze trente-quatre cinquante-six soixante-dix-huit",
 "clean": "Tu peux m'appeler au 06 12 34 56 78."}
```

Real pairs carry the session of their unit in `file`
(`20180612-0900-PLENARY-en`, `044c_EBPH`); hold out by that key, never by
row.

## Reproduce a build, or train the next profile

```bash
# the shipped English build, on Hugging Face Jobs (~ $1)
hf jobs uv run hf/jobs/train.py --flavor a10g-small --timeout 2h --secrets HF_TOKEN -- \
    --lang en --pairs flowcorp-ch/BudgieScribe-data:mix/pairs_mix_en.jsonl \
    --out flowcorp-ch/scribe-en-repro --epochs 2 --batch 4

# BudgieScribe-Mini (Qwen3-1.7B, LoRA) from the same French data
hf jobs uv run hf/jobs/train.py --flavor a10g-large --timeout 4h --secrets HF_TOKEN -- \
    --lang fr --profil mini --pairs flowcorp-ch/BudgieScribe-data:mix/pairs_mix.jsonl \
    --out flowcorp-ch/scribe-mini-fr-next

# locally
hf download flowcorp-ch/BudgieScribe-data --repo-type dataset --local-dir <work>
export SCRIBE_LANG=fr SCRIBE_TRAVAIL=<work>/fr
python scribe/entrainement/train.py --profil mini --pairs <work>/mix/pairs_mix.jsonl --out scribe-mini-fr-next
```

Then GGUF (TRAINING.md §8) and the four evaluations (EVALUATION.md) against
the shipped build's weights, which are the A/B baseline.

## Personal data

`pii_scan.py` ran on both mixes; the full reports are in the archive
(`<lang>/pii_*.txt`) and the counts per family in `manifest.json`. Every hit
is in a synthetic family (`itn-telephone`, `itn-email`, `cmp-*`, `cri-*`:
random digit strings, template e-mail domains) or is a VoxPopuli session id
read as a phone number; the handful outside those families were read
(« 2020 Strategy », « 850 et le drive »). The training mixes keep the
generators' template domains (`gmail.com`, `free.fr`, …); only the public
held-out sets get the RFC 2606 domain swap of `exporter_heldout.py`.

## Updating

From the training machine, after a build is shipped:

```bash
python scribe/pipeline/archiver.py --lang fr --build scribe-v10 --mix pairs_mix10.jsonl <out>
python scribe/pipeline/archiver.py --lang en --build scribe-en-v8 --mix pairs_mix_en8.jsonl <out>
hf upload flowcorp-ch/BudgieScribe-data <out> . --type dataset --commit-message "scribe-v10, scribe-en-v8"
hf upload flowcorp-ch/scribe-v10 <work>/poc-fr/scribe-v10 . --private
```

`contrib/` is mirrored here from the code repository's `contrib/` by
`publish.yml` on every merge; it is the only path that writes to this
dataset without a person running the commands above.
