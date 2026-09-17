# -*- coding: utf-8 -*-
"""Porte d'entree des contributions de donnees : contrib/<lang>/<nom>.jsonl.

    python scribe/pipeline/verifier_contribution.py contrib/fr/alex-2026-09.jsonl [...]
    python scribe/pipeline/verifier_contribution.py --tout        # tout contrib/

C'est ce que la CI execute sur chaque pull request qui touche contrib/. Rien
ici ne juge la QUALITE d'une paire — ca, c'est la lecture par un mainteneur.
Ce script refuse ce qui est mecaniquement faux, pour que la lecture ne porte
que sur le sens :

  CHEMIN       contrib/<fr|en>/<handle>-<AAAA-MM>.jsonl, minuscules et tirets.
  LIGNE        JSON valide, cles id/file/lang/control/dirty/clean/source,
               `held_out` absent ou false (le decoupage train/eval se fait au
               melange, pas dans une contribution).
  COHERENCE    lang == dossier == [Lang: ..] de la ligne de controle ;
               file == nom du fichier sans extension (c'est la cle de trace
               dans les melanges) ; id unique dans TOUT contrib/.
  CONTROLE     la ligne de controle est exactement celle de spec.control_line
               pour des valeurs admises (STYLINGS, STRUCTURES, CONTEXTS).
  TAILLE       5 a 150 mots cote sale (moins de 20 : avertissement, pas refus).
  DOUBLON      un cote sale deja present ailleurs dans contrib/ (a l'espace
               et a la casse pres) est refuse : il n'apprend rien deux fois.
  PII          pii_scan.py : e-mail hors domaine reserve, IBAN, nom banni,
               code postal + ville REFUSENT ; telephones et adresses sont
               listes pour relecture.
  STRUCTURE    valider_paires.py sur le fichier : majuscule initiale,
               ponctuation finale, paires identiques, accents.

Sortie : un rapport lisible, et le meme en Markdown dans $GITHUB_STEP_SUMMARY
quand la CI le fournit. Code de retour 1 si un refus, 0 sinon. Stdlib pure.
"""
import collections
import json
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path.insert(0, ICI)
import spec  # noqa: E402  STYLINGS / STRUCTURES / CONTEXTS / control_line

LANGUES = ("fr", "en")
RE_NOM = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d{4}-\d{2}\.jsonl$")
CLES = ("id", "file", "lang", "control", "dirty", "clean", "source")
RE_CONTROL = re.compile(
    r"^\[Styling: (?P<styling>[a-z-]+)\] \[Structure: (?P<structure>[a-z]+)\] "
    r"\[Context: (?P<context>[a-z]+)\] \[Lang: (?P<lang>[a-z]{2})\]$")
BLOQUANT_PII = re.compile(r"  (email|iban|nom_banni|code_postal_ville) ")


def cle_doublon(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def tous_les_fichiers():
    out = []
    for lang in LANGUES:
        d = os.path.join(RACINE, "contrib", lang)
        if os.path.isdir(d):
            out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".jsonl")]
    return out


