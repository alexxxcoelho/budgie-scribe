# -*- coding: utf-8 -*-
"""Auto-corrections du locuteur — generateur deterministe.

LE PROBLEME
La spec du format demande de « trancher les auto-corrections en gardant la valeur
retenue par le locuteur » (spec.py:132). Le modele ne le fait pas :

    SALE    ... vendredi non pardon jeudi on a rendez-vous ...
    ATTENDU ... jeudi, on a rendez-vous ...
    OBTENU  ... vendredi, non pardon, jeudi, on a rendez-vous ...

Il ponctue l'hesitation au lieu de la resoudre. La cause n'est pas la taille du
modele : le recensement (§0.8) compte 13 auto-corrections dans TOUT le corpus,
soit 0,16 pour 1 000 mots. L'ITN, lui, est passe de 10 % a 100 % avec 9 203
exemples synthetiques. Meme cause, meme remede.

LE PIEGE, ET POURQUOI LES CONTRE-EXEMPLES PESENT 40 %
« non », « enfin » et « plutôt » sont, en francais parle, bien plus souvent des
marqueurs de discours que des marqueurs de correction :

    « non, c'est vrai que... »      -> « non » repond, il ne corrige rien
    « enfin bref, on verra »        -> « enfin » ponctue, il ne corrige rien
    « c'est plutôt cher »           -> « plutôt » compare, il ne corrige rien
    « jeudi et vendredi »           -> deux valeurs, toutes deux gardees

Un modele entraine uniquement sur des corrections apprendrait « supprime ce qui
precede non/enfin/plutôt » et couperait du contenu valide. C'est exactement le
biais que les familles `deja_chiffres` et `sans_nombre` ont evite pour l'ITN :
« sans les deux derniers blocs, on remplacerait un biais par un autre ».

Usage : gen_correction.py [n] [sortie.jsonl]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260902
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]"
HESITATIONS = ["euh ", "bah ", "ben ", "alors euh ", "hum ", ""]

try:
    from num2words import num2words
except ImportError:                                      # pragma: no cover
    num2words = None

# ── Vocabulaire, pour la variete combinatoire ───────────────────────────────
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
PRENOMS = ["Marie", "Julie", "Thomas", "Nicolas", "Sophie", "Camille", "Lucas",
           "Emma", "Antoine", "Claire", "Pierre", "Sarah", "Hugo", "Laura",
           "Mathieu", "Inès", "Olivier", "Chloé", "Vincent", "Manon"]
VILLES = ["Lyon", "Villeurbanne", "Marseille", "Aix", "Nantes", "Rennes",
          "Bordeaux", "Toulouse", "Lille", "Grenoble", "Nice", "Strasbourg",
          "Montpellier", "Annecy", "Dijon", "Reims"]
LIEUX = ["au bureau", "à la maison", "au restaurant", "chez toi", "chez moi",
         "à l'agence", "en salle deux", "au premier étage", "à la gare",
         "dans le hall", "au café d'en bas", "en visio"]

# Le GENRE voyage avec le nom : sans lui on ecrit « la maquette est plutôt
# cher », et 6 000 paires de francais fautif apprennent le francais fautif.
OBJETS_G = [("le dossier", "m"), ("le devis", "m"), ("le contrat", "m"),
            ("la facture", "f"), ("le rapport", "m"),
            ("la présentation", "f"), ("le compte rendu", "m"),
            ("la maquette", "f"), ("le planning", "m"), ("la commande", "f"),
            ("le brief", "m"), ("la note", "f")]
OBJETS = [o for o, _ in OBJETS_G]
GENRE = dict(OBJETS_G)

VERBES_ENVOI = ["envoyer", "transmettre", "faire suivre", "renvoyer", "partager"]

# (masculin, feminin). Les adverbes « tot »/« tard » ont ete retires : ce ne
# sont pas des adjectifs, ils ne s'accordent pas et faussaient les gabarits.
ADJ_G = [("cher", "chère"), ("long", "longue"),
         ("compliqué", "compliquée"), ("urgent", "urgente"),
         ("clair", "claire"), ("lourd", "lourde"), ("simple", "simple"),
         ("rapide", "rapide"), ("prêt", "prête"),
         ("complet", "complète")]


def adj(rng, objet):
    """L'adjectif accorde avec l'objet passe."""
    m, f = rng.choice(ADJ_G)
    return f if GENRE.get(objet) == "f" else m


DEBUTS = ["je te confirme que", "je pense que", "on avait dit que",
          "il me semble que", "j'ai noté que", "on s'était dit que",
          "je te disais que", "de mémoire"]

# ── Marqueurs de correction, par famille ────────────────────────────────────
M_PARDON = ["non pardon", "pardon", "non pardon non", "excuse-moi", "non excuse-moi"]
M_ENFIN = ["enfin", "enfin non", "enfin plutôt"]
M_PLUTOT = ["ou plutôt", "ou alors plutôt", "plutôt"]
M_VEUX_DIRE = ["je veux dire", "enfin je veux dire", "je voulais dire",
               "c'est-à-dire"]
M_NON_SEC = ["non", "non non"]


def maj(s):
    return s[0].upper() + s[1:] if s else s


def _remplace(rng, liste, sauf):
    """Un element different de `sauf` — sinon la correction ne corrige rien."""
    autres = [x for x in liste if x != sauf]
    return rng.choice(autres)


# ═══ FAMILLES DE CORRECTION : le modele doit TRANCHER ══════════════════════

def gen_pardon(rng):
    """« vendredi non pardon jeudi » -> « jeudi »"""
    forme = rng.choice(["jour", "prenom", "ville", "lieu", "objet"])
    m = rng.choice(M_PARDON)
    debut = rng.choice(DEBUTS)
    if forme == "jour":
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        d = "%s on se voit %s %s %s" % (debut, a, m, b)
        c = "%s on se voit %s." % (maj(debut), b)
    elif forme == "prenom":
        a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
        d = "%s c'est %s qui s'en occupe %s %s" % (debut, a, m, b)
        c = "%s c'est %s qui s'en occupe." % (maj(debut), b)
    elif forme == "ville":
        a = rng.choice(VILLES); b = _remplace(rng, VILLES, a)
        d = "la réunion est à %s %s a %s" % (a, m, b)
        c = "La réunion est à %s." % b
    elif forme == "lieu":
        a = rng.choice(LIEUX); b = _remplace(rng, LIEUX, a)
        d = "on se retrouve %s %s %s" % (a, m, b)
        c = "On se retrouve %s." % b
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        # UN SEUL tirage, reutilise des deux cotes. Tirer deux fois faisait
        # changer le verbe entre l'entree et la sortie — des paires qui
        # apprennent litteralement au modele a remplacer les verbes.
        v = rng.choice(VERBES_ENVOI)
        d = "il faut %s %s %s %s" % (v, a, m, b)
        c = "Il faut %s %s." % (v, b)
    return d, c


def gen_enfin(rng):
    """« a Lyon enfin a Villeurbanne » -> « a Villeurbanne »"""
    m = rng.choice(M_ENFIN)
    if rng.random() < 0.5:
        a = rng.choice(VILLES); b = _remplace(rng, VILLES, a)
        d = "c'est à %s %s à %s" % (a, m, b)
        c = "C'est à %s." % b
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        d = "j'ai relu %s %s %s" % (a, m, b)
        c = "J'ai relu %s." % b
    return d, c


def gen_plutot(rng):
    """« mardi ou plutôt mercredi » -> « mercredi »"""
    m = rng.choice(M_PLUTOT)
    if rng.random() < 0.5:
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        d = "on cale ça %s %s %s" % (a, m, b)
        c = "On cale ça %s." % b
    else:
        a = rng.choice(LIEUX); b = _remplace(rng, LIEUX, a)
        d = "je te propose %s %s %s" % (a, m, b)
        c = "Je te propose %s." % b
    return d, c


def gen_veux_dire(rng):
    """« Marie je veux dire Julie » -> « Julie »"""
    m = rng.choice(M_VEUX_DIRE)
    a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
    tpl = rng.choice([
        ("il faut prévenir %s %s %s", "Il faut prévenir %s."),
        ("c'est %s qui a le dossier %s %s", "C'est %s qui a le dossier."),
        ("j'en ai parlé à %s %s %s", "J'en ai parlé à %s."),
    ])
    return tpl[0] % (a, m, b), tpl[1] % b


def gen_non_sec(rng):
    """« a dix heures non a onze heures » -> « a 11h »"""
    m = rng.choice(M_NON_SEC)
    forme = rng.choice(["heure", "jour", "lieu", "prenom", "objet"])
    if forme == "heure" and num2words:
        ha = rng.randint(8, 19); hb = _remplace(rng, list(range(8, 20)), ha)
        mn = rng.choice([0, 0, 15, 30, 45])
        d = "le rendez-vous est à %s heures %s a %s heures%s" % (
            num2words(ha, lang="fr"), m, num2words(hb, lang="fr"),
            "" if not mn else " " + num2words(mn, lang="fr"))
        c = "Le rendez-vous est à %dh%s." % (hb, "" if not mn else "%02d" % mn)
    elif forme == "jour":
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        v = rng.choice(["je passe", "on livre", "je rappelle", "il arrive",
                        "on demarre", "je rends %s" % rng.choice(OBJETS)])
        d = "%s %s %s %s" % (v, a, m, b); c = "%s %s." % (maj(v), b)
    elif forme == "lieu":
        a = rng.choice(LIEUX); b = _remplace(rng, LIEUX, a)
        d = "c'est %s %s %s" % (a, m, b); c = "C'est %s." % b
    elif forme == "prenom":
        a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
        d = "demande à %s %s à %s" % (a, m, b); c = "Demande à %s." % b
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        d = "il me faut %s %s %s" % (a, m, b); c = "Il me faut %s." % b
    return d, c


def gen_nombre(rng):
    """« trois cents non trois cent cinquante euros » -> « 350 euros »

    Cette famille fait travailler DEUX competences a la fois : trancher la
    correction et normaliser le nombre. Elle renforce l'ITN au lieu de lui
    faire concurrence."""
    if not num2words:
        raise RuntimeError("num2words requis")
    m = rng.choice(M_NON_SEC + M_PARDON[:2])
    forme = rng.choice(["montant", "quantite", "pourcent"])
    if forme == "montant":
        a = rng.choice([100, 150, 200, 250, 300, 500, 800, 1200, 1500, 2000])
        b = a + rng.choice([50, 100, 150, 200, 500])
        d = "le devis est à %s euros %s %s euros" % (
            num2words(a, lang="fr"), m, num2words(b, lang="fr"))
        c = "Le devis est à %s euros." % ("{:,}".format(b).replace(",", " "))
    elif forme == "quantite":
        a = rng.randint(2, 40); b = _remplace(rng, [x for x in range(2, 41)], a)
        d = "il en faut %s %s %s" % (num2words(a, lang="fr"), m,
                                     num2words(b, lang="fr"))
        c = "Il en faut %d." % b
    else:
        a = rng.choice([10, 15, 20, 25, 30, 40, 50])
        b = _remplace(rng, [10, 15, 20, 25, 30, 40, 50, 60, 70], a)
        d = "on est à %s pour cent %s %s pour cent" % (
            num2words(a, lang="fr"), m, num2words(b, lang="fr"))
        c = "On est à %d %%." % b
    return d, c


# Verbes transitifs, pour composer des groupes verbaux varies : c'est la
# combinatoire, pas le poids, qui fixe le nombre de paires distinctes qu'une
# famille peut produire. VERBES x OBJETS x gabarits = quelques milliers.
VERBES_ACTION = ["relire", "valider", "boucler", "reprendre", "corriger",
                 "envoyer", "chiffrer", "classer", "signer", "archiver",
                 "revoir", "préparer"]


def gen_faux_depart(rng):
    """« je vais... on va y aller » -> « on va y aller »

    Pas de marqueur : c'est la reprise seule qui signale l'abandon. Le modele
    doit couper l'amorce, pas la ponctuer."""
    v = "%s %s" % (rng.choice(VERBES_ACTION), rng.choice(OBJETS))
    tpl = rng.choice([
        ("je vais je vais pas %s on va le faire", "On va le faire."),
        ("il faudrait qu'on qu'on puisse %s", "Il faudrait qu'on puisse %s."),
        ("on pourrait on devrait plutôt %s", "On devrait plutôt %s."),
        ("je te je t'envoie de quoi %s", "Je t'envoie de quoi %s."),
        ("faut que je faut qu'on puisse %s", "Il faut qu'on puisse %s."),
        ("j'ai commencé à j'ai fini de %s", "J'ai fini de %s."),
        ("on avait on s'était dit de %s", "On s'était dit de %s."),
    ])
    if tpl[0].count("%s") == 0:
        return tpl[0], tpl[1]
    return tpl[0] % v, tpl[1] % v


