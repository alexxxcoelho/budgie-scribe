# Evaluating a BudgieScribe build

Four instruments, in this order. A counter never decides alone: every number
points at outputs that a person then reads.

## 1. Held-out synthetic sets — literal scoring, no judge

Each generator (`scribe/generateurs/gen_*.py`) writes 8 % of what it produces
into a held-out slice, by family, never seen in training. Because the
generators start from the **value**, the expected output is known to the
character, and scoring is exact string comparison.

```bash
export SCRIBE_LANG=en SCRIBE_TRAVAIL=<work>/poc-en
python scribe/bancs/eval_synth.py <checkpoint-dir|base> heldout_correction_en.jsonl
python scribe/bancs/eval_itn.py   <checkpoint-dir>            # numbers only, by family
```

Both load a `transformers` checkpoint (the fp32 output of training) and
decode greedily; the published GGUF was checked to give identical output on
the release control set, and its card examples are reproduced by
`examples/replay_examples.sh`. On Hugging Face Jobs: `hf/jobs/eval.py`.

Reported per axis: exact matches, and for numbers **wrong value** separately
from wrong formatting. A wrong amount that reads fluently is the worst failure
this model can produce, and it is the number to watch first.

The held-out sets are published as
[flowcorp-ch/BudgieScribe-eval](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-eval)
so that any build, from anyone, is scored on the same cases.

## 2. Blind A/B against the current build — LLM judge, mirrored

80 real units held out by session. Two builds produce their outputs; a local
judge model sees each pair in both orders, without knowing which is which,
and must pick or declare a tie. The judge's own determinism is measured
(`accord_juges.py`) before its verdicts count.

```bash
python scribe/bancs/ab_eval.py gen_current.jsonl gen_candidate.jsonl ab_result.jsonl
```

Read the result as a sign test: with 80 cases, a z below 1.96 means nothing
to conclude, and a difference of one point of judge score is noise. The
project has never merged on a non-significant A/B and does not intend to.

## 3. Real dictations through the production path

The check a user feels. Real takes, transcribed by the engine that ships in
Budgie Echo, then passed through the **runtime** that serves the model
(1,200-byte chunks on sentence boundaries, guard rails, raw text returned on a
rejected output), then compared to the raw transcript. Compare **pairwise**,
raw against normalized on the same take, with the mirrored-order and
forced-tie controls of §2; an absolute 1–5 grade without a reference is too
noisy to rank a build against its own input, and no number of that kind is
published.

Lesson learned the hard way: replay a post-processor through its production
path, not through its model. Sending whole 10-minute takes to the model
directly produced loops and 70 % losses that were artifacts of the replay,
not of the model.

The corpus of takes is not published (it is personal dictation); the method
is, and any team can run it on its own takes.

## 4. Regurgitation probe — before any publication

Fifty prompts of the form « je m'appelle », « mon adresse est », « mon
numéro est », "my email is", greedy, on the GGUF about to be published; every
output through `scribe/pipeline/pii_scan.py`. The expected result is zero
findings. A model that completes a name or a number it was never given in the
input has memorized something, and does not ship.

## How to read a results table

| Column | Means | Do not read as |
|---|---|---|
| exact 634/634 | on synthetic cases of that family, output identical to the expected string | "the model is perfect at formatting" — the family is what the generator covers |
| wrong value 7 (0.3 %) | digits differ from the dictated value | fewer is better; zero is the target; anything above 1 % blocks a release |
| A/B 37 / 30 | wins / losses against the compared build on 80 real units, rest ties | significant only if z ≥ 1.96 |

## Reproducing the published numbers

Every number in MODELS.md and on the model cards was produced by one of the
scripts above on the stated build. The synthetic sets and the scripts are
public; the A/B set and the real takes are not (personal or license-bound
data), so 2 and 3 are reproducible in method, not in bytes. Open an issue if a
published number does not match what you get on the public sets.
