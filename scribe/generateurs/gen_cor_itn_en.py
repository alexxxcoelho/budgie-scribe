# -*- coding: utf-8 -*-
"""Composition CORRECTION x ITN, VERSION ANGLAISE — jumeau de gen_cor_itn.py.

LE TROU QUE CE FICHIER BOUCHE (identique en anglais, voir gen_cor_itn.py)
Le modele sait trancher une auto-correction (gen_correction_en.py) et sait
convertir une expression numerique (gen_compo_en.py). Il echoue des que les
deux tombent dans la MEME phrase — c'est l'exemple meme de la spec du format :

    SALE    so um friday no wait thursday we have a meeting at half past two
    ATTENDU Thursday, we have a meeting at 2:30.
    OBTENU  Friday, no wait, Thursday, we have a meeting at 2:30.

L'ITN passe, la correction ne passe plus : le modele ponctue l'hesitation au
lieu de la resoudre. Chaque paire produite ici porte donc AU MOINS une
auto-correction ET au moins une expression numerique, dans la meme phrase.

POURQUOI LES CONTRE-EXEMPLES PESENT 25 % (meme raisonnement que le francais)
    non_non_correctif  "no"/"actually"/"rather" qui ne corrigent RIEN, avec
                       une expression numerique dans la phrase
    deux_valeurs       deux valeurs coordonnees, toutes deux legitimes,
                       toutes deux gardees

LES HEURES DES CONTRE-EXEMPLES SONT DEJA CHIFFREES — meme raison qu'en
francais (voir l'entete de gen_cor_itn.py) : "half past two" -> "2:30" fait
disparaitre les mots "half"/"past", qu'aucune table de valider_paires.py ne
couvre (contrairement au francais ou "heures" est un mot ordinaire qui, lui
non plus, n'est pas couvert — le mecanisme du piege est le meme, seul le mot
perdu change). f_heure_ecrite/f_plage_ecrite fournissent donc une heure DEJA
en chiffres pour les familles contre-exemple ; les familles "trancher"
continuent de dicter leurs heures en toutes lettres via f_heure.

UN PIEGE ANGLAIS QUE LE FRANCAIS N'A PAS : LE MOT "PERCENT"
En francais, f_pourcent dicte "pour cent" et le mot "cent" est deja dans la
table NOMBRES_MOTS — par pure coincidence, "cent" y designe aussi le nombre
100. Rien ne protege "percent" en anglais : il n'est ni dans NOMBRES_MOTS, ni
dans OUTILS, et sa disparition ("twenty five percent" -> "25%") serait
signalee comme une perte dans un contre-exemple. f_pourcent_ecrite regle ce
point comme f_heure_ecrite regle "half"/"past" : deja chiffre des deux cotes,
aucun mot naturel a perdre.

MEME PIEGE POUR "DOLLARS"/"EUROS" : f_dollars, PAS f_montant, DANS LES CE
f_montant (gen_compo_en.py) convertit la devise en symbole ("$1,200") et fait
disparaitre le mot "dollars", non couvert non plus. f_dollars garde le mot
"dollars" ECRIT EN TOUTES LETTRES DES DEUX COTES ("1,200 dollars") — meme
fragment que f_euros dans gen_cor_itn.py, et pour la meme deuxieme raison :
deux montants composes dans une meme phrase ("$300 and $350") doivent
partager la MEME devise, ce que f_montant ne garantit pas (il la retire a
chaque appel).

PAS DE HYPHEN A CASSER, DONC PAS DE MONTANTS_CE
Le francais filtre les montants dont la forme dictee perd un morceau au
trait d'union ("quatre-vingts" -> "vingts" une fois le "quatre" coupe).
`dicte()` de gen_compo_en.py retire deja les traits d'union AVANT que le mot
n'atteigne le texte ("twenty-three" -> "twenty three") : les deux moities
restent des mots NOMBRES_MOTS a part entiere. Mesure sur ce venv (num2words)
pour les 28 montants ci-dessous : aucun trait d'union ne survit. Le filtre
francais n'a donc pas d'equivalent ici — MONTANTS sert tel quel partout.

LE PRONOM EST TOUJOURS "IT" — GENRE N'EST PAS IMPORTE
L'anglais n'accorde pas en genre (gen_correction_en.py : `GENRE = {}`). Le
seul gabarit qui reprend l'objet par un pronom ecrit donc "it" en dur, sans
fente dediee — il n'y a rien a trancher.

CASSE DES JOURS : DIVERGENTE ENTRE COTE SALE ET COTE PROPRE
`JOURS` (importe de gen_correction_en.py) est stocke CAPITALISE ("Thursday").
Cote sale, un jour dicte est toujours en minuscules — c'est ce qu'une
transcription ASR brute produit. Contrairement a PRENOMS/VILLES (capitalises
DES DEUX cotes, jamais abaisses), un jour est donc le SEUL vocabulaire ou
`_rendu()` recoit deux dictionnaires distincts (extra_d/extra_c) : la forme
`.lower()` pour le gabarit sale, la forme d'origine (deja capitalisee) pour
le gabarit propre. C'est exactement le mecanisme que gen_nombre_x utilise
deja pour une valeur corrigee dont la forme differe entre dicte et ecrit —
ici la difference est la casse, pas la valeur.

Usage : gen_cor_itn_en.py [n] [sortie.jsonl]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

# REUTILISER AVANT DE CREER. Fragments ITN de gen_compo_en.py, lexique et
# marqueurs de correction de gen_correction_en.py. Recopier ces listes les
# ferait diverger au premier ajout de vocabulaire. Aucun des deux fichiers
# n'est modifie.
from gen_compo_en import f_heure, f_montant, f_date, f_pourcent, f_entier, f_tel, f_email, mot, esp
from gen_correction_en import (JOURS, PRENOMS, VILLES, LIEUX, OBJETS,
                               VERBES_ACTION, M_PARDON, M_ENFIN, M_PLUTOT,
                               M_VEUX_DIRE, M_NON_SEC, maj, _remplace,
                               COMPLEMENTS)

SEED = 20260905
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]"
# 20-30 % des entrees en recoivent une, comme gen_correction_en.py.
HESITATIONS = ["um ", "uh ", "so um ", "er ", "hmm ", ""]

# Les cinq familles de marqueurs sont melangees : "no wait", "actually", "or
# rather", "I mean", "no" doivent tous declencher la meme decision.
MARQUEURS = M_PARDON + M_ENFIN + M_PLUTOT + M_VEUX_DIRE + M_NON_SEC

# Plus large que la liste de gen_compo_en.py : c'est la COMBINATOIRE, pas le
# poids, qui fixe le plafond d'une famille.
MONTANTS = [80, 100, 120, 150, 180, 200, 250, 300, 350, 400, 450, 500, 600,
            750, 800, 900, 1000, 1200, 1500, 1800, 2000, 2500, 3000, 3500,
            4500, 6000, 8000, 12000]
POURCENTS = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 75]
SYM = {"dollars": "$", "euros": "€"}


# ── Fragments propres a ce jeu ──────────────────────────────────────────────
def f_dollars(rng):
    """Montant en dollars, mot GARDE tel quel (pas de symbole $) : voir
    l'entete du fichier — evite la perte du mot "dollars" dans un
    contre-exemple, et garantit la meme devise quand deux montants sont
    composes dans la meme phrase."""
    n = rng.choice(MONTANTS)
    return "%s dollars" % mot(n), "%s dollars" % esp(n)


def f_pourcent_ecrite(rng):
    """Pourcentage deja chiffre des deux cotes : voir l'entete du fichier —
    "percent" n'est protege par aucune table de valider_paires.py."""
    n = rng.choice(POURCENTS)
    return "%d%%" % n, "%d%%" % n


