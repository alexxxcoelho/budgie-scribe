# -*- coding: utf-8 -*-
"""Six blocs de mise en forme, ANGLAIS — chaine vide, « ? », faux depart nu,
listes, e-mails, adresses internet. Jumeau de gen_forme.py, meme structure,
meme piege symetrique par bloc ; AUCUN fichier francais n'est touche.

POURQUOI UN FICHIER SEPARE ET NON gen_forme.py PARAMETRE
Un modele par langue (decision du 2026-09-05, voir spec_en.py). Les gabarits,
le lexique et une regle de casse divergent trop pour vivre dans un `if lang` :
l'anglais capitalise TOUJOURS un nom de jour (« Monday »), le francais jamais ;
l'anglais n'accorde rien en genre, ce qui simplifie les objets/adjectifs par
rapport a gen_forme.py. Deux fichiers lisibles valent mieux qu'un fichier a
branches.

CONVENTIONS RELEVEES DANS spec_en.py, PAS INVENTEES
  - PAS d'espace avant « ? » : 0 occurrence contre 79 dans VoxPopuli EN, alors
    que le francais en met (503 contre 21) — c'est l'inverse exact.
  - apostrophe ASCII (U+0027), jamais typographique.
  - e-mail : « Hi Sarah,\\n\\n<corps>\\n\\nThanks,\\nJohn » — salutation ET
    signature VIENNENT du cote sale (contrairement au francais, ou elles sont
    ajoutees) ; ligne de controle en Structure: lists exige AU MOINS trois
    elements, sinon prose meme si la consigne dit `lists`.
  - listes : chaque element commence par une MAJUSCULE (spec_en.STRUCTURE_RULES
    le dit explicitement ; le francais ne le demande pas).

LES CONTRE-EXEMPLES, ENCORE
Meme piege que gen_forme.py, transpose :
  vide          -> `pas_vide` : hesitations AUTOUR d'un vrai contenu
  question      -> `question_indirecte` : « i don't know HOW it works »
                   contient un mot interrogatif et n'est PAS une question
  liste         -> `liste_en_prose` (meme contenu, [Structure: prose]) et
                   `liste_trop_courte` (deux elements : la spec en exige trois)
  email         -> `email_en_general` : meme contenu, [Context: general],
                   donc AUCUNE mise en page d'e-mail ajoutee
  url           -> `point_ordinaire` : « that's a good point », « at noon »
                   (attention : « at noon » n'est jamais une adresse)

UN DETAIL QUI N'EN EST PAS UN : LES JOURS DE LA SEMAINE
Stockes en minuscules partout (comme les autres noms communs), et remis en
majuscule par `fix_days()` sur le SEUL cote propre, en un point unique dans
`main()` — plutot que de recapitaliser a chaque gabarit qui mentionne un jour,
ce qui finirait tot ou tard par en oublier un.

Usage : gen_forme_en.py [n] [sortie.jsonl]
"""
import collections, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260905
PLANCHER = 200

# Hesitations "pures" : servent de prefixe/suffixe autour d'un vrai contenu.
# Un sous-ensemble plus large (FILLERS_VIDE) sert au bruit total du bloc 1 —
# le validateur connait deja "so"/"yeah"/"well" comme hesitations possibles en
# anglais (voir valider_paires.py, table "en"), donc les utiliser ici ne cree
# aucun faux positif.
HESITATIONS = ["um", "uh", "er", "erm", "hmm", "mm", "mhm", "hm"]
FILLERS_VIDE = HESITATIONS + ["well", "so", "okay", "ok", "right", "yeah", "like"]


def ctrl(structure="prose", context="general"):
    """Le registre est fige a semi-formal : l'axe styling est reporte (v2),
    identique a gen_forme.py. Ordre et syntaxe copies de spec_en.control_line."""
    return ("[Styling: semi-formal] [Structure: %s] [Context: %s] [Lang: en]"
            % (structure, context))


# ── Vocabulaire ─────────────────────────────────────────────────────────────
# Jours stockes en minuscules (comme un nom commun ordinaire cote sale) ; le
# cote propre les recapitalise via fix_days(), jamais ici.
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
        "sunday"]
