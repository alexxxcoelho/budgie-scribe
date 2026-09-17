# -*- coding: utf-8 -*-
"""Manifeste du corpus Budgie COMPLET (FR + EN), et conversion en WAV 16 kHz.

Meme regle d'hygiene que le sous-ensemble du POC (notes d'entrainement §section 0.5) :
  mode_name == 'Recording'  et  processingSteps == ('transcription',)  et  raw_text vide
Sans elle, on melange des sorties LLM au cote sale.

D4 retient FR *et* EN : Alex dicte du francais truffe de termes techniques
anglais, et un modele FR pur traite ces ilots comme du bruit.
"""
import sqlite3, json, os, re, glob, wave, collections

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
REC = os.path.expanduser("~/.budgie/echo/recordings")
DB = os.path.expanduser("~/.budgie/echo/history.db")
WAV = os.path.join(SP, "wav_full")

ACC = re.compile(r"[àâäéèêëïîôöùûüçœ]")
FRW = {"le","la","les","des","une","un","du","de","et","est","que","qui","pas","pour",
       "dans","avec","sur","je","ce","mais","donc","alors","tout","plus","bien","fait",
       "faire","chose","quand","meme","aussi","voila","truc"}
ENW = {"the","a","an","of","and","is","that","to","in","it","you","we","they","for",
       "with","have","has","was","were","will","would","this","these","there","but",
       "not","are","on","at","be","been","do","does","did","from","about","what","when"}
WORD = re.compile(r"[a-zA-ZÀ-ÿ']+")


def flac_duration(path):
    with open(path, "rb") as f:
        if f.read(4) != b"fLaC":
            return None
        hdr = f.read(4)
        if len(hdr) < 4 or (hdr[0] & 0x7F) != 0:
            return None
        info = f.read(34)
        if len(info) < 18:
            return None
        bits = int.from_bytes(info[10:18], "big")
        rate = (bits >> 44) & 0xFFFFF
        total = bits & ((1 << 36) - 1)
        return total / rate if rate else None


def wav_duration(path):
    try:
        with wave.open(path) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return None


def language(text, words):
    fr = sum(1 for w in words if w in FRW)
    en = sum(1 for w in words if w in ENW)
    accents = len(ACC.findall(text.lower()))
    if accents > len(words) * 0.02 or fr > en:
        return "fr"
    if en > fr:
        return "en"
    return "amb"


def main():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    rows = list(con.execute("select id, mode_name, status, text, raw_text, json from entries"))
    rejected = collections.Counter()
    keep = []
    for rid, mode, status, text, raw, js in rows:
        if mode != "Recording":            rejected["mode != Recording"] += 1; continue
        if status != "completed":          rejected["non termine"] += 1; continue
        if (raw or "").strip():            rejected["raw_text non vide (LLM)"] += 1; continue
        try:
            data = json.loads(js or "{}")
            entry = data.get("entry") if isinstance(data.get("entry"), dict) else data
        except Exception:
            entry = {}
        if tuple(s.get("modeId") for s in (entry.get("processingSteps") or [])) != ("transcription",):
            rejected["etapes != (transcription,)"] += 1; continue
        t = (text or "").strip()
        w = WORD.findall(t.lower())
        if len(w) < 8:                     rejected["trop court"] += 1; continue
        found = [a for a in sorted(glob.glob(os.path.join(REC, rid, "audio.*")))
                 if a.lower().endswith((".flac", ".wav"))]
        if not found:                      rejected["audio absent"] += 1; continue
        a = found[0]
        dur = flac_duration(a) if a.lower().endswith(".flac") else wav_duration(a)
        if not dur or dur < 2:             rejected["duree illisible ou < 2 s"] += 1; continue
        keep.append(dict(id=rid, audio=a.replace(os.sep, "/"), words=len(w),
                         duration_s=round(dur, 2), lang=language(t, w), asr_whisper=t))

    print("entrees en base : %d" % len(rows))
    for k, v in rejected.most_common():
        print("   rejet %-28s %d" % (k, v))
    by = collections.Counter(r["lang"] for r in keep)
    print("RETENU : %d enregistrements  %s" % (len(keep), dict(by)))
    for lang in ("fr", "en", "amb"):
        sub = [r for r in keep if r["lang"] == lang]
        if sub:
            print("   %-4s %3d fichiers | %6.2f h | %7d mots"
                  % (lang, len(sub), sum(r["duration_s"] for r in sub) / 3600,
                     sum(r["words"] for r in sub)))
    print("TOTAL %.2f h  |  au-dela de 30 s : %d (%.0f%%)"
          % (sum(r["duration_s"] for r in keep) / 3600,
             sum(1 for r in keep if r["duration_s"] > 30),
             100.0 * sum(1 for r in keep if r["duration_s"] > 30) / len(keep)))

    os.makedirs(WAV, exist_ok=True)
    import soundfile as sf
    converted = 0
    for r in keep:
        dst = os.path.join(WAV, r["id"] + ".wav")
        if not os.path.exists(dst):
            data, rate = sf.read(r["audio"], dtype="int16", always_2d=True)
            if data.shape[1] > 1:
                data = data.mean(axis=1, dtype="int16").reshape(-1, 1)
            assert rate == 16000, "%s : %d Hz inattendu" % (r["id"], rate)
            sf.write(dst, data, rate, subtype="PCM_16")
            converted += 1
        r["wav"] = dst.replace(os.sep, "/")
    print("WAV convertis : %d (deja presents : %d) | %.1f Go"
          % (converted, len(keep) - converted,
             sum(os.path.getsize(r["wav"]) for r in keep) / 1e9))

    out = os.path.join(SP, "corpus_full.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in sorted(keep, key=lambda x: x["duration_s"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("ecrit -> %s" % out)


if __name__ == "__main__":
    main()
