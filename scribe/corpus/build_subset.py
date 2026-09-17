# -*- coding: utf-8 -*-
"""POC — construit le sous-ensemble stratifié de ~100 audios français.

Applique la règle d'hygiène du corpus (notes d'entrainement §0.5) :
  mode_name == 'Recording'  et  processingSteps == ('transcription',)  et  raw_text vide
Sans ça, on mélangerait des sorties LLM (magic-wand, restyle) au côté sale ASR.
"""
import sqlite3, json, os, re, glob, wave, collections, random

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
REC = os.path.expanduser("~/.budgie/echo/recordings")
DB  = os.path.expanduser("~/.budgie/echo/history.db")


def flac_duration(path):
    """Durée depuis le bloc STREAMINFO — aucun décodage."""
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


ACC = re.compile(r"[àâäéèêëïîôöùûüçœ]")
FRW = {"le","la","les","des","une","un","du","de","et","est","que","qui","pas","pour",
       "dans","avec","sur","je","ce","mais","donc","alors","tout","plus","bien","fait",
       "faire","chose","quand","meme","aussi","voila","truc"}
WORD = re.compile(r"[a-zA-ZÀ-ÿ']+")


def is_fr(text, words):
    return len(ACC.findall(text.lower())) > len(words) * 0.02 or \
           sum(1 for x in words if x in FRW) > len(words) * 0.06


def bucket(n):
    if n < 50:   return "<50"
    if n < 150:  return "50-149"
    if n < 400:  return "150-399"
    if n < 900:  return "400-899"
    return "900+"


def main():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    rows = list(con.execute("select id, mode_name, status, text, raw_text, json from entries"))

    rejected = collections.Counter()
    cands = []
    for rid, mode, status, text, raw, js in rows:
        if mode != "Recording":            rejected["mode != Recording"] += 1; continue
        if status != "completed":          rejected["non terminé"] += 1; continue
        if (raw or "").strip():            rejected["raw_text non vide (LLM)"] += 1; continue
        # La colonne `json` de history.db stocke l'entree NUE ; les fichiers
        # recordings/<id>/history.json l'enveloppent dans {"entry": ...}.
        # Accepter les deux formes, sinon tout est rejete en silence.
        try:
            data = json.loads(js or "{}")
            entry = data.get("entry") if isinstance(data.get("entry"), dict) else data
        except Exception:
            entry = {}
        steps = tuple(s.get("modeId") for s in (entry.get("processingSteps") or []))
        if steps != ("transcription",):    rejected["étapes != (transcription,)"] += 1; continue
        t = (text or "").strip()
        w = WORD.findall(t.lower())
        if len(w) < 8:                     rejected["trop court"] += 1; continue
        if not is_fr(t, w):                rejected["non français"] += 1; continue
        found = [a for a in sorted(glob.glob(os.path.join(REC, rid, "audio.*")))
                 if a.lower().endswith((".flac", ".wav"))]
        if not found:                      rejected["audio absent"] += 1; continue
        a = found[0]
        dur = flac_duration(a) if a.lower().endswith(".flac") else wav_duration(a)
        if not dur or dur < 2:             rejected["durée illisible ou < 2 s"] += 1; continue
        cands.append(dict(id=rid, audio=a.replace(os.sep, "/"), words=len(w),
                          duration_s=round(dur, 2), bytes=os.path.getsize(a),
                          asr_whisper=t))

    print("entrées en base : %d" % len(rows))
    print("rejets :")
    for k, v in rejected.most_common():
        print("   %-30s %d" % (k, v))
    print("candidats éligibles : %d" % len(cands))

    by = collections.defaultdict(list)
    for r in cands:
        by[bucket(r["words"])].append(r)
    order = ["<50", "50-149", "150-399", "400-899", "900+"]
    print("disponible par tranche : %s" % {k: len(by.get(k, [])) for k in order})

    # Sur-pondération délibérée de la queue : c'est là que Cohere dépasse
    # sa fenêtre de 30 s, et c'est là qu'un normaliseur de référence s'effondrait.
    target = {"<50": 30, "50-149": 30, "150-399": 20, "400-899": 12, "900+": 8}
    rng = random.Random(20260901)
    subset = []
    for b in order:
        pool = sorted(by.get(b, []), key=lambda r: r["id"])
        n = target[b]
        take = pool if len(pool) <= n else rng.sample(pool, n)
        if len(pool) < n:
            print("   ! tranche %s : %d disponibles pour %d demandes - toutes prises"
                  % (b, len(pool), n))
        subset.extend(take)
    subset.sort(key=lambda r: r["duration_s"])

    out = os.path.join(SP, "subset.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in subset:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tot_s = sum(r["duration_s"] for r in subset)
    tot_w = sum(r["words"] for r in subset)
    over = sum(1 for r in subset if r["duration_s"] > 30)
    med = subset[len(subset) // 2]["duration_s"]
    print()
    print("SOUS-ENSEMBLE : %d audios | %.1f min (%.2f h) | %d mots Whisper"
          % (len(subset), tot_s / 60, tot_s / 3600, tot_w))
    print("  duree min/med/max : %.1fs / %.1fs / %.1fs"
          % (subset[0]["duration_s"], med, subset[-1]["duration_s"]))
    print("  au-dela de la fenetre Cohere sure (30 s) : %d/%d (%.0f%%)"
          % (over, len(subset), 100.0 * over / len(subset)))
    print("  ecrit -> %s" % out)


if __name__ == "__main__":
    main()
