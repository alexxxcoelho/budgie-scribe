# -*- coding: utf-8 -*-
"""Invariants structurels d'un jeu de paires — le filet sous les generateurs.

POURQUOI CE FICHIER EXISTE
`gen_correction.py` tirait son verbe DEUX FOIS, une fois pour le cote sale et
une fois pour le cote propre :

    sale   : il faut faire suivre le dossier non excuse-moi la maquette
    propre : Il faut ENVOYER la maquette.

Des paires qui apprennent litteralement au modele a remplacer les verbes —
c'est-a-dire l'invention, le defaut que tout le projet traque. Rien ne l'a
signale : ni le compte par famille, ni le taux de doublons. C'est la LECTURE
d'un echantillon qui l'a trouve, par hasard.

Un generateur deterministe doit se verifier automatiquement. Les invariants
ci-dessous sont mecaniques, donc ils ne dependent d'aucun juge :

  INVENTION    un mot de contenu present dans `clean` et absent de `dirty`.
               Les nombres sont exemptes : l'ITN les transforme legitimement.
  PERTE        une famille « contre-exemple » doit conserver TOUT le contenu ;
               si elle en perd, elle enseigne l'inverse de son role.
  FORME        `clean` commence par une majuscule et finit par une ponctuation.
  IDENTITE     une paire dont les deux cotes sont identiques au caractere pres
               n'apprend rien, sauf dans les familles contre-exemples ou c'est
               precisement le but (a la ponctuation pres).
  ACCENTS      un jeu de francais sans accents apprend a supprimer les accents.
               Informatif seulement en anglais, qui n'en a pas.

DEUX LANGUES, UNE TABLE PAR LANGUE
Depuis le 2026-09-05 le depot porte un modele par langue. Les invariants sont
les memes ; ce qui change, ce sont les LISTES — hesitations, nombres en lettres,
mots-outils, synonymes de registre, ajouts attendus par famille. Elles sont
declarees par langue dans TABLES, et la langue se lit dans le champ `lang` des
paires (ou `--lang`). Les listes francaises sont inchangees au caractere pres :
le validateur est calibre contre des jeux connus bons, et un jeu francais valide
hier doit l'etre encore aujourd'hui.

Usage : valider_paires.py <paires.jsonl> [--lang fr|en] [prefixe_contre_exemples...]
"""
import collections, json, re, sys, unicodedata

# Jeux dont le cote propre est DERIVE MECANIQUEMENT du cote sale : tout mot
# apparu y est un bug de generateur, donc ELIMINATOIRE. Les autres viennent
# du professeur, qui reecrit legitimement — la, c'est INFORMATIF.
# `coritn` (gen_cor_itn.py) manquait a cette liste pendant la phase francaise :
# ses inventions n'etaient qu'informatives. Ajoute ici ; le jeu francais
# pairs_cor_itn.jsonl passe toujours (verifie le 2026-09-05).
SYNTHETIQUES = ("itn", "correction", "forme", "compo", "coritn")

# Familles dont la sortie est STRUCTUREE : une liste Markdown ne finit pas par
# un point, un e-mail finit par « Cordialement, » / « Thanks,\nJohn ».
STRUCTUREES = {"liste", "email"}

