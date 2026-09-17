# Training BudgieScribe, end to end

The reproducible recipe behind the published models, and the procedure for a
new language. Every command below produced a shipped build; nothing is
described that was not run.

The repository contains code, prompts, documentation and only the **CC0 pairs
accepted through `contrib/` pull requests**. Licensed corpora, derived private
mixes, audio and weights never enter it. That is a license obligation for the
French corpus (see `NOTICE` §2). The pipeline reads and writes those private
artifacts in a work directory outside the repository, given by
`SCRIBE_TRAVAIL` (default: the current directory).

## 0. What a BudgieScribe model is

A **transcript normalizer**: a supervised fine-tune of a Qwen3 base model
that maps the raw output of a speech-to-text engine to the text the speaker
meant to dictate. The published builds are full fine-tunes of
[Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) (the `nano` profile);
larger profiles train a LoRA adapter on 1.7B / 4B / 8B (§7).

- **One model per language, at `nano`.** A 0.6B full fine-tune is exactly the
  configuration where a second language added to the same model overwrites the
  first. The pipeline is shared; data, spec and generators are per language.
  A LoRA profile keeps the base intact under the adapter, which is what makes
  a multilingual build worth trying there; nothing in the pipeline forbids a
  concatenated pairs file.
- **One format**, described in [FORMAT.md](FORMAT.md). The spec module of
  each language (`scribe/pipeline/spec.py`, `spec_en.py`) is the **single
  source** of that format for the teacher, the training data and inference.
  If the three diverge, the model learns a format it will never be given again.
- **Greedy decoding, always.** Everything is measured greedy.

## 1. Hardware and environment

The training script is standard `transformers` + `torch`: it runs on any
GPU with 16 GB of memory, CUDA, ROCm or Apple MPS, and on Hugging Face Jobs.

| | |
|---|---|
| Python | 3.12 |
| Training | `torch` ≥ 2.4, `transformers==4.57.6` (5.x breaks gradient-checkpointing recomputation on some torch builds), `peft` (LoRA profiles), `num2words` |
| Teacher / judges | any instruction model of 12B+ served locally by `llama-server` (the published builds used Gemma 12B QAT, Q4_0); a cloud API works too (`pipeline/llm.py`) |
| GGUF | llama.cpp **b10816** (`convert_hf_to_gguf.py` + `llama-quantize`), the release Budgie Echo serves with |
| One run | 34k pairs, 2 epochs: **43 min** on an AMD Radeon AI PRO R9700; ~1 h on an A10G (`hf jobs`, ≈ $1) |

Layout of the work directory, one per language:

```
<work>/
  poc-fr/  or  poc-en/      <- SCRIBE_TRAVAIL: units, pairs, models, logs
  hf/                       HF_HOME (base model cache)
  llamacpp/                 llama.cpp checkout at b10816
```

The generic device path (CUDA, MPS, CPU) is wired but has only been exercised on ROCm so far; open an issue with the log if it fails elsewhere. The published builds were trained on Windows with native ROCm; that
configuration (venvs, wheels, the PowerShell drivers in `scripts/`) is
documented in `scripts/README-rocm-windows.md` as *our* setup, not as a
requirement. The Python modules are what matter and run unchanged elsewhere.

> Keep the work directory on a real disk and copy every checkpoint somewhere
> else once. The French training data of one shipped build was lost when a
> temporary folder was purged.

That "somewhere else" is the private dataset
[flowcorp-ch/BudgieScribe-data](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-data)
(card: `hf/BudgieScribe-data/README.md`). It holds, for each shipped build,
the exact mix it was trained on (`mix/pairs_mix.jsonl` fr,
`mix/pairs_mix_en.jsonl` en), the components of that mix, the corpus units
and ASR transcripts, the teacher's raw outputs and adjudications, the mixes
of the previous builds, every `run.json`, the logs, the overnight chains, and
a snapshot of the code that produced the build. Not the weights: the
shipped GGUF is on the Hub (MODELS.md) and is the A/B baseline; the bf16
checkpoints stay on the training machine. Private because the French side
derives from SUMM-RE (NOTICE §2). Access is by request; with it,
§2–§6 can be skipped entirely and §7 starts from the Hub:

```bash
hf download flowcorp-ch/BudgieScribe-data --repo-type dataset --local-dir <work>
python scribe/entrainement/train.py --pairs <work>/mix/pairs_mix_en.jsonl --out scribe-en-repro --epochs 2 --batch 4
```

After a build ships, `scribe/pipeline/archiver.py` writes the archive from
the work directory and `hf upload` sends it (commands on the card).

## 2. Corpus: from recordings to dictation-sized units