# ═══ CONTRE-EXEMPLES : le modele ne doit RIEN supprimer ════════════════════

def gen_non_reponse(rng):
    """« non c'est vrai que ... » — « non » repond, il ne corrige pas."""
    # La combinatoire, pas le poids, fixe le plafond d'une famille : cinq
    # phrases figees plafonnaient a 129 paires. Ici chaque gabarit tire ses
    # propres fentes, ce qui multiplie les variantes par plusieurs centaines.
    _o1 = rng.choice(OBJETS)
    _o2 = rng.choice(OBJETS)
    suite = rng.choice([
        "c'est vrai que %s est un peu %s" % (_o1, adj(rng, _o1)),
        "je ne crois pas que ce soit possible %s" % rng.choice(LIEUX),
        "on n'a pas encore reçu %s" % rng.choice(OBJETS),
        "ce n'est pas ce qu'on avait dit %s" % rng.choice(JOURS),
        "je préfère qu'on en reparle %s" % rng.choice(JOURS),
        "%s n'est pas encore %s" % (_o2, adj(rng, _o2)),
        "on ne sera pas %s %s" % (rng.choice(LIEUX), rng.choice(JOURS)),
        "je n'ai pas eu %s de %s" % (rng.choice(OBJETS), rng.choice(PRENOMS)),
        "ce n'est pas %s qui s'en occupe" % rng.choice(PRENOMS),
        "on ne peut pas %s %s avant %s" % (rng.choice(VERBES_ACTION),
                                           rng.choice(OBJETS), rng.choice(JOURS)),
        "%s ne veut pas %s %s" % (rng.choice(PRENOMS), rng.choice(VERBES_ACTION),
                                  rng.choice(OBJETS)),
        "je ne serai pas a %s %s" % (rng.choice(VILLES), rng.choice(JOURS)),
    ])
    d = "non %s" % suite
    c = "Non, %s." % suite
    return d, c