# Prenoms : deja au format attendu cote propre. Utilises en minuscules cote
# sale via .lower() au point d'usage (l'e-mail en depend litteralement — voir
# le contrat : « hey sarah ... thanks john »).
NAMES = ["Sarah", "John", "Emily", "Michael", "Anna", "David", "Laura",
         "James", "Sophie", "Daniel", "Rachel", "Chris", "Emma", "Mark",
         "Julia", "Kevin", "Grace", "Tom", "Olivia", "Ryan"]
CITIES = ["Boston", "Chicago", "Denver", "Austin", "Seattle", "Portland",
          "Miami", "Atlanta", "Dallas", "Phoenix"]

# Pas d'accord de genre en anglais : un seul jeu d'adjectifs, contrairement a
# ADJ_G/GENRE dans gen_forme.py.
OBJECTS = ["the report", "the invoice", "the contract", "the proposal",
           "the budget", "the presentation", "the schedule", "the order",
           "the draft", "the summary", "the mockup", "the brief"]
ADJS = ["ready", "approved", "finished", "signed", "complete", "clear"]

GROCERIES = ["bread", "milk", "butter", "eggs", "cheese", "apples", "coffee",
             "rice", "pasta", "salad", "chicken", "chocolate", "yogurt",
             "sugar", "flour", "tomatoes"]
TASKS = ["review the contract", "send the invoice", "call the client",
         "prepare the meeting", "approve the quote", "fix the mockup",
         "book the room", "follow up with the vendor", "file the documents",
         "update the schedule", "check the accounts", "close the budget",
         "quote the order", "sign the contract", "send it over",
         "call him back", "draft the email", "revise the slides",
         "print the handout", "confirm the venue", "test the software",
         "translate the document", "schedule the call", "renew the license"]
TOPICS = ["the budget", "the schedule", "the meeting", "the hiring",
          "the delivery", "the quote", "the strategy", "the calendar",
          "the pricing", "the maintenance"]

DOMAINS = ["google", "github", "wikipedia", "amazon", "reddit", "dropbox",
           "notion", "anthropic", "spotify", "stackoverflow", "medium",
           "zoom", "microsoft", "apple"]
TLD = [("com", "com"), ("org", "org"), ("net", "net"), ("io", "io"),
       ("dev", "dev"), ("co", "co"), ("edu", "edu")]
PATHS = ["contact", "help", "docs", "blog", "pricing", "account", "search",
         "terms", "api", "download", "about", "faq"]
NUM_PATHS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
SUBS = ["docs", "mail", "support", "blog", "dev", "shop"]

UNITES = {3: "three", 4: "four", 5: "five"}

GREETINGS = ["hi", "hello", "hey", "dear", "good morning"]
SIGNOFFS = ["thanks", "best", "best regards", "cheers", "kind regards",
            "regards"]

DAY_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|"
                     r"sunday)\b")
# Le pronom "I" est TOUJOURS en majuscule en anglais, meme au milieu d'une
# phrase — piege rencontre dans gen_question_indirecte, ou une amorce
# ("actually ", "honestly "...) est concatenee AVANT le gabarit qui commence
# par "i", si bien que maj() (qui ne touche que le tout premier caractere)
# capitalise l'amorce et laisse le "i" original en minuscule au milieu :
# "Actually i don't know ..." — faux depart identique a celui des jours.
# (?!'s) exclut « dot the i's » (point_ordinaire) : c'est la LETTRE i, pas le
# pronom — sans cette exclusion, fix_i() la recapitalise a tort en "I's".
I_RE = re.compile(r"\bi'(m|ll|ve|d)\b|\bi\b(?!'s)")


def maj(s):
    return s[0].upper() + s[1:] if s else s


def fix_days(s):
    """Recapitalise un nom de jour ou qu'il apparaisse dans le texte propre.
    Un jour de la semaine est TOUJOURS en majuscule en anglais, pas seulement
    en debut de phrase — contrairement a maj(), qui ne traite que le premier
    caractere. Applique UNE SEULE FOIS, dans main(), sur chaque cote propre."""
    return DAY_RE.sub(lambda m: m.group(1).capitalize(), s)


def fix_i(s):
    """Recapitalise "i"/"i'm"/"i'll"/"i've"/"i'd" ou qu'ils apparaissent.
    Meme logique que fix_days() : un correctif global, en un seul point,
    plutot qu'une recapitalisation gabarit par gabarit."""
    return I_RE.sub(lambda m: "I'" + m.group(1) if m.group(1) else "I", s)


