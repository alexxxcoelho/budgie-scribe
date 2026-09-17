# -*- coding: utf-8 -*-
"""Decoupe SUMM-RE a l'unite, sur les bornes de parole annotees a la main.

POURQUOI. Decoder la piste entiere ne marche pas : chaque piste est le micro
d'UN participant, et ses 73 % de non-parole ne sont pas du silence mais la
diaphonie des trois autres. Mesure sur les 254 pistes : le ratio mots
Cohere / mots humains passe de 1,56 (densite > 35 %) a 4,34 (densite < 15 %),
et Cohere fabrique de la reunion plausible — participants nommes, sujets
inventes — a partir de la bouillie. Le VAD Silero n'y peut rien : de la
diaphonie EST de la parole, simplement pas celle qu'on veut.

CE QUE CA CHANGE. On dispose de l'horodatage mot a mot de la transcription
HUMAINE. On coupe donc l'audio sur exactement les zones annotees, une unite a
la fois, et Cohere ne voit jamais la bouillie. 84 h de piste deviennent ~23 h
de parole reelle, et chaque sortie s'aligne 1:1 avec une reference humaine.

CE QUE CA COUTE, et il faut le dire. Le cote sale ne porte plus les erreurs de
segmentation que l'ASR commettrait lui-meme aux frontieres de silence : il est
legerement plus propre que ce que la production produirait. C'est un compromis
assume — l'alternative mesuree est 89 % de sorties hallucinees.
"""
import json, os, sys, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
OUT_WAV = os.path.join(SP, "summre_units_wav")
PAD_S = 0.25          # marge de part et d'autre, pour ne pas raboter les attaques
MIN_WORDS = 8


def main():
    import numpy as np, soundfile as sf

    os.makedirs(OUT_WAV, exist_ok=True)
    rows = [json.loads(l) for l in open(os.path.join(SP, "summre_manifest.jsonl"), encoding="utf-8")]
    held = set(json.load(open(os.path.join(SP, "summre_eval_meetings.json"), encoding="utf-8")))

    jobs_path = os.path.join(SP, "summre_unit_jobs.jsonl")
    ref_path = os.path.join(SP, "summre_unit_ref.jsonl")
    jobs = open(jobs_path, "w", encoding="utf-8")
    refs = open(ref_path, "w", encoding="utf-8")

    stats = collections.Counter()
    for r in rows:
        if not r["units"]:
            continue
        audio, rate = sf.read(r["wav"], dtype="float32", always_2d=False)
        assert rate == 16000, "%s : %d Hz" % (r["id"], rate)
        n = len(audio)
        for k, u in enumerate(r["units"]):
            if u["words"] < MIN_WORDS:
                stats["unite trop courte"] += 1
                continue
            a = max(0, int((u["start"] - PAD_S) * 16000))
            b = min(n, int((u["end"] + PAD_S) * 16000))
            if b - a < 16000 // 2:
                stats["span trop bref"] += 1
                continue
            uid = "%s#%03d" % (r["id"], k)
            wav = os.path.join(OUT_WAV, uid.replace("#", "_") + ".wav")
            if not os.path.exists(wav):
                sf.write(wav, np.clip(audio[a:b], -1.0, 1.0), 16000, subtype="PCM_16")
            jobs.write(json.dumps({"id": uid, "wav": wav.replace(os.sep, "/"), "lang": "fr",
                                   "duration_s": round((b - a) / 16000.0, 2)},
                                  ensure_ascii=False) + "\n")
            refs.write(json.dumps({"id": uid, "asr_whisper": u["transcript"], "lang": "fr",
                                   "meeting_id": r["meeting_id"], "track": r["id"],
                                   "speaker_id": r["speaker_id"], "words": u["words"],
                                   "held_out": r["meeting_id"] in held},
                                  ensure_ascii=False) + "\n")
            stats["unites"] += 1
            stats["secondes"] += (b - a) / 16000.0

    jobs.close(); refs.close()
    print("unites ecrites : %d  |  %.2f h de parole reelle" % (stats["unites"], stats["secondes"] / 3600))
    for k, v in stats.most_common():
        if k not in ("unites", "secondes"):
            print("   ecarte %-22s %d" % (k, v))
    print("-> %s" % jobs_path)


if __name__ == "__main__":
    main()
