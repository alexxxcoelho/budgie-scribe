# -*- coding: utf-8 -*-
"""SUMM-RE : telechargement, reechantillonnage et decoupe en unites de dictee.

Pourquoi ce corpus : reunions francaises spontanees, UN MICRO PAR PARTICIPANT,
donc chaque piste est structurellement un monologue a trous — ce qu'un corpus
public francais offre de plus proche de la dictee. dev et test sont transcrits
et alignes A LA MAIN, mot a mot.

Trois decisions materialisees ici :

1. Le decoupage evaluation/entrainement se fait sur `meeting_id`, JAMAIS sur la
   piste (notes d'entrainement §0.13). Trois a quatre pistes partagent la meme
   conversation ; separer par piste mettrait le meme contenu des deux cotes.

2. Le reechantillonnage 48 -> 16 kHz utilise un filtre polyphase anti-repliement
   (`resample_poly`), pas une interpolation lineaire. C'est la chaine de capture
   live d'Echo qui sert de reference, et elle emploie un sinc anti-repliement.

3. On ne garde que dev et test. Le split `train` de SUMM-RE est transcrit
   AUTOMATIQUEMENT par Whisper : c'est le cote sale d'un autre ASR, pas une
   verite. Son audio reste utilisable, sa transcription non.
"""
import json, os, sys, io, time, glob, collections, random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
OUT_WAV = os.path.join(SP, "summre_wav")
CACHE = os.path.join(SP, "summre_parquet")
SEED = 20260901
REPO = "linagora/SUMM-RE"
BASE = "https://huggingface.co/datasets/%s/resolve/main/" % REPO


def shard_list(split):
    import urllib.request
    meta = json.load(urllib.request.urlopen(
        "https://huggingface.co/api/datasets/%s" % REPO, timeout=40))
    return sorted(s["rfilename"] for s in meta["siblings"]
                  if s["rfilename"].startswith("data/%s/" % split))


def fetch(rfilename, dst):
    import urllib.request
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return os.path.getsize(dst)
    tmp = dst + ".part"
    urllib.request.urlretrieve(BASE + rfilename, tmp)
    os.replace(tmp, dst)
    return os.path.getsize(dst)


