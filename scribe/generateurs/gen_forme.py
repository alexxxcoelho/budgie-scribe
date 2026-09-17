# -*- coding: utf-8 -*-
"""Six blocs de mise en forme, generes — chaine vide, « ? », faux depart nu,
listes, e-mails, adresses internet.

CE QUE CE FICHIER CORRIGE
Le bilan du 2026-09-02 a montre un motif net : tout ce qui a un generateur
synthetique est a 100 %, tout ce qui depend du corpus reel est partiel ou
absent. Les six blocs ci-dessous sont dans la spec du format et echouaient tous :

    « euh euh hum bah euh »  -> « Euh hum bah »      la spec exige une chaine VIDE
    « quelle heure il est »  -> « ... il est. »      pas de « ? »
    « je vais je vais pas le faire on va le faire »  ponctue au lieu de trancher
    [Structure: lists]       -> identique a prose    1 seul exemple d'entrainement
    [Context: email]         -> identique a general  10 exemples
    adresses internet        -> jamais rencontrees   0 exemple

CONVENTIONS RELEVEES DANS LE CORPUS, PAS INVENTEES
  - espace AVANT « ? », « ! », « : » : U+0020 ordinaire, 503 occurrences,
    aucune espace fine insecable
  - apostrophe ASCII U+0027 (2 827) et non typographique (342)
  - e-mail : « Bonjour,\\n\\n<corps>\\n\\nCordialement, »
  - listes : « - element », un par ligne. La phrase d'introduction et le
    minimum de trois elements viennent de la SPEC, pas de l'unique paire
    `lists` du corpus, qui ne respecte ni l'un ni l'autre.

LES CONTRE-EXEMPLES, ENCORE
Chaque bloc a son piege symetrique, et c'est la troisieme fois que la regle se
verifie : sans eux, on remplace un biais par un autre.

  vide          -> `pas_vide` : des hesitations AUTOUR d'un vrai contenu ne
                   doivent pas vider la sortie
  question      -> `interrogative_indirecte` : « je sais pas COMMENT on fait »
                   contient un mot interrogatif et n'est PAS une question
  liste         -> `liste_en_prose` (meme contenu, [Structure: prose]) et
                   `liste_trop_courte` (deux elements : la spec en exige trois)
  email         -> `email_en_general` : meme contenu, [Context: general],
                   donc AUCUNE salutation ajoutee
  url           -> `point_ordinaire` : « le point de vue », « a ce point-la »

Usage : gen_forme.py [n] [sortie.jsonl]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260903
HESITATIONS = ["euh", "bah", "ben", "hum", "heu", "hein", "bon"]


def ctrl(structure="prose", context="general"):
    """Le registre est fige a semi-formal : l'axe styling est reporte (v2)."""
    return ("[Styling: semi-formal] [Structure: %s] [Context: %s] [Lang: fr]"
            % (structure, context))


# ── Vocabulaire ─────────────────────────────────────────────────────────────
# ACCENTUE. Un jeu de francais sans accents apprend a supprimer les accents —
# defaut deja rencontre sur gen_correction.py, et corrige la aussi.
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
PRENOMS = ["Marie", "Julie", "Thomas", "Nicolas", "Sophie", "Camille", "Lucas",
           "Emma", "Antoine", "Claire", "Pierre", "Sarah", "Hugo", "Laura",
           "Mathieu", "Inès", "Olivier", "Chloé", "Vincent", "Manon"]
VILLES = ["Lyon", "Marseille", "Nantes", "Rennes", "Bordeaux", "Toulouse",
          "Lille", "Grenoble", "Nice", "Strasbourg", "Montpellier", "Annecy",
          "Dijon", "Reims", "Angers", "Brest"]

# Le GENRE voyage avec le nom, sinon on ecrit « la presentation est pret ».
OBJETS_G = [("le dossier", "m"), ("le devis", "m"), ("le contrat", "m"),
            ("la facture", "f"), ("le rapport", "m"),
            ("la présentation", "f"), ("le planning", "m"),
            ("la commande", "f"), ("la note", "f"), ("le compte rendu", "m"),
            ("la maquette", "f"), ("le brief", "m")]
OBJETS = [o for o, _ in OBJETS_G]
GENRE = dict(OBJETS_G)
ADJ_G = [("prêt", "prête"), ("validé", "validée"),
         ("terminé", "terminée"), ("signé", "signée"),
         ("complet", "complète"), ("clair", "claire")]


