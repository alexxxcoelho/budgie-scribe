# -*- coding: utf-8 -*-
"""Batterie de pii_scan.py — stdlib pure, `python -m unittest`."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import pii_scan  # noqa: E402


def cats(texte):
    return sorted({c for c, _ in pii_scan.scanner_texte(texte)})


class Emails(unittest.TestCase):
    def test_email_reel_signale(self):
        self.assertEqual(cats("ecris a jean.dupont@orange.fr demain"), ["email"])

    def test_domaine_exemple_admis(self):
        self.assertEqual(cats("support@example.com et contact@gobudgie.com"), [])


class Telephones(unittest.TestCase):
    def test_fr(self):
        self.assertIn("telephone", cats("appelle le 06 12 34 56 78"))

    def test_ch_international(self):
        self.assertIn("telephone", cats("mon numero est +41 79 123 45 67"))

    def test_us(self):
        self.assertIn("telephone", cats("call (415) 555-2671 tonight"))

    def test_montant_et_date_ne_sont_pas_des_telephones(self):
        self.assertEqual(cats("ca fait 23 450 euros le 3 mars 2026 a 14h30"), [])

    def test_annee_et_heure(self):
        self.assertEqual(cats("rendez-vous en 2026 a 10 heures 30"), [])


class Adresses(unittest.TestCase):
    def test_rue_fr(self):
        self.assertIn("adresse", cats("j'habite 12 rue des Lilas"))

    def test_street_en(self):
        self.assertIn("adresse", cats("meet me at 221B Baker Street"))

    def test_code_postal_ville(self):
        self.assertIn("code_postal_ville", cats("envoie ca a 1000 Lausanne"))

    def test_phrase_sans_adresse(self):
        self.assertEqual(cats("on prend la route ensemble puis la rue est barree"), [])


class Iban(unittest.TestCase):
    def test_iban(self):
        self.assertIn("iban", cats("vire sur CH93 0076 2011 6238 5295 7"))


class Noms(unittest.TestCase):
    def test_aucun_nom_dans_le_code(self):
        self.assertEqual(pii_scan.NOMS_BANNIS_DEFAUT, frozenset())

    def test_fichier_projet_charge_si_present(self):
        noms = pii_scan._noms_bannis(None)
        self.assertEqual(noms, pii_scan._lire_noms(pii_scan.FICHIER_NOMS_PROJET)
                         if pii_scan.FICHIER_NOMS_PROJET.exists() else set())

    def test_prenom_seul_tolere(self):
        self.assertEqual(cats("Alex et Marie viennent demain"), [])

    def test_nom_ajoute(self):
        trouves = pii_scan.scanner_texte("Mme Durand arrive", frozenset({"durand"}))
        self.assertEqual([c for c, _ in trouves], ["nom_banni"])


class Fichier(unittest.TestCase):
    def test_jsonl_signale_la_bonne_ligne(self):
        lignes = [
            {"sale": "bonjour euh on se voit demain", "propre": "Bonjour, on se voit demain."},
            {"sale": "mon mail c'est paul point martin arobase free point fr",
             "propre": "Mon mail c'est paul.martin@free.fr"},
            {"sale": "ca fait vingt euros", "propre": "Ca fait 20 euros."},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            for l in lignes:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
            chemin = f.name
        try:
            signalees = pii_scan.scanner_fichier(chemin, frozenset())
        finally:
            os.unlink(chemin)
        self.assertEqual([n for n, _ in signalees], [2])
        self.assertEqual(signalees[0][1][0][0], "email")

    def test_code_de_sortie(self):
        self.assertEqual(pii_scan.main(["--texte", "rien ici"]), 0)
        self.assertEqual(pii_scan.main(["--texte", "ecris a a@b.io"]), 1)


if __name__ == "__main__":
    unittest.main()