TABLES = {
    "fr": {
        # Ce que chaque famille AJOUTE legitimement, declare par elle et non
        # devine. Cinq calibrages successifs ont montre que l'invariant « aucun
        # mot de `clean` absent de `dirty` » est trop grossier applique
        # globalement : il faut le declarer par famille. Sa valeur reste
        # entiere — c'est lui qui aurait attrape le verbe interverti de
        # gen_correction.py, qui empoisonnait 1 100 paires.
        "ajouts": {
            # la spec exige « une ligne de salutation [...] puis un bloc de signature »
            "email": {"bonjour", "cordialement"},
            # l'introduction d'une liste nomme ce qu'elle enumere
            "liste": {"choses", "points"},
            "liste_en_prose": {"choses", "points"},
            "liste_trop_courte": {"choses", "points"},
            # une adresse dictee se recompose : « double ve » -> « www », etc.
            "url": {"https", "www", "disponible"},
        },
        # Mots-outils : leur presence ou absence ne prouve rien, la
        # normalisation les ajoute et les retire legitimement (« il faut
        # QU'on », « C'EST »...). Les hesitations DISPARAISSENT partout, y
        # compris dans les contre-exemples : c'est la premiere regle de la spec.
        # Les compter comme une perte de contenu produit un faux positif —
        # calibrage verifie sur pairs_itn.jsonl, jeu connu bon, qui en
        # montrait 217.
        "hesitations": set("euh eu heu hum hein bah ben ba be bon voila alors".split()),
        # Les nombres ECRITS EN LETTRES disparaissent legitimement du cote
        # propre : c'est l'ITN qui les remplace par des chiffres. Sans cette
        # liste, `liste_en_prose` remontait 763 faux positifs.
        "nombres_mots": set("""un une deux trois quatre cinq six sept huit neuf dix onze
            douze treize quatorze quinze seize dix-sept dix-huit dix-neuf vingt trente
            quarante cinquante soixante quatre-vingt quatre-vingts cent cents mille
            million millions milliard milliards demi demie premier premiere""".split()),
        # Substitutions de REGISTRE que les generateurs font expres : « trucs »
        # -> « choses » en semi-formal. Sans cette table, `liste_en_prose`
        # remontait 248 faux positifs.
        "synonymes": {"trucs": "choses", "truc": "chose", "bagnole": "voiture",
                      "ouais": "oui", "boulot": "travail", "dispo": "disponible"},
        "outils": set("""a à au aux avec ce cet cette ces c d de des du elle en et eux il ils
            je j l la le les leur lui ma mais me même mes moi mon n ne nos notre nous on ou
            par pas pour qu que qui s sa se ses son sur ta te tes toi ton tu un une vos
            votre vous y est sont était c'est qu'on d'accord le la les de d que qu
            il_y y_a plus moins bien très trop si non oui alors donc car or ni""".split()),
        # Radical grossier : coupe la marque d'accord finale. La spec autorise
        # « accords, homophones et conjugaisons corriges » : « filme » ->
        # « filmee » est une correction attendue, pas une invention.
        "suffixes": ("ees", "ee", "es", "s", "e"),
        "accents": True,
    },
    "en": {
        # le normaliseur de reference, contexte email : « Hey Sarah,\n\nBody\n\nThanks,\nJohn ».
        # La salutation et la signature sont IMPOSEES par la consigne.
        "ajouts": {
            "email": {"hi", "hello", "hey", "dear", "thanks", "thank", "regards",
                      "best", "cheers", "sincerely"},
            "liste": {"things", "points", "items"},
            "liste_en_prose": {"things", "points", "items"},
            "liste_trop_courte": {"things", "points", "items"},
            "url": {"https", "www", "available"},
        },
        # Relevees dans la spec anglaise (spec_en.CORE_RULES). « like » et
        # « well » ne sont hesitations que parfois ; ici on les EXEMPTE
        # (une exemption ne fait que taire un signalement), le piege inverse
        # etant le faux positif massif mesure en francais.
        "hesitations": set("um uh er erm hmm mm mhm hm like well so okay ok right yeah".split()),
        # « am »/« pm » et « www »/« https » y figurent aussi : ce sont des
        # ATOMES DE FORME que l'ITN recompose a partir de lettres dictees une
        # a une (« p m », « double u double u double u ») — des jetons d'une
        # lettre que `mots()` ne voit pas. Sans eux, 352 paires de
        # pairs_compo_en.jsonl (« 11:20pm », « www.x.com ») etaient accusees
        # d'invention alors qu'elles suivent la spec du format au caractere.
        "nombres_mots": set("""zero one two three four five six seven eight nine ten eleven
            twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty
            thirty forty fifty sixty seventy eighty ninety hundred thousand million
            billion half quarter first second third fourth fifth sixth seventh eighth
            ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth
            seventeenth eighteenth nineteenth twentieth thirtieth oh double triple
            point dot am pm www https http""".split()),
        # Familiarites lissees en semi-formal (spec du format : « gonna » ->
        # « going to »). La cle est la forme parlee, la valeur le mot standard
        # que la sortie doit contenir a la place.
        "synonymes": {"gonna": "going", "wanna": "want", "gotta": "got", "kinda": "kind",
                      "sorta": "sort", "yeah": "yes", "yep": "yes", "nope": "no",
                      "stuff": "things", "guys": "people", "cuz": "because",
                      "dunno": "know", "lemme": "let", "gimme": "give"},
        "outils": set("""a an the and or but nor so yet for of to in on at by with from as
            into onto up down off over under about above below between through
            i me my mine you your yours he him his she her hers it its we us our ours
            they them their theirs this that these those who whom whose which what
            is am are was were be been being have has had do does did will would
            shall should can could may might must need dare ought
            not no nor n't dont don't cant can't wont won't isnt isn't
            if then than because since while when where why how there here
            very too quite rather just also only even still already yet
            ll ve re d s m t""".split()),
        # Marques flexionnelles anglaises : pluriel, passe, participe present,
        # 3e personne. « report » -> « reports », « send » -> « sending ».
        "suffixes": ("ing", "ies", "ed", "es", "s"),
        "accents": False,
    },
}