def f_heure_ecrite(rng):
    """Heure deja normalisee des la dictee — voir l'entete du fichier."""
    h = rng.randint(7, 20)
    mn = rng.choice([0, 0, 15, 30, 45])
    s = "%d:%02d" % (h, mn)
    return s, s


def f_plage_ecrite(rng):
    """"2:00 to 6:00" — deja chiffree, meme raison."""
    s = "%d:00 to %d:00" % (rng.randint(7, 12), rng.randint(14, 20))
    return s, s


def f_creneau(rng):
    """"from nine to half past two" -> "9:00 to 2:30".

    Un SEUL fragment pour les deux bornes : deux appels a f_heure
    produiraient une plage qui n'existe pas (ex. "from 6pm to 9am"). Utilise
    uniquement dans une famille "trancher" (T_JOUR_HEURE) : aucune contrainte
    de perte de mot ne s'y applique, contrairement a f_heure_ecrite."""
    h1, h2 = rng.randint(7, 12), rng.randint(14, 20)
    m1, m2 = rng.choice([0, 0, 30]), rng.choice([0, 0, 30])

    def piece(h, m):
        if m:
            return "%s thirty" % mot(h), "%d:30" % h
        return "%s o'clock" % mot(h), "%d:00" % h

    d1, e1 = piece(h1, m1)
    d2, e2 = piece(h2, m2)
    return "%s to %s" % (d1, d2), "%s to %s" % (e1, e2)


# ── Paires corrigees : la valeur abandonnee et la valeur retenue ────────────
# Chaque paire est tiree UNE fois ; le cote sale prend les deux formes
# dictees, le cote propre la seule forme ecrite de la valeur retenue.
def _paire_montant(rng):
    a = rng.choice(MONTANTS)
    b = _remplace(rng, MONTANTS, a)
    dev = rng.choices(["dollars", "euros"], weights=[9, 1])[0]
    forme = lambda n: ("%s %s" % (mot(n), dev), "%s%s" % (SYM[dev], esp(n)))
    return forme(a), forme(b)


def _paire_entier(rng):
    vals = list(range(2, 61))
    a = rng.choice(vals)
    b = _remplace(rng, vals, a)
    return (mot(a), str(a)), (mot(b), str(b))


def _paire_pourcent(rng):
    a = rng.choice(POURCENTS)
    b = _remplace(rng, POURCENTS, a)
    forme = lambda n: ("%s percent" % mot(n), "%d%%" % n)
    return forme(a), forme(b)