def gen_enfin_discursif(rng):
    """« enfin bref », « enfin voila » — ponctuation, pas correction."""
    forme = rng.choice(["bref", "voila", "tu vois", "quoi"])
    corps = rng.choice([
        "on verra %s" % rng.choice(JOURS),
        "%s est presque pret" % rng.choice(OBJETS),
        "il faut avancer sur %s" % rng.choice(OBJETS),
        "on se retrouve %s" % rng.choice(LIEUX),
    ])
    if rng.random() < 0.5:
        d, c = "%s enfin %s" % (corps, forme), "%s, enfin %s." % (maj(corps), forme)
    else:
        d, c = "enfin %s %s" % (forme, corps), "Enfin %s, %s." % (forme, corps)
    return d, c


def gen_double_valeur(rng):
    """« jeudi et vendredi » — deux valeurs legitimes, toutes deux gardees."""
    forme = rng.choice(["jours", "prenoms", "villes", "objets"])
    if forme == "jours":
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        d = "je suis dispo %s et %s" % (a, b); c = "Je suis dispo %s et %s." % (a, b)
    elif forme == "prenoms":
        a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
        d = "c'est %s et %s qui s'en occupent" % (a, b)
        c = "C'est %s et %s qui s'en occupent." % (a, b)
    elif forme == "villes":
        a = rng.choice(VILLES); b = _remplace(rng, VILLES, a)
        d = "on a des bureaux a %s et a %s" % (a, b)
        c = "On a des bureaux a %s et a %s." % (a, b)
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        d = "il me faut %s et %s" % (a, b); c = "Il me faut %s et %s." % (a, b)
    return d, c