def deaccent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _mots(s, outils):
    """Mots de CONTENU, deaccentues et minuscules, nombres exclus.

    L'APOSTROPHE est normalisee EN PREMIER. Le professeur ecrit l'apostrophe
    typographique (U+2019), l'ASR l'apostrophe ASCII : sans cette etape,
    « l’as filme » se decoupe en « l | as | filme » d'un cote et
    « l | as | filmee » de l'autre, et 325 paires reelles sur 1 200 se
    retrouvaient accusees d'invention. C'est le meme piege que le `fold()`
    qui, en supprimant les apostrophes, avait fait rejeter 47 % des bonnes
    paires : un normaliseur de surface qui ne normalise pas assez condamne
    du travail correct. Le piege vaut dans les deux langues.
    """
    s = deaccent(s.lower().replace("’", "'").replace("ʼ", "'"))
    bruts = re.findall(r"[a-z']+", s)
    return [m.strip("'") for m in bruts
            if m.strip("'") and m.strip("'") not in outils and len(m.strip("'")) > 1]


def _racine(m, suffixes):
    """Radical grossier : coupe la marque d'accord ou de flexion finale."""
    for suf in suffixes:
        if m.endswith(suf) and len(m) - len(suf) >= 3:
            return m[:-len(suf)]
    return m


def chiffres(s):
    return collections.Counter(re.findall(r"\d+", s))


# Interface HISTORIQUE, francaise : `bench_prof.py` importe `mots`, `racine`,
# HESITATIONS, NOMBRES_MOTS, SYNONYMES depuis ce module. Les tables par langue
# ne doivent pas casser cet import — le banc francais est une mesure faite, on
# ne la rejoue pas. Ces noms designent la table francaise, et rien d'autre.
HESITATIONS = TABLES["fr"]["hesitations"]
NOMBRES_MOTS = TABLES["fr"]["nombres_mots"]
SYNONYMES = TABLES["fr"]["synonymes"]
OUTILS = TABLES["fr"]["outils"]
AJOUTS_ATTENDUS = TABLES["fr"]["ajouts"]


def mots(s):
    return _mots(s, OUTILS)


def racine(m):
    return _racine(m, TABLES["fr"]["suffixes"])


def _langue(rows, force):
    if force:
        return force
    langues = collections.Counter(r.get("lang", "fr") for r in rows)
    if len(langues) > 1:
        print("!!! plusieurs langues dans le jeu : %s — passez --lang" % dict(langues))
        sys.exit(2)
    return next(iter(langues)) if langues else "fr"


