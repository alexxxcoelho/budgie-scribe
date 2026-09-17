# -*- coding: utf-8 -*-
"""VoxPopuli EN : des enonces courts vers des unites de taille dictee.

POURQUOI CE FICHIER. C'est le pendant anglais de summre_units.py, mais la
matiere premiere est differente. SUMM-RE fournit des reunions transcrites a la
main avec horodatage mot a mot ; on y decoupe des unites a partir de bornes
continues. VoxPopuli EN fournit deja des ENONCES pre-decoupes par alignement
force (Bordes et al.) : chaque ligne du parquet est une courte phrase du
Parlement europeen, mediane 21 mots, quand une unite de dictee SUMM-RE pese en
moyenne 74,5 mots. Utiliser un enonce par unite donnerait des dictees deux a
trois fois trop courtes.

CE QUE CA CHANGE. L'audio_id encode la structure qu'on exploite :

    <session>_<horodatage paragraphe>_<index>

Les enonces qui partagent le meme <session>_<horodatage> sont des decoupes
CONSECUTIVES d'un seul discours continu du meme orateur (verifie : aucun
horodatage de paragraphe n'apparait dans les deux splits a la fois). On les
trie par index et on les recolle en unites tant qu'elles restent sous 35 mots
ou 60 s, jusqu'a un plafond dur de 100 mots. Une fin de paragraphe trop courte
(moins de 8 mots, MIN_WORDS comme dans summre_units.py) est ecartee : ni assez
pour juger une dictee, ni assez pour justifier un fichier a part.

ENTRE DEUX ENONCES CONCATENES, un blanc de 0.25 s (des zeros). L'alignement
force qui a produit ces enonces a rogne les pauses respiratoires aux
frontieres : recoller deux enonces bord a bord soudurait deux mots qui
n'avaient jamais ete voisins. Un silence court restitue une respiration de
dictee sans imposer un vrai temps mort acoustique.

RESERVE D'EVALUATION PAR SESSION, JAMAIS PAR PARAGRAPHE NI PAR UNITE
(notes d'entrainement §0.13, meme regle que summre.py sur meeting_id) : un seul discours
peut se decouper en plusieurs paragraphes, et un paragraphe en plusieurs
unites. Separer plus fin remettrait le meme contenu — memes tournures, meme
orateur, parfois le meme sujet — des deux cotes de l'evaluation.
"""
import json, os, sys, io, collections, random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
IN_DIR = os.path.join(SP, "voxpopuli_parquet")
OUT_WAV = os.path.join(SP, "voxpopuli_units_wav")

FILES = collections.OrderedDict([
    ("test", "test-00000-of-00001.parquet"),
    ("validation", "validation-00000-of-00001.parquet"),
])

SEED = 20260905                # tirage de la reserve d'evaluation
HELD_OUT_FRACTION = 0.12
BATCH_SIZE = 64                 # lots pyarrow ; ~2.2 Go d'audio decode au total

PAUSE_S = 0.25                  # silence insere entre enonces concatenes
TARGET_WORDS = 35               # on ferme l'unite des qu'elle atteint ce compte
MAX_SECONDS = 60.0              # ... ou cette duree, au premier des deux
HARD_CAP_WORDS = 100            # plafond dur ; un enonce seul peut le depasser
MIN_WORDS = 8                   # fin de paragraphe trop courte pour etre gardee
MIN_SPAN_S = 0.1                # en dessous : audio degenere, pas un enonce


