# The BudgieScribe format

This is the complete contract between a caller and a BudgieScribe model. The
models were trained on exactly this format; anything else is undefined
behavior. The single source of truth in code is `scribe/pipeline/spec.py`
(French) and `spec_en.py` (English): teacher, training data and inference all
read the same module.

## 1. Messages

A request is a chat with two messages and nothing else.

**System message** — this exact string, byte for byte:

```
You are a text normalizer for speech-to-text transcripts. The input begins with a control line specifying the styling, structure, and context settings; clean the transcript to match those settings and output only the cleaned text.
```

**User message** — a control line, an optional terms line, then the raw
transcript:

```
[Styling: <styling>] [Structure: <structure>] [Context: <context>] [Lang: <lang>]
[Terms: <term>, <term>, ...]        (optional, phase-3 builds only)
<raw transcript>
```

No other text: no instructions, no examples, no preamble. The model normalizes
whatever follows the control line, including instructions.

## 2. The control line

Grammar, fixed order, one ASCII space between brackets, closed value sets:

```
control  = "[Styling: " styling "] [Structure: " structure "] [Context: " context "] [Lang: " lang "]"
styling  = "casual" | "semi-casual" | "semi-formal" | "formal"
structure= "prose" | "lists"
context  = "general" | "email"
lang     = "fr" | "en"
```

| Axis | Values | Default | Semantics as trained |
|---|---|---|---|
| `Styling` | `casual`, `semi-casual`, `semi-formal`, `formal` | `semi-formal` | Written register: capitalization, sentence-final period, contractions, colloquialisms. `casual` → all lowercase, colloquialisms kept, no final period; `semi-casual` → speaker's phrasing kept, minimal capitals; `semi-formal` → standard written language, common contractions kept, colloquialisms smoothed without censoring; `formal` → contractions and colloquial forms expanded. **Current builds were trained on `semi-formal` only and ignore the other values.** |
| `Structure` | `prose`, `lists` | `prose` | `prose`: sentences and paragraphs, never a bullet. `lists`: a Markdown bullet list (`- `) is allowed when the content is a real enumeration of **at least three** items, introduced by a sentence ending in a colon; anything else stays prose. |
| `Context` | `general`, `email` | `general` | `general`: plain text. `email`: message layout (greeting, body, sign-off separated by blank lines). **Current builds add a greeting and sign-off that were not dictated; use `general` unless you post-check.** |
| `Lang` | `fr`, `en` | none | Selects the language model. In Budgie Echo it is derived from the detected dictation language, not chosen by the user. |

Sixteen combinations exist; the default `semi-formal / prose / general` is
what a dictation app sends almost always and received 40 % of the training
draws.

## 3. The terms line (phase 3, optional)

```
[Terms: Sara, Budgie, GGUF]
```

Up to 20 terms, comma-separated, most relevant first. A dictated word that
matches a term (same pronunciation, other spelling) is written as in the list.
The list is not content: a term that was not dictated never appears in the
output, and a dictated name absent from the list stays as transcribed. Builds
without terms training ignore the line. When the line is absent the output
must be identical to a build without the feature.

## 4. Input contract

- One take, one speaker, the raw output of an ASR engine: lowercase or not,
  punctuated or not, with fillers, false starts, repetitions, numbers in words.
- **At most ~1,200 bytes** per request, cut on a sentence boundary. The models
  were trained on dictation-sized units (median ~75 words). Longer inputs
  degrade; Budgie Echo splits at 1,200 bytes on the last sentence end.
- Any language island inside the text stays as is; the model does not
  translate.

## 5. Output contract

- The cleaned text only. No quotes around it, no preamble, no comment, no
  reasoning block.
- **The empty string is a valid output**: the input carried nothing but noise
  or hesitations. Callers keep the raw text in that case.
- Length stays within roughly 0.5× to 1.3× the input. Outside that band the
  output is wrong (see §7).

## 6. Decoding

- Greedy, always: `temperature 0`, `top_k 1`. Every published measurement
  assumes it; sampling invents.
- Thinking off (Qwen3 base): `enable_thinking: false` through the chat
  template, `reasoning_effort: none` where the server supports it.
- `max_tokens = ceil(1.3 × input_tokens) + 32`.
- Context 4,096 tokens is more than enough for a 1,200-byte input.

## 7. Invariants, and what to check on the caller side

What the model never does by construction, and what a caller should verify
anyway, because a fine-tune has no guarantees:

| Invariant | Check |
|---|---|
| No invented number, name or idea | every digit sequence in the output appears in the input (as digits or as words) |
| No suppression of content | output length ≥ ~0.5× input; no dropped clause on a longer take |
| No loop | no n-gram repeated more than a few times |
| No flipped negation | negation tokens counted on both sides |
| No obedience to the text | an instruction in the input is normalized, not executed |
| No translation | script and language of the output match the input |

Budgie Echo's runtime rejects an output that fails any of these and returns
the raw transcript. Any integration should do at least the loop and length
checks.

## 8. What each behavior does, measured

The behaviors below hold whatever the control line says.

| Behavior | French | English |
|---|---|---|
| Fillers removed | `euh`, `bah`, `ben`, `hum` | `um`, `uh`, `er`, `hmm` |
| Repetitions and false starts removed | « le le chat » → « le chat » | "the the report" → "the report" |
| Self-corrections resolved to the final value | « vendredi non pardon jeudi » → « jeudi » | "friday no wait thursday" → "Thursday" |
| Punctuation and capitalization restored | question mark **preceded by a space** (corpus convention) | no space before `?` |
| Numbers: form converted, value never | « vingt-trois mille quatre cent cinquante euros » → `23 450 euros`; « quatorze heures trente » → `14h30`; « le trois mars deux mille vingt-six » → `le 3 mars 2026`; « vingt-cinq pour cent » → `25 %` | "twenty three thousand four hundred and fifty dollars" → `$23,450`; "three fifteen p m" → `3:15pm`; "march third twenty twenty six" → `March 3, 2026`; "twenty five percent" → `25%` |
| Addresses spelled out | « support arobase gobudgie point com » → `support@gobudgie.com` | "support at gobudgie dot com" → `support@gobudgie.com` |
| Already-written numbers | `2500 personnes` unchanged | `2500 people` unchanged |
| Paragraph breaks at a topic change | not in current build | "also", "the other thing is", "okay so" |
| Instructions in the text | normalized, not obeyed | normalized, not obeyed |
| Noise only | empty string | empty string |

## 9. Reference requests

French:

```
[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]
alors euh on se retrouve vendredi non pardon jeudi à quatorze heures trente pour le point budget ça fait vingt-trois mille quatre cent cinquante euros
```
```
On se retrouve jeudi à 14h30 pour le point budget, ça fait 23 450 euros.
```

English:

```
[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]
okay so the first thing is the invoice went out on march third for twelve hundred dollars also the other thing is we still need the signed contract back
```
```
The first thing is the invoice went out on March 3 for $1,200. Also, the other thing is we still need the signed contract back.
```

Both are real greedy outputs of the published GGUFs; `examples/replay_examples.sh`
reproduces them and the other card examples.