def bruit(rng, n=None):
    n = n or rng.randint(1, 5)
    return " ".join(rng.choice(HESITATIONS) for _ in range(n))


# ═══ 1. CHAINE VIDE SUR DU BRUIT ═══════════════════════════════════════════

def gen_vide(rng):
    """« um uh hmm er um » -> chaine VIDE.

    Spec (CORE_RULES) : « If the input is nothing but noise or filler, return
    an EMPTY string. That is a valid result, not a failure. »"""
    forme = rng.choice(["hesit", "hesit_ponct", "mot_seul", "souffle"])
    if forme == "hesit":
        d = " ".join(rng.choice(FILLERS_VIDE) for _ in range(rng.randint(1, 6)))
    elif forme == "hesit_ponct":
        d = ", ".join(rng.choice(FILLERS_VIDE) for _ in range(rng.randint(2, 4)))
    elif forme == "mot_seul":
        d = rng.choice(FILLERS_VIDE + ["alright", "yep", "nope", "mkay"])
    else:
        d = "%s... %s..." % (rng.choice(FILLERS_VIDE), rng.choice(FILLERS_VIDE))
    return d, ""


def gen_pas_vide(rng):
    """CONTRE-EXEMPLE : des hesitations AUTOUR d'un vrai contenu.

    Sans cette famille, le modele apprendrait « beaucoup d'hesitations donc
    vide » et effacerait des phrases qui portent du sens."""
    o = rng.choice(OBJECTS)
    corps = rng.choice([
        "we'll meet on %s" % rng.choice(DAYS),
        "we need to %s" % rng.choice(TASKS),
        "%s is handling it" % rng.choice(NAMES),
        "i'm heading to %s on %s" % (rng.choice(CITIES), rng.choice(DAYS)),
        "%s is %s" % (o, rng.choice(ADJS)),
        "we'll talk about it after %s" % rng.choice(TOPICS),
    ])
    d = "%s %s %s" % (bruit(rng, rng.randint(1, 3)), corps,
                       bruit(rng, rng.randint(0, 2)))
    return " ".join(d.split()), maj(corps) + "."


# ═══ 2. POINT D'INTERROGATION ══════════════════════════════════════════════

# Gabarits a une tache (%s = TASKS). Pas d'espace avant « ? » — convention
# inverse du francais, relevee dans VoxPopuli EN (spec_en.py, source 2).
Q_TEMPLATES = [
    ("can you %s", "Can you %s?"),
    ("do we have time to %s", "Do we have time to %s?"),
    ("when are we going to %s", "When are we going to %s?"),
    ("how do we %s", "How do we %s?"),
    ("why do we need to %s", "Why do we need to %s?"),
    ("who has to %s", "Who has to %s?"),
    ("how much does it cost to %s", "How much does it cost to %s?"),
    ("where can we %s", "Where can we %s?"),
    ("what do we need to %s", "What do we need to %s?"),
    ("can you %s before tonight", "Can you %s before tonight?"),
    ("do you think we can %s", "Do you think we can %s?"),
    ("shouldn't we %s first", "Shouldn't we %s first?"),
]
# Interrogatives completes, sans %s — collent aux exemples du contrat.
Q_LITERAL = [
    ("can you tell me what time it is", "Can you tell me what time it is?"),
    ("where do we meet tomorrow", "Where do we meet tomorrow?"),
    ("what time does the meeting start", "What time does the meeting start?"),
    ("do you know where the file is", "Do you know where the file is?"),
    ("can you tell me who's coming", "Can you tell me who's coming?"),
]
# Etat d'un objet (%s = OBJECTS) — « is the invoice ready ».
Q_STATE = [
    ("is %s ready", "Is %s ready?"),
    ("is %s done", "Is %s done?"),
    ("is %s finished", "Is %s finished?"),
]


def gen_question(rng):
    k = rng.random()
    if k < 0.5:
        tpl_d, tpl_c = rng.choice(Q_TEMPLATES)
        v = rng.choice(TASKS)
        d, c = tpl_d % v, tpl_c % v
    elif k < 0.75:
        d, c = rng.choice(Q_LITERAL)
    else:
        tpl_d, tpl_c = rng.choice(Q_STATE)
        o = rng.choice(OBJECTS)
        d, c = tpl_d % o, tpl_c % o
    if rng.random() < 0.3:
        d = "%s %s" % (rng.choice(HESITATIONS), d)
    return d, c