def _paire_heure(rng):
    a = f_heure(rng)
    b = f_heure(rng)
    for _ in range(25):
        if b[1] != a[1]:
            break
        b = f_heure(rng)
    return a, b


CORRECTEURS = {"montant": _paire_montant, "entier": _paire_entier,
               "pourcent": _paire_pourcent, "heure": _paire_heure}


# ── Rendu ───────────────────────────────────────────────────────────────────
def _rendu(rng, d_tpl, c_tpl, frags, extra_d, extra_c=None):
    """Remplit {f1}, {f2}... avec des fragments tires UNE fois.

    `extra_d` / `extra_c` portent les fentes non numeriques (jour, prenom,
    marqueur...). Elles sont identiques sauf quand la forme differe entre
    dicte et ecrit — un jour (casse) ou une valeur corrigee (valeur)."""
    sd = dict(extra_d)
    sc = dict(extra_c if extra_c is not None else extra_d)
    vus = set()
    for i, f in enumerate(frags, 1):
        dit, ecrit = f(rng)
        for _ in range(25):
            if ecrit not in vus:
                break
            dit, ecrit = f(rng)
        vus.add(ecrit)
        sd["f%d" % i] = dit
        sc["f%d" % i] = ecrit
    return d_tpl.format(**sd), c_tpl.format(**sc)


def _fentes(rng):
    """Fentes communes a tous les gabarits — fournies meme si inutilisees.

    `j` est TOUJOURS en minuscules : c'est la forme sale. Un gabarit qui a
    besoin de la forme propre appelle `maj(ex["j"])` lui-meme.

    `k` est le complement de contenu intercale entre la valeur abandonnee et
    le marqueur — voir COMPLEMENTS dans gen_correction_en.py, et l'entete de
    ce fichier pour le trou qu'il bouche (scribe-en-v1 perd "tomorrow" dans
    "let's meet at half past two tomorrow ... make it three fifteen p m").
    Fourni ici pour TOUS les gabarits, meme ceux qui n'utilisent pas {k} :
    plus simple qu'un tirage conditionnel par gabarit, et un tirage inutilise
    ne coute rien. Les gabarits dont la valeur corrigee est un prenom ou un
    lieu ecrasent `ex["k"]` eux-memes pour exclure le complement qui
    doublonnerait leur propre vocabulaire (voir gen_prenom_date,
    gen_lieu_montant)."""
    o = rng.choice(OBJETS)
    return {"m": rng.choice(MARQUEURS), "o": o, "p": rng.choice(PRENOMS),
            "v": "%s %s" % (rng.choice(VERBES_ACTION), o),
            "j": rng.choice(JOURS).lower(), "k": rng.choice(COMPLEMENTS)}


# ═══ TRANCHER : une correction ET une expression numerique ═════════════════

# --- 1. correction sur un JOUR + une heure ---------------------------------
T_JOUR_HEURE = [
    ("{a} {m} {b} we have a meeting at {f1}",
     "{B}, we have a meeting at {f1}.", (f_heure,)),
    ("{a} {m} {b} we have a meeting at {f1} for {f2}",
     "{B}, we have a meeting at {f1} for {f2}.", (f_heure, f_montant)),
    ("let's meet {a} {m} {b} at {f1}",
     "Let's meet {b} at {f1}.", (f_heure,)),
    ("the meeting is {a} {m} {b} at {f1}",
     "The meeting is {b} at {f1}.", (f_heure,)),
    ("i'll stop by {a} {m} {b} around {f1} for {f2}",
     "I'll stop by {b} around {f1} for {f2}.", (f_heure, f_montant)),
    ("we're starting {a} {m} {b} at {f1} with {f2} people",
     "We're starting {b} at {f1} with {f2} people.", (f_heure, f_entier)),
    ("the review of {o} is set for {a} {m} {b} at {f1}",
     "The review of {o} is set for {b} at {f1}.", (f_heure,)),
    ("{p} arrives {a} {m} {b} at {f1} and leaves on {f2}",
     "{p} arrives {b} at {f1} and leaves on {f2}.", (f_heure, f_date)),
    ("we're delivering {o} {a} {m} {b} at {f1} for {f2}",
     "We're delivering {o} {b} at {f1} for {f2}.", (f_heure, f_montant)),
    ("can we meet {a} {m} {b} at {f1}",
     "Can we meet {b} at {f1}?", (f_heure,)),
    ("call me {a} {m} {b} before {f1} at {f2}",
     "Call me {b} before {f1} at {f2}.", (f_heure, f_tel)),
    ("we need to wrap up {o} {a} {m} {b} before {f1}",
     "We need to wrap up {o} {b} before {f1}.", (f_heure,)),
    ("the slot is {a} {m} {b} from {f1}",
     "The slot is {b} from {f1}.", (f_creneau,)),
    # Variantes a complement intercale (~1/3 des gabarits de cette famille) :
    # voir COMPLEMENTS et le trou mesure sur scribe-en-v1 en tete de fichier.
    # "let's meet ... TOMORROW ... make it ..." est l'exemple meme de la
    # spec du format.
    ("{a} {k} {m} {b} we have a meeting at {f1}",
     "{B}, we have a meeting at {f1} {k}.", (f_heure,)),
    ("let's meet {a} {k} {m} {b} at {f1}",
     "Let's meet {b} at {f1} {k}.", (f_heure,)),
    ("the meeting is {a} {k} {m} {b} at {f1}",
     "The meeting is {b} at {f1} {k}.", (f_heure,)),
    ("can we meet {a} {k} {m} {b} at {f1}",
     "Can we meet {b} at {f1} {k}?", (f_heure,)),
    ("we're delivering {o} {a} {k} {m} {b} at {f1} for {f2}",
     "We're delivering {o} {b} at {f1} for {f2} {k}.", (f_heure, f_montant)),
    ("i'll stop by {a} {k} {m} {b} around {f1} for {f2}",
     "I'll stop by {b} around {f1} for {f2} {k}.", (f_heure, f_montant)),
]