def gen_plutot_comparatif(rng):
    """« c'est plutôt cher » — « plutôt » compare, il ne corrige pas."""
    _o = rng.choice(OBJETS)
    a = adj(rng, _o)
    corps = rng.choice([
        "%s est plutôt %s" % (_o, a),
        "je suis plutôt %s pour %s" % (rng.choice(["d'accord", "réservé", "favorable"]),
                                       rng.choice(OBJETS)),
        "c'est plutôt %s comme solution" % a,
        "on est plutôt %s sur le planning" % rng.choice(["en avance", "en retard",
                                                         "dans les temps"]),
        "%s est plutôt du genre à %s %s" % (rng.choice(PRENOMS),
                                            rng.choice(VERBES_ACTION),
                                            rng.choice(OBJETS)),
        "je passerais plutôt %s qu'à %s" % (rng.choice(LIEUX), rng.choice(LIEUX)),
        "%s serait plutôt dispo %s" % (rng.choice(PRENOMS), rng.choice(JOURS)),
        "on ira plutôt à %s qu'à %s" % (rng.choice(VILLES), rng.choice(VILLES)),
        "%s me paraît plutôt %s" % (rng.choice(OBJETS), a),
        "il vaut plutôt %s %s %s" % (rng.choice(VERBES_ACTION), rng.choice(OBJETS),
                                     rng.choice(JOURS)),
    ])
    return corps, maj(corps) + "."