def adj(rng, objet):
    m, f = rng.choice(ADJ_G)
    return f if GENRE.get(objet) == "f" else m


# Deux natures distinctes : des NOMS qu'on prend, des VERBES qu'on fait. Les
# melanger produisait « il faut prendre relire le contrat ».
COURSES = ["le pain", "le lait", "le beurre", "les œufs", "le fromage",
           "les pommes", "le café", "le riz", "les pâtes",
           "la salade", "le poulet", "le chocolat", "les yaourts", "le sucre",
           "la farine", "les tomates"]
TACHES = ["relire le contrat", "envoyer la facture", "appeler le client",
          "préparer la réunion", "valider le devis",
          "corriger la maquette", "réserver la salle",
          "relancer le fournisseur", "archiver les dossiers",
          "mettre à jour le planning", "vérifier les comptes",
          "boucler le budget", "chiffrer la commande", "signer le contrat"]
SUJETS = ["le budget", "le planning", "la réunion", "le recrutement",
          "la livraison", "le devis", "la stratégie", "le calendrier",
          "les tarifs", "la maintenance"]
DOMAINES = ["google", "github", "wikipedia", "leboncoin", "ameli", "impots",
            "lemonde", "openstreetmap", "gobudgie", "anthropic", "arte",
            "service-public", "meteofrance", "sncf"]
TLD = [("com", "com"), ("fr", "fr"), ("org", "org"), ("net", "net"),
       ("io", "io"), ("dev", "dev"), ("eu", "eu")]
CHEMINS = ["contact", "aide", "docs", "blog", "tarifs", "compte", "recherche",
           "mentions-legales", "api", "telechargement", "a-propos", "faq"]

UNITES = {3: "trois", 4: "quatre", 5: "cinq"}

MOTS_Q = [
    ("est-ce que tu peux %s", "Est-ce que tu peux %s ?"),
    ("est-ce qu'on a le temps de %s", "Est-ce qu'on a le temps de %s ?"),
    ("quand est-ce qu'on va %s", "Quand est-ce qu'on va %s ?"),
    ("comment on fait pour %s", "Comment on fait pour %s ?"),
    ("pourquoi il faut %s", "Pourquoi il faut %s ?"),
    ("qui doit %s", "Qui doit %s ?"),
    ("combien ça coûte de %s", "Combien ça coûte de %s ?"),
    ("où est-ce qu'on peut %s", "Où est-ce qu'on peut %s ?"),
    ("qu'est-ce qu'il faut pour %s", "Qu'est-ce qu'il faut pour %s ?"),
    ("peux-tu %s avant ce soir", "Peux-tu %s avant ce soir ?"),
    ("tu crois qu'on peut %s", "Tu crois qu'on peut %s ?"),
    ("il faudrait pas %s d'abord", "Il faudrait pas %s d'abord ?"),
]
# Les MEMES mots interrogatifs, mais en subordonnee : PAS de « ? ».
# Douze gabarits x quatorze taches x quatre amorces : c'est la combinatoire,
# et non le poids, qui fixe le plafond d'une famille — lecon de `sans_nombre`
# puis de `non_sec`, rencontree deux fois.
MOTS_Q_INDIRECT = [
    "je ne sais pas comment on fait pour %s",
    "je te dirai quand on pourra %s",
    "il faudra voir qui doit %s",
    "je me demande combien ça coûte de %s",
    "on verra où on peut %s",
    "personne ne sait pourquoi il faut %s",
    "j'ignore quand il faudra %s",
    "elle m'a demandé si on allait %s",
    "on cherche encore qui va %s",
    "reste à savoir comment %s",
    "je note ce qu'il faut pour %s",
    "il m'a expliqué pourquoi il valait mieux %s",
]
AMORCES_IND = ["", "du coup ", "en fait ", "honnêtement "]


def maj(s):
    return s[0].upper() + s[1:] if s else s


def bruit(rng, n=None):
    n = n or rng.randint(1, 5)
    return " ".join(rng.choice(HESITATIONS) for _ in range(n))


# ═══ 1. CHAINE VIDE SUR DU BRUIT ═══════════════════════════════════════════