def to_16k_mono(pcm, rate):
    """48 kHz -> 16 kHz par filtre polyphase. `resample_poly` applique un
    passe-bas avant decimation ; une interpolation lineaire ne le ferait pas et
    replierait le spectre au-dessus de 8 kHz dans la bande utile."""
    import numpy as np
    from scipy.signal import resample_poly
    if pcm.ndim > 1:
        pcm = pcm.mean(axis=1)
    if rate == 16000:
        return pcm.astype(np.float32)
    from math import gcd
    g = gcd(int(rate), 16000)
    return resample_poly(pcm.astype(np.float64), 16000 // g, int(rate) // g).astype(np.float32)


def units_from_segments(segments, target_words=110, max_gap=3.0):
    """Regroupe les segments en unites de taille dictee, en coupant sur les
    silences longs et aux frontieres de mots que le corpus fournit."""
    units, buf, words = [], [], 0
    prev_end = None
    for seg in segments:
        n = len(seg.get("words") or [])
        if not n:
            continue
        gap = (seg["start"] - prev_end) if prev_end is not None else 0.0
        if buf and (words + n > target_words or gap > max_gap):
            units.append(buf); buf, words = [], 0
        buf.append(seg); words += n
        prev_end = seg["end"]
    if buf:
        units.append(buf)
    return [u for u in units if sum(len(s.get("words") or []) for s in u) >= 8]


def main():
    splits = sys.argv[1].split(",") if len(sys.argv) > 1 else ["dev", "test"]
    max_shards = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    os.makedirs(OUT_WAV, exist_ok=True); os.makedirs(CACHE, exist_ok=True)

    import numpy as np, soundfile as sf
    import pyarrow.parquet as pq

    manifest_path = os.path.join(SP, "summre_manifest.jsonl")
    manifest = open(manifest_path, "w", encoding="utf-8")
    stats = collections.Counter()
    meetings = collections.defaultdict(set)
    t0 = time.time()

    for split in splits:
        shards = shard_list(split)
        if max_shards:
            shards = shards[:max_shards]
        print("%s : %d shards" % (split, len(shards)), flush=True)
        for si, rf in enumerate(shards):
            dst = os.path.join(CACHE, os.path.basename(rf))
            size = fetch(rf, dst)
            table = pq.read_table(dst)
            rows = table.to_pylist()
            for r in rows:
                audio = r["audio"]
                data, rate = sf.read(io.BytesIO(audio["bytes"]), dtype="float32", always_2d=False)
                mono16 = to_16k_mono(np.asarray(data), rate)
                wav = os.path.join(OUT_WAV, "%s.wav" % r["audio_id"])
                if not os.path.exists(wav):
                    sf.write(wav, np.clip(mono16, -1.0, 1.0), 16000, subtype="PCM_16")
                segments = r.get("segments") or []
                speech = sum(s["end"] - s["start"] for s in segments)
                nwords = sum(len(s.get("words") or []) for s in segments)
                units = units_from_segments(segments)
                meetings[split].add(r["meeting_id"])
                manifest.write(json.dumps({
                    "id": r["audio_id"], "meeting_id": r["meeting_id"],
                    "speaker_id": r["speaker_id"], "split": split,
                    "wav": wav.replace(os.sep, "/"), "lang": "fr",
                    "duration_s": round(len(mono16) / 16000.0, 2),
                    "speech_s": round(speech, 2), "words": nwords,
                    "n_units": len(units),
                    "units": [{"start": u[0]["start"], "end": u[-1]["end"],
                               "words": sum(len(s.get("words") or []) for s in u),
                               "transcript": " ".join(s["transcript"] for s in u)}
                              for u in units],
                    # Segments bruts conserves : re-decouper autrement doit
                    # couter zero, pas un nouveau telechargement de 26 Go.
                    "segments": [{"start": s["start"], "end": s["end"],
                                  "transcript": s["transcript"],
                                  "n_words": len(s.get("words") or [])}
                                 for s in segments],
                }, ensure_ascii=False) + "\n")
                manifest.flush()
                stats["tracks"] += 1
                stats["seconds"] += len(mono16) / 16000.0
                stats["speech"] += speech
                stats["words"] += nwords
                stats["units"] += len(units)
            os.remove(dst)   # 26 Go de parquet ne servent qu'une fois
            print("   [%s %d/%d] %.0f Mo | %d pistes | %.1f h | %d unites | %.0f s ecoulees"
                  % (split, si + 1, len(shards), size / 1e6, stats["tracks"],
                     stats["seconds"] / 3600, stats["units"], time.time() - t0), flush=True)

    manifest.close()
    print("\nTOTAL %d pistes | %.2f h audio | %.2f h parole (%.0f%%) | %d mots | %d unites"
          % (stats["tracks"], stats["seconds"] / 3600, stats["speech"] / 3600,
             100.0 * stats["speech"] / max(1e-9, stats["seconds"]), stats["words"], stats["units"]))
    for split in splits:
        print("   %s : %d reunions" % (split, len(meetings[split])))

    # Reserve d'evaluation, PAR REUNION, avant toute generation.
    all_meetings = sorted({m for s in meetings.values() for m in s})
    rng = random.Random(SEED)
    rng.shuffle(all_meetings)
    held = set(all_meetings[:max(1, round(len(all_meetings) * 0.10))])
    json.dump(sorted(held), open(os.path.join(SP, "summre_eval_meetings.json"), "w"))
    print("evaluation tenue a l'ecart : %d reunions sur %d (par meeting_id, jamais par piste)"
          % (len(held), len(all_meetings)))


if __name__ == "__main__":
    main()