def gen_affirmation(rng):
    """CONTRE-EXEMPLE : une declarative finit par un point, pas un « ? ».
    Inclut aussi des PROPOSITIONS INDEPENDANTES JUXTAPOSEES sans conjonction
    (meme trou du format que point_ordinaire, transpose) : deux clauses, deux
    phrases. Garde aussi les versions a une seule proposition ci-dessous."""
    if rng.random() < 0.2:
        v1, v2 = rng.sample(TASKS, 2)
        c1, c2 = rng.choice([
            ("we can %s" % v1, "we still need to %s" % v2),
            ("%s is %s" % (rng.choice(OBJECTS), rng.choice(ADJS)),
             "we can %s %s" % (v2, rng.choice(DAYS))),
            ("we made good progress on %s" % rng.choice(TOPICS),
             "we still have to %s" % v2),
        ])
        d = "%s %s" % (c1, c2)
        if rng.random() < 0.3:
            d = "%s %s" % (rng.choice(HESITATIONS), d)
        return d, "%s. %s." % (maj(c1), maj(c2))
    corps = rng.choice([
        "we can %s %s" % (rng.choice(TASKS), rng.choice(DAYS)),
        "%s is going to %s" % (rng.choice(NAMES), rng.choice(TASKS)),
        "we need to %s before %s" % (rng.choice(TASKS), rng.choice(DAYS)),
        "i'm going to %s tonight" % rng.choice(TASKS),
        "we're making good progress on %s" % rng.choice(TOPICS),
    ])
    d = corps if rng.random() < 0.7 else "%s %s" % (rng.choice(HESITATIONS), corps)
    return d, maj(corps) + "."


# Meme mots interrogatifs qu'au bloc 2, mais en subordonnee : PAS de « ? ».
IND_TEMPLATES = [
    "i don't know how we %s",
    "i'll let you know when we can %s",
    "we'll have to see who should %s",
    "i wonder how much it costs to %s",
    "we'll see where we can %s",
    "nobody knows why we need to %s",
    "i don't know when we'll %s",
    "she asked whether we could %s",
    "we're still figuring out who will %s",
    "it remains to be seen how we %s",
    "i'm noting what we need to %s",
    "he explained why it's better to %s",
]
AMORCES_IND = ["", "actually ", "honestly ", "by the way "]
LITERAL_IND = [
    "i don't know how it works",
    "tell me when you arrive",
    "she asked whether the report was ready",
    "i don't know what time it is",
    "let me know when you're done",
]


def gen_question_indirecte(rng):
    """CONTRE-EXEMPLE : un mot interrogatif en subordonnee n'est PAS une
    question. « i don't know HOW it works » finit par un point."""
    if rng.random() < 0.35:
        corps = rng.choice(LITERAL_IND)
    else:
        corps = rng.choice(AMORCES_IND) + rng.choice(IND_TEMPLATES) % rng.choice(TASKS)
    return corps, maj(corps) + "."


# ═══ 3. FAUX DEPART SANS MARQUEUR ══════════════════════════════════════════

def gen_faux_depart_nu(rng):
    """« i'll i'll send it » -> « I'll send it. »

    Aucun marqueur de correction : c'est la reprise seule qui signale
    l'abandon."""
    v1, v2 = rng.sample(TASKS, 2)
    j = rng.choice(DAYS)
    d, c = rng.choice([
        ("i'll i'll %s" % v2, "I'll %s." % v2),
        ("we need to we should %s" % v2, "We should %s." % v2),
        ("we can we must %s today" % v2, "We must %s today." % v2),
        ("i'm going to i'll %s tonight" % v2, "I'll %s tonight." % v2),
        ("we need to we need you to %s" % v2, "We need you to %s." % v2),
        ("we said we agreed to %s" % v2, "We agreed to %s." % v2),
        ("i thought i think we should %s" % v2, "I think we should %s." % v2),
        ("we're meeting we're meeting instead on %s" % j,
         "We're meeting instead on %s." % j),
        ("you can you could %s" % v2, "You could %s." % v2),
        ("she has she had promised to %s" % v2, "She had promised to %s." % v2),
        ("we should we'll have to %s before %s" % (v2, j),
         "We'll have to %s before %s." % (v2, j)),
        ("i started to i finished up %s" % v1, "I finished up %s." % v1),
    ])
    return d, c