def gen_vide(rng):
    """« euh euh hum bah euh » -> chaine VIDE.

    Spec : « Si l'entree n'est que du bruit ou du remplissage, renvoie une
    chaine VIDE. C'est un resultat valide, pas un echec. »"""
    forme = rng.choice(["hesit", "hesit_ponct", "mot_seul", "souffle"])
    if forme == "hesit":
        d = bruit(rng, rng.randint(1, 6))
    elif forme == "hesit_ponct":
        d = ", ".join(rng.choice(HESITATIONS) for _ in range(rng.randint(2, 4)))
    elif forme == "mot_seul":
        d = rng.choice(HESITATIONS + ["voilà", "donc", "alors", "ouais", "mmh"])
    else:
        d = "%s... %s..." % (rng.choice(HESITATIONS), rng.choice(HESITATIONS))
    return d, ""


def gen_pas_vide(rng):
    """CONTRE-EXEMPLE : des hesitations AUTOUR d'un vrai contenu.

    Sans cette famille, le modele apprendrait « beaucoup d'hesitations donc
    vide » et effacerait des phrases qui portent du sens."""
    o = rng.choice(OBJETS)
    corps = rng.choice([
        "on se voit %s" % rng.choice(JOURS),
        "il faut %s" % rng.choice(TACHES),
        "%s s'en occupe" % rng.choice(PRENOMS),
        "je pars à %s %s" % (rng.choice(VILLES), rng.choice(JOURS)),
        "%s est %s" % (o, adj(rng, o)),
        "on en reparle après %s" % rng.choice(SUJETS),
    ])
    d = "%s %s %s" % (bruit(rng, rng.randint(1, 3)), corps, bruit(rng, rng.randint(0, 2)))
    return " ".join(d.split()), maj(corps) + "."


# ═══ 2. POINT D'INTERROGATION ══════════════════════════════════════════════

def gen_question(rng):
    """Une interrogative finit par « ? », precede d'une espace ORDINAIRE —
    convention relevee dans le corpus : 378 occurrences contre 21."""
    tpl_d, tpl_c = rng.choice(MOTS_Q)
    v = rng.choice(TACHES)
    d = tpl_d % v
    if rng.random() < 0.3:
        d = "%s %s" % (rng.choice(HESITATIONS), d)
    return d, tpl_c % v


def gen_affirmation(rng):
    """CONTRE-EXEMPLE : une declarative finit par un point."""
    corps = rng.choice([
        "on peut %s %s" % (rng.choice(TACHES), rng.choice(JOURS)),
        "%s va %s" % (rng.choice(PRENOMS), rng.choice(TACHES)),
        "il faut %s avant %s" % (rng.choice(TACHES), rng.choice(JOURS)),
        "je vais %s ce soir" % rng.choice(TACHES),
        "on avance bien sur %s" % rng.choice(SUJETS),
    ])
    d = corps if rng.random() < 0.7 else "%s %s" % (rng.choice(HESITATIONS), corps)
    return d, maj(corps) + "."


def gen_question_indirecte(rng):
    """CONTRE-EXEMPLE : un mot interrogatif en subordonnee n'est PAS une
    question. « je ne sais pas COMMENT on fait » finit par un point."""
    corps = rng.choice(AMORCES_IND) + rng.choice(MOTS_Q_INDIRECT) % rng.choice(TACHES)
    return corps, maj(corps) + "."


# ═══ 3. FAUX DEPART SANS MARQUEUR ══════════════════════════════════════════

def gen_faux_depart_nu(rng):
    """« je vais je vais pas le faire on va le faire » -> « On va le faire. »

    Aucun marqueur de correction : c'est la reprise seule qui signale
    l'abandon. Distinct des familles a marqueur de gen_correction.py."""
    v1, v2 = rng.sample(TACHES, 2)
    j = rng.choice(JOURS)
    d, c = rng.choice([
        ("je vais je vais pas %s on va %s" % (v1, v2), "On va %s." % v2),
        ("il faut il faudrait plutôt %s" % v2, "Il faudrait plutôt %s." % v2),
        ("on peut on doit %s aujourd'hui" % v2, "On doit %s aujourd'hui." % v2),
        ("je te je vais %s ce soir" % v2, "Je vais %s ce soir." % v2),
        ("faut que je faut que tu %s" % v2, "Il faut que tu %s." % v2),
        ("on avait dit on avait convenu de %s" % v2, "On avait convenu de %s." % v2),
        ("j'ai commencé à %s j'ai fini de %s" % (v1, v2), "J'ai fini de %s." % v2),
        ("je pensais je crois qu'il faut %s" % v2, "Je crois qu'il faut %s." % v2),
        ("on se voit on se voit plutôt %s" % j, "On se voit plutôt %s." % j),
        ("tu peux tu pourrais %s" % v2, "Tu pourrais %s." % v2),
        ("elle a elle avait promis de %s" % v2, "Elle avait promis de %s." % v2),
        ("faudrait faudra %s avant %s" % (v2, j), "Il faudra %s avant %s." % (v2, j)),
    ])
    return d, c


