# Contributing to BudgieScribe

Three ways to help, in the order that moves the models fastest. Each ends in
a pull request that CI checks the same way for everyone.

Ground rules for every contribution:

- **No personal data, ever.** No surname, postal address, phone number,
  e-mail address, bank identifier or anything that identifies a real person.
  First names alone are fine. `scribe/pipeline/pii_scan.py` runs on every data
  file in CI; run it locally first.
- **You hold the rights** to what you contribute, or it is CC0 / CC-BY. Say
  which in the pull request. CC BY-SA and non-commercial corpora are not
  accepted (the weights are Apache 2.0).
- **Measured, not argued.** A change to data, spec or generators is accepted
  on the held-out sets and a blind A/B, not on a description.

## 1. Data: dictation pairs

The models are short of one thing: real dictation with the text the speaker
meant. A pair is one JSON line:

```json
{"lang": "fr", "sale": "alors euh on se voit jeudi non vendredi à dix heures", "propre": "On se voit vendredi à 10 heures.", "control": {"styling": "semi-formal", "structure": "prose", "context": "general"}, "source": "own-dictation"}
```

- `sale` is the **raw output of an ASR engine**, not a transcript you typed:
  the model learns to fix what engines actually produce. The easiest way to
  get it exactly as Budgie Echo sees it:

  ```bash
  echo-cli stt transcribe --raw --format pairs my_take.wav > pairs.jsonl
  ```

  This writes the raw side for each take with Scribe off; you fill in
  `propre`. The CLI is free to use (60 minutes of local transcription per
  month) and downloads from [gobudgie.com/echo/cli](https://gobudgie.com/echo/cli).
  Any other engine is welcome too; say which one in `source`.
- `propre` is what you meant, under the rules of [FORMAT.md](FORMAT.md) §8:
  fillers gone, corrections resolved, numbers written, nothing added, nothing
  summarized. When in doubt, keep the speaker's words.
- Between 20 and 150 words per pair. A long recording becomes several pairs
  cut on sentence boundaries.

Before opening the pull request:

```bash
python scribe/pipeline/pii_scan.py pairs.jsonl          # must print "0 ligne(s) signalee(s)"
python scribe/pipeline/valider_paires.py pairs.jsonl    # structural invariants: no invention, no loss, accents (fr)
```

Then a pull request on the data repository
[huggingface.co/datasets/flowcorp-ch/BudgieScribe-data](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-data)
(one folder per language, one file per contribution, a `README` line with the
license you assert). CI reruns both checks; a maintainer reads fifty pairs;
merged pairs enter the next training round and the results are posted back
on the pull request.

Fifty good pairs are worth more than five hundred careless ones: the learning
curve on real pairs plateaus early, coverage of rare phenomena is what moves
the model.

## 2. Training: run the recipe, or a new language

[TRAINING.md](TRAINING.md) is the full recipe. It is standard `transformers`
+ `torch` and runs on any 16 GB GPU (CUDA, ROCm, Apple MPS), or on Hugging
Face Jobs for about a dollar a run:

```bash
hf jobs uv run hf/jobs/train.py --flavor a10g-small --timeout 2h --secrets HF_TOKEN -- --lang en --pairs flowcorp-ch/BudgieScribe-data:mix/pairs_mix_en.jsonl --out <you>/scribe-en-next
```

What is worth training, in order of measured impact:

| Language | Gap | Where the fix lives |
|---|---|---|
| fr | no paragraph breaks on long takes | port `gen_paragraphes_en.py` to French, retrain |
| fr | one-word meaning substitutions on colloquial speech | counter-examples in `gen_correction.py` (words that must stay) |
| en, fr | `Context: email` adds a greeting that was not dictated | `CONTEXT_RULES["email"]` in the spec, counter-examples in `gen_forme_*` |
| en | discourse openers ("Okay, so") kept | counter-examples in `gen_correction_en.py` |
| en, fr | `Styling` axis inert | draw the register in `gen_forme_*` / `gen_correction_*` |
| any | **a new language** | TRAINING.md §10, one day plus one GPU hour |

A training pull request contains: the generator or spec change, the mix
composition printed by `melanger.py`, the held-out results, the A/B against
the current build, and the GGUF's SHA-256. Not the weights: maintainers
rebuild them from the recipe before publishing, so that the published bytes
always come from the published code.

## 3. Verification: read, replay, report

The cheapest and most needed contribution. Pick one:

- **Replay the card examples** on your machine with
  `examples/replay_examples.sh` and report any output that differs from the
  card (it should not; if it does, the GGUF or the runtime is not what we
  think).
- **Read fifty outputs** of a build on your own dictations and file the
  failures as issues, one phenomenon per issue, with the raw input and the
  output. "The model changed the meaning of X" with the exact text is the
  most valuable issue this project can receive.
- **Run the held-out evaluation** on a proposed build
  ([EVALUATION.md](EVALUATION.md)) and post the table on the pull request.
  Two independent runs of the same table are how a change gets merged.

## Style of the repository

- One file per language for anything language-specific (`spec_<lang>.py`,
  `gen_*_<lang>.py`); never a generator with branches.
- A generator writes from the **value**, so the expected output is known to
  the character.
- Data never enters the repository. The work directory is `SCRIBE_TRAVAIL`.
- Comments and documentation say what was measured, with the number, or say
  "not measured".
