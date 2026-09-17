# -*- coding: utf-8 -*-
"""Batterie de archiver.py — le routage des fichiers du travail, et une archive
complete sur un repertoire fabrique. Stdlib pure, `python -m unittest`."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import archiver  # noqa: E402


class Routage(unittest.TestCase):
    """Chaque nom du vrai repertoire de travail va au bon dossier ; ce qui n'a
    rien a faire dans l'archive (audio, poids, doc) renvoie None."""

    def d(self, nom, lang="en", mix="pairs_mix_en7.jsonl"):
        return archiver.destination(nom, lang, mix)

    def test_le_mix_du_build_prend_le_nom_canonique(self):
        self.assertEqual(self.d("pairs_mix_en7.jsonl"), "mix/pairs_mix_en.jsonl")
        self.assertEqual(self.d("pairs_mix9.jsonl", "fr", "pairs_mix9.jsonl"), "mix/pairs_mix.jsonl")

    def test_les_autres_melanges_sont_de_l_historique(self):
        self.assertEqual(self.d("pairs_mix_en.jsonl"), "en/history/pairs_mix_en.jsonl")
        self.assertEqual(self.d("pairs_mix_en6.jsonl"), "en/history/pairs_mix_en6.jsonl")
        self.assertEqual(self.d("pairs_itn_en.v5.jsonl"), "en/history/pairs_itn_en.v5.jsonl")
        self.assertEqual(self.d("pairs_vox_en6.jsonl"), "en/history/pairs_vox_en6.jsonl")

    def test_composantes(self):
        self.assertEqual(self.d("pairs_itn_en.jsonl"), "en/pairs/pairs_itn_en.jsonl")
        self.assertEqual(self.d("pairs_cor_itn_en.jsonl"), "en/pairs/pairs_cor_itn_en.jsonl")
        self.assertEqual(self.d("pairs_summre.jsonl", "fr", "pairs_mix9.jsonl"), "fr/pairs/pairs_summre.jsonl")

    def test_professeur(self):
        self.assertEqual(self.d("pairs_vox_en.jsonl.progress"), "en/teacher/pairs_vox_en.jsonl.progress")
        self.assertEqual(self.d("pairs_vox_en6.jsonl.adjudged"), "en/teacher/pairs_vox_en6.jsonl.adjudged")

    def test_corpus(self):
        for nom in ("units_en.jsonl", "cohere_units_en.jsonl", "qc_units_en.jsonl", "eval_set_en.jsonl",
                    "vox_unit_ref.jsonl", "vox_unit_jobs.jsonl", "vox_eval_sessions.json"):
            self.assertEqual(self.d(nom), "en/corpus/" + nom, nom)
        for nom in ("summre_manifest.jsonl", "summre_eval_meetings.json"):
            self.assertEqual(self.d(nom, "fr", "x"), "fr/corpus/" + nom, nom)

    def test_journaux_avant_le_corpus(self):
        # `qc_units_en.log` ressemble a un fichier de corpus ; c'est un journal.
        self.assertEqual(self.d("qc_units_en.log"), "en/logs/qc_units_en.log")
        self.assertEqual(self.d("train_en_v7.log"), "en/logs/train_en_v7.log")

    def test_scripts_et_bancs(self):
        self.assertEqual(self.d("eval_en_v6.sh"), "en/scripts/eval_en_v6.sh")
        self.assertEqual(self.d("transcrire_cohere.cmd"), "en/scripts/transcrire_cohere.cmd")
        self.assertEqual(self.d("dl_voxpopuli.py"), "en/scripts/dl_voxpopuli.py")
        self.assertEqual(self.d("evalsynth_scribe-en-v7_pairs_itn_en.json"),
                         "en/bench/evalsynth_scribe-en-v7_pairs_itn_en.json")
        self.assertEqual(self.d("ab_blind_reels_card.txt"), "en/bench/ab_blind_reels_card.txt")

    def test_ecartes(self):
        for nom in ("scribe-en-v7.zip", "s1-mini-README.md", "section_022.md", "unite.wav"):
            self.assertIsNone(self.d(nom), nom)


class ArchiveComplete(unittest.TestCase):
    """Un travail minuscule : le mix, une composante, un build, un .log, un
    zip a ecarter. L'archive doit avoir le manifeste, le SHA du mix, le
    run.json du build sans sa courbe, et le rapport pii."""

    def test_bout_en_bout(self):
        with tempfile.TemporaryDirectory() as tmp:
            travail, sortie = os.path.join(tmp, "poc-en"), os.path.join(tmp, "archive")
            os.makedirs(os.path.join(travail, "scribe-en-v1"))
            ligne = json.dumps({"id": "itn-00001", "file": "itn-telephone", "source": "itn", "lang": "en",
                                "held_out": False, "dirty": "call five five five", "clean": "Call 555-010-9999."})
            for nom in ("pairs_mix_en1.jsonl", "pairs_itn_en.jsonl"):
                with open(os.path.join(travail, nom), "w", encoding="utf-8") as f:
                    f.write(ligne + "\n" + ligne + "\n")
            with open(os.path.join(travail, "scribe-en-v1", "run.json"), "w") as f:
                json.dump({"steps": 3, "lr": 1e-5, "log": [{"step": 1, "loss": 0.5}]}, f)
            open(os.path.join(travail, "train_en_v1.log"), "w").close()
            open(os.path.join(travail, "scribe-en-v1.zip"), "wb").close()

            res = subprocess.run([sys.executable, archiver.__file__, "--lang", "en", "--build", "scribe-en-v1",
                                  "--mix", "pairs_mix_en1.jsonl", "--travail", travail, sortie],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("scribe-en-v1.zip", res.stdout)

            with open(os.path.join(sortie, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
            self.assertEqual(m["langues"]["en"]["mix"], "mix/pairs_mix_en.jsonl")
            self.assertEqual(m["langues"]["en"]["train"], {"steps": 3, "lr": 1e-5})
            self.assertEqual(m["fichiers"]["mix/pairs_mix_en.jsonl"]["lines"], 2)
            self.assertEqual(len(m["fichiers"]["mix/pairs_mix_en.jsonl"]["sha256"]), 64)
            self.assertIn("en/pairs/pairs_itn_en.jsonl", m["fichiers"])
            self.assertIn("en/builds/scribe-en-v1/run.json", m["fichiers"])
            self.assertIn("en/logs/train_en_v1.log", m["fichiers"])
            self.assertTrue(os.path.isfile(os.path.join(sortie, "en", "pii_pairs_mix_en1.txt")))
            # le telephone synthetique est compte dans sa famille, pas signale a lire
            self.assertEqual(m["langues"]["en"]["pii_scan"]["par_genre"], {"telephone": 2})
            self.assertNotIn("A LIRE", res.stdout)


if __name__ == "__main__":
    unittest.main()