# ═══ 4. LISTES ═════════════════════════════════════════════════════════════

def _enumere_sale(items):
    """Le cote sale d'une enumeration dictee : aucune virgule, « et » final."""
    n = len(items)
    return " ".join(("et " if k == n - 1 else "") + x for k, x in enumerate(items))


def _intro(rng, n, verbal):
    """L'introduction s'accorde a la NATURE des elements : on PREND des noms,
    on FAIT des taches. Les melanger donnait « il faut prendre relire le
    contrat ». Le compte est dicte EN LETTRES, comme a l'oral — c'est le bloc
    ITN qui le remet en chiffres."""
    lettre = UNITES[n]
    if verbal:
        return rng.choice([
            ("on doit faire %s choses" % lettre, "On doit faire %d choses :" % n),
            ("il y a %s points à voir" % lettre, "Il y a %d points à voir :" % n),
            ("il reste %s trucs à faire" % lettre, "Il reste %d choses à faire :" % n),
        ])
    return rng.choice([
        ("faut prendre %s choses" % lettre, "Il faut prendre %d choses :" % n),
        ("il nous faut %s trucs" % lettre, "Il nous faut %d choses :" % n),
        ("j'ai besoin de %s choses" % lettre, "J'ai besoin de %d choses :" % n),
    ])


def gen_liste(rng):
    """[Structure: lists] + au moins trois elements -> puces Markdown."""
    verbal = rng.random() < 0.5
    src = TACHES if verbal else COURSES
    n = rng.randint(3, 5)
    it = rng.sample(src, n)
    intro_d, intro_c = _intro(rng, n, verbal)
    d = "%s %s" % (intro_d, _enumere_sale(it))
    c = intro_c + "\n" + "\n".join("- %s" % x for x in it)
    return d, c, ctrl(structure="lists")


def gen_liste_en_prose(rng):
    """CONTRE-EXEMPLE : le MEME contenu en [Structure: prose] reste en prose.

    Sans lui, le modele mettrait des puces des qu'il voit une enumeration,
    quelle que soit la consigne."""
    verbal = rng.random() < 0.5
    src = TACHES if verbal else COURSES
    n = rng.randint(3, 5)
    it = rng.sample(src, n)
    intro_d, intro_c = _intro(rng, n, verbal)
    d = "%s %s" % (intro_d, _enumere_sale(it))
    c = "%s %s." % (intro_c, ", ".join(it[:-1]) + " et " + it[-1])
    return d, c, ctrl(structure="prose")


def gen_liste_trop_courte(rng):
    """CONTRE-EXEMPLE : deux elements, MEME en [Structure: lists].

    La spec est explicite : « il faut AU MOINS TROIS elements, et ce qui n'est
    pas une vraie enumeration reste en prose »."""
    verbal = rng.random() < 0.5
    it = rng.sample(TACHES if verbal else COURSES, 2)
    verbe_d, verbe_c = ("on doit", "On doit") if verbal else ("faut prendre", "Il faut prendre")
    d = "%s %s et %s" % (verbe_d, it[0], it[1])
    c = "%s %s et %s." % (verbe_c, it[0], it[1])
    return d, c, ctrl(structure="lists")


# ═══ 5. E-MAILS ════════════════════════════════════════════════════════════

def _corps_mail(rng):
    o = rng.choice(OBJETS)
    return rng.choice([
        "je voulais te dire que %s est %s on peut se voir %s"
        % (o, adj(rng, o), rng.choice(JOURS)),
        "je te confirme qu'on se retrouve %s pour %s"
        % (rng.choice(JOURS), rng.choice(TACHES)),
        "il faudrait %s avant %s si c'est possible"
        % (rng.choice(TACHES), rng.choice(JOURS)),
        "je reviens vers toi au sujet de %s c'est bon de mon côté"
        % rng.choice(SUJETS),
        "merci d'avance pour %s je reste dispo %s"
        % (rng.choice(TACHES), rng.choice(JOURS)),
    ])


