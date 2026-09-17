<!-- Data contribution? Keep the first block, delete the second. Code? The other way round. -->

## Data: dictation pairs

- File(s): `contrib/<lang>/<handle>-<YYYY-MM>.jsonl`
- Engine that produced the raw side (`source` field): 
- Number of pairs: 
- Context (what kind of dictation, any particular phenomenon covered): 

I confirm that:

- [ ] the raw side is the **unedited output of an ASR engine**, the clean side is what was meant, under [FORMAT.md §8](../FORMAT.md) — nothing added, nothing summarized
- [ ] the voice is mine, or I have the speaker's consent to publish these transcripts
- [ ] there is **no personal data** (names of third parties, real e-mail addresses, phone numbers, postal addresses, account numbers) — `python scribe/pipeline/pii_scan.py <file>` printed nothing blocking
- [ ] `python scribe/pipeline/verifier_contribution.py <file>` passes locally
- [ ] I release these pairs under **CC0 1.0** so they can be trained on and redistributed

## Code

- What changes and why:
- How it was verified (which bench, which numbers before / after):
- [ ] one variable per round: data, base model and hyperparameters are not changed together
