# Published models

One Hub repository per **family** (Nano, Mini, BudgieScribe, Large — one
training profile each, see TRAINING.md §7), both languages inside as
`<Family>-<lang>-Q4_K_M.gguf`. The GGUF bytes on Hugging Face are the bytes
Budgie Echo downloads; the SHA-256 is the contract, and
[`models/manifest.json`](models/manifest.json) is where it is written down.

## Nano — flowcorp-ch/BudgieScribe-Nano

Qwen3-0.6B, full fine-tune, one file per language.

### French — `BudgieScribe-Nano-fr-Q4_K_M.gguf`

| | |
|---|---|
| Hugging Face | [flowcorp-ch/BudgieScribe-Nano](https://huggingface.co/flowcorp-ch/BudgieScribe-Nano) |
| Internal build | `scribe-v9` (phase 3) |
| File | `BudgieScribe-Nano-fr-Q4_K_M.gguf` — 396,704,576 bytes (378.3 MiB) |
| SHA-256 | `5df4ab0d5a1a481c90cfd21a621b68d47f09600651438549c7605aa8ffb28463` |
| Base | Qwen/Qwen3-0.6B, full SFT, 38,042 training units, 9,512 steps, 61 min |
| Real data | SUMM-RE (CC BY-SA 4.0), ~14 % of the mix, teacher-cleaned, adjudicated |
| llama.cpp | b10816 |

Held-out synthetic sets (measured on `scribe-v8`, the previous build of the
same recipe; `scribe-v9` tables pending):

| Axis | Cases | Exact |
|---|---:|---:|
| Formatting blocks | 635 | 635 |
| Self-corrections | 476 | 476 |
| Inverse text normalization | 797 | 794 |
| Composition (2–3 adjacent numbers) | 319 | 317 |

Blind A/B against the base model, 80 held-out real units: 37 wins / 30
losses, rest ties.

Known limits (observed on v8; paragraphs and email are phase-3 targets of
v9): no paragraph breaks; `Styling` axis inert; `Context: email`
adds an undictated greeting; small counts written as digits (« trois » →
`3`); phone numbers dictated with « double » can lose a digit.

### English — `BudgieScribe-Nano-en-Q4_K_M.gguf`

| | |
|---|---|
| Hugging Face | [flowcorp-ch/BudgieScribe-Nano](https://huggingface.co/flowcorp-ch/BudgieScribe-Nano) |
| Internal build | `scribe-en-v7` (phase 3) |
| File | `BudgieScribe-Nano-en-Q4_K_M.gguf` — 396,704,576 bytes (378.3 MiB) |
| SHA-256 | `02b3eb0b385d54a5c2fbe5c4a29c144fee9196972a22eef5d4659120147f49b5` |
| Base | Qwen/Qwen3-0.6B, full SFT, 35,306 training units, 8,828 steps, 65 min |
| Real data | VoxPopuli EN (CC0), 1,382 pairs, teacher-cleaned, adjudicated |
| llama.cpp | b10816 |

Held-out synthetic sets (measured on `scribe-en-v5`, the previous build of
the same recipe; `scribe-en-v7` tables pending):

| Axis | Cases | Exact |
|---|---:|---:|
| Self-correction × number in one sentence | 237 | 237 |
| Composition (2–3 adjacent numbers) | 319 | 318 |
| Formatting blocks | 634 | 634 |
| Self-corrections | 474 | 474 |
| Inverse text normalization | 798 | 792 |
| Wrong numeric value, all 2,462 held-out cases | 2,462 | **7 (0.3 %)** |
| Hand-written real cases | 32 | 27 exact, 32 correct values |

VoxPopuli, 170 held-out units, word accuracy against the official transcript:
93.9 %.

Known limits (observed on en-v5; email and embedded amounts are phase-3
targets of en-v7): `Styling` axis inert; `Context: email` adds an undictated
greeting and sign-off; "like" filler kept; "gonna" → "I'll"; British
spellings americanized; amounts embedded mid-sentence can lose the symbol;
phone numbers dictated with "double" / "triple": 32/36; one wrong value in
798 ("… and nineteen pounds" read as pence).

## Retired or unpublished builds

| Build | Why it is not published |
|---|---|
| `scribe-v7` (fr) | trained with 162 personal dictation units; kept local by rule, never distributed |
| `scribe-v1`–`v6`, `scribe-en-v1`–`v4` | superseded; results in the training notes of each generator |

## Next builds

`scribe-v9` and `scribe-en-v7` are the phase-3 builds (`Context: email` lays
out only what was dictated; French paragraphs; embedded amounts; phone
numbers; the optional `[Terms:]` line) and are the published bytes above.
Their held-out tables are still to be run; the previous build's tables stand
in until then. Larger profiles (`mini` 1.7B, `standard` 4B, `large` 8B, see
TRAINING.md §7) have no published build yet.
