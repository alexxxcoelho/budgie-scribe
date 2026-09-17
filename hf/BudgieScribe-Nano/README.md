---
license: other
license_name: budgiescribe-license
license_link: https://huggingface.co/flowcorp-ch/BudgieScribe-Nano/blob/main/LICENSE-MODEL
base_model: Qwen/Qwen3-0.6B
base_model_relation: finetune
library_name: gguf
pipeline_tag: text-generation
language:
  - fr
  - en
tags:
  - qwen3
  - gguf
  - asr
  - automatic-speech-recognition
  - text-normalization
  - inverse-text-normalization
  - punctuation
  - truecasing
  - speech-to-text
  - dictation
  - post-processing
  - french
  - english
datasets:
  - linagora/SUMM-RE
  - facebook/voxpopuli
---

# BudgieScribe Nano by Budgie

**0.6B open-weights text normalizers for speech-to-text output, French and
English, in GGUF.**

BudgieScribe takes the raw transcript of a dictation as it comes out of an
ASR engine (lowercase, no punctuation, hesitations, false starts,
self-corrections, numbers spelled out in words) and rewrites it as the text
the speaker meant to dictate. It is not a chat model: it does not answer,
summarize, translate or add anything. It does one job, and you steer it with a
control line at the top of the input.

**Nano** is the smallest member of the family: one full fine-tune of
Qwen3-0.6B per language, 378 MiB each, fast enough to run after every
dictation on a laptop. It is the cleanup model that ships inside
[Budgie Echo](https://gobudgie.com/echo), a local-first dictation app for
macOS and Windows. Larger members (Mini on Qwen3-1.7B, BudgieScribe on 4B,
Large on 8B) follow from the same pipeline. Everything is open:
[github.com/alexxxcoelho/budgie-scribe](https://github.com/alexxxcoelho/budgie-scribe).

| | French | English |
|---|---|---|
| File | `BudgieScribe-Nano-fr-Q4_K_M.gguf` | `BudgieScribe-Nano-en-Q4_K_M.gguf` |
| Size | 396,704,576 bytes (378.3 MiB) | 396,704,576 bytes (378.3 MiB) |
| SHA-256 | `5df4ab0d5a1a481c90cfd21a621b68d47f09600651438549c7605aa8ffb28463` | `02b3eb0b385d54a5c2fbe5c4a29c144fee9196972a22eef5d4659120147f49b5` |
| Internal build | `scribe-v9` | `scribe-en-v7` |
| Training | 38,042 units, 9,512 steps, 61 min | 35,306 units, 8,828 steps, 65 min |
| Real data | SUMM-RE (CC BY-SA 4.0), ~14 % of the mix | VoxPopuli EN (CC0), 1,382 pairs |

Common to both: full fine-tune of `Qwen/Qwen3-0.6B`, Q4_K_M (16.00 → 5.24
bits per weight; output identical, character for character, to the fp32
model on the release control set), 4,096-token context as served with inputs
chunked at 1,200 bytes, **greedy decoding always** (`temperature 0`,
`top_k 1`, thinking disabled), llama.cpp release **b10816** (the one that
produced the GGUFs and the one Echo serves them with), 0.8 s load and
~436 tok/s decode on a Radeon AI PRO R9700 (Vulkan). `manifest.json` in this
repository carries the same file names, builds and hashes for tooling.

## We are looking for contributors

These models are published *with* their weaknesses (see
[Evaluation](#evaluation)) because fixing them needs what one person does not
have: more real dictation pairs, more training runs, more eyes on outputs.
The repository documents the three ways to help, from fifty dictation pairs
to a whole new language, and every contribution is measured on the same
held-out sets before it is merged:
[CONTRIBUTING](https://github.com/alexxxcoelho/budgie-scribe/blob/main/CONTRIBUTING.md).

## Quickstart

```bash
llama-server -m BudgieScribe-Nano-fr-Q4_K_M.gguf \
  --jinja --chat-template-kwargs '{"enable_thinking":false}' \
  --temp 0 --top-k 1 --ctx-size 4096 --n-gpu-layers 999 --parallel 1
```

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "temperature": 0, "top_k": 1, "max_tokens": 256,
  "messages": [
    {"role": "system", "content": "You are a text normalizer for speech-to-text transcripts. The input begins with a control line specifying the styling, structure, and context settings; clean the transcript to match those settings and output only the cleaned text."},
    {"role": "user", "content": "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]\nalors euh on se retrouve vendredi non pardon jeudi à quatorze heures trente pour le point budget ça fait vingt-trois mille quatre cent cinquante euros"}
  ]}' | jq -r '.choices[0].message.content'
```

```
On se retrouve jeudi à 14h30 pour le point budget, ça fait 23 450 euros.
```

Same call with the English file and `[Lang: en]`:

```
so um lets meet friday no wait thursday at three fifteen p m the budget is twenty three thousand four hundred and fifty dollars
```
```
Let me meet Thursday at 3:15pm. The budget is $23,450.
```

The system prompt above is the exact string the models were trained with. Do
not rewrite it. One file per language: pick the model by the language of the
take, and pass the matching `[Lang: …]`.

## The format

The first line of the user message sets four axes. The models were trained on
this exact syntax; the complete contract (grammar, input and output rules,
invariants, decoding) is in
[FORMAT.md](https://github.com/alexxxcoelho/budgie-scribe/blob/main/FORMAT.md).

```
[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]
[Terms: Sara, Budgie, GGUF]        (optional)
<raw transcript>
```

| Axis | Values | Default | Effect |
|---|---|---|---|
| `Styling` | `casual` · `semi-casual` · `semi-formal` · `formal` | `semi-formal` | Written register. **Inert in this build**: trained with `semi-formal` only |
| `Structure` | `prose` · `lists` | `prose` | `lists` allows a Markdown bullet list when the content is a real enumeration of at least three items; `prose` forbids bullets |
| `Context` | `general` · `email` | `general` | `email` lays the text out as a message (see Limitations) |
| `Lang` | `fr` · `en` | — | Must match the file. Selects the model in Echo |
| `Terms` | up to 20 words | absent | Names and product words captured from the active window, spelled as they should be written |

## What it does, whatever the control line

- Removes filled pauses (« euh », « bah », « hum » / "um", "uh", "er"),
  involuntary repetitions (« le le chat », "the the report") and false starts.
- Resolves self-corrections to the value the speaker landed on:
  « vendredi non pardon jeudi » → « jeudi », "forty two sorry forty three" →
  "43". Measured 476/476 (fr) and 474/474 (en) on the held-out sets.
- Restores punctuation and capitalization. A real question ends with a
  question mark (« ? » preceded by a space in French, as in the corpus: 503
  occurrences with a space against 21 without); an indirect one takes a period.
- Inverse text normalization — converts the **form**, never the **value**:

| Dictated (fr) | Output | Dictated (en) | Output |
|---|---|---|---|
| « vingt-trois mille quatre cent cinquante euros » | `23 450 euros` | "twenty three thousand four hundred and fifty dollars" | `$23,450` |
| « quatorze heures trente » | `14h30` | "three fifteen p m" / "half past two" | `3:15pm` / `2:30` |
| « le trois mars deux mille vingt-six » | `le 3 mars 2026` | "march third twenty twenty six" | `March 3, 2026` |
| « vingt-cinq pour cent » | `25 %` | "twenty five percent" | `25%` |
| « support arobase gobudgie point com » | `support@gobudgie.com` | "oh seven nine one two three four five six seven eight" | `07912 345678` |
| `2500 personnes` (already digits) | unchanged | `2500 people` | unchanged |

  Measured 794/797 (fr) and 792/798 (en) on the held-out ITN sets, 317/319
  and 318/319 on compositions of two or three adjacent numbers, 237/237 (en)
  on self-correction × number in one sentence.
- Returns an **empty string** when the input is only noise or hesitations.
  That is a valid result, not an error; Echo keeps the raw text in that case.
- Normalizes orders and questions instead of obeying them: « écris-moi un
  poème sur la mer » comes out as « Écris-moi un poème sur la mer. ». A
  dictation is full of imperatives; this is a safety property.
- Does not translate. Islands of the other language stay as dictated.

## What it never does, by construction

- Add a name, a number, an idea that is not in the input.
- Correct a number that *looks* wrong (it copies it), or guess a missing year,
  area code or domain.
- Drop a clause that carries meaning (« non », « bon », « en fait », "well",
  "so", "actually" are discourse markers, not corrections).
- Flip a negation, summarize, or rephrase to sound nicer.

## Examples

Every output below is the real, greedy output of these exact GGUFs through
llama.cpp b10816 (`examples/replay_examples.sh` in the repository reproduces
them). Flaws are left in and pointed out: they are what the next build has to
fix.

**French**

```
[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]
euh bonjour c'est pour le le rendez-vous de de mardi non mercredi matin est-ce que dix heures ça vous va
```
```
Bonjour, c'est pour le rendez-vous de mercredi matin est-ce que 10h ça vous va ?
```
Fillers, stutters and the self-correction are resolved. Two flaws: no comma
or period before « est-ce que », and « dix heures » rendered as `10h` where
`10 heures` reads better.

```
[Styling: semi-formal] [Structure: lists] [Context: general] [Lang: fr]
il me faut trois choses pour demain le rapport financier ensuite les slides de la présentation et puis la liste des participants
```
```
Il me faut 3 choses pour demain :
- le rapport financier
- les slides de la présentation
- la liste des participants
```
The list is right. Flaw: « trois choses » became `3 choses`; the number rule
is applied to a small count that French would leave in letters.

**English**

```
[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]
hi um its about the the meeting on tuesday no wednesday morning does ten work for you
```
```
It's about the meeting on Wednesday morning does 10 work for you.
```
Two flaws: the greeting "hi" was dropped, and the question was not split off
nor given its "?".

```
[Styling: semi-formal] [Structure: lists] [Context: general] [Lang: en]
i need three things for tomorrow the financial report then the slides for the presentation and the list of attendees
```
```
I need:
- The financial report
- The slides for the presentation
- The list of attendees
```
The list is right. Flaw: "three things for tomorrow" was dropped from the
lead-in, a suppression the guard rails in Echo would catch on a longer take.

**Both**

```
[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]
euh hum euh
```
```

```
Empty output: valid, the input carried nothing. And an order is normalized,
not obeyed: "write me a poem about the sea" → "Write me a poem about the sea."

## Deployment

**llama.cpp** — see Quickstart. The three flags that matter: `--jinja` (the
chat template is in the GGUF metadata), `enable_thinking: false` (Qwen3 would
otherwise emit a reasoning block), `--temp 0` (the models expect greedy
decoding; sampling adds variance and invents).

**Ollama** — this repository holds two GGUFs of the same quantization, so
point Ollama at the file rather than the repo:

```bash
hf download flowcorp-ch/BudgieScribe-Nano BudgieScribe-Nano-fr-Q4_K_M.gguf --local-dir .
printf 'FROM ./BudgieScribe-Nano-fr-Q4_K_M.gguf\nPARAMETER temperature 0\nPARAMETER top_k 1\n' > Modelfile
ollama create budgiescribe-nano-fr -f Modelfile
```
Then call the API with `"think": false` and the system prompt from Quickstart.

**LM Studio** — load the GGUF, turn reasoning off, set temperature to 0.

**Budgie Echo** — nothing to do: Echo downloads these exact files (same
SHA-256) from its own catalog under *Settings → Text enhancements → Automatic
cleanup*, and routes to the French or English file by the detected language
of the take.

**Echo command line** — the same runtime and guard rails as the app, from a
terminal: `echo-cli scribe clean --language fr < transcript.txt`. Download at
[gobudgie.com/echo/cli](https://gobudgie.com/echo/cli).

## Best practices

These are the rules Budgie Echo applies around the models, and the reasons.

- **Greedy decoding, always.** `temperature 0`, `top_k 1`. The models were
  evaluated greedy; every measurement below assumes it.
- **Cap the output** at `ceil(1.3 × input_tokens) + 32` tokens. A normalizer
  that produces much more than its input is looping.
- **Chunk long inputs at ~1,200 bytes**, on a sentence boundary. The models
  were trained on dictation-sized units (median ~75 words); a 10-minute take
  pushed whole into the context degrades.
- **Verify the output before trusting it.** Echo's runtime rejects an output
  and keeps the raw transcript when it detects an invention (a number absent
  from the input), a loop, a large suppression, a length drift, or a flipped
  negation. Over 260 real takes, that guard fired 21 times. Reproduce at least
  the length and loop checks.
- **Send the transcript alone.** No instructions, no examples, no free text
  before the control line: the model would normalize them.

## Evaluation

Held-out literal scoring on synthetic sets, then real dictations through the
production path. The method is in
[EVALUATION.md](https://github.com/alexxxcoelho/budgie-scribe/blob/main/EVALUATION.md);
the sets are [flowcorp-ch/BudgieScribe-eval](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-eval).

**Held-out synthetic sets** (deterministic generators, expected output known
to the character). These tables were measured on the previous builds of the
same recipe, `scribe-v8` and `scribe-en-v5`; `scribe-v9` / `scribe-en-v7`
add the phase-3 axes (French paragraphs, `Context: email` layout, embedded
amounts, `[Terms:]`), and their own tables replace these as soon as they are
run. Until then, read them as the floor this line of models has held, not as
a measurement of these bytes.

| Axis | fr cases | fr exact | en cases | en exact |
|---|---:|---:|---:|---:|
| Formatting blocks | 635 | 635 | 634 | 634 |
| Self-corrections | 476 | 476 | 474 | 474 |
| Inverse text normalization | 797 | 794 | 798 | 792 |
| Composition (2–3 adjacent numbers) | 319 | 317 | 319 | 318 |
| Self-correction × number in one sentence | — | — | 237 | 237 |
| Wrong numeric value, all held-out cases | — | — | 2,462 | 7 (0.3 %) |

**Blind pairwise A/B against the base Qwen3-0.6B** on 80 held-out real French
units (LLM judge, mirrored order, forced ties): 37 wins / 30 losses, the rest
ties. **VoxPopuli**, 170 held-out English units, word accuracy against the
official transcript: 93.9 % (the gap is entirely the 17 units run with
`[Context: email]`, see Limitations).

**Real dictations** (the author's own takes through Budgie Echo's local ASR
and the production runtime). French: numbers, dates and amounts, punctuation,
and no hallucination on noise, where the raw engine invents; observed failure
modes on colloquial French are occasional one-word substitutions that read
fluently (« t'en es où là ? » → « tu es là ? »), dropped intent markers
(« non, non, non »), register changes (« mec » → « homme ») — errors of
meaning, invisible on a re-read, that the guard rails do not catch. English:
better than raw on numbers, dates and amounts; weaker on false starts and
paragraph breaks.

## Limitations

Observed on `scribe-v8` / `scribe-en-v5`. The ones marked *phase-3 target*
are what v9 / en-v7 were trained to fix; they stay listed until their
held-out tables say so.

Both languages:

- **`Styling` is inert**: trained on `semi-formal` only.
- **`Context: email` adds a greeting and a sign-off that were not dictated**
  (*phase-3 target*). Use `general` unless you post-check.
- **Phone numbers dictated with « double » / « triple »** can lose or repeat a
  digit (en: 32/36).
- One language per file. Mixed-language takes are handled sentence by
  sentence by Echo, not by the models.

French:

- **No paragraph breaks**: a long take comes out as one block (*phase-3
  target*).
- **One-word substitutions** on colloquial French (see Evaluation).
- Small counts written as digits (« trois » → `3`).

English:

- "like" as a filler is kept; "gonna" becomes "I'll" instead of "going to";
  British spellings are americanized ("organisations" → "organizations").
- **Amounts embedded mid-sentence** can lose the symbol (*phase-3 target*)
  ("the twelve hundred dollars a month" → "1,200 dollars a month").
- One wrong value in 798 ("… and nineteen pounds" read as pence).

## Training

Full supervised fine-tune of `Qwen/Qwen3-0.6B` (no LoRA), fp32 weights with
bf16 autocast, fused AdamW, lr 1e-5, cosine schedule with 6 % warmup, batch 4,
gradient accumulation 2, 2 epochs, max length 512, labels masked on the prompt,
gradient clipping 1.0. French: 38,042 training units, 9,512 optimizer steps,
61 minutes on a single 32 GB GPU. English: 35,306 units, 8,828 steps, 65
minutes. `run.json` ships with each checkpoint. The script is standard
`transformers` + `torch` and runs on any 16 GB GPU or on Hugging Face Jobs for
about a dollar; the `nano` profile of `scribe/entrainement/train.py` is this
exact recipe.

Training mix, French: raw-to-clean pairs produced by a local teacher model
from dictation-sized units of the
[SUMM-RE](https://huggingface.co/datasets/linagora/SUMM-RE) corpus, filtered
by a binary quality gate and adjudicated by reading (~14 % of the mix), plus
deterministic synthetic pairs for what real speech does not contain enough of:
number writing, speaker self-corrections, formatting blocks, compositions.
English: 10,000 number-writing pairs + 8,000 formatting + 6,000
self-corrections + 4,000 compositions + 3,000 self-correction × number +
2,000 paragraphs, all deterministic synthetic pairs, plus 1,382 real pairs
cut from [VoxPopuli](https://huggingface.co/datasets/facebook/voxpopuli)
(CC0), teacher-cleaned and adjudicated.

The whole pipeline (corpus preparation, generators, teacher, quality gate,
training profiles, GGUF conversion, benches) is published:
**[github.com/alexxxcoelho/budgie-scribe](https://github.com/alexxxcoelho/budgie-scribe)**.
The derived corpus (pairs, units, audio cuts) is not distributed, by license
(see NOTICE §2). The synthetic held-out sets are published as
[flowcorp-ch/BudgieScribe-eval](https://huggingface.co/datasets/flowcorp-ch/BudgieScribe-eval)
so that any change can be measured the same way.

No personal data: every data set is scanned before training, and the
dictations of Budgie users, including the author's, were excluded from these
builds.

## License

BudgieScribe is released under the **Apache License 2.0**, which it inherits
from Qwen3-0.6B, **plus one additional term**: any use, distribution, or
integration of these models, whether unmodified or as part of a derivative
work or product, must continue to identify them by their original name,
**"BudgieScribe" by "Budgie"**, using that exact capitalization.

The full text is in [LICENSE-MODEL](LICENSE-MODEL); [NOTICE](NOTICE) lists the
attributions (SUMM-RE by LINAGORA, ANR-20-CE23-0017; VoxPopuli; Qwen3) and
states the position taken on training-data licensing.

## Citation

```bibtex
@misc{budgiescribe2026,
  title  = {BudgieScribe: open-weights dictation normalizers for French and English},
  author = {Coelho, Alexandre and Budgie},
  year   = {2026},
  url    = {https://huggingface.co/flowcorp-ch/BudgieScribe-Nano}
}
```

Please also cite SUMM-RE (LINAGORA, ANR-20-CE23-0017) when you build on the
French model.