def verifier(path, ids_vus, sales_vus, rapport):
    """Ajoute au rapport ; retourne le nombre de refus."""
    refus, avert = [], []
    rel = os.path.relpath(path, RACINE)
    parts = rel.split(os.sep)
    if len(parts) != 3 or parts[0] != "contrib" or parts[1] not in LANGUES:
        refus.append("chemin attendu contrib/<fr|en>/<nom>.jsonl, recu %s" % rel)
        rapport.append((rel, refus, avert, 0)); return len(refus)
    lang_dossier, nom = parts[1], parts[2]
    if not RE_NOM.match(nom):
        refus.append("nom de fichier attendu <handle>-<AAAA-MM>.jsonl (minuscules, tirets), recu %s" % nom)
    stem = nom[:-len(".jsonl")]

    rows = []
    for n, ligne in enumerate(open(path, encoding="utf-8"), 1):
        if not ligne.strip():
            continue
        try:
            r = json.loads(ligne)
        except ValueError as e:
            refus.append("ligne %d : JSON invalide (%s)" % (n, e)); continue
        manque = [k for k in CLES if k not in r]
        if manque:
            refus.append("ligne %d : cles manquantes %s" % (n, ", ".join(manque))); continue
        if r.get("held_out"):
            refus.append("ligne %d (%s) : held_out doit etre absent ou false" % (n, r["id"]))
        if r["lang"] != lang_dossier:
            refus.append("ligne %d (%s) : lang %r mais dossier %s" % (n, r["id"], r["lang"], lang_dossier))
        if r["file"] != stem:
            refus.append("ligne %d (%s) : file doit valoir %r (le nom du fichier), recu %r" % (n, r["id"], stem, r["file"]))
        m = RE_CONTROL.match(r["control"])
        if not m:
            refus.append("ligne %d (%s) : ligne de controle hors format : %r" % (n, r["id"], r["control"][:80]))
        else:
            g = m.groupdict()
            attendu = spec.control_line(g["styling"], g["structure"], g["context"], g["lang"])
            if (g["styling"] not in spec.STYLINGS or g["structure"] not in spec.STRUCTURES
                    or g["context"] not in spec.CONTEXTS or attendu != r["control"]):
                refus.append("ligne %d (%s) : valeur de controle inconnue dans %r" % (n, r["id"], r["control"]))
            if g["lang"] != lang_dossier:
                refus.append("ligne %d (%s) : [Lang: %s] mais dossier %s" % (n, r["id"], g["lang"], lang_dossier))
        if not r["dirty"].strip() or not r["clean"].strip():
            refus.append("ligne %d (%s) : cote sale ou propre vide" % (n, r["id"]))
        nmots = len(r["dirty"].split())
        if nmots > 150:
            refus.append("ligne %d (%s) : %d mots cote sale, maximum 150 — coupez sur une fin de phrase" % (n, r["id"], nmots))
        elif nmots < 5:
            refus.append("ligne %d (%s) : %d mots cote sale, minimum 5" % (n, r["id"], nmots))
        elif nmots < 20:
            avert.append("ligne %d (%s) : %d mots, court (20 a 150 recommandes)" % (n, r["id"], nmots))
        if r["id"] in ids_vus:
            refus.append("ligne %d : id %r deja utilise dans %s" % (n, r["id"], ids_vus[r["id"]]))
        ids_vus.setdefault(r["id"], rel)
        k = cle_doublon(r["dirty"])
        if k in sales_vus and sales_vus[k] != (rel, r["id"]):
            refus.append("ligne %d (%s) : cote sale identique a %s/%s" % (n, r["id"], *sales_vus[k]))
        sales_vus.setdefault(k, (rel, r["id"]))
        rows.append(r)

    # PII : le scan designe, ici on tranche. On ne lui donne que les deux
    # textes — un id comme « 2026-09-001 » passerait pour un telephone.
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        for r in rows:
            tmp.write(json.dumps({"dirty": r["dirty"], "clean": r["clean"]},
                                 ensure_ascii=False) + "\n")
    scan = subprocess.run([sys.executable, os.path.join(ICI, "pii_scan.py"), tmp.name],
                          capture_output=True, text=True).stdout
    os.unlink(tmp.name)
    for l in scan.splitlines():
        l = l.replace(tmp.name, rel).strip()
        if BLOQUANT_PII.search(l):
            refus.append("donnee personnelle : " + l)
        elif re.search(r"  (telephone|adresse) ", l):
            avert.append("a relire : " + l)

    # Invariants structurels (forme, identite, accents ; l'invention est
    # informative sur des sources reelles — c'est la lecture qui la juge).
    if rows and not refus:
        val = subprocess.run([sys.executable, os.path.join(ICI, "valider_paires.py"), path,
                              "--lang", lang_dossier], capture_output=True, text=True)
        if val.returncode != 0:
            pbs = [l.strip() for l in val.stdout.splitlines() if l.startswith("PB ")]
            refus.append("valider_paires : " + "; ".join(pbs or ["voir la sortie"]))
    rapport.append((rel, refus, avert, len(rows)))
    return len(refus)


def main():
    args = sys.argv[1:]
    fichiers = tous_les_fichiers() if "--tout" in args else [os.path.abspath(a) for a in args]
    if not fichiers:
        print("rien a verifier"); return 0
    # Les ids et cotes sales de TOUT contrib/ servent de reference aux doublons.
    ids_vus, sales_vus = {}, {}
    for f in tous_les_fichiers():
        if f in fichiers:
            continue
        rel = os.path.relpath(f, RACINE)
        for ligne in open(f, encoding="utf-8"):
            try:
                r = json.loads(ligne)
            except ValueError:
                continue
            ids_vus.setdefault(r.get("id"), rel)
            sales_vus.setdefault(cle_doublon(r.get("dirty", "")), (rel, r.get("id")))

    rapport, total = [], 0
    for f in fichiers:
        total += verifier(f, ids_vus, sales_vus, rapport)

    lignes = ["## Contributions de donnees", ""]
    for rel, refus, avert, n in rapport:
        etat = "REFUS" if refus else "OK"
        lignes.append("### %s — %s, %d paires" % (rel, etat, n))
        lignes += ["- ❌ " + r for r in refus]
        lignes += ["- ⚠️ " + a for a in avert]
        if not refus and not avert:
            lignes.append("- rien a signaler ; reste la lecture par un mainteneur")
        lignes.append("")
    texte = "\n".join(lignes)
    print(texte)
    resume = os.environ.get("GITHUB_STEP_SUMMARY")
    if resume:
        with open(resume, "a", encoding="utf-8") as f:
            f.write(texte + "\n")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