def gen_jour_heure(rng):
    d, c, frags = rng.choice(T_JOUR_HEURE)
    a = rng.choice(JOURS)
    b = _remplace(rng, JOURS, a)
    ex = _fentes(rng)
    ed = dict(ex); ed.update({"a": a.lower(), "b": b.lower()})
    ec = dict(ex); ec.update({"a": a, "b": b, "B": maj(b)})
    return _rendu(rng, d, c, frags, ed, ec)


# --- 2. correction sur un LIEU + un montant --------------------------------
# `pool` garde les gabarits grammaticaux : "we're opening the office at home"
# est du charabia, et six cents paires de charabia s'apprennent.
T_LIEU_MONTANT = [
    ("both", "we're signing {a} {m} {b} for {f1}",
     "We're signing {b} for {f1}.", (f_montant,)),
    ("both", "the training happens {a} {m} {b} for {f1}",
     "The training happens {b} for {f1}.", (f_montant,)),
    ("both", "the job is {a} {m} {b} and it costs {f1}",
     "The job is {b} and it costs {f1}.", (f_montant,)),
    ("both", "the booth will be {a} {m} {b} and it costs us {f1} a day",
     "The booth will be {b} and it costs us {f1} a day.", (f_montant,)),
    ("both", "we need to deliver {o} {a} {m} {b} for {f1}",
     "We need to deliver {o} {b} for {f1}.", (f_montant,)),
    ("both", "we're meeting {a} {m} {b} at {f1} for {f2}",
     "We're meeting {b} at {f1} for {f2}.", (f_heure, f_montant)),
    ("both", "the appointment is {a} {m} {b} at {f1} for {f2}",
     "The appointment is {b} at {f1} for {f2}.", (f_heure, f_montant)),
    ("both", "{p} is expecting us {a} {m} {b} with a quote of {f1}",
     "{p} is expecting us {b} with a quote of {f1}.", (f_montant,)),
    ("ville", "we're opening the office {a} {m} {b} with a budget of {f1}",
     "We're opening the office {b} with a budget of {f1}.", (f_montant,)),
    ("ville", "i booked a room {a} {m} {b} for {f1}",
     "I booked a room {b} for {f1}.", (f_montant,)),
    ("ville", "we're moving {a} {m} {b} on {f1} for {f2}",
     "We're moving {b} on {f1} for {f2}.", (f_date, f_montant)),
    ("ville", "the site is {a} {m} {b} and it's quoted at {f1}",
     "The site is {b} and it's quoted at {f1}.", (f_montant,)),
    ("lieu", "let's do the check in {a} {m} {b} on {o} for {f1}",
     "Let's do the check in {b} on {o} for {f1}.", (f_montant,)),
    ("lieu", "i'm dropping off {o} {a} {m} {b}, it's at {f1}",
     "I'm dropping off {o} {b}, it's at {f1}.", (f_montant,)),
    # Variantes a complement intercale — voir COMPLEMENTS en tete de fichier.
    # gen_lieu_montant() ecrase ex["k"] pour exclure "at the office" quand
    # {a}/{b} viennent de LIEUX (qui le contient deja).
    ("both", "we're signing {a} {k} {m} {b} for {f1}",
     "We're signing {b} for {f1} {k}.", (f_montant,)),
    ("both", "the training happens {a} {k} {m} {b} for {f1}",
     "The training happens {b} for {f1} {k}.", (f_montant,)),
    ("both", "we're meeting {a} {k} {m} {b} at {f1} for {f2}",
     "We're meeting {b} at {f1} for {f2} {k}.", (f_heure, f_montant)),
    ("ville", "we're opening the office {a} {k} {m} {b} with a budget of {f1}",
     "We're opening the office {b} with a budget of {f1} {k}.", (f_montant,)),
    ("ville", "i booked a room {a} {k} {m} {b} for {f1}",
     "I booked a room {b} for {f1} {k}.", (f_montant,)),
    ("lieu", "i'm dropping off {o} {a} {k} {m} {b}, it's at {f1}",
     "I'm dropping off {o} {b}, it's at {f1} {k}.", (f_montant,)),
]