# ═══ 4. LISTES ═════════════════════════════════════════════════════════════

# Elements "de voyage" : un troisieme bassin lexical nominal, a cote de TASKS
# (verbal) et GROCERIES (courses) — introduit pour le trou du format (« for the
# trip we need sunscreen and then a first aid kit ... »).
TRIP_ITEMS = ["sunscreen", "a first aid kit", "chargers for everything",
              "snacks", "a map", "extra batteries", "bug spray",
              "a rain jacket", "spare socks", "a power bank", "a flashlight",
              "bottled water"]

# Liaisons "parlees" entre elements d'une enumeration dictee : le gabarit
# precedent n'utilisait QUE "and", et seulement devant le dernier element —
# une regularite trop nette (spec du format ; le modele du 2026-09-05 restait
# en prose sur « for the trip we need sunscreen and then a first aid kit and
# um chargers for everything », un cas hors de cette regularite). "" = virgule
# implicite (aucun mot de liaison, juste une pause dictee). Deux jeux :
#   LINKERS_SAFE   -> mots tous dans OUTILS ou HESITATIONS (valider_paires.py,
#                     table "en") : utilisable meme dans un contre-exemple, ou
#                     la regle "aucun contenu perdu" s'applique.
#   LINKERS_RICHE  -> ajoute "plus" et "oh and", absents de OUTILS : les
#                     perdre du cote propre compterait comme une perte de
#                     contenu dans un contre-exemple. Reserve a `gen_liste`
#                     (famille positive, cette regle ne s'y applique pas).
LINKERS_SAFE = ["and then", "and also", "and um", "and then also", "and uh",
                "and", ""]
LINKERS_RICHE = LINKERS_SAFE + ["plus", "oh and"]


def _liste_source(rng):
    """Bassin lexical + nature (verbal ou nominal) qui va avec l'introduction."""
    kind = rng.choice(["tasks", "groceries", "trip"])
    src = {"tasks": TASKS, "groceries": GROCERIES, "trip": TRIP_ITEMS}[kind]
    return kind, src


def _intro_natural(rng, n, kind):
    """Introductions variees d'une enumeration parlee. Le gabarit precedent
    n'ecrivait que « we need N things » : le modele a appris a n'attendre une
    liste que sous cette forme unique, et retombait en prose sur toute autre
    tournure (trou du format du 2026-09-05). Le compte est dicte EN LETTRES ;
    c'est le bloc ITN qui le remet en chiffres, comme partout dans ce fichier.
    Apostrophe gardee identique des deux cotes ("don't"/"there's") : la table
    OUTILS de valider_paires.py connait "dont"/"don't" mais pas "theres" tout
    court, une divergence d'apostrophe y serait accusee a tort d'invention."""
    mot = UNITES[n]
    base = [
        ("%s things to do today" % mot, "%d things to do today:" % n),
        ("don't forget", "Don't forget:"),
    ]
    if kind == "trip":
        base.append(("for the trip we need", "For the trip we need:"))
    elif kind == "groceries":
        base.append(("we still have to buy", "We still have to buy:"))
        base.append(("on the list there's", "On the list there's:"))
    return rng.choice(base)


def _enumere_sale_naturel(rng, items, linkers):
    """Enumeration parlee : liaison variee AVANT chaque element (pas
    seulement "and" devant le dernier), y compris la virgule implicite
    (liaison vide) et une hesitation imbriquee dans la liaison ("and um") —
    exactement la forme du fragment de la spec qui restait en prose."""
    parts = [items[0]]
    for x in items[1:]:
        liaison = rng.choice(linkers)
        parts.append("%s %s" % (liaison, x) if liaison else x)
    return " ".join(parts)


