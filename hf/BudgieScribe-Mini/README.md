---
license: other
license_name: budgiescribe-license
license_link: https://huggingface.co/flowcorp-ch/BudgieScribe-Mini/blob/main/LICENSE-MODEL
base_model: Qwen/Qwen3-1.7B
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
  - text-normalization
  - inverse-text-normalization
  - speech-to-text
  - dictation
---

# BudgieScribe Mini by Budgie

**No build published yet.** BudgieScribe Mini is the mid-size member of the BudgieScribe
family of text normalizers for speech-to-text output: a LoRA fine-tune of
`Qwen/Qwen3-1.7B` (1.7 B) trained with the `mini` profile of
[github.com/alexxxcoelho/budgie-scribe](https://github.com/alexxxcoelho/budgie-scribe)
(`scribe/entrainement/train.py --profil mini`), same format, same
evaluation sets and same guard rails as
[BudgieScribe-Nano](https://huggingface.co/flowcorp-ch/BudgieScribe-Nano).

Files will appear here as `BudgieScribe-Mini-fr-Q4_K_M.gguf` and `BudgieScribe-Mini-en-Q4_K_M.gguf`
once a build passes the held-out sets and the blind A/B against Nano
(EVALUATION.md). Until then, use Nano.