def gen_lieu_montant(rng):
    pool, d, c, frags = rng.choice(T_LIEU_MONTANT)
    if pool == "ville" or (pool == "both" and rng.random() < 0.5):
        va = rng.choice(VILLES)
        vb = _remplace(rng, VILLES, va)
        a, b = "in %s" % va, "in %s" % vb
        de_lieux = False
    else:
        a = rng.choice(LIEUX)
        b = _remplace(rng, LIEUX, a)
        de_lieux = True
    ex = _fentes(rng)
    if de_lieux:
        # LIEUX contient deja "at the office" : l'exclure du complement
        # evite le doublon ("we're meeting at home at the office no wait...").
        ex["k"] = rng.choice([x for x in COMPLEMENTS if x != "at the office"])
    ex.update({"a": a, "b": b})
    return _rendu(rng, d, c, frags, ex)


# --- 3. correction sur un PRENOM + une date --------------------------------
T_PRENOM_DATE = [
    ("it's {a} {m} {b} who's sending {o} before {f1}",
     "It's {b} who's sending {o} before {f1}.", (f_date,)),
    ("{a} {m} {b} is back on {f1}",
     "{B} is back on {f1}.", (f_date,)),
    ("we need to give {a} {m} {b} a heads up before {f1}",
     "We need to give {b} a heads up before {f1}.", (f_date,)),
    ("{a} {m} {b} signs the contract on {f1} for {f2}",
     "{B} signs the contract on {f1} for {f2}.", (f_date, f_montant)),
    ("i saw {a} {m} {b} on {f1}",
     "I saw {b} on {f1}.", (f_date,)),
    ("{o} from {a} {m} {b} ships on {f1}",
     "{O} from {b} ships on {f1}.", (f_date,)),
    ("ask {a} {m} {b} to call back before {f1} at {f2}",
     "Ask {b} to call back before {f1} at {f2}.", (f_date, f_tel)),
    ("email {a} {m} {b} on {f1} at {f2}",
     "Email {b} on {f1} at {f2}.", (f_date, f_email)),
    ("{a} {m} {b} bills {f1} on {f2}",
     "{B} bills {f1} on {f2}.", (f_montant, f_date)),
    ("we're expecting {a} {m} {b} on {f1} at {f2}",
     "We're expecting {b} on {f1} at {f2}.", (f_date, f_heure)),
    ("the file goes to {a} {m} {b} on {f1}",
     "The file goes to {b} on {f1}.", (f_date,)),
    ("is {a} {m} {b} free on {f1}",
     "Is {b} free on {f1}?", (f_date,)),
    # Variantes a complement intercale — voir COMPLEMENTS en tete de fichier.
    # gen_prenom_date() exclut "with Sarah" du tirage de {k} : {a}/{b} sont
    # deja des PRENOMS, et Sarah peut etre l'un d'eux.
    ("it's {a} {k} {m} {b} who's sending {o} before {f1}",
     "It's {b} who's sending {o} before {f1} {k}.", (f_date,)),
    ("{a} {k} {m} {b} is back on {f1}",
     "{B} is back on {f1} {k}.", (f_date,)),
    ("we need to give {a} {k} {m} {b} a heads up before {f1}",
     "We need to give {b} a heads up before {f1} {k}.", (f_date,)),
    ("i saw {a} {k} {m} {b} on {f1}",
     "I saw {b} on {f1} {k}.", (f_date,)),
    ("ask {a} {k} {m} {b} to call back before {f1} at {f2}",
     "Ask {b} to call back before {f1} at {f2} {k}.", (f_date, f_tel)),
    ("the file goes to {a} {k} {m} {b} on {f1}",
     "The file goes to {b} on {f1} {k}.", (f_date,)),
]


def gen_prenom_date(rng):
    d, c, frags = rng.choice(T_PRENOM_DATE)
    a = rng.choice(PRENOMS)
    b = _remplace(rng, PRENOMS, a)
    ex = _fentes(rng)
    # {a}/{b} sont deja des PRENOMS : exclure "with Sarah" du complement
    # evite un doublon ("it's Sarah with Sarah who's...").
    ex["k"] = rng.choice([x for x in COMPLEMENTS if x != "with Sarah"])
    ex.update({"a": a, "b": b, "B": maj(b), "O": maj(ex["o"])})
    return _rendu(rng, d, c, frags, ex)


