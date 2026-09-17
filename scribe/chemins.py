# -*- coding: utf-8 -*-
"""Ou sont le code, les invites, et les donnees. Trois choses, pas une.

POURQUOI CE FICHIER EXISTE
Tant que le pipeline tenait dans un seul repertoire temporaire, une ligne
suffisait a tout adresser :

    SP = os.path.dirname(os.path.abspath(__file__))

Cette ligne repondait en fait a TROIS questions differentes, et elle n'y
repondait juste que parce que les trois reponses etaient le meme dossier :

  1. ou sont mes modules freres        -> `import spec`, `from bench_juge ...`
  2. ou sont les invites systeme       -> `_sys_qc.txt`, `_sys_ab.txt`
  3. ou sont les donnees               -> `pairs_mix6.jsonl`, `juge_*.json`

Le depot separe (1) et (2) en sous-repertoires, et surtout il ne contient
JAMAIS (3) : le corpus derive de SUMM-RE ne se distribue pas (voir NOTICE,
et notes d'entrainement §section 0.12). Confondre les trois n'est donc plus possible.

  RACINE   la racine du code, `scribe/`. Fixe, versionnee.
  PROMPTS  `scribe/prompts/`. Fixe, versionnee.
  TRAVAIL  le repertoire de donnees. Hors depot, volatil, choisi a l'execution
           par SCRIBE_TRAVAIL, sinon le repertoire courant.

Le repertoire courant comme defaut n'est pas un hasard : les scripts .ps1 font
`Push-Location` sur le repertoire de donnees avant chaque appel, exactement
comme avant. Un script lance depuis le dossier de donnees se comporte donc
comme la version d'origine, sans variable a poser.

Importer ce module ajoute aussi les quatre repertoires de code a sys.path :
`bench_prof.py` (bancs) a besoin de `spec` et `valider_paires` (pipeline), et
`gen_rocm.py` (entrainement) a besoin de `eval_synth` (bancs). Sans ca, la
mise en dossiers casserait deux imports qui marchaient.

POURQUOI LA LANGUE SE DECIDE ICI, ET NULLE PART AILLEURS
Un modele par langue (decision du 2026-09-05) : `spec_en.py` est un fichier
separe de `spec.py`, meme interface, mais le pipeline (professeur, filtre, QC,
arbitrage, juge A/B) est LUI partage entre les deux langues. Il faut donc UN
SEUL endroit qui decide, a partir de SCRIBE_LANG, quelle spec et quelle invite
charger — sinon chaque module retesterait la variable a sa facon, et un jour
l'un d'eux la testerait mal. `spec()` choisit le module, `prompt()` choisit le
fichier d'invite ; aucun autre fichier du pipeline ne doit lire SCRIBE_LANG
directement, il doit passer par l'un des deux.
"""
import importlib
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(RACINE, "prompts")

LANG = os.environ.get("SCRIBE_LANG", "fr")

# Ordre stable, pour que le chemin d'import ne depende pas de qui importe.
# `archive` en est ABSENT a dessein : ce qu'il contient n'est pas recable, et
# le mettre ici laisserait un module perime repondre au nom d'un module vivant.
CODE = [os.path.join(RACINE, d)
        for d in ("pipeline", "bancs", "generateurs", "entrainement", "corpus")]

for _d in [RACINE] + CODE:
    if _d not in sys.path:
        sys.path.insert(0, _d)

TRAVAIL = os.environ.get("SCRIBE_TRAVAIL") or os.getcwd()


_SPEC_CACHE = {}


def spec():
    """Le module de spec pour SCRIBE_LANG : `spec` en francais (le defaut, si
    la variable est absente), `spec_en` si SCRIBE_LANG=en. Mis en cache : LANG
    est lue une fois a l'import de ce module et ne bouge plus en cours de
    process, inutile de refaire l'import a chaque appel.

    C'est LE point de bascule : `make_pairs_v2.py`, `teach.py` et
    `adjudicate.py` font `spec = chemins.spec()` au lieu de `import spec`, et
    n'ont plus jamais a savoir que l'anglais existe."""
    if LANG not in _SPEC_CACHE:
        nom = "spec_en" if LANG == "en" else "spec"
        _SPEC_CACHE[LANG] = importlib.import_module(nom)
    return _SPEC_CACHE[LANG]


def prompt(nom):
    """Le texte d'une invite systeme. Echoue fort si elle manque : une invite
    absente donnerait un juge sans consigne, et un juge sans consigne note.

    SCRIBE_LANG != fr cherche D'ABORD la variante <racine>_<LANG><ext> — par
    exemple `_sys_ab.txt` devient `_sys_ab_en.txt` — et ne retombe sur le nom
    francais que si cette variante n'existe pas encore. Ce repli est voulu,
    pas une erreur avalee : tant qu'une invite anglaise n'est pas ecrite, mieux
    vaut que le juge continue de tourner (en francais) que de faire planter la
    chaine de nuit sur un fichier manquant."""
    if LANG != "fr":
        racine, ext = os.path.splitext(nom)
        candidat = "%s_%s%s" % (racine, LANG, ext)
        if os.path.exists(os.path.join(PROMPTS, candidat)):
            nom = candidat
    with open(os.path.join(PROMPTS, nom), encoding="utf-8") as f:
        return f.read()


def travail(*morceaux):
    """Un chemin dans le repertoire de donnees."""
    return os.path.join(TRAVAIL, *morceaux)