The model is trained on **units**: stretches of one speaker, 20 to 150 words,
cut on annotated speech boundaries or silence, that look like one dictation.

| Language | Source | License | Script |
|---|---|---|---|
| French | [SUMM-RE](https://huggingface.co/datasets/linagora/SUMM-RE), manually transcribed `dev`+`test` only | CC BY-SA 4.0 | `scribe/corpus/summre.py`, `summre_units.py` |
| English | [VoxPopuli](https://huggingface.co/datasets/facebook/voxpopuli) `en`, `test`+`validation` | CC0 1.0 | `scribe/corpus/voxpopuli.py` |

```bash
export SCRIBE_LANG=en SCRIBE_TRAVAIL=<work>/poc-en
python scribe/corpus/voxpopuli.py        # parquet -> 16 kHz WAV units + manifest + eval reserve
```

Two rules learned the hard way:

- **Hold out by meeting / session, never by track.** Multi-microphone
  meetings put the same conversation on both sides of the fence otherwise, and
  the score becomes a polite lie.
- **Multi-track meetings are full of cross-talk**: each track is mostly the
  other participants' murmur, on which an ASR engine invents plausible
  content. `triage_units.py` sorts units by word ratio before any expensive
  reading; `read_pass.py` has a model read each unit and reject the invented
  ones.

The **raw side** of each pair is the ASR transcript of the unit (the published
builds used the engine that ships in Budgie Echo). The manual transcript is
kept only as a reference for quality control, never as a training target: it
records what was said, not what the speaker meant to dictate.

## 3. Quality gate on the raw side

Before a unit reaches the teacher, a judge decides whether the ASR transcript
is usable at all: binary OK / KO with closed causes (invention, suppression,
loop, translation, wrong speaker). A three-class scale was tried and dropped;
the middle class was noise.

```bash
python scribe/pipeline/qc_pass.py cohere_units_en.jsonl vox_unit_ref.jsonl qc_units_en.jsonl
python scribe/pipeline/preparer_unites.py cohere_units_en.jsonl qc_units_en.jsonl vox_unit_ref.jsonl units_en.jsonl eval_set_en.jsonl
```

`preparer_unites.py` also sets aside the **A/B evaluation set** (80 units)
that no later step may see. Reference transcripts carry anonymization and
annotation conventions (`SPEAKER_n`, joined words, markers); the judge prompt
declares them, otherwise it condemns a candidate for "changing an entity" it
transcribed right.

## 4. Teacher: the clean side

A teacher model rewrites each raw unit under the full spec of the language
(`spec.teacher_prompt(styling, structure, context)`), with a control line
sampled per unit: 40 % the default `semi-formal / prose / general`, the rest
drawn over the axes. One combination per unit covers all 16 modes at a
sixteenth of the cost of enumerating them.

```bash
python scribe/bancs/bench_prof_en.py enseigner <teacher> units_en.jsonl   # measure a candidate teacher first
python scribe/pipeline/teach.py units_en.jsonl pairs_vox_en.jsonl        # teacher + filter + adjudication
```

The teacher is measured before it is adopted (`bancs/bench_prof*.py`: two
candidates, mirrored A/B, adjudicated by both); the one used for the shipped
builds produced zero invented values on either side.

Then two mechanical nets:

- **Filter** (`make_pairs_v2.py` / `teach.py`): flags pairs whose clean side
  invents, drops content, flips a negation or ignores the control line. The
  filter is wrong more than once in two, structurally, so it **sorts, it does
  not decide**: every flagged pair goes to
- **Adjudication by reading** (`adjudicate.py`): a second pass that sees the
  pair *with the rule that applies* and recovers what the filter over-flagged
  (81–87 % recovered on the shipped runs).
- **`valider_paires.py`**: invariants of any pair set (invention, loss,
  identity, form; for French, accents: a set without accents teaches the model
  to strip them).
- **`pii_scan.py`**: no surname, address, phone, e-mail or bank identifier.
  Mandatory before mixing, and in CI.

## 5. Synthetic generators: what real speech does not contain

Real dictation contains almost none of the phenomena a user notices most:
13 self-corrections in 80,000 words, 17 spelled-out numbers. Deterministic
generators produce them **from the value**, so the expected output is known to
the character and can be scored without a judge.

| Generator (en) | Family | Shipped count (en) |
|---|---|---:|
| `gen_itn_en.py` | numbers, amounts, dates, times, percentages, phones, addresses | 10,000 |
| `gen_forme_en.py` | formatting blocks (lists, e-mail layout) + counter-examples that must stay prose | 8,000 |
| `gen_correction_en.py` | speaker self-corrections, resolved to the final value | 6,000 |
| `gen_compo_en.py` | 2–3 numeric expressions in one sentence | 4,000 |
| `gen_cor_itn_en.py` | self-correction × number in the same sentence | 3,000 |
| `gen_paragraphes_en.py` | multi-topic takes → paragraph breaks | 2,000 |

The French twins have the same names without `_en`. **One file per language,
never a generator with branches**: conventions differ (French puts a space
before `? ! :`, English does not; French keeps elisions in `casual`, English
drops apostrophes), and each `spec_*.py` cites the corpus measurement that
justifies its convention.

```bash
python scribe/generateurs/gen_itn_en.py 10000
python scribe/generateurs/gen_correction_en.py 6000
# ... forme, compo, cor_itn, paragraphes
python scribe/pipeline/valider_paires.py pairs_itn_en.jsonl
```

Each generator writes its own held-out slice (8 %, by family). The principle
that drove every version: **what the model is never shown, it never
produces.** Each shipped build closed one hole found by real cases placed in
the bench (correction × number, embedded amounts, "twelve hundred dollars",
unpunctuated paragraphs). The learning curve on real pairs plateaus around
1,200 pairs; volume is not the constraint, coverage of the tail is.

## 6. Mixing

```bash
python scribe/pipeline/melanger.py pairs_mix_en.jsonl pairs_itn_en.jsonl pairs_forme_en.jsonl pairs_correction_en.jsonl pairs_compo_en.jsonl pairs_cor_itn_en.jsonl pairs_paragraphes_en.jsonl pairs_vox_en.jsonl
python scribe/pipeline/pii_scan.py pairs_mix_en.jsonl
```

Shipped English mix (`scribe-en-v7`): 38,409 pairs (35,306 trained on, 3,103
held out), of which 1,409 real. Shipped French mix (`scribe-v9`): 41,387
pairs (38,042 / 3,345), of which 4,387 real (10.6 %). Both files, with their
components, are in the private dataset (§1). Below ~5 % real, the gradient
is dominated by memorized templates (loss → 0.000 in a few hundred steps);
at ~14 % (the `v8` mix) it carries information (loss 0.948 → 0.046).
Read fifty pairs of every new family before training; reading is what found
"we is preparing" and "ie".

## 7. Training

```bash
python scribe/entrainement/train.py --pairs pairs_mix_en.jsonl --out scribe-en-next --epochs 2 --batch 4
python scribe/entrainement/train.py --profil standard --pairs pairs_mix.jsonl --out scribe-standard-fr-next
```

For a reproducible Hugging Face Job over the public reviewed contributions,
pin the dataset commit and select the language files explicitly:

```bash
hf jobs uv run hf/jobs/train.py --flavor a10g-small --timeout 2h \
  --secrets HF_TOKEN -- \
  --lang fr --profil nano \
  --source 'flowcorp-ch/BudgieScribe-contrib@<dataset-commit>:contrib/fr/*.jsonl' \
  --out <namespace>/scribe-fr-next
```

`--source` is repeatable, so a run may use only the public contributions, only
an authorized private mix, or an explicit combination. The job rejects mixed
languages and duplicate ids/transcripts, then stores `selection.json` in the
private checkpoint. It records the resolved Hub commits, exact files, row
count and hashes. `--profil` chooses the standard size; `--base` can replace
the profile's base model and `--methode full|lora` can replace its method.

(`train.py` is `train_rocm.py` with generic device selection: `cuda`, then
`mps`, then CPU; on ROCm, torch reports the device as `cuda`.)

### Profiles

The base model, the method and the default hyperparameters come from a
**profile** (`--profil`, table in `scribe/entrainement/modeles.py`); every
value can be overridden on the command line (`--base`, `--methode`, `--lr`,
`--batch`, `--accum`, `--lora-r`, `--lora-alpha`).

| Profile | Base | Method | lr | batch × accum | Memory on one GPU |
|---|---|---|---|---|---|
| `nano` (published) | Qwen3-0.6B | full SFT | 1e-5 | 8 × 2 | ~10 GB |
| `mini` | Qwen3-1.7B | LoRA r=32 | 1e-4 | 8 × 2 | ~5 GB |
| `standard` | Qwen3-4B | LoRA r=32 | 1e-4 | 4 × 4 | ~10 GB |
| `large` | Qwen3-8B | LoRA r=32 | 1e-4 | 2 × 8 | ~18 GB |

Why the method changes with size: full SFT keeps fp32 weights and fp32 AdamW
state, 16 bytes per parameter — 27 GB for 1.7B before activations, 64 GB for
4B. That does not fit a 32 GB card, and ROCm spills to host memory silently
rather than failing. LoRA freezes the base in bf16 and trains an adapter on
every linear projection (q/k/v/o, gate/up/down); at the end of the run the
adapter is **merged into the weights** and the folder is saved as a plain
bf16 model. `gguf`, `eval-itn` and `eval-ab` load it like a full run. The
adapter alone is also kept in `<out>/adaptateur/` (tens of MB) for a server
that prefers to load base + adapter (vLLM).

`--methode full` on `mini` is legitimate on a 40 GB+ GPU (an A100 on Hugging
Face Jobs); on `standard` and `large` it is not an option on one card.

| | |
|---|---|
| Precision | full: fp32 weights and optimizer state, bf16 autocast on matmuls · LoRA: bf16 frozen base, fp32 adapter, bf16 autocast |
| Optimizer | fused AdamW where available, cosine schedule, 6 % warmup, grad clip 1.0 |
| Epochs | 2 |
| Max length | 512 tokens, labels masked on the prompt |
| Gradient checkpointing | on; `use_cache` forced back to `true` in the saved config (see §8) |
| Shipped runs (`nano`) | en-v5: 7,898 steps, 43.2 min, 24 units/s · fr-v8: 8,010 steps |

Do not change the base or the hyperparameters in the same round as the data:
one variable per round. The run writes `run.json` next to the weights with
every parameter, including `profil`, `base` and `methode`; the evaluation
scripts read it, so a `mini` candidate is compared to the 1.7B base, not to
the 0.6B (`eval_itn.py base:mini` addresses a profile's base directly). On
Hugging Face Jobs: `hf/jobs/train.py --profil …`, about a dollar for `nano`
on `a10g-small`; `mini` and `standard` fit an A10G, `large` wants an A100.

**Do not train with an inference server loaded on the same GPU.** A resident
`llama-server` keeps ~7 GB of VRAM and silently drops throughput five-fold,
with no error.

## 8. Conversion to GGUF

```bash
python scribe/entrainement/check_use_cache.py scribe-en-next     # refuses use_cache: false
python <llama.cpp>/convert_hf_to_gguf.py scribe-en-next --outfile scribe-en-next-f16.gguf --outtype f16
<llama.cpp>/llama-quantize scribe-en-next-f16.gguf scribe-en-next-Q4_K_M.gguf Q4_K_M
sha256sum scribe-en-next-Q4_K_M.gguf
```

- Left at `use_cache: false` by gradient checkpointing, the model still
  answers, ten minutes per sentence instead of four seconds, and no
  reading-based evaluation notices. Check it **before** converting.
- Convert with the llama.cpp release you serve with (b10816 for Budgie Echo).
- A LoRA profile's output folder is already merged; convert it as is. Do not
  convert `adaptateur/`.
- Q4_K_M was checked against fp32 on the release control set: identical
  output, character for character, including the empty string.

Then the one question the bytes cannot answer: **did this model see personal
data?** If yes, it does not leave the machine.

## 9. Evaluation

[EVALUATION.md](EVALUATION.md): held-out literal scoring, blind A/B against
the current build, real takes through the production path, regurgitation
probe. A build is published when all four are done and written in
[MODELS.md](MODELS.md).

## 10. Adding a language

What the English model needed, in order; expect one working day plus one GPU
hour:

1. **A corpus** of spontaneous speech with manual transcripts, CC0 or CC-BY,
   a few hours. Parliament corpora (VoxPopuli covers 16 languages) are
   prepared speech, less disfluent than dictation, but licensed clean.
2. `scribe/corpus/<corpus>.py`: units of 20–150 words, held out by session.
3. `scribe/pipeline/spec_<lang>.py`: the same interface as `spec_en.py`, with
   the language's typographic conventions **measured in the corpus, not
   assumed**, and its own `CORE_RULES` / `ITN_RULES`.
4. Judge and teacher prompts `scribe/prompts/_sys_*_<lang>.txt`.
5. The generator twins (`gen_itn_<lang>.py`, ...), each with its held-out
   slice; `num2words` support for the language.
6. Quality gate → teacher → adjudication → mix (§3–6), then train (§7),
   convert (§8), evaluate (§9).
7. Exit gate: ≥ 99 % exact on every synthetic axis, A/B over the base
   significant, zero invented value, a reading of 50 real outputs, and a clean
   regurgitation probe.

`SCRIBE_LANG=<lang>` makes `chemins.spec()` and `chemins.prompt()` load the
new files; nothing else in the pipeline is language-specific. Open an issue
before starting so the language is not done twice.