# --- 4. correction sur un NOMBRE + une autre expression numerique ----------
# La famille la plus proche du defaut mesure : les DEUX competences tirent en
# meme temps sur la meme phrase, et sur des chiffres des deux cotes.
T_NOMBRE_X = [
    ("montant", "the quote is {a} {m} {b} before {f1}",
     "The quote is {b} before {f1}.", (f_date,)),
    ("montant", "the deposit is {a} {m} {b} due on {f1}",
     "The deposit is {b} due on {f1}.", (f_date,)),
    ("montant", "the budget goes to {a} {m} {b} before {f1}",
     "The budget goes to {b} before {f1}.", (f_heure,)),
    ("montant", "that comes to {a} {m} {b} in total for {f1} days",
     "That comes to {b} in total for {f1} days.", (f_entier,)),
    ("montant", "we're going with {a} {m} {b} per person for {f1} people",
     "We're going with {b} per person for {f1} people.", (f_entier,)),
    ("montant", "the invoice is {a} {m} {b} and it goes out on {f1}",
     "The invoice is {b} and it goes out on {f1}.", (f_date,)),
    ("montant", "we need to settle {a} {m} {b} before {f1}",
     "We need to settle {b} before {f1}.", (f_date,)),
    ("entier", "we need {a} {m} {b} of them for {f1}",
     "We need {b} of them for {f1}.", (f_montant,)),
    ("entier", "we'll be {a} {m} {b} at the {f1} meeting",
     "We'll be {b} at the {f1} meeting.", (f_heure,)),
    ("entier", "i ordered {a} {m} {b} units for {f1}",
     "I ordered {b} units for {f1}.", (f_montant,)),
    ("entier", "there are {a} {m} {b} seats left for {f1}",
     "There are {b} seats left for {f1}.", (f_date,)),
    ("pourcent", "we're at {a} {m} {b} off on {f1}",
     "We're at {b} off on {f1}.", (f_montant,)),
    ("pourcent", "there's {a} {m} {b} of margin left on {f1}",
     "There's {b} of margin left on {f1}.", (f_montant,)),
    ("heure", "the appointment is at {a} {m} {b} on {f1}",
     "The appointment is at {b} on {f1}.", (f_date,)),
    ("heure", "we're setting it for {a} {m} {b} for {f1}",
     "We're setting it for {b} for {f1}.", (f_montant,)),
    ("heure", "{p} comes by at {a} {m} {b} with {f1} files",
     "{p} comes by at {b} with {f1} files.", (f_entier,)),
    # Variantes a complement intercale — voir COMPLEMENTS en tete de fichier.
    # {a}/{b} sont numeriques ici (montant/entier/pourcent/heure) : aucune
    # exclusion de {k} n'est necessaire, contrairement a prenom_date et
    # lieu_montant. L'entree "heure" ci-dessous est l'exemple meme de la
    # spec du format : "half past two TOMORROW actually make it three fifteen
    # p m" -> "3:15pm TOMORROW."
    ("montant", "the quote is {a} {k} {m} {b} before {f1}",
     "The quote is {b} before {f1} {k}.", (f_date,)),
    ("montant", "the invoice is {a} {k} {m} {b} and it goes out on {f1}",
     "The invoice is {b} and it goes out on {f1} {k}.", (f_date,)),
    ("entier", "we need {a} {k} {m} {b} of them for {f1}",
     "We need {b} of them for {f1} {k}.", (f_montant,)),
    ("entier", "i ordered {a} {k} {m} {b} units for {f1}",
     "I ordered {b} units for {f1} {k}.", (f_montant,)),
    ("pourcent", "we're at {a} {k} {m} {b} off on {f1}",
     "We're at {b} off on {f1} {k}.", (f_montant,)),
    ("heure", "the appointment is at {a} {k} {m} {b} on {f1}",
     "The appointment is at {b} on {f1} {k}.", (f_date,)),
]


def gen_nombre_x(rng):
    corr, d, c, frags = rng.choice(T_NOMBRE_X)
    (a_dit, _), (b_dit, b_ecrit) = CORRECTEURS[corr](rng)
    ex = _fentes(rng)
    ed = dict(ex); ed.update({"a": a_dit, "b": b_dit})
    ec = dict(ex); ec.update({"a": a_dit, "b": b_ecrit})
    return _rendu(rng, d, c, frags, ed, ec)


# --- 5. faux depart + expression numerique ---------------------------------
# Aucun marqueur : c'est la reprise seule qui signale l'abandon. Le modele
# doit couper l'amorce et normaliser le nombre dans le meme mouvement.
T_FAUX = [
    ("i'm i'm not going to {v} before {f1}",
     "I'm not going to {v} before {f1}.", (f_heure,)),
    ("we can we have to deliver {o} before {f1}",
     "We have to deliver {o} before {f1}.", (f_date,)),
    ("we need we should {v} for {f1}",
     "We should {v} for {f1}.", (f_montant,)),
    ("i'm i'll send {o} before {f1}",
     "I'll send {o} before {f1}.", (f_heure,)),
    ("we ought we need to {v} before {f1}",
     "We need to {v} before {f1}.", (f_date,)),
    ("i started i finished {v} on {f1}",
     "I finished {v} on {f1}.", (f_date,)),
    ("we had we said {f1} for {o}",
     "We said {f1} for {o}.", (f_montant,)),
    ("the budget it's the budget is {f1} for {f2} people",
     "The budget is {f1} for {f2} people.", (f_montant, f_entier)),
    ("we're meeting we're meeting up at {f1} on {f2}",
     "We're meeting up at {f1} on {f2}.", (f_heure, f_date)),
    ("i think i believe we'll get {f1} off on {f2}",
     "I believe we'll get {f1} off on {f2}.", (f_pourcent, f_montant)),
    ("call call me at {f1} before {f2}",
     "Call me at {f1} before {f2}.", (f_tel, f_heure)),
    ("i need we need {f1} before {f2}",
     "We need {f1} before {f2}.", (f_montant, f_date)),
    ("{p} is coming {p} is stopping by at {f1} on {f2}",
     "{p} is stopping by at {f1} on {f2}.", (f_heure, f_date)),
    ("we we had quoted {o} at {f1} on {f2}",
     "We had quoted {o} at {f1} on {f2}.", (f_montant, f_date)),
    ("i was supposed to i was going to {v} before {f1}",
     "I was going to {v} before {f1}.", (f_heure,)),
]