FAMILLES = [
    # trancher
    ("pardon", gen_pardon, 15),
    ("enfin", gen_enfin, 11),
    ("plutot", gen_plutot, 9),
    ("veux_dire", gen_veux_dire, 8),
    ("non_sec", gen_non_sec, 10),
    ("nombre", gen_nombre, 12),
    ("faux_depart", gen_faux_depart, 8),
    # ne rien supprimer — 27 % du jeu, et c'est deliberé
    ("non_reponse", gen_non_reponse, 13),
    ("enfin_discursif", gen_enfin_discursif, 7),
    ("double_valeur", gen_double_valeur, 7),
    ("plutot_comparatif", gen_plutot_comparatif, 8),
]


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_correction.jsonl")
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
        # Le cote sale doit ressembler a de l'ASR : une hesitation de temps en
        # temps, qui disparait en sortie comme partout ailleurs.
        if rng.random() < 0.20:
            h = rng.choice(HESITATIONS)
            if h:
                dirty = h + dirty
        stats[fam] += 1
        rows.append({"id": "cor-%05d" % len(rows), "file": "cor-%s" % fam,
                     "source": "correction", "lang": "fr", "held_out": False,
                     "styling": "semi-formal", "structure": "prose",
                     "context": "general", "control": CONTROL,
                     "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart PAR FAMILLE. Un decoupage par fichier emporterait des
    # familles entieres : elles n'ont que onze valeurs de `file` distinctes.
    par_fam = collections.defaultdict(list)
    for r in rows:
        par_fam[r["file"]].append(r)
    for fam, group in par_fam.items():
        for r in rng.sample(group, max(1, int(len(group) * 0.08))):
            r["held_out"] = True

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tranche = sum(stats[n] for n, _, _ in FAMILLES[:7])
    print("paires d'auto-correction : %d  (%d tentatives, %d doublons ecartes)"
          % (len(rows), tries, tries - len(rows)))
    print("%-20s %6s %6s" % ("famille", "n", "%"))
    for fam, _, _ in FAMILLES:
        marque = "" if fam in [f[0] for f in FAMILLES[:7]] else "   <- contre-exemple"
        print("%-20s %6d %5.1f%%%s" % (fam, stats[fam],
                                       100.0 * stats[fam] / max(1, len(rows)), marque))
    print("\ntrancher : %d (%.0f %%) | ne rien supprimer : %d (%.0f %%)"
          % (tranche, 100.0 * tranche / max(1, len(rows)),
             len(rows) - tranche, 100.0 * (len(rows) - tranche) / max(1, len(rows))))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