def gen_liste(rng):
    """[Structure: lists] + au moins trois elements -> puces Markdown, chaque
    element avec une MAJUSCULE initiale (spec_en.STRUCTURE_RULES, explicite —
    le francais ne le demande pas). Enumeration NATURELLE : introduction et
    liaisons variees (trou du format du 2026-09-05)."""
    kind, src = _liste_source(rng)
    n = rng.randint(3, 5)
    it = rng.sample(src, n)
    intro_d, intro_c = _intro_natural(rng, n, kind)
    d = "%s %s" % (intro_d, _enumere_sale_naturel(rng, it, LINKERS_RICHE))
    c = intro_c + "\n" + "\n".join("- %s" % maj(x) for x in it)
    return d, c, ctrl(structure="lists")


def gen_liste_en_prose(rng):
    """CONTRE-EXEMPLE : le MEME style d'enumeration (introduction variee,
    liaisons parlees) mais en [Structure: prose] reste en prose, elements en
    minuscule (position non initiale). Liaisons limitees a LINKERS_SAFE — voir
    le commentaire au-dessus de sa definition."""
    kind, src = _liste_source(rng)
    n = rng.randint(3, 5)
    it = rng.sample(src, n)
    intro_d, intro_c = _intro_natural(rng, n, kind)
    d = "%s %s" % (intro_d, _enumere_sale_naturel(rng, it, LINKERS_SAFE))
    c = "%s %s." % (intro_c, ", ".join(it[:-1]) + " and " + it[-1])
    return d, c, ctrl(structure="prose")


def gen_liste_trop_courte(rng):
    """CONTRE-EXEMPLE : deux elements, MEME en [Structure: lists], MEME avec
    une liaison parlee.

    STRUCTURE_RULES est explicite : « it takes AT LEAST THREE items, and
    anything that is not a real enumeration stays as prose. »"""
    kind, src = _liste_source(rng)
    it = rng.sample(src, 2)
    verbe_d, verbe_c = {"tasks": ("we need to", "We need to"),
                         "groceries": ("we need", "We need"),
                         "trip": ("for the trip we need", "For the trip we need")}[kind]
    liaison = rng.choice(LINKERS_SAFE)
    d = "%s %s %s" % (verbe_d, it[0],
                       "%s %s" % (liaison, it[1]) if liaison else it[1])
    c = "%s %s and %s." % (verbe_c, it[0], it[1])
    return d, c, ctrl(structure="lists")


# ═══ 5. E-MAILS ═════════════════════════════════════════════════════════════

def _corps_mail(rng):
    """(dirty, clean) — deux clauses parfois, la seconde une question, comme
    dans le contrat (« ... can you send the numbers by end of week thanks
    john » -> deux phrases cote propre)."""
    o = rng.choice(OBJECTS)
    adj_ = rng.choice(ADJS)
    t = rng.choice(TASKS)
    day = rng.choice(DAYS)
    topic = rng.choice(TOPICS)
    return rng.choice([
        ("just wanted to follow up on %s can you %s" % (topic, t),
         "Just wanted to follow up on %s. Can you %s?" % (topic, t)),
        ("just wanted to let you know that %s is %s can we meet on %s"
         % (o, adj_, day),
         "Just wanted to let you know that %s is %s. Can we meet on %s?"
         % (o, adj_, day)),
        ("just confirming that we're meeting on %s to %s" % (day, t),
         "Just confirming that we're meeting on %s to %s." % (day, t)),
        ("it would be great if you could %s before %s if possible" % (t, day),
         "It would be great if you could %s before %s if possible." % (t, day)),
        ("following up on %s everything looks good on my end" % topic,
         "Following up on %s, everything looks good on my end." % topic),
        ("thanks in advance can you %s by %s" % (t, day),
         "Thanks in advance. Can you %s by %s?" % (t, day)),
    ])


def gen_email(rng):
    """[Context: email] -> salutation, corps, signature, separes par des
    lignes vides. Contrairement au francais, la salutation ET la signature
    VIENNENT du cote sale (« hey sarah ... thanks john »), le cote propre les
    reformate seulement."""
    name = rng.choice(NAMES)
    sender = rng.choice(NAMES)
    greet = rng.choice(GREETINGS)
    signoff = rng.choice(SIGNOFFS)
    body_d, body_c = _corps_mail(rng)
    d = "%s %s %s %s %s" % (greet, name.lower(), body_d, signoff, sender.lower())
    if rng.random() < 0.3:
        d = "%s %s" % (rng.choice(HESITATIONS), d)
    c = "%s %s,\n\n%s\n\n%s,\n%s" % (maj(greet), name, body_c, maj(signoff), sender)
    return d, c, ctrl(context="email")