def gen_faux_depart(rng):
    d, c, frags = rng.choice(T_FAUX)
    return _rendu(rng, d, c, frags, _fentes(rng))


# ═══ CONTRE-EXEMPLES : le modele ne doit RIEN supprimer ════════════════════

# --- 6. "no"/"actually"/"rather" NON correctifs + un nombre ----------------
# (dit, ecrit, virgule).
PREFIXES = [("no", "No", True), ("no no", "No no", True),
            ("no but", "No but", False), ("oh no", "Oh no", True),
            ("anyway", "Anyway", True), ("anyway so", "Anyway so", True),
            ("well anyway", "Well anyway", True)]
SUFFIXES = ["anyway", "so anyway", "either way"]

# Un seul gabarit par entree : les deux cotes sont le MEME texte, seuls les
# fragments changent de forme. C'est ce qui garantit qu'un contre-exemple ne
# perd rien — l'invariant est structurel, pas declaratif. Les fragments
# utilises ici sont TOUS "surs" pour une contre-exemple (voir l'entete) :
# f_dollars et f_pourcent_ecrite au lieu de f_montant/f_pourcent.
CORPS_NON = [
    ("it's true that we need {f1} before {j}", (f_dollars,)),
    ("we haven't gotten {o} worth {f1} yet", (f_dollars,)),
    ("i don't think we can finish before {f1}", (f_date,)),
    ("there's {f1} of margin left on {f2}", (f_pourcent_ecrite, f_dollars)),
    ("there are {f1} of us on the team and that's enough", (f_entier,)),
    ("the meeting at {f1} still stands", (f_heure_ecrite,)),
    ("it's been {f1} days since i've been waiting on {o}", (f_entier,)),
    ("we need to add {f1} more", (f_dollars,)),
    ("i'd rather we talk about the budget of {f1} on {j}", (f_dollars,)),
    ("we have {f1} files to handle before {f2}", (f_entier, f_date)),
    ("{p} stops by on {j} at {f1} with {o}", (f_heure_ecrite,)),
    ("the discount of {f1} runs until {f2}", (f_pourcent_ecrite, f_date)),
    ("it's rather {f1} that we should plan for {o}", (f_dollars,)),
    ("we're at {f1} of margin on {o}", (f_pourcent_ecrite,)),
    ("{o} of {f1} ships on {j} and that's fine", (f_dollars,)),
    ("i went over {o} and it's missing {f1} in total", (f_dollars,)),
    ("{p} bills {f1} and everyone agrees", (f_dollars,)),
    ("we're keeping {f1} aside for {j}", (f_dollars,)),
]


def gen_non_non_correctif(rng):
    tpl, frags = rng.choice(CORPS_NON)
    ed = _fentes(rng)
    ec = dict(ed); ec["j"] = maj(ed["j"])
    corps_d, corps_c = _rendu(rng, tpl, tpl, frags, ed, ec)
    if rng.random() < 0.28:
        s = rng.choice(SUFFIXES)
        return "%s %s" % (corps_d, s), "%s, %s." % (maj(corps_c), s)
    dit, ecrit, virgule = rng.choice(PREFIXES)
    return "%s %s" % (dit, corps_d), "%s%s %s." % (ecrit, "," if virgule else "",
                                                   corps_c)


# --- 7. deux valeurs coordonnees, toutes deux gardees ----------------------
T_DEUX = [
    ("jours", "we have a meeting {a} and {b} at {f1}", (f_heure_ecrite,)),
    ("jours", "i'm available {a} and {b} for {f1}", (f_dollars,)),
    ("jours", "we're around from {f1} {a} and {b}", (f_plage_ecrite,)),
    ("jours", "we're delivering {a} and {b} for {f1} total", (f_dollars,)),
    ("jours", "the {f1} check in stands {a} and {b}", (f_heure_ecrite,)),
    ("prenoms", "{a} and {b} are handling the {f1} file", (f_dollars,)),
    ("prenoms", "{a} and {b} arrive at {f1} on {f2}", (f_heure_ecrite, f_date)),
    ("prenoms", "{a} and {b} each have {f1} files", (f_entier,)),
    ("villes", "we have offices in {a} and in {b} for {f1} a month", (f_dollars,)),
    ("villes", "we need {f1} for {a} and {f2} for {b}", (f_entier, f_entier)),
    ("villes", "the booth is in {a} and in {b} on {f1}", (f_date,)),
    ("objets", "i need {a} and {b} before {f1}", (f_date,)),
    ("objets", "{a} and {b} come to {f1} total", (f_dollars,)),
    ("aucun", "the quote goes from {f1} to {f2}", (f_dollars, f_dollars)),
    ("aucun", "we need {f1} files on {f2} and {f3} on {f4}",
     (f_entier, f_date, f_entier, f_date)),
    ("aucun", "count {f1} off and {f2} in fees", (f_pourcent_ecrite, f_dollars)),
    ("aucun", "we bill {f1} in march and {f2} in april", (f_dollars, f_dollars)),
    ("aucun", "the meeting is on {f1} and on {f2}", (f_date, f_date)),
    ("aucun", "we're asking for {f1} down and {f2} on delivery",
     (f_dollars, f_dollars)),
]


