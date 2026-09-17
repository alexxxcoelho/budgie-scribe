# -*- coding: utf-8 -*-
"""Scan de donnees personnelles sur un jeu de paires ou d'unites (JSONL).

Regle du projet, posee le 2026-09-17 : ce qui part en public ne contient
AUCUN nom de famille, AUCUNE adresse postale, AUCUN numero de telephone,
AUCUNE adresse e-mail reelle, AUCUN IBAN. Les prenoms seuls sont toleres.

Ce module ne juge pas, il designe : chaque ligne signalee doit etre LUE. Il
tourne (1) avant `melanger.py`, (2) en CI sur chaque contribution de donnees,
(3) sur les sorties d'une sonde de regurgitation d'un modele.

Usage :
    python pii_scan.py pairs.jsonl [autre.jsonl ...] [--noms noms_bannis.txt]
    python pii_scan.py --texte "..."           # une chaine, pour la sonde

Code de sortie : 0 si rien, 1 si au moins une ligne signalee.

Stdlib pure : il tourne partout, y compris dans une action CI sans venv.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# E-mail : n'importe quel local@domaine.tld. Les domaines d'exemple reserves
# (RFC 2606) et ceux que les generateurs utilisent volontairement sont admis.
DOMAINES_ADMIS = {"example.com", "example.org", "example.net", "gobudgie.com"}
RE_EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+\.)+[a-z]{2,}\b", re.I)

# Telephones : FR (0X XX XX XX XX, +33), CH (+41, 07X XXX XX XX), UK (07XXX,
# +44), US (XXX-XXX-XXXX, (XXX) XXX-XXXX, +1). Espaces, points, tirets admis.
RE_TEL = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\d)"
)
# Au moins 9 chiffres au total : ecarte les montants, dates, heures.
MIN_CHIFFRES_TEL = 9

RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b")

# Adresse postale. Francais : numero puis type de voie (« 12 rue des Lilas »).
# Anglais / allemand : numero (eventuellement suivi d'une lettre), jusqu'a deux
# mots, puis le suffixe de voie (« 221B Baker Street », « 5 Long Acre Road »).
RE_ADRESSE = re.compile(
    r"\b\d{1,4}\s?(?:bis|ter)?,?\s+(?:rue|avenue|av\.|boulevard|bd|chemin|"
    r"impasse|all[ée]e|place|route|quai|cours|square)\b"
    r"|\b\d{1,4}[A-Za-z]?\s+(?:[A-Za-z'-]+\s+){0,2}(?:street|st\.|road|rd\.|"
    r"avenue|ave\.|lane|drive|dr\.|court|way|strasse|straße|gasse|platz)\b",
    re.I,
)
# Code postal suivi d'une ville capitalisee : « 1000 Lausanne », « 75011 Paris ».
RE_CP_VILLE = re.compile(r"\b(?:\d{4,5}|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\s+[A-ZÉ][a-zé-]{2,}\b")

# Noms de famille bannis. Le code n'en porte aucun : la liste du projet vit
# dans `noms_bannis.txt` a cote de ce module (prive, jamais publie), et un
# contributeur ajoute la sienne par --noms. Un nom par ligne, compares en
# minuscules, mots entiers.
NOMS_BANNIS_DEFAUT = frozenset()
FICHIER_NOMS_PROJET = Path(__file__).with_name("noms_bannis.txt")


def _lire_noms(chemin):
    noms = set()
    for ligne in Path(chemin).read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip().lower()
        if ligne and not ligne.startswith("#"):
            noms.add(ligne)
    return noms


def _noms_bannis(chemin):
    noms = set(NOMS_BANNIS_DEFAUT)
    if FICHIER_NOMS_PROJET.exists():
        noms |= _lire_noms(FICHIER_NOMS_PROJET)
    if chemin:
        noms |= _lire_noms(chemin)
    return noms


def scanner_texte(texte, noms_bannis=frozenset(NOMS_BANNIS_DEFAUT)):
    """Renvoie la liste des (categorie, extrait) trouves dans `texte`."""
    trouves = []
    for m in RE_EMAIL.finditer(texte):
        domaine = m.group(0).split("@", 1)[1].lower()
        if domaine not in DOMAINES_ADMIS:
            trouves.append(("email", m.group(0)))
    for m in RE_TEL.finditer(texte):
        if sum(c.isdigit() for c in m.group(0)) >= MIN_CHIFFRES_TEL:
            trouves.append(("telephone", m.group(0).strip()))
    for m in RE_IBAN.finditer(texte):
        trouves.append(("iban", m.group(0)))
    for m in RE_ADRESSE.finditer(texte):
        trouves.append(("adresse", m.group(0)))
    for m in RE_CP_VILLE.finditer(texte):
        trouves.append(("code_postal_ville", m.group(0)))
    mots = re.findall(r"[a-zA-ZÀ-ÿ'-]+", texte.lower())
    for mot in mots:
        if mot in noms_bannis:
            trouves.append(("nom_banni", mot))
    return trouves


# Champs textuels d'une ligne JSONL du projet : paires (sale/propre), unites,
# generations. Tout champ chaine est scanne : un nom dans un champ inattendu
# est encore un nom.
def _textes(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _textes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textes(v)


def scanner_fichier(chemin, noms_bannis):
    signalees = []
    with open(chemin, encoding="utf-8") as f:
        for numero, ligne in enumerate(f, 1):
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                obj = json.loads(ligne)
            except json.JSONDecodeError:
                obj = ligne
            trouves = []
            for texte in _textes(obj):
                trouves.extend(scanner_texte(texte, noms_bannis))
            if trouves:
                signalees.append((numero, trouves))
    return signalees


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("fichiers", nargs="*", help="JSONL a scanner")
    ap.add_argument("--noms", help="fichier de noms de famille bannis, un par ligne")
    ap.add_argument("--texte", help="scanner une chaine au lieu de fichiers")
    args = ap.parse_args(argv)
    noms = _noms_bannis(args.noms)

    if args.texte is not None:
        trouves = scanner_texte(args.texte, noms)
        for cat, extrait in trouves:
            print("%-18s %s" % (cat, extrait))
        return 1 if trouves else 0

    if not args.fichiers:
        ap.error("donnez des fichiers JSONL ou --texte")
    total = 0
    for chemin in args.fichiers:
        signalees = scanner_fichier(chemin, noms)
        total += len(signalees)
        for numero, trouves in signalees:
            for cat, extrait in trouves:
                print("%s:%d  %-18s %s" % (chemin, numero, cat, extrait))
    print("%d ligne(s) signalee(s)" % total, file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