def gen_email_en_general(rng):
    """CONTRE-EXEMPLE : le MEME contenu en [Context: general] reste une seule
    ligne de prose, sans mise en page d'e-mail — pas de salutation isolee, pas
    de bloc de signature."""
    name = rng.choice(NAMES)
    sender = rng.choice(NAMES)
    greet = rng.choice(GREETINGS)
    signoff = rng.choice(SIGNOFFS)
    body_d, body_c = _corps_mail(rng)
    d = "%s %s %s %s %s" % (greet, name.lower(), body_d, signoff, sender.lower())
    if rng.random() < 0.3:
        d = "%s %s" % (rng.choice(HESITATIONS), d)
    # body_c suit directement une virgule (salutation), pas un point : son
    # premier mot ne doit pas hériter de la majuscule qu'il porte quand il
    # ouvre un nouveau paragraphe dans gen_email. Seule la 2e phrase interne
    # de body_c (apres un point ou un « ? ») garde sa majuscule.
    body_lc = body_c[0].lower() + body_c[1:] if body_c else body_c
    c = "%s %s, %s %s, %s." % (maj(greet), name, body_lc, maj(signoff), sender)
    return d, c, ctrl(context="general")


# ═══ 6. ADRESSES INTERNET ═══════════════════════════════════════════════════

def gen_url(rng):
    """« github dot com slash docs » -> « github.com/docs »."""
    dom = rng.choice(DOMAINS)
    tld_d, tld_c = rng.choice(TLD)
    proto = rng.random() < 0.25
    kind = rng.random()   # 0.30 rien, 0.35 www, 0.35 sous-domaine
    path = rng.random() < 0.4
    num_path = rng.random() < 0.3

    parts_d, parts_c = [], []
    if proto:
        parts_d.append(rng.choice(["h t t p s colon slash slash",
                                   "https colon slash slash"]))
        parts_c.append("https://")
    if kind < 0.30:
        pass
    elif kind < 0.65:
        parts_d.append(rng.choice(["double u double u double u dot",
                                   "w w w dot"]))
        parts_c.append("www.")
    else:
        sub = rng.choice(SUBS)
        parts_d.append("%s dot" % sub)
        parts_c.append("%s." % sub)
    parts_d.append("%s dot %s" % (dom, tld_d))
    parts_c.append("%s.%s" % (dom, tld_c))
    if path:
        if num_path:
            numword = rng.choice(list(NUM_PATHS))
            parts_d.append("slash %s" % numword)
            parts_c.append("/%s" % NUM_PATHS[numword])
        else:
            seg = rng.choice(PATHS)
            parts_d.append("slash %s" % seg)
            parts_c.append("/%s" % seg)

    url_c = "".join(parts_c)
    phrase_d, phrase_c = rng.choice([
        ("go check out %s", "Go check out %s."),
        ("you'll find everything on %s", "You'll find everything on %s."),
        ("the address is %s", "The address is %s."),
        ("take a look at %s for the details", "Take a look at %s for the details."),
        ("it's available on %s", "It's available on %s."),
    ])
    return phrase_d % " ".join(parts_d), phrase_c % url_c


