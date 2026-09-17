# BudgieScribe

**Small open-weights models that turn raw speech-to-text output into the text
you meant to dictate. One model per language. 378 MiB each. Runs on a laptop.**

A dictation engine gives you this:

```
alors euh on se retrouve vendredi non pardon jeudi à quatorze heures trente pour le point budget ça fait vingt-trois mille quatre cent cinquante euros
```

BudgieScribe gives you this:

```
On se retrouve jeudi à 14h30 pour le point budget, ça fait 23 450 euros.
```

It removes fillers and false starts, resolves self-corrections to the value
the speaker landed on, restores punctuation and capitalization, and writes
numbers, dates, times and amounts the way you would type them. It never adds,
summarizes, answers or translates.

Each model is a full supervised fine-tune of Qwen3-0.6B, trained on public
speech corpora and deterministic synthetic pairs, with no personal data. They
ship inside [Budgie Echo](https://gobudgie.com/echo), a local-first dictation
app for macOS and Windows; this repository is everything needed to reproduce,
evaluate and improve them.

One Hub repository per family, both languages inside:

| Family | Base | Hub repository | Status |
|---|---|---|---|
| **Nano** | Qwen3-0.6B, full fine-tune | [flowcorp-ch/BudgieScribe-Nano](https://huggingface.co/flowcorp-ch/BudgieScribe-Nano) | published (`-fr`, `-en`) |
| Mini | Qwen3-1.7B, LoRA | flowcorp-ch/BudgieScribe-Mini | training profile ready, no build yet |
| BudgieScribe | Qwen3-4B, LoRA | flowcorp-ch/BudgieScribe | training profile ready, no build yet |
| Large | Qwen3-8B, LoRA | flowcorp-ch/BudgieScribe-Large | training profile ready, no build yet |

Current results, limits and build ids: [MODELS.md](MODELS.md).
[`models/manifest.json`](models/manifest.json) is the contract: file name,
build and SHA-256 of every published GGUF. [`publish.yml`](.github/workflows/publish.yml)
re-downloads each file from the Hub, refuses to publish a card whose bytes
do not match the manifest, and pushes through a Hugging Face Trusted
Publisher — no token stored anywhere.

## Try it in three commands

```bash
hf download flowcorp-ch/BudgieScribe-Nano BudgieScribe-Nano-fr-Q4_K_M.gguf --local-dir .
llama-server -m BudgieScribe-Nano-fr-Q4_K_M.gguf --jinja --chat-template-kwargs '{"enable_thinking":false}' --temp 0 --top-k 1
examples/replay_examples.sh "$(which llama-server)" BudgieScribe-Nano-fr-Q4_K_M.gguf fr
```

Or with Ollama: `ollama create` from the downloaded GGUF (the card shows the
Modelfile), then send the format described in [FORMAT.md](FORMAT.md) with
thinking off and temperature 0.

Or without installing anything: use Budgie Echo, or the Echo command line
tool, which runs the same models with the same guard rails
(`echo-cli scribe clean --language fr < transcript.txt`). Download:
[gobudgie.com/echo/cli](https://gobudgie.com/echo/cli).

## Scribe Cloud

If you cannot run the model where you dictate — on a phone, for instance —
Budgie hosts it. Any Budgie account can call BudgieScribe on our servers
through the Budgie gateway (`POST /api/scribe/normalize` with your account
token, the text and its language). Budgie Echo on iOS uses this path.

**Scribe Cloud is free.** There is no credit, quota or plan attached to it.

In exchange, **the requests may be used to train future BudgieScribe
versions.** Every call is logged (input, output, language, model version).
Before anything reaches a training set it goes through the same PII scanner
this repository publishes ([`scribe/pipeline/pii_scan.py`](scribe/pipeline/pii_scan.py) — names,
e-mails, phone numbers, addresses, identifiers), and it is fully anonymised:
nothing in a training pair can be traced back to an account or a person.
Deleting your Budgie account unlinks your rows immediately; they stay in the
corpus only as anonymous text. If you would rather keep your dictations out
of any corpus, run the model locally — that is what the weights above are for.

## Where it stands, honestly

On synthetic held-out sets the models are near-perfect on what they were
trained for: self-corrections, formatting, numbers (fewer than 1 % wrong
values). On **real dictation graded blind**, the current French build scores
*below* the raw transcript, and the English build is level with it. The
errors are one-word meaning substitutions that read fluently. The numbers are
in [MODELS.md](MODELS.md) and on the model cards; nothing is hidden, because
the point of publishing is to fix exactly this.

## We need help

This is a one-person effort with a clear method and not enough data. Three
ways to contribute, all documented in [CONTRIBUTING.md](CONTRIBUTING.md):

1. **Data.** Real dictation pairs, raw ASR output on one side and the text
   the speaker meant on the other. Any language, any accent, any domain, as
   long as you hold the rights and it contains no personal data. The Echo CLI
   produces the raw side exactly as the app sees it.
2. **Training.** A run costs about a dollar on Hugging Face Jobs or an hour on
   any 16 GB GPU. The recipe is in [TRAINING.md](TRAINING.md); a new language
   is a documented, one-day procedure.
3. **Verification.** Every change is measured the same way, on the same
   held-out sets, before it is merged. [EVALUATION.md](EVALUATION.md) explains
   the instruments and how to read them. Reading fifty outputs is as valuable
   as writing code.

Open an issue to say what you want to do, or a pull request if it is already
done.

## Repository layout

```
FORMAT.md        the exact contract: system string, control line, input/output rules
MODELS.md        every published build: file, hash, results, known limits
CONTRIBUTING.md  data, training, verification — how to help
TRAINING.md      the recipe, end to end, and "adding a language"
EVALUATION.md    the instruments and how to read the numbers
scribe/          corpus/ generateurs/ pipeline/ entrainement/ bancs/ prompts/
scripts/         drivers (PowerShell today; the Python modules run anywhere)
examples/        replay_examples.sh
hf/              model cards and Hugging Face Jobs recipes
```

The repository contains code, prompts and documentation only. Training data
never enters it: the derived French corpus may not be redistributed (see
[NOTICE](NOTICE)), and the same rule is applied to every language.

## License

Code: Apache 2.0 ([LICENSE](LICENSE)). Model weights: Apache 2.0 plus one
term, the model must keep its name, "BudgieScribe" by "Budgie"
([LICENSE-MODEL](LICENSE-MODEL)). Attributions and the position taken on
training-data licensing: [NOTICE](NOTICE).