def main():
    args = [a for a in sys.argv[1:]]
    force = None
    if "--lang" in args:
        i = args.index("--lang")
        force = args[i + 1]
        del args[i:i + 2]
    path = args[0]
    # TOUTES les familles contre-exemple des generateurs. Les oublier fait
    # remonter des milliers de faux « identique » : une famille contre-exemple
    # a precisement pour but de sortir l'entree inchangee. Les generateurs
    # anglais reprennent les MEMES noms de famille que les francais : c'est
    # une regle du chantier, pour que cette liste reste unique.
    contre = set(args[1:]) or {
        # gen_itn.py
        "deja_chiffres", "sans_nombre",
        # gen_correction.py
        "non_reponse", "enfin_discursif", "double_valeur", "plutot_comparatif",
        # gen_forme.py
        "pas_vide", "affirmation", "question_indirecte", "liste_en_prose",
        "liste_trop_courte", "email_en_general", "point_ordinaire",
        # gen_cor_itn.py
        "non_non_correctif", "deux_valeurs",
    }
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    lang = _langue(rows, force)
    if lang not in TABLES:
        print("!!! langue inconnue : %s" % lang)
        sys.exit(2)
    T = TABLES[lang]
    HESITATIONS, NOMBRES_MOTS = T["hesitations"], T["nombres_mots"]
    SYNONYMES, OUTILS, SUFFIXES = T["synonymes"], T["outils"], T["suffixes"]
    AJOUTS_ATTENDUS = T["ajouts"]
    mots = lambda s: _mots(s, OUTILS)
    racine = lambda m: _racine(m, SUFFIXES)

    pb = collections.defaultdict(list)
    mots_apparus = collections.Counter()
    par_fam = collections.Counter()
    accentues = 0
    for r in rows:
        fam = r.get("file", "").split("-", 1)[-1]
        par_fam[fam] += 1
        d, c = r["dirty"], r["clean"]
        if re.search(r"[à-ÿ]", c):
            accentues += 1

        # INVENTION — un mot de contenu apparu de nulle part
        md, mc = set(mots(d)), set(mots(c))
        rd = {racine(x) for x in md}
        attendus = AJOUTS_ATTENDUS.get(fam, set())
        inventes = {x for x in (mc - md) - HESITATIONS - NOMBRES_MOTS - attendus
                    if racine(x) not in rd
                    and not any(SYNONYMES.get(y) == x for y in md)}
        if inventes:
            # ELIMINATOIRE pour le synthetique, ou `clean` est derive
            # mecaniquement de `dirty` : un mot apparu y est forcement un bug
            # de generateur. INFORMATIF pour le reel, ou le professeur reecrit
            # legitimement — normalisation de registre (« ca » -> « cela »,
            # « on peut » -> « nous pouvons », « c'est pas » -> « ce n'est
            # pas ») et mise en page imposee par la consigne : CONTEXT_RULES
            # email exige « une ligne de salutation [...] puis un bloc de
            # signature », d'ou les « Bonjour, » et « Cordialement, » ajoutes.
            cle = "invention" if r.get("source") in SYNTHETIQUES \
                else "reecriture_professeur"
            pb[cle].append((r["id"], fam, sorted(inventes)[:4]))
            for x in inventes:
                mots_apparus[x] += 1

        # FORME — synthetique seulement. Une unite reelle est un morceau
        # d'enregistrement continu : elle commence et finit ou la decoupe l'a
        # laissee, donc minuscule initiale et absence de point final y sont
        # normales. Les gabarits synthetiques, eux, sont sous notre controle.
        synth = r.get("source") in SYNTHETIQUES
        if synth and c[:1].islower():
            pb["minuscule_initiale"].append((r["id"], fam, c[:40]))
        if synth and fam not in STRUCTUREES and c and c[-1] not in ".!?…":
            pb["sans_ponctuation_finale"].append((r["id"], fam, c[-40:]))

        # CONTRE-EXEMPLES : rien ne doit disparaitre
        if fam in contre:
            rc = {racine(x) for x in mc}
            perdus = {x for x in (md - mc) - HESITATIONS - NOMBRES_MOTS
                      if racine(x) not in rc
                      and SYNONYMES.get(x) not in mc}
            if perdus:
                pb["contre_exemple_perd"].append((r["id"], fam, sorted(perdus)[:4]))
            # Le decompte de chiffres ne vaut que si l'entree n'en dicte
            # aucun en lettres : sinon l'ITN cree legitimement un chiffre
            # absent du cote sale.
            if not (set(mots(d)) & NOMBRES_MOTS) and chiffres(d) != chiffres(c):
                pb["contre_exemple_chiffres"].append((r["id"], fam, ""))
        else:
            # une famille « trancher » doit reellement trancher — mais une
            # unite REELLE deja propre peut legitimement sortir inchangee.
            if synth and deaccent(d.lower()).strip(" .") == deaccent(c.lower()).strip(" ."):
                pb["identique"].append((r["id"], fam, c[:40]))

    n = len(rows)
    print("=== %s — %d paires, langue %s ===" % (path, n, lang))
    if T["accents"]:
        print("accents dans le cote propre : %d (%.0f %%)" % (accentues, 100.0 * accentues / n))
    else:
        print("accents dans le cote propre : %d (informatif, langue sans accents)" % accentues)
    print()
    if pb["reecriture_professeur"]:
        print("i  %-26s %5d   (informatif : le professeur reecrit)"
              % ("reecriture_professeur", len(pb["reecriture_professeur"])))
        print("      mots les plus souvent ajoutes : %s"
              % ", ".join("%s x%d" % kv for kv in mots_apparus.most_common(8)))
        print("      a relire si un mot de CONTENU y figure ; les formes de")
        print("      registre et les formules d'e-mail sont attendues.")
        print()
    total = 0
    for cle in ("invention", "contre_exemple_perd", "contre_exemple_chiffres",
                "identique", "minuscule_initiale", "sans_ponctuation_finale"):
        k = len(pb[cle])
        total += k
        etat = "OK " if k == 0 else "PB "
        print("%s %-26s %5d" % (etat, cle, k))
        for ident, fam, det in pb[cle][:3]:
            print("      %-12s [%s] %s" % (ident, fam, det))
    print()
    if total == 0:
        print("aucun defaut structurel — le jeu peut servir a l'entrainement")
    else:
        print("%d defauts : a corriger AVANT d'entrainer" % total)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