def gen_point_ordinaire(rng):
    """CONTRE-EXEMPLE : « point », « dot » et « at » comme mots ordinaires.
    Attention a « at noon » : « at » sans chiffre autour n'est jamais une
    adresse. Inclut aussi des PROPOSITIONS INDEPENDANTES JUXTAPOSEES sans
    conjonction (trou du format du 2026-09-05) : « let's get to the point we'll
    meet at the station » reste soudee en une seule phrase alors qu'il en faut
    deux — c'est la reprise du sujet suivant, pas un connecteur, qui marque la
    frontiere. Garde aussi les versions a une seule proposition ci-dessous."""
    if rng.random() < 0.3:
        c1, c2 = rng.choice([
            ("let's get to the point", "we'll meet at the station"),
            ("let's get to the point", "the deadline is %s" % rng.choice(DAYS)),
            ("that's a good point", "we should write it down"),
            ("that's a good point", "we should %s" % rng.choice(TASKS)),
            ("we're at the same point as last %s" % rng.choice(DAYS),
             "we should move on"),
            ("there's a point to settle about %s" % rng.choice(TOPICS),
             "let's talk about it tomorrow"),
            ("i have a blocking point on %s" % rng.choice(TOPICS),
             "we need to fix it before %s" % rng.choice(DAYS)),
        ])
        d = "%s %s" % (c1, c2)
        if rng.random() < 0.3:
            d = "%s %s" % (rng.choice(HESITATIONS), d)
        return d, "%s. %s." % (maj(c1), maj(c2))
    corps = rng.choice([
        "i don't share your point of view on %s" % rng.choice(TOPICS),
        "we're at the same point as last %s" % rng.choice(DAYS),
        "there's a point to settle about %s" % rng.choice(TOPICS),
        "that's a good point for %s" % rng.choice(NAMES),
        "let's put that point on the agenda for %s" % rng.choice(DAYS),
        "i have a blocking point on %s" % rng.choice(TOPICS),
        "let's take stock on %s %s" % (rng.choice(TOPICS), rng.choice(DAYS)),
        "at this point we should %s" % rng.choice(TASKS),
        "let's get to the point about %s" % rng.choice(TOPICS),
        "we'll meet at the station at noon on %s" % rng.choice(DAYS),
        "he's always on the dot for %s" % rng.choice(TOPICS),
        "don't forget to dot the i's and cross the t's on %s" % rng.choice(TOPICS),
    ])
    d = corps if rng.random() < 0.7 else "%s %s" % (rng.choice(HESITATIONS), corps)
    return d, maj(corps) + "."


FAMILLES = [
    ("vide", gen_vide, 8),
    ("pas_vide", gen_pas_vide, 8),                      # contre-exemple
    ("question", gen_question, 13),
    ("affirmation", gen_affirmation, 7),                # contre-exemple
    ("question_indirecte", gen_question_indirecte, 7),  # contre-exemple
    ("faux_depart_nu", gen_faux_depart_nu, 10),
    ("liste", gen_liste, 12),
    ("liste_en_prose", gen_liste_en_prose, 7),          # contre-exemple
    ("liste_trop_courte", gen_liste_trop_courte, 5),    # contre-exemple
    ("email", gen_email, 10),
    ("email_en_general", gen_email_en_general, 6),      # contre-exemple
    ("url", gen_url, 12),
    ("point_ordinaire", gen_point_ordinaire, 7),        # contre-exemple
]
CONTRE = {"pas_vide", "affirmation", "question_indirecte", "liste_en_prose",
          "liste_trop_courte", "email_en_general", "point_ordinaire"}


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_forme_en.jsonl")
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
            res = fns[fam](rng)
        except Exception:
            continue
        dirty, clean = res[0], fix_i(fix_days(res[1]))
        control = res[2] if len(res) > 2 else ctrl()
        cle = (dirty, control)
        if cle in seen:
            continue
        seen.add(cle)
        stats[fam] += 1
        rows.append({"id": "frm-en-%05d" % len(rows), "file": "frm-%s" % fam,
                     "source": "forme", "lang": "en", "held_out": False,
                     "styling": "semi-formal",
                     "structure": "lists" if "lists" in control else "prose",
                     "context": "email" if "email" in control else "general",
                     "control": control, "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart PAR FAMILLE, comme gen_forme.py : un decoupage par
    # fichier emporterait des familles entieres, elles n'ont que treize
    # valeurs de `file`.
    par_fam = collections.defaultdict(list)
    for r in rows:
        par_fam[r["file"]].append(r)
    for fam, group in par_fam.items():
        for r in rng.sample(group, max(1, int(len(group) * 0.08))):
            r["held_out"] = True

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(rows)
    pos = sum(stats[k] for k in noms if k not in CONTRE)
    print("paires de mise en forme (EN) : %d  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    print("%-22s %6s %6s" % ("famille", "n", "%"))
    sous = []
    for fam, _, _ in FAMILLES:
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        print("%-22s %6d %5.1f%%%s" % (fam, stats[fam], 100.0 * stats[fam] / max(1, n), marque))
        if stats[fam] < PLANCHER:
            sous.append(fam)
    print("\nregle : %d (%.0f %%) | contre-exemple : %d (%.0f %%)"
          % (pos, 100.0 * pos / max(1, n), n - pos, 100.0 * (n - pos) / max(1, n)))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
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