def gen_email(rng):
    """[Context: email] -> salutation, corps, signature, separes par des lignes
    vides. Convention relevee dans le corpus, pas inventee."""
    corps = _corps_mail(rng)
    d = corps if rng.random() < 0.6 else "%s %s" % (rng.choice(HESITATIONS), corps)
    return d, "Bonjour,\n\n%s.\n\nCordialement," % maj(corps), ctrl(context="email")


def gen_email_en_general(rng):
    """CONTRE-EXEMPLE : le MEME contenu en [Context: general] n'a NI salutation
    NI signature. Sans lui, le modele signerait tout."""
    corps = _corps_mail(rng)
    d = corps if rng.random() < 0.6 else "%s %s" % (rng.choice(HESITATIONS), corps)
    return d, maj(corps) + ".", ctrl(context="general")


# ═══ 6. ADRESSES INTERNET ══════════════════════════════════════════════════

def gen_url(rng):
    """« github point com slash docs » -> « github.com/docs »"""
    dom = rng.choice(DOMAINES)
    tld_d, tld_c = rng.choice(TLD)
    www = rng.random() < 0.35
    proto = rng.random() < 0.2
    chemin = rng.random() < 0.4

    parts_d, parts_c = [], []
    if proto:
        parts_d.append(rng.choice(["h t t p s deux points slash slash",
                                   "https deux points slash slash"]))
        parts_c.append("https://")
    if www:
        parts_d.append(rng.choice(["double vé double vé double vé point",
                                   "trois double vé point", "w w w point"]))
        parts_c.append("www.")
    parts_d.append("%s point %s" % (dom.replace("-", " tiret "), tld_d))
    parts_c.append("%s.%s" % (dom, tld_c))
    if chemin:
        seg = rng.choice(CHEMINS)
        parts_d.append("slash %s" % seg.replace("-", " tiret "))
        parts_c.append("/%s" % seg)

    url_c = "".join(parts_c)
    phrase_d, phrase_c = rng.choice([
        ("va voir sur %s", "Va voir sur %s."),
        ("tu trouveras tout sur %s", "Tu trouveras tout sur %s."),
        ("l'adresse c'est %s", "L'adresse est %s."),
        ("regarde %s pour les détails", "Regarde %s pour les détails."),
        ("c'est dispo sur %s", "C'est disponible sur %s."),
    ])
    return phrase_d % " ".join(parts_d), phrase_c % url_c


def gen_point_ordinaire(rng):
    """CONTRE-EXEMPLE : « point » comme mot ordinaire.

    Sans lui, le modele collerait un nom de domaine des qu'il lit « point »."""
    corps = rng.choice([
        "je ne partage pas ton point de vue sur %s" % rng.choice(SUJETS),
        "on en est au même point qu'%s dernier" % rng.choice(JOURS),
        "il y a un point à régler sur %s" % rng.choice(SUJETS),
        "c'est un bon point pour %s" % rng.choice(PRENOMS),
        "mettons ce point à l'ordre du jour de %s" % rng.choice(JOURS),
        "j'ai un point de blocage sur %s" % rng.choice(SUJETS),
        "on fait le point sur %s %s" % (rng.choice(SUJETS), rng.choice(JOURS)),
        "à ce point-là il vaut mieux %s" % rng.choice(TACHES),
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
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_forme.jsonl")
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
        dirty, clean = res[0], res[1]
        control = res[2] if len(res) > 2 else ctrl()
        cle = (dirty, control)
        if cle in seen:
            continue
        seen.add(cle)
        stats[fam] += 1
        rows.append({"id": "frm-%05d" % len(rows), "file": "frm-%s" % fam,
                     "source": "forme", "lang": "fr", "held_out": False,
                     "styling": "semi-formal",
                     "structure": "lists" if "lists" in control else "prose",
                     "context": "email" if "email" in control else "general",
                     "control": control, "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart PAR FAMILLE : un decoupage par fichier emporterait
    # des familles entieres, elles n'ont que treize valeurs de `file`.
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
    print("paires de mise en forme : %d  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    print("%-22s %6s %6s" % ("famille", "n", "%"))
    for fam, _, _ in FAMILLES:
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        print("%-22s %6d %5.1f%%%s" % (fam, stats[fam], 100.0 * stats[fam] / max(1, n), marque))
    print("\nregle : %d (%.0f %%) | contre-exemple : %d (%.0f %%)"
          % (pos, 100.0 * pos / max(1, n), n - pos, 100.0 * (n - pos) / max(1, n)))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