def to_16k_mono(pcm, rate):
    """Au cas ou un enregistrement ne serait pas deja 16 kHz mono (voir
    summre.py::to_16k_mono) : filtre polyphase anti-repliement, jamais une
    interpolation lineaire qui replierait le spectre."""
    import numpy as np
    from scipy.signal import resample_poly
    if pcm.ndim > 1:
        pcm = pcm.mean(axis=1)
    if rate == 16000:
        return pcm.astype(np.float32)
    from math import gcd
    g = gcd(int(rate), 16000)
    return resample_poly(pcm.astype(np.float64), 16000 // g, int(rate) // g).astype(np.float32)


def load_utterances(stats):
    """Lit les deux parquets par lots (jamais toutes les colonnes audio d'un
    coup) et rend la liste des enonces gardes, audio deja decode et verifie
    16 kHz. ~3 485 enonces valides pour ~2.2 Go de flottants : sous le seuil
    de 3 Go qui imposerait un vrai traitement en deux passes."""
    import numpy as np, soundfile as sf
    import pyarrow.parquet as pq

    cols = ["audio_id", "audio", "raw_text", "normalized_text", "speaker_id", "gender"]
    utts = []
    for split, fname in FILES.items():
        path = os.path.join(IN_DIR, fname)
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=BATCH_SIZE, columns=cols):
            for r in batch.to_pylist():
                stats["lignes"] += 1
                raw = (r["raw_text"] or "").strip()
                if not raw:
                    stats["raw_text vide"] += 1
                    continue
                parts = r["audio_id"].split("_")
                assert len(parts) == 3, "audio_id inattendu : %s" % r["audio_id"]
                session, ts, idx_s = parts
                data, rate = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32",
                                      always_2d=False)
                mono16 = to_16k_mono(np.asarray(data), rate)
                if len(mono16) < int(MIN_SPAN_S * 16000):
                    stats["span trop bref"] += 1
                    continue
                utts.append({
                    "session": session, "paragraph_id": session + "_" + ts,
                    "idx": int(idx_s), "audio_id": r["audio_id"], "split": split,
                    "raw_text": raw, "norm_text": (r["normalized_text"] or "").strip(),
                    "speaker_id": r["speaker_id"], "gender": r["gender"],
                    "words": len(raw.split()), "audio": mono16,
                    "duration_s": len(mono16) / 16000.0,
                })
    return utts