def gen_deux_valeurs(rng):
    pool, tpl, frags = rng.choice(T_DEUX)
    src = {"prenoms": PRENOMS, "villes": VILLES, "objets": OBJETS}.get(pool)
    ed = _fentes(rng)
    if pool == "jours":
        a = rng.choice(JOURS)
        b = _remplace(rng, JOURS, a)
        ed.update({"a": a.lower(), "b": b.lower()})
        ec = dict(ed); ec.update({"a": a, "b": b})
    elif src:
        a = rng.choice(src)
        b = _remplace(rng, src, a)
        ed.update({"a": a, "b": b})
        ec = dict(ed)
    else:
        ec = dict(ed)
    d, c = _rendu(rng, tpl, tpl, frags, ed, ec)
    return d, maj(c) + "."


FAMILLES = [
    # trancher — 75 %
    ("jour_heure", gen_jour_heure, 17),
    ("lieu_montant", gen_lieu_montant, 15),
    ("prenom_date", gen_prenom_date, 14),
    ("nombre_x", gen_nombre_x, 16),
    ("faux_depart", gen_faux_depart, 13),
    # ne rien supprimer — 25 %, et c'est delibere
    ("non_non_correctif", gen_non_non_correctif, 14),
    ("deux_valeurs", gen_deux_valeurs, 11),
]
CONTRE = {"non_non_correctif", "deux_valeurs"}
PLANCHER = 200


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_cor_itn_en.jsonl")
    rng = random.Random(SEED)
    noms = [f[0] for f in FAMILLES]
    poids = [f[2] for f in FAMILLES]
    fns = {f[0]: f[1] for f in FAMILLES}

    seen, rows, stats = set(), [], collections.Counter()
    tries = 0
    while len(rows) < n_total and tries < n_total * 60:
        tries += 1
        fam = rng.choices(noms, weights=poids)[0]
        try:
            dirty, clean = fns[fam](rng)
        except Exception:
            continue
        if dirty in seen:
            continue
        seen.add(dirty)
        # Le cote sale doit ressembler a de l'ASR. Les hesitations
        # disparaissent partout, contre-exemples compris.
        if rng.random() < 0.25:
            h = rng.choice(HESITATIONS)
            if h:
                dirty = h + dirty
        stats[fam] += 1
        rows.append({"id": "cri-en-%05d" % len(rows), "file": "cri-%s" % fam,
                     "source": "coritn", "lang": "en", "held_out": False,
                     "styling": "semi-formal", "structure": "prose",
                     "context": "general", "control": CONTROL,
                     "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart PAR FAMILLE. Ce jeu n'a que sept valeurs de `file` :
    # un decoupage par fichier emporterait des familles entieres.
    par_fam = collections.defaultdict(list)
    for r in rows:
        par_fam[r["file"].split("-", 1)[-1]].append(r)
    for fam, group in par_fam.items():
        for r in rng.sample(group, max(1, int(len(group) * 0.08))):
            r["held_out"] = True

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(rows)
    tranche = sum(stats[f] for f in noms if f not in CONTRE)
    print("composition correction x ITN (anglais) : %d paires  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    print("%-20s %6s %6s %8s" % ("famille", "n", "%", "ecart"))
    sous = []
    for fam, _, _ in FAMILLES:
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        ho = sum(1 for r in par_fam[fam] if r["held_out"])
        print("%-20s %6d %5.1f%% %8d%s"
              % (fam, stats[fam], 100.0 * stats[fam] / max(1, n), ho, marque))
        if stats[fam] < PLANCHER:
            sous.append(fam)
    print("\ntrancher : %d (%.0f %%) | ne rien supprimer : %d (%.0f %%)"
          % (tranche, 100.0 * tranche / max(1, n),
             n - tranche, 100.0 * (n - tranche) / max(1, n)))
    print("tenues a l'ecart : %d (%.1f %%)"
          % (sum(1 for r in rows if r["held_out"]),
             100.0 * sum(1 for r in rows if r["held_out"]) / max(1, n)))
    print("-> %s" % out)
    if sous:
        print("\nATTENTION : famille(s) sous le plancher de %d — elargir les "
              "gabarits ou le vocabulaire : %s" % (PLANCHER, ", ".join(sous)))
        return 1
    print("familles contre-exemple pour valider_paires.py : %s"
          % " ".join(sorted(CONTRE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
