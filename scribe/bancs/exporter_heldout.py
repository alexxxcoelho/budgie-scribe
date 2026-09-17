# -*- coding: utf-8 -*-
"""Produit le dataset public flowcorp-ch/BudgieScribe-eval depuis les generateurs.

    python scribe/bancs/exporter_heldout.py <dossier-de-sortie>

Regenere chaque famille synthetique avec ses graines fixes (les generateurs
sont deterministes : memes comptes que les cartes, 797/476/635/319/238 en
francais), garde la tranche `held_out`, et ecrit <sortie>/<lang>/heldout_<famille>.jsonl.

DONNEES PERSONNELLES — regle du projet (pii_scan.py) : rien de plausiblement
reel ne part. Les generateurs fabriquent des adresses `prenomnom@gmail.com`
qui peuvent appartenir a quelqu'un ; on remplace le domaine, DES DEUX COTES
de la paire (« gmail point com » cote sale, `gmail.com` cote propre), par un
domaine reserve RFC 2606. Les telephones sont des suites de chiffres au
hasard, inevitables dans un jeu d'ITN, et restent. Le scan tourne ensuite et
refuse la sortie s'il reste un e-mail, un IBAN, un nom banni.
"""
import json
import os
import re
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(RACINE, "generateurs")
FAMILLES = {
    "fr": ["itn", "correction", "forme", "compo", "cor_itn"],
    "en": ["itn_en", "correction_en", "forme_en", "compo_en", "cor_itn_en"],
}
ADMIS = {"example.com", "example.org", "example.net", "gobudgie.com"}
CIBLES = ["example.com", "example.org", "example.net"]
RE_EMAIL = re.compile(r"\b([\w.+-]+)@((?:[\w-]+\.)+[a-z]{2,})\b", re.I)


def anonymiser_emails(r):
    """Remplace le domaine de chaque e-mail, cote propre puis cote sale.

    Cote sale, le domaine est dicte mot a mot (« service tiret public point
    fr », "gmail dot com") : on reconstruit le motif parle a partir du domaine
    ecrit, tirets compris. Une paire dont le cote sale ne se realigne pas est
    une erreur, pas un cas a laisser passer.
    """
    mot, tiret = ("point", "tiret") if r["lang"] == "fr" else ("dot", "dash")
    for m in list(RE_EMAIL.finditer(r["clean"])):
        local, ecrit = m.group(1), m.group(2)
        if ecrit.lower() in ADMIS:
            continue
        new = CIBLES[sum(map(ord, ecrit)) % len(CIBLES)]
        r["clean"] = r["clean"].replace("%s@%s" % (local, ecrit), "%s@%s" % (local, new))
        parle = r"\s+".join(
            r"\s+%s\s+" % mot if p == "." else (r"\s+%s\s+" % tiret if p == "-" else re.escape(p))
            for p in re.split(r"([.-])", ecrit) if p)
        parle = re.sub(r"(\\s\+)+", r"\\s+", parle)
        r["dirty"], k = re.subn(r"\b" + parle + r"\b", new.replace(".", " %s " % mot),
                                r["dirty"], count=1, flags=re.I)
        if k != 1:
            raise SystemExit("cote sale non realigne pour %s : %s" % (r["id"], r["dirty"][:100]))
    return r


def main():
    out = sys.argv[1]
    tmp = os.path.join(out, "_gen")
    for lang, fams in FAMILLES.items():
        os.makedirs(os.path.join(out, lang), exist_ok=True)
        os.makedirs(os.path.join(tmp, lang), exist_ok=True)
        env = dict(os.environ, SCRIBE_LANG=lang, SCRIBE_TRAVAIL=os.path.join(tmp, lang))
        for fam in fams:
            subprocess.run([sys.executable, os.path.join(GEN, "gen_%s.py" % fam)],
                           env=env, check=True, stdout=subprocess.DEVNULL)
            src = os.path.join(tmp, lang, "pairs_%s.jsonl" % fam)
            rows = [json.loads(l) for l in open(src, encoding="utf-8")]
            tenus = [anonymiser_emails(r) for r in rows if r.get("held_out")]
            dst = os.path.join(out, lang, "heldout_%s.jsonl" % fam.replace("_en", ""))
            with open(dst, "w", encoding="utf-8") as f:
                for r in tenus:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print("%s/%s : %d tenues a l'ecart sur %d" % (lang, fam, len(tenus), len(rows)))
    subprocess.run(["rm", "-rf", tmp], check=True)

    # Garde : le scan designe, ce script tranche. Un telephone synthetique est
    # admis ; un e-mail, un IBAN, un nom banni, un code postal + ville refusent.
    fichiers = [os.path.join(out, l, f) for l in FAMILLES for f in sorted(os.listdir(os.path.join(out, l)))]
    rapport = subprocess.run([sys.executable, os.path.join(RACINE, "pipeline", "pii_scan.py")] + fichiers,
                             capture_output=True, text=True).stdout
    bloquant = [l for l in rapport.splitlines() if re.search(r"  (email|iban|nom_banni|code_postal_ville) ", l)]
    if bloquant:
        print("\n".join(bloquant))
        raise SystemExit("REFUS : donnee personnelle dans un jeu public")
    print("pii_scan : aucun e-mail, IBAN ni nom ; telephones synthetiques admis")


if __name__ == "__main__":
    main()