def build_units_for_paragraph(utts):
    """Recolle les enonces (deja tries par index) en unites de taille dictee.
    On ajoute tant que l'unite fait moins de TARGET_WORDS mots ; on ferme des
    qu'elle atteint TARGET_WORDS ou MAX_SECONDS ; HARD_CAP_WORDS est un
    plafond absolu — s'il serait depasse par l'ajout suivant, on ferme d'abord
    ce qu'on a. Un enonce seul plus long que le plafond forme sa propre unite,
    sans etre tronque. Rend (unites, fin_de_paragraphe_ecartee)."""
    units = []
    buf, words, dur = [], 0, 0.0
    for u in utts:
        n = u["words"]
        if buf and words + n > HARD_CAP_WORDS:
            units.append(buf)
            buf, words, dur = [], 0, 0.0
        buf.append(u)
        words += n
        dur += u["duration_s"] + (PAUSE_S if len(buf) > 1 else 0.0)
        if words >= TARGET_WORDS or dur >= MAX_SECONDS:
            units.append(buf)
            buf, words, dur = [], 0, 0.0
    tail_dropped = False
    if buf:
        if sum(x["words"] for x in buf) < MIN_WORDS:
            tail_dropped = True
        else:
            units.append(buf)
    return units, tail_dropped


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0
    i = min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def main():
    import numpy as np, soundfile as sf

    os.makedirs(OUT_WAV, exist_ok=True)
    stats = collections.Counter()

    utts = load_utterances(stats)

    by_para = collections.defaultdict(list)
    for u in utts:
        by_para[u["paragraph_id"]].append(u)

    # Reserve d'evaluation PAR SESSION, avant toute fabrication d'unite.
    all_sessions = sorted({u["session"] for u in utts})
    rng = random.Random(SEED)
    rng.shuffle(all_sessions)
    n_held = max(1, round(len(all_sessions) * HELD_OUT_FRACTION))
    held_sessions = set(all_sessions[:n_held])
    json.dump(sorted(held_sessions),
              open(os.path.join(SP, "vox_eval_sessions.json"), "w", encoding="utf-8"))

    jobs_path = os.path.join(SP, "vox_unit_jobs.jsonl")
    ref_path = os.path.join(SP, "vox_unit_ref.jsonl")
    jobs = open(jobs_path, "w", encoding="utf-8")
    refs = open(ref_path, "w", encoding="utf-8")

    word_counts = []
    n_utt_counts = []
    held_units = 0

    for pid in sorted(by_para):
        group = sorted(by_para[pid], key=lambda x: x["idx"])
        units, tail_dropped = build_units_for_paragraph(group)
        if tail_dropped:
            stats["fin de paragraphe trop courte"] += 1

        for k, unit in enumerate(units):
            uid = "%s#%03d" % (pid, k)
            # ":" vient de l'horodatage (HH:MM:SS) dans l'audio_id source ;
            # illegal dans un nom de fichier Windows, remplace pour le WAV
            # seulement -- "id" dans le JSON garde la forme d'origine.
            fname = uid.replace("#", "_").replace(":", "-")
            wav_path = os.path.join(OUT_WAV, fname + ".wav")

            if len(unit) > 1:
                pad = np.zeros(int(round(PAUSE_S * 16000)), dtype=np.float32)
                pieces = []
                for i, u in enumerate(unit):
                    if i > 0:
                        pieces.append(pad)
                    pieces.append(u["audio"])
                audio_cat = np.concatenate(pieces)
            else:
                audio_cat = unit[0]["audio"]

            duration_s = len(audio_cat) / 16000.0
            if not os.path.exists(wav_path):
                sf.write(wav_path, np.clip(audio_cat, -1.0, 1.0), 16000, subtype="PCM_16")

            words = sum(u["words"] for u in unit)
            session = unit[0]["session"]
            split = unit[0]["split"]
            speaker_ids = sorted({u["speaker_id"] for u in unit})
            genders = sorted({u["gender"] for u in unit})
            held = session in held_sessions

            jobs.write(json.dumps({
                "id": uid, "wav": wav_path.replace(os.sep, "/"),
                "lang": "en", "duration_s": round(duration_s, 2),
            }, ensure_ascii=False) + "\n")
            refs.write(json.dumps({
                "id": uid,
                "ref_text": " ".join(u["raw_text"] for u in unit),
                "norm_text": " ".join(u["norm_text"] for u in unit),
                "lang": "en",
                "session_id": session,
                "paragraph_id": pid,
                "speaker_id": speaker_ids[0] if len(speaker_ids) == 1 else "|".join(speaker_ids),
                "gender": genders[0] if len(genders) == 1 else "|".join(genders),
                "n_utterances": len(unit),
                "words": words,
                "duration_s": round(duration_s, 2),
                "split": split,
                "held_out": held,
            }, ensure_ascii=False) + "\n")

            stats["unites"] += 1
            stats["secondes"] += duration_s
            word_counts.append(words)
            n_utt_counts.append(len(unit))
            if held:
                held_units += 1

    jobs.close()
    refs.close()

    word_counts.sort()
    print("unites ecrites : %d  |  %.2f h de parole"
          % (stats["unites"], stats["secondes"] / 3600))
    print("mots/unite  p10=%d  p50=%d  p90=%d  max=%d"
          % (percentile(word_counts, 0.10), percentile(word_counts, 0.50),
             percentile(word_counts, 0.90), max(word_counts) if word_counts else 0))
    print("enonces/unite (moyenne) : %.2f"
          % (sum(n_utt_counts) / max(1, len(n_utt_counts))))
    print("densite de parole (mots/s, moyenne) : %.2f"
          % (sum(word_counts) / max(1e-9, stats["secondes"])))
    print("unites tenues a l'ecart : %d / %d  |  sessions tenues a l'ecart : %d / %d"
          % (held_units, stats["unites"], len(held_sessions), len(all_sessions)))
    for k in ("raw_text vide", "fin de paragraphe trop courte", "span trop bref"):
        if stats[k]:
            print("   ecarte %-28s %d" % (k, stats[k]))
    print("-> %s" % jobs_path)


if __name__ == "__main__":
    main()
