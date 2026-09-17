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
meant. Contributions arrive as **pull requests** on this repository, in
`contrib/<lang>/<handle>-<YYYY-MM>.jsonl` — one file per contributor and
month, one language per folder. Git keeps the history, the CI keeps the
gate, a maintainer keeps the reading.

A pair is one JSON line, in the exact shape the training script reads:

```json
{"id": "alex-2026-09-001", "file": "alex-2026-09", "lang": "fr",
 "control": "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]",
 "dirty": "alors euh on se voit jeudi non vendredi à dix heures",
 "clean": "On se voit vendredi à 10 heures.",
 "source": "budgie-echo-cohere"}
```

- `dirty` is the **raw output of an ASR engine**, not a transcript you typed:
  the model learns to fix what engines actually produce. The easiest way to
  get it exactly as Budgie Echo sees it is to let the app and its CLI collect
  your own dictations. On an Apple silicon Mac, install the CLI from its
  Homebrew tap, then sign in once:

  ```bash
  brew install alexxxcoelho/budgie/echo-cli
  echo-cli login
  ```

  Create and export contribution pairs with:

  ```bash
  echo-cli scribe prepare                       # your Echo history → candidate pairs,
                                                # corrected by a local teacher model
  echo-cli transcribe --capture my_take.wav     # a file's raw transcript joins the queue
  # …review each pair in Budgie Echo → Import audio → Scribe training…
  echo-cli scribe export --contrib contrib --handle <you>
  ```

  `prepare` is idempotent (run it daily); `export` writes
  `contrib/<lang>/<you>-YYYY-MM.jsonl` in this exact format, ready for the
  verifier. In the app, turn on *Settings → Text enhancements → Collect
  training pairs* and every correction you make by hand on a result becomes a
  candidate too. The CLI is free to use. Homebrew keeps it current with
  `brew upgrade echo-cli`. Any other engine is welcome too; name it in
  `source`.
- `clean` is what you meant, under the rules of [FORMAT.md](FORMAT.md) §8:
  fillers gone, corrections resolved, numbers written, nothing added, nothing
  summarized. When in doubt, keep the speaker's words.
- `control` is the line the model will be given (`spec.control_line`); use
  `semi-formal` / `prose` / `general` unless the take really is a list or an
  e-mail. `file` is the file name without extension — it is the key that
  traces the pair through every training mix. `id` is unique across the
  whole `contrib/` folder. No `held_out`: the train/eval split is made at
  mixing time, by file, never inside a contribution.
- Between 20 and 150 words per pair. A long recording becomes several pairs
  cut on sentence boundaries.
- **No personal data**: no third-party names, real e-mail addresses, phone
  numbers, postal addresses, account numbers. Your own voice, or the
  speaker's consent. Pairs are released under **CC0 1.0** (the pull request
  template asks you to confirm).

Copy `contrib/fr/exemple-2026-09.jsonl` or `contrib/en/example-2026-09.jsonl`
to start; they are templates and never enter a training mix.

Before opening the pull request, run the same gate the CI runs:

```bash
python scribe/pipeline/verifier_contribution.py contrib/fr/<handle>-2026-09.jsonl
```

It refuses what is mechanically wrong — file name, missing keys, a control
line outside the grammar, a language that disagrees with the folder, a
duplicate of a pair already in `contrib/`, personal data (`pii_scan.py`),
structural faults (`valider_paires.py`: capitalization, final punctuation,
identical sides, missing accents) — and prints why, line by line.

What happens then:

1. **CI** (`check-data.yml`) reruns the gate on the changed files and posts
   the report in the checks. A red check means the pull request is not read
   yet: fix and push again.
2. **A maintainer reads the pairs** — up to fifty of them — for what no
   script sees: a meaning that drifted, a number rewritten, a filler that was
   in fact a word. Comments go on the pull request lines.
3. **Merge.** The file is mirrored to `contrib/` of the training dataset
   ([flowcorp-ch/BudgieScribe-data](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-data))
   by `publish.yml`, and enters the next training round.
4. **Results come back.** The next build's `MODELS.md` entry and the pull
   request get the held-out tables and the blind A/B against the previous
   build; `file` in the mix says exactly which contribution was in it.

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
