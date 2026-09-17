# -*- coding: utf-8 -*-
"""Garde-fous d'inference — jalon M4 des notes d'entrainement.

    « Ces trois controles sont ecrits en M4 et LIVRES AVEC LE MODELE, pas
      apres. »                                        (notes d'entrainement, jalon M4)

Ils s'appliquent au couple (entree, sortie) AU MOMENT DE L'INFERENCE, et non a
un corpus : ce sont les seules verifications qui tournent quand plus aucun
humain ne lit. La regle du projet vaut ici comme ailleurs — LE FILTRE TRIE, LA
LECTURE TRANCHE (notes d'entrainement §0.15) : une faute levee ici est un candidat a la
relecture ou au repli sur l'entree, jamais un verdict.

LES QUATRE CONTROLES, ET CE QUE CHACUN ATTRAPE QUE LES AUTRES NE VOIENT PAS

  1. DIFF entree/sortie          -> `invention`, `boucle`
     Un mot de CONTENU present en sortie et absent de l'entree est une
     invention. Le meme passage attrape la boucle degeneree : un bloc de
     tokens repete, signature du decodage glouton (notes d'entrainement §0.16).

  2. COUVERTURE PAR PHRASE       -> `suppression`
     Le diff est aveugle a la suppression silencieuse, puisque TOUS les mots
     de sortie existent en entree. On verifie donc que chaque proposition de
     l'entree a une contrepartie en sortie.

  3. PLAFOND DE DERIVE           -> `derive_longueur`
     Dans les deux sens : sortie qui enfle (delayage, obeissance) et sortie
     amputee. Calibrage repris du filtre de generation, ou il a tourne sur
     ~11 000 paires.

  4. POLARITE PAR PROPOSITION    -> `polarite`
     Le POC a produit « je sais » -> « je ne sais » (notes d'entrainement §0.14). Ni le
     diff ni le filtre ne pouvaient la voir : « ne » et « pas » sont des
     mots-outils, exclus par construction du controle des mots inventes. La
     phrase reste fluide, tous ses mots existent en entree, et elle dit le
     contraire. C'est « le SEUL garde-fou automatique possible sur la classe
     de fautes la plus grave ».

CE QUI EST REPRIS DE `pipeline/valider_paires.py` ET `pipeline/make_pairs_v2.py`,
POURQUOI CHAQUE PIECE EXISTE — chacune a ete payee par un faux positif mesure :

  - NORMALISATION DE L'APOSTROPHE U+2019 : le professeur ecrit l'apostrophe
    typographique, l'ASR l'apostrophe ASCII. Sans cette etape, 325 paires
    reelles sur 1 200 etaient accusees d'invention a tort.
  - EXEMPTION DES HESITATIONS : « supprimer les hesitations » est la premiere
    regle de la spec. Les compter comme une perte de contenu produisait 217
    faux positifs sur un jeu connu bon.
  - EXEMPTION DES NOMBRES EN LETTRES : l'ITN les convertit legitimement
    (« six » -> « 6 »). Sans cette liste, 763 faux positifs.
  - RACINE GROSSIERE : la spec autorise « accords, homophones et conjugaisons
    corriges ». « filme » -> « filmee » est une correction attendue.
  - APPUI PAR TETE DE 4 CARACTERES : `has_counterpart` de pipeline/make_pairs_v2.
  - TABLE DE REGISTRE : la tete de 4 caracteres relie « prend » a « prenons »,
    mais rien ne relie « peut » a « pouvons ». `Styling: formal` demande
    pourtant ce passage a chaque phrase (« on » -> « nous »), et le garde-fou
    signalait la conjugaison elle-meme comme une INVENTION critique. 40 faux
    positifs sur pairs_mix7.jsonl pour les seuls verbes irreguliers.

Le biais est assume et il est dans un seul sens : ces exemptions font MANQUER
des fautes plutot qu'en inventer. Un garde-fou qui crie au loup est desarme au
bout de trois jours ; un garde-fou silencieux garde son pouvoir d'alerte.

LA CHAINE VIDE EST UN RESULTAT VALIDE, JAMAIS UNE FAUTE. C'est la spec du format
(« Si l'entree n'est que du bruit, renvoie une chaine VIDE »), et le
notes d'entrainement §le repete au jalon M5 : « La chaine vide reste un resultat valide,
pas une erreur. » Juger si l'abstention etait justifiee est le travail du
lecteur, pas celui d'un comparateur de surface.

CE QUE CES GARDE-FOUS ONT ETE MESURES A FAIRE, ET SUR QUOI

Un garde-fou dont on ne connait pas le taux de fausse alerte n'est pas
livrable : c'est le premier chiffre que quiconque veut l'activer demandera.

  pairs_mix6.jsonl — 32 518 paires DEJA ACCEPTEES par le depot. Tout
  signalement y est suspect de fausse alerte. Premiere version : 7,7 %. Apres
  lecture d'un echantillon et correction de ce que la lecture a montre : 1,9 %.
  Apres la REVUE INDEPENDANTE de ce fichier (voir plus bas) : 1,55 %.
  Les corrections sont documentees a l'endroit ou elles s'appliquent ; l'une
  d'elles etait un bug reel (« un » et « une », mots-outils ET nombres,
  sortaient du sac avant d'avoir marque l'entree comme numerique).

  pairs_neuves.jsonl.adjudged — 837 paires REJETEES par le filtre mecanique du
  depot, puis RELUES une par une. C'est la population la plus dure qui existe
  ici : elle est constituee des echecs connus d'un comparateur de surface.
  La lecture en declare 776 bonnes (93 % : le filtre s'etait trompe).

                            garde muet   garde signale
      lecture : paire BONNE        481             295      (etait 407 / 369)
      lecture : paire FAUSSE        13              48      (etait   9 /  52)

  Soit 79 % des fautes confirmees par la lecture, en restant muet sur 62 % des
  paires que le filtre du depot condamnait a tort. Ce n'est pas un score de
  filtre, c'est un rapport de tri.

CE QUE LA REVUE INDEPENDANTE A CHANGE, ET CE QU'ELLE A COUTE

La premiere version faisait ce que le paragraphe precedent annoncait comme une
limite de methode : elle signalait le reecrit de REGISTRE que la ligne de
controle DEMANDE. La lecture des signalements a montre que ce n'etait pas une
limite mais deux trous nommables, et qu'ils se bouchent :

  - les VERBES IRREGULIERS du passage « on » -> « nous » (voir REGISTRE) ;
  - des MOTS-OUTILS oublies par la premiere liste — « elles » quand « elle »,
    « ils » et « eux » y etaient ; « etre » et « ete » quand « est », « sera »
    et « avait » y etaient ; « beaucoup » quand « peu », « trop » et « moins »
    y etaient. Rien ne justifiait l'omission, et chacune se payait.

Le prix est paye sur « plus » (voir _NEG_AMBIGU) et sur « quel » : 74 fausses
alertes en moins sur les paires relues BONNES, 4 detections reelles en moins
sur les paires relues FAUSSES. Le rapport est de dix-huit contre un dans le
sens du silence, ce qui est la direction du biais assume par tout ce fichier.
Les quatre detections perdues sont nommees a l'endroit de chaque exemption.

Il reste du bruit irreductible, et il faut le dire : une reformulation qui
change de tournure sans changer de sens (« faut que je dise au client que la
livraison est reportee » -> « La livraison est reportee. » sous
`Context: email`) reste comptee comme une suppression. Les memes mots se
retrouvent des deux cotes du verdict et aucune regle de surface ne les separe.
notes d'entrainement §0.15 : « Ce n'est pas un bug corrigeable, c'est une limite de
methode. » — mais elle est plus etroite qu'annonce.

Stdlib seule, aucune dependance.

API
    verifier(entree, sortie, control) -> [Faute, ...]   # vide = rien a signaler

    Faute(type, gravite, message, preuve)
        type    : invention | boucle | suppression | derive_longueur | polarite
        gravite : critique | grave | avertissement
        preuve  : un extrait CITABLE, pris dans l'entree ou la sortie

CLI
    python garde.py paires.jsonl        # champs entree/sortie (ou dirty/clean)
"""
import collections
import re
import unicodedata

__all__ = ["Faute", "Controle", "verifier", "parse_control",
           "CRITIQUE", "GRAVE", "AVERTISSEMENT"]


# --------------------------------------------------------------------------
# Gravites
# --------------------------------------------------------------------------
CRITIQUE = "critique"            # le sens a change : negation, invention
GRAVE = "grave"                  # du contenu a disparu, ou le decodeur a boucle
AVERTISSEMENT = "avertissement"  # symptome, pas diagnostic

_RANG = {CRITIQUE: 0, GRAVE: 1, AVERTISSEMENT: 2}


# --------------------------------------------------------------------------
# Calibrage — chaque constante porte la mesure dont elle sort
# --------------------------------------------------------------------------

# Plafond de longueur, repris tel quel du filtre de generation. `lists` et
# `email` ajoutent legitimement de la structure (puces, salutation, signature),
# donc le plafond se desserre pour eux. La marge absolue protege les entrees
# courtes, ou un ratio ne veut rien dire.
PLAFOND_STRICT = 1.15
PLAFOND_LARGE = 1.35
MARGE_ABSOLUE = 12

# Amputation. Le seuil en mots existe parce qu'une entree de 8 mots peut
# legitimement en rendre 3 (« euh bah le chat » -> « Le chat. »).
AMPUTATION_RATIO = 0.45
AMPUTATION_MIN_MOTS = 25

# Boucle. Calibrage du correctif porte dans le decodeur (notes d'entrainement §0.16) :
# « au moins 3 repetitions couvrant au moins 12 tokens », ce qui laisse passer
# un « non non non » emphatique. On y ajoute deux conditions que le decodeur
# n'avait pas a poser et qui, ici, evitent d'accuser une reprise legitime :
#   - le bloc repete doit porter au moins un mot de CONTENU ;
#   - les repetitions doivent etre GROUPEES. Une boucle degeneree est
#     contigue ; une tournure qui revient trois fois dans 900 mots ne l'est
#     pas, et n'est pas une boucle.
BOUCLE_TAILLES = (8, 6, 5, 4)
BOUCLE_MIN_REPETITIONS = 3
BOUCLE_MIN_TOKENS = 12
BOUCLE_ECART_MAX = 3   # tolerance, en tokens, au-dela de la longueur du bloc

# Couverture. Une proposition d'un seul mot de contenu ne se juge pas : trop de
# bruit pour trop peu de signal. Deux mots perdus au minimum, et la majorite de
# la proposition disparue, avant de parler de suppression.
COUVERTURE_MIN_MOTS = 2
COUVERTURE_MIN_PERDUS = 2
COUVERTURE_SEUIL = 0.5
COUVERTURE_MAX_FAUTES = 3   # au-dela, on agrege : 60 fautes ne se lisent pas

# Decoupe en propositions. Une entree ASR arrive souvent sans ponctuation du
# tout ; au-dela de cette taille on retombe sur les virgules, puis sur une
# fenetre fixe, pour que la preuve reste LOCALISABLE.
PROP_MAX_MOTS = 30
PROP_FENETRE = 20


# --------------------------------------------------------------------------
# Lexiques — union des deux jeux eprouves, deaccentues a l'initialisation
# --------------------------------------------------------------------------

# Mots-outils. Leur presence ou leur absence ne prouve rien : la normalisation
# les ajoute et les retire legitimement (« il faut QU'on », « C'EST »). Union
# de OUTILS (pipeline/valider_paires.py) et STOP (pipeline/make_pairs_v2.py) — plus on en exclut,
# moins on crie au loup, et le controle de couverture travaille de toute facon
# sur des propositions entieres.
_OUTILS_BRUT = """
a à au aux avec ce cet cette ces c d de des du elle en et eux il ils je j l la
le les leur lui ma mais me même mes moi mon n ne nos notre nous on ou par pas
pour qu que qui s sa se ses son sur ta te tes toi ton tu un une vos votre vous
y est sont était étaient sera seront suis es sommes êtes ai as avons avez ont
avait avaient plus moins bien mal très trop si non oui alors donc car or ni
quoi dont où celui celle ceux celles leurs peu tout tous toute toutes même
aussi encore déjà sans sous dans chez vers entre depuis pendant avant après
comme quand ainsi puis enfin voilà voila
lequel laquelle lesquels lesquelles auquel auxquels auxquelles duquel desquels
desquelles quelque quelques chaque autre autres tel telle tels telles
the a an of and or but is are was were to in on at it its this that these those
i you he she we they me him her them my your his our their be been being have
has had do does did not no yes for with from by as so if then than
"""
# Second bloc, mesure sur pairs_mix7.jsonl : des mots-outils que la premiere
# liste avait OUBLIES, chacun paye par des signalements sur des sorties lues
# correctes. Ils sont tous de la meme classe que leurs voisins deja presents —
# c'est l'omission qui etait arbitraire, pas l'ajout.
#
#   elles            « elle », « ils », « eux » etaient la, « elles » non. La
#                    reprise d'un pluriel feminin (« ils » -> « elles ») est un
#                    accord corrige, que la spec autorise. 5 signalements.
#   etre avoir ete   « est », « sera », « avait » etaient la, les infinitifs et
#                    le participe non. La voix passive est le mouvement le plus
#                    banal de `Styling: formal` (« on reporte » -> « cela a ete
#                    reporte ») et elle les consomme tous les trois.
#                    Reserve assumee, comme pour « point » : « ete » est aussi
#                    la saison. Un ete invente passera ; c'est le meme biais.
#   beaucoup         « peu », « trop », « tres », « moins » etaient la. 6.
#   seulement        adverbes restrictifs, meme classe que « aussi » et
#   uniquement       « encore » deja presents ; le professeur les ajoute en
#   simplement       developpant « c'est QUE au moment ou » -> « c'est
#   notamment        SEULEMENT au moment ou ». 9 signalements.
#   possessifs       « chaque prof a son. » -> « chaque prof a LE SIEN. » : la
#   toniques         reprise pronominale d'un possessif tronque par l'ASR.
_OUTILS_BRUT += """
elles
être avoir été étant ayant soit soient sois soyons soyez fut furent
serait seraient serais aurait auraient aurais aura auront avais avions aviez
étais étions étiez
sien sienne siens siennes mien mienne miens miennes tien tienne tiens tiennes
quel quelle quels quelles cela
beaucoup seulement uniquement
puisque parce afin jusque jusqu durant
"""
# Chaque mot ci-dessus est PAYE, ou complete un paradigme dont un membre l'est.
# L'ablation un a un sur les 1 030 paires que la version precedente signalait
# donne : cela +6, seulement +5, etre +4, soit +4, soient +4, quelles +4,
# beaucoup +4, elles +3, quel +3, uniquement +3, aurait +3, afin +3, sien +2,
# aura +2, avais +2, sois +2, puisque +2, parce +2, jusqu +2, durant +2, ete +1.
# Les autres tiennent parce qu'un lexique amputé est un piège : garder « sien »
# sans « sienne », ou « être » sans « avoir », c'est promettre une exemption qui
# ne vaut qu'a la moitie des phrases. Ce qui ne payait rien ET n'appartenait a
# aucun paradigme deja present a ete RETIRE (« cependant », « toutefois »,
# « neanmoins », « pourtant », « certes », « selon », « malgre », « sauf »,
# « aupres », « envers », « lorsque », « ceci », « simplement », « notamment ») :
# une exemption gratuite ne coute rien aujourd'hui et rend muet demain.
#
# « quel » est le seul de la liste dont le prix est connu ET non nul : il efface
# 3 fausses alertes et fait manquer, sur les 837 paires relues, « Que d'alcool
# fort. » -> « Quel alcool fort. » (quantite changee en qualite). Un determinant
# interrogatif reste un mot-outil ; la lecture, elle, garde ce cas.

# Hesitations : elles DISPARAISSENT partout, y compris dans les contre-exemples.
_HESITATIONS_BRUT = "euh eu heu hum hein bah ben ba be bon voila alors mmh hmm"

# Nombres ecrits en lettres -> chiffre, pour faire le pont dans les deux sens.
# L'ITN convertit legitimement ; sans ce pont, « six mois » -> « 6 mois » etait
# accuse d'invention.
_NOMBRES_CHIFFRES = {
    "zero": "0", "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
    "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9", "dix": "10",
    "onze": "11", "douze": "12", "treize": "13", "quatorze": "14", "quinze": "15",
    "seize": "16", "vingt": "20", "vingts": "20", "trente": "30", "quarante": "40",
    "cinquante": "50", "soixante": "60", "cent": "100", "cents": "100",
    "mille": "1000",
}
# Vocabulaire que l'ITN absorbe ou produit sans que ce soit une perte ni une
# invention. Mesure sur pairs_mix6.jsonl : « treize heures moins le quart » ->
# « 12h45 » perd « heures » et « quart », « minuit » -> « 0h » fait surgir un
# « 0 ». Ce ne sont pas des fautes, c'est la conversion demandee.
_NOMBRES_AUTRES_BRUT = """
million millions milliard milliards demi demie demis demies premier premiere
premiers premieres second seconde secondes deuxieme troisieme quatrieme
cinquieme dizaine dizaines centaine centaines millier milliers pour cents
heure heures minute minutes quart quarts midi minuit moitie tiers douzaine
douzaines pourcent pourcents euro euros centime centimes
point points slash arobase tiret underscore
"""
# Reserve assumee sur les quatre derniers : spec.py previent que « le mot
# "point" n'est PAS toujours une adresse » (« on fait le point »). Les exempter
# coute un peu de rappel sur ces tournures ; ne pas les exempter accusait de
# suppression toute adresse dictee, qui les consomme TOUS —
# « h t t p s deux points slash slash sncf point eu » -> « https://sncf.eu ».

# Substitutions de REGISTRE que la ligne de controle DEMANDE. `semi-formal`
# lisse les familiarites (« ouais » -> « oui », « bagnole » -> « voiture »),
# `formal` developpe l'oral. Table reprise de SYNONYMES (pipeline/valider_paires.py),
# ou son absence remontait 248 faux positifs sur une seule famille ; les trois
# dernieres entrees viennent de la mesure sur pairs_mix6.jsonl, ou « trucs » ->
# « choses » pesait a lui seul 653 signalements et « ça » -> « cela » 89.
#
# La table joue dans LES DEUX SENS, et il le faut : le mot d'arrivee ne doit
# pas compter comme invente, et le mot de depart ne doit pas compter comme
# perdu.
SYNONYMES = {
    "trucs": "choses", "truc": "chose", "machin": "chose", "machins": "choses",
    "bagnole": "voiture", "ouais": "oui", "boulot": "travail",
    "dispo": "disponible", "ca": "cela", "ok": "accord", "okay": "accord",
    "mec": "homme", "nana": "femme", "fric": "argent", "bouquin": "livre",
}

# Correspondances de REGISTRE que ni la racine ni la tete de quatre caracteres
# ne peuvent relier, parce que le RADICAL change. `Styling: formal` developpe
# l'oral, et son mouvement le plus frequent est « on » + 3e personne du
# singulier -> « nous » + 1re personne du pluriel :
#
#     « on peut voir ca »  ->  « nous pouvons voir cela »
#
# Pour un verbe REGULIER la tete de quatre caracteres suffit (« prend » /
# « prenons » partagent « pren »). Pour la petite dizaine d'irreguliers du
# francais, elle ne peut pas : « peut » / « pouvons », « va » / « allons »
# n'ont pas une lettre en commun. Le garde-fou signalait donc la conjugaison
# elle-meme comme une INVENTION, en gravite critique, sur une sortie qui obeit
# a la ligne de controle. Mesure sur pairs_mix7.jsonl : allons(13), pouvons(8),
# faisons, voulons, savons, devons, fasse — 40 des 432 signalements
# d'invention, tous sur des sorties correctes.
#
# S'y ajoutent les substitutions lexicales que la meme consigne demande et que
# la mesure a montrees : « des fois » -> « parfois », « les gens » -> « les
# personnes », « en vrai » -> « en realite », « genre » -> « par exemple »,
# « d'ouf » -> « fou », et les troncations que l'oral produit et que l'ecrit
# developpe (« pubs » -> « publicites », « notifs » -> « notifications »).
#
# La table est lue DANS LES DEUX SENS (voir `_equivalents`) : une seule entree
# par famille suffit, le mot d'arrivee n'est pas invente et le mot de depart
# n'est pas perdu. Ses valeurs entrent aussi dans le balayage par prefixe, ce
# qui couvre les formes non listees (« pourrions » s'appuie sur « pourrons »).
#
# Le risque de cette table est le meme que celui de toutes les exemptions du
# fichier, et il va dans le sens assume : elle ne peut que RENDRE MUET, jamais
# faire crier. Une entree de plus, c'est une invention de moins detectee, pas
# une fausse alerte de plus.
REGISTRE = {
    # Les irreguliers, a la SEULE 3e personne du singulier : c'est la forme que
    # « on » impose a l'oral, et la seule que le passage a « nous » deplace.
    # Y ajouter les autres personnes serait gratuit et couteux — la mesure l'a
    # montre : avec « vais » dans la table, « je vais je vais pas verifier les
    # comptes on va chiffrer la commande » -> « On va chiffrer la commande. »
    # trouvait un appui pour son faux depart et la SUPPRESSION reelle des
    # comptes cessait d'etre vue. Une table de registre doit relier ce que la
    # consigne demande de changer, rien de plus.
    "va": ("aller", "allons", "allez", "irons", "irait", "irions"),
    "peut": ("pouvoir", "pouvons", "pouvez", "pourra", "pourrons",
             "pourrait", "pourrions", "puisse", "puissions"),
    "doit": ("devoir", "devons", "devez", "devra", "devrons", "devrait",
             "devrions", "falloir", "faut", "faudra"),
    "fait": ("faire", "faisons", "faites", "ferons", "ferait", "ferions",
             "fasse", "fassions"),
    "veut": ("vouloir", "voulons", "voulez", "voudra", "voudrons",
             "voudrait", "voudrions"),
    "sait": ("savoir", "savons", "savez", "saura", "saurons", "saurait"),
    "vaut": ("valoir", "valons", "vaudra", "vaudrait"),
    # « il faut prevenir le client » -> « le client DOIT etre prevenu » : la
    # tournure impersonnelle et le modal disent la meme obligation, et passer
    # de l'une a l'autre est le mouvement type de `Context: email`.
    "faut": ("falloir", "faudra", "faudrait", "fallait", "faille",
             "devoir", "doit", "devra", "devrait", "devons"),
    # substitutions lexicales de registre, mesurees
    "aussi": ("egalement",),
    "vite": ("rapidement",),
    "fois": ("parfois",),
    "gens": ("personnes", "personne", "gens"),
    "vrai": ("realite", "vraiment"),
    "genre": ("exemple",),
    "ouf": ("fou", "incroyable", "genial", "formidable"),
    "bosse": ("travail", "travailler", "travaille"),
    "bosser": ("travailler", "travaille", "travail"),
    # troncations de l'oral que l'ecrit developpe
    "pub": ("publicite",),
    "pubs": ("publicites", "publicite"),
    "notif": ("notification",),
    "notifs": ("notifications", "notification"),
    "perso": ("personnellement", "personnel"),
    "docu": ("documentaire",),
}

# Prefixes d'adresse recomposes par l'ITN : « double ve double ve double ve »
# -> « www », « h t t p s deux points slash slash » -> « https ». Les lettres
# dictees une a une ne survivent pas a la tokenisation, donc le mot recompose
# n'a jamais d'appui. Ce ne sont pas des mots de contenu — exemption
# inconditionnelle, comme AJOUTS_ATTENDUS["url"] de pipeline/valider_paires.py.
# Mesure : 401 signalements « www » et 108 « https » sur pairs_mix6.jsonl.
VOCABULAIRE_ADRESSE = {"www", "http", "https", "ftp", "mailto"}

# Marques d'AUTO-CORRECTION. « Trancher les auto-corrections en gardant la
# valeur retenue par le locuteur » est une regle explicite de la spec : ce qui
# precede la marque DOIT disparaitre. C'est la fonction phare de Scribe, et
# sans cette exemption le garde-fou signale precisement la fonctionnalite.
# Mesure : les familles cor-pardon et cor-veux_dire dominaient les 820
# signalements de suppression sur pairs_mix6.jsonl.
MARQUES_REPARATION = {"pardon", "excuse", "excuses", "excusez", "plutot"}
_VERBES_REPARATION = ("veux", "voulais")

# Marqueurs de negation — regex reprise VERBATIM de pipeline/make_pairs_v2.py. Garder la
# meme regle a l'entrainement et a l'inference n'est pas une coquetterie : un
# modele filtre sur une definition et verifie sur une autre est verifie a
# cote. Reserve connue et assumee : « plus » est aussi un comparatif et
# « personne » aussi un nom. Le controle compare des ECARTS, pas des presences,
# ce qui absorbe l'essentiel du bruit.
NEG = re.compile(r"\b(ne|n'|pas|plus|jamais|rien|aucun[e]?s?|nul[le]*s?|ni|personne)\b",
                 re.IGNORECASE)
_NEG_NE = ("ne", "n'")

# « plus » est capture par NEG et doit l'etre — « il n'y en a plus » est une
# negation — mais il est AUSSI le comparatif le plus courant du francais, et
# jusqu'a un nom propre (« le canal plus » -> « Canal+ »). Le compter parmi les
# marqueurs PLEINS faisait de sa disparition une inversion de sens : 19 des 75
# signalements de polarite sur pairs_mix7.jsonl, et 18 des 57 sur les paires
# relues et declarees BONNES.
#
# Il est donc sorti du compte des marqueurs pleins — mais PAS du fichier, et
# c'est la ou l'ecrire ailleurs se serait paye : il reste dans le budget qui
# legitime un « ne » restaure. Sans cela, « on en veut plus » -> « on n'en veut
# plus » (l'elision que le professeur ENSEIGNE) ferait apparaitre un « ne »
# sans appui, et on aurait echange une famille de fausses alertes contre une
# autre.
#
# Ce que cette classe fait perdre est mesure et assume : sur les 837 paires
# relues, elle coute au plus une detection reelle (« Plus d'hesitation. »
# supprime) pour dix-huit fausses alertes evitees.
_NEG_AMBIGU = ("plus",)

# Ce que la ligne de controle autorise a AJOUTER. Repris de AJOUTS_ATTENDUS
# (pipeline/valider_paires.py) : la spec `Context: email` exige « une ligne de
# salutation [...] puis un bloc de signature ». Sans cette exemption, tout
# e-mail correct est signale comme une invention.
AJOUTS_ATTENDUS = {
    "email": {"bonjour", "bonsoir", "cordialement", "salutations", "merci"},
}


def _deaccent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _pliage(mots_bruts):
    return {_deaccent(m.lower()) for m in mots_bruts.split() if m}


OUTILS = _pliage(_OUTILS_BRUT)
HESITATIONS = _pliage(_HESITATIONS_BRUT)
# Les sacs travaillent sur des tokens deaccentues : les tables doivent l'etre
# aussi, sinon une entree accentuee y serait ecrite sans jamais servir.
SYNONYMES = {_deaccent(k): _deaccent(v) for k, v in SYNONYMES.items()}
REGISTRE = {_deaccent(k): tuple(_deaccent(v) for v in vs)
            for k, vs in REGISTRE.items()}
NOMBRES_CHIFFRES = {_deaccent(k): v for k, v in _NOMBRES_CHIFFRES.items()}
NOMBRES_AUTRES = _pliage(_NOMBRES_AUTRES_BRUT)
NOMBRES_MOTS = set(NOMBRES_CHIFFRES) | NOMBRES_AUTRES


# --------------------------------------------------------------------------
# Normalisation de surface
# --------------------------------------------------------------------------

# U+2019 apostrophe typographique, U+02BC lettre modificative, U+2018 guillemet
# simple ouvrant, U+00B4 accent aigu isole : quatre facons d'ecrire la meme
# elision. Le professeur en emploie une, l'ASR une autre. Cette ligne vaut 325
# faux positifs sur 1 200 paires.
_APOSTROPHES = ("’", "ʼ", "‘", "´", "`")

_MOT = re.compile(r"[0-9]+|[a-z]+(?:'[a-z]+)*")
_FIN_PHRASE = re.compile(r"(?<=[.!?…])\s+")
_FIN_PROPOSITION = re.compile(r"(?<=[.!?…;:])\s+")


def normaliser_apostrophes(texte):
    """Toutes les apostrophes deviennent l'apostrophe ASCII."""
    for a in _APOSTROPHES:
        texte = texte.replace(a, "'")
    return texte


def _tokens(texte):
    """Tokens minuscules, deaccentues, apostrophe normalisee."""
    return _MOT.findall(_deaccent(normaliser_apostrophes(texte).lower()))


def racine(mot):
    """Radical grossier : coupe la marque d'accord finale.

    La spec autorise explicitement « accords, homophones et conjugaisons
    corriges ». « filme » -> « filmee » est donc une correction ATTENDUE, pas
    une invention — mais deaccentues ce sont deux mots differents. On compare
    les radicaux.
    """
    for suf in ("ees", "ee", "es", "s", "e"):
        if mot.endswith(suf) and len(mot) - len(suf) >= 3:
            return mot[:-len(suf)]
    return mot


Sac = collections.namedtuple("Sac", "contenu racines nombres porte_nombre synonymes")


def _sac_tokens(tokens):
    """Sac de mots de CONTENU, plus ses valeurs numeriques et ses synonymes.

    Sont ecartes, et chaque exclusion est une lecon payee :
      - les nombres et unites    : l'ITN les convertit en chiffres
      - les mots-outils          : la normalisation les bouge legitimement
      - les mots de moins de 3   : « as », « le », le bruit de tokenisation
        caracteres
      - les hesitations          : la spec ORDONNE de les supprimer

    L'ORDRE DE CES TESTS EST LOAD-BEARING, et une mesure l'a montre : « un » et
    « une » sont A LA FOIS des mots-outils et des nombres. Testes contre les
    mots-outils d'abord, ils sortaient avant d'avoir marque le texte comme
    porteur d'un nombre, et « une heure » -> « 1h » etait accuse d'avoir
    invente le chiffre 1.
    """
    contenu, nombres, synonymes = set(), set(), set()
    porte_nombre = False
    for tok in tokens:
        if tok.isdigit():
            nombres.add(tok.lstrip("0") or "0")
            porte_nombre = True
            continue
        for piece in tok.split("'"):
            if not piece:
                continue
            # Avant tout filtre : les substitutions de registre, dont certaines
            # partent d'un mot trop court (« ça », « ok ») ou d'un mot-outil
            # (« aussi » -> « egalement ») pour survivre aux filtres suivants.
            if piece in SYNONYMES:
                synonymes.add(SYNONYMES[piece])
            if piece in REGISTRE:
                synonymes.update(REGISTRE[piece])
            if piece in NOMBRES_MOTS:
                porte_nombre = True
                if piece in NOMBRES_CHIFFRES:
                    nombres.add(NOMBRES_CHIFFRES[piece])
                continue
            if len(piece) < 3 or piece in OUTILS or piece in HESITATIONS:
                continue
            contenu.add(piece)
    return Sac(contenu, {racine(m) for m in contenu}, nombres, porte_nombre,
               synonymes)


def sac(texte):
    return _sac_tokens(_tokens(texte))


def _equivalents(mot):
    """`mot` et les formes que la ligne de controle autorise a lui substituer.

    C'est ce qui rend les deux tables lisibles DANS LES DEUX SENS avec une
    seule entree. Le sac d'un texte porte deja, dans `synonymes`, l'expansion
    des mots QU'IL CONTIENT — de quoi juger un mot de sortie contre l'entree.
    Le controle de couverture pose la question inverse (un mot de l'ENTREE
    a-t-il survecu ?), et la table doit alors se lire a l'envers : sans cette
    fonction il faudrait ecrire chaque correspondance deux fois, donc la voir
    diverger au premier ajout.
    """
    formes = {mot}
    syn = SYNONYMES.get(mot)
    if syn:
        formes.add(syn)
    formes.update(REGISTRE.get(mot, ()))
    return formes


def _appui(mot, source):
    """`mot` a-t-il une contrepartie dans le sac `source` ?

    Quatre chances, de la plus stricte a la plus lache : le mot lui-meme, son
    radical (accords, conjugaisons), un synonyme de registre que la ligne de
    controle reclame, puis un prefixe commun d'au moins quatre caracteres —
    `has_counterpart` de pipeline/make_pairs_v2.py, elargi aux deux sens pour couvrir
    « bug » -> « bugue ».

    Les quatre chances sont offertes a chaque forme equivalente, pas seulement
    a `mot` : « peut » doit pouvoir s'appuyer sur « pourrons » sans que la
    table ait a lister toutes les personnes de tous les temps.

    La derniere regle fait manquer des inventions (« impossible » s'appuie sur
    « important ») ; c'est le prix admis pour ne pas condamner « local » /
    « locaux ». Le biais du garde-fou est constant : manquer une faute plutot
    que d'en inventer une.
    """
    # Le balayage par prefixe interroge aussi les substitutions de registre du
    # sac source : une table qui ne vaudrait que pour la forme exacte listee
    # obligerait a y ecrire toute la conjugaison.
    candidats = source.contenu | source.synonymes
    for forme in _equivalents(mot):
        if forme in source.contenu or forme in source.synonymes:
            return True
        if racine(forme) in source.racines:
            return True
        tete = forme[:4]
        if len(tete) < 4:
            continue
        for c in candidats:
            if len(c) >= 4 and c.startswith(tete):
                return True
            # Sens inverse, pour la francisation orthographique : « bug » ->
            # « bugue ». On n'admet que deux caracteres de rallonge, sinon
            # « port » adopterait « portefeuille ».
            if len(c) >= 3 and forme.startswith(c) and len(forme) - len(c) <= 2:
                return True
    return False


# --------------------------------------------------------------------------
# Ligne de controle
# --------------------------------------------------------------------------

_AXE = re.compile(r"\[\s*(styling|structure|context|lang)\s*:\s*([^\]]*?)\s*\]",
                  re.IGNORECASE)


class Controle(object):
    """Les quatre axes de la ligne de controle (spec du format + D2 du PRD)."""

    __slots__ = ("styling", "structure", "context", "lang")

    def __init__(self, styling="semi-formal", structure="prose",
                 context="general", lang="fr"):
        self.styling = styling
        self.structure = structure
        self.context = context
        self.lang = lang

    def __repr__(self):
        return ("[Styling: %s] [Structure: %s] [Context: %s] [Lang: %s]"
                % (self.styling, self.structure, self.context, self.lang))

    def __eq__(self, autre):
        return isinstance(autre, Controle) and repr(self) == repr(autre)


def parse_control(control=None):
    """Accepte None, un Controle, un dict, ou la ligne de controle elle-meme.

    Le harnais d'inference tient la ligne sous forme de chaine ; les tests et
    les generateurs preferent un dict. Refuser l'une des deux formes ferait
    recopier ce parseur ailleurs, donc diverger.
    """
    if control is None:
        return Controle()
    if isinstance(control, Controle):
        return control
    if isinstance(control, dict):
        return Controle(
            styling=str(control.get("styling", "semi-formal")).lower(),
            structure=str(control.get("structure", "prose")).lower(),
            context=str(control.get("context", "general")).lower(),
            lang=str(control.get("lang", "fr")).lower())
    champs = {m.group(1).lower(): m.group(2).strip().lower()
              for m in _AXE.finditer(str(control))}
    return Controle(styling=champs.get("styling", "semi-formal"),
                    structure=champs.get("structure", "prose"),
                    context=champs.get("context", "general"),
                    lang=champs.get("lang", "fr"))


# --------------------------------------------------------------------------
# Faute
# --------------------------------------------------------------------------

class Faute(object):
    """Une faute detectee, avec de quoi la verifier a la main.

    `preuve` n'est pas decoratif : c'est ce qui permet a un humain de trancher
    en trois secondes sans relancer le modele. Un garde-fou qui dit « suspect »
    sans citer se fait desactiver.
    """

    __slots__ = ("type", "gravite", "message", "preuve")

    def __init__(self, type, gravite, message, preuve=""):
        self.type = type
        self.gravite = gravite
        self.message = message
        self.preuve = preuve

    def __repr__(self):
        return "Faute(%r, %r, %r, %r)" % (self.type, self.gravite,
                                          self.message, self.preuve)

    def __str__(self):
        return "%-9s %-16s %s | preuve: %s" % (self.gravite, self.type,
                                               self.message, self.preuve)

    def __eq__(self, autre):
        return isinstance(autre, Faute) and repr(self) == repr(autre)

    def as_dict(self):
        return {"type": self.type, "gravite": self.gravite,
                "message": self.message, "preuve": self.preuve}


# --------------------------------------------------------------------------
# Extraction de preuve
# --------------------------------------------------------------------------

def _phrases(texte):
    return [p.strip() for p in _FIN_PHRASE.split(texte.strip()) if p.strip()]


def _citer(texte, cibles, limite=180):
    """Premiere phrase de `texte` qui porte l'une des `cibles` (deja pliees)."""
    cibles = set(cibles)
    for phrase in _phrases(texte):
        vus = set()
        for tok in _tokens(phrase):
            vus.add(tok)
            vus.update(p for p in tok.split("'") if p)
        if vus & cibles:
            return _court(phrase, limite)
    return _court(texte.strip(), limite)


def _court(texte, limite):
    texte = " ".join(texte.split())
    return texte if len(texte) <= limite else texte[:limite - 1] + "…"


# --------------------------------------------------------------------------
# Controle 1 — DIFF entree/sortie : invention et boucle
# --------------------------------------------------------------------------

def _controle_invention(entree, sortie, ctrl):
    se, ss = sac(entree), sac(sortie)
    attendus = AJOUTS_ATTENDUS.get(ctrl.context, set()) | \
        AJOUTS_ATTENDUS.get(ctrl.structure, set())

    inventes = sorted(m for m in ss.contenu - se.contenu
                      if m not in attendus
                      and m not in VOCABULAIRE_ADRESSE
                      and not _appui(m, se))
    fautes = []
    if inventes:
        fautes.append(Faute(
            "invention", CRITIQUE,
            "mot(s) de contenu en sortie sans appui dans l'entree : %s"
            % ", ".join(inventes[:6]),
            _citer(sortie, inventes)))

    # Les chiffres sont du contenu, et « un chiffre inexact dans un montant ou
    # une date est la faute la plus grave » (spec du professeur). Mais l'ITN
    # COMPOSE : « vingt-cinq » donne « 25 », qui n'est ni « 20 » ni « 5 ». Des
    # que l'entree porte le moindre nombre, la verification mecanique n'est
    # plus possible et on se tait — c'est le lecteur qui juge la valeur
    # (M4, priorite 1 : « negations, dates, chiffres »). Quand l'entree n'en
    # porte AUCUN, en revanche, un chiffre en sortie sort de nulle part.
    if not se.porte_nombre:
        surgis = sorted(ss.nombres, key=lambda v: (len(v), v))
        if surgis:
            fautes.append(Faute(
                "invention", CRITIQUE,
                "valeur(s) numerique(s) en sortie alors que l'entree n'en "
                "porte aucune : %s" % ", ".join(surgis[:6]),
                _citer(sortie, surgis)))
    return fautes


def _occurrences(tokens, bloc):
    n = len(bloc)
    return [i for i in range(len(tokens) - n + 1) if tuple(tokens[i:i + n]) == bloc]


def _plus_longue_grappe(positions, ecart_max):
    """Longueur du plus long train d'occurrences quasi collees."""
    meilleur = courant = 1
    for prec, suiv in zip(positions, positions[1:]):
        if suiv - prec <= ecart_max:
            courant += 1
            meilleur = max(meilleur, courant)
        else:
            courant = 1
    return meilleur


def _controle_boucle(entree, sortie, ctrl):
    ts = _tokens(sortie)
    te = _tokens(entree)
    for n in BOUCLE_TAILLES:
        if len(ts) < 2 * n:
            continue
        comptes = collections.Counter(tuple(ts[i:i + n])
                                      for i in range(len(ts) - n + 1))
        bloc, k = comptes.most_common(1)[0]
        if k < BOUCLE_MIN_REPETITIONS or k * n < BOUCLE_MIN_TOKENS:
            continue
        # Un bloc de purs mots-outils n'est pas une boucle, c'est du francais.
        if not any(t not in OUTILS and len(t) >= 3 and not t.isdigit()
                   for t in bloc):
            continue
        # Les repetitions doivent etre GROUPEES : une boucle est contigue.
        if _plus_longue_grappe(_occurrences(ts, bloc),
                               n + BOUCLE_ECART_MAX) < BOUCLE_MIN_REPETITIONS:
            continue
        # Si l'entree bouclait deja autant, ce n'est pas le modele qui boucle :
        # il recopie fidelement une boucle du DECODEUR (notes d'entrainement §0.16).
        if k <= len(_occurrences(te, bloc)):
            continue
        return [Faute(
            "boucle", GRAVE,
            "bloc de %d mots repete %d fois en sortie (%d fois en entree)"
            % (n, k, len(_occurrences(te, bloc))),
            _court(" ".join(bloc), 180))]
    return []


# --------------------------------------------------------------------------
# Controle 2 — COUVERTURE PAR PHRASE
# --------------------------------------------------------------------------

def propositions(texte):
    """Decoupe l'entree en unites dont on peut exiger une contrepartie.

    La virgule coupe AUTANT que le point, et ce n'est pas un detail : sur une
    entree de vingt mots sans ponctuation forte, ne couper qu'aux points
    laisserait une proposition entiere disparaitre sans que la majorite du
    texte bouge — donc sans rien declencher. C'est exactement la suppression
    silencieuse que ce controle existe pour voir.

    Trop couper ne coute rien en revanche : une unite portant moins de deux
    mots de contenu est ignoree par le controle (« du coup », « voilà »).

    Une entree ASR arrive souvent sans la moindre ponctuation. Passe une
    certaine taille on retombe donc sur une fenetre fixe, pour que la preuve
    reste LOCALISABLE plutot que de designer le texte entier.
    """
    unites = []
    for brut in _FIN_PROPOSITION.split(texte.strip()):
        for morceau in re.split(r",\s*", brut):
            morceau = morceau.strip()
            if not morceau:
                continue
            mots = morceau.split()
            if len(mots) <= PROP_MAX_MOTS:
                unites.append(morceau)
            else:
                for i in range(0, len(mots), PROP_FENETRE):
                    unites.append(" ".join(mots[i:i + PROP_FENETRE]))
    return unites


def _apres_reparation(tokens):
    """Ce qui reste d'une proposition apres sa derniere auto-correction.

    « on se retrouve en visio pardon chez toi » : ce qui precede « pardon » est
    la valeur ABANDONNEE par le locuteur, et la spec ordonne de la supprimer.
    Exiger sa contrepartie en sortie, c'est signaler la fonction phare de
    Scribe comme une faute.
    """
    debut = 0
    for i, tok in enumerate(tokens):
        if tok in MARQUES_REPARATION:
            debut = i + 1
        elif (tok == "dire" and i >= 1 and tokens[i - 1] in _VERBES_REPARATION):
            debut = i + 1
    return tokens[debut:]


def _controle_couverture(entree, sortie, ctrl):
    """Rend (fautes, propositions_perdues) — la seconde sert a la polarite."""
    ss = sac(sortie)
    perdues = []
    for prop in propositions(entree):
        sp = _sac_tokens(_apres_reparation(_tokens(prop)))
        if len(sp.contenu) < COUVERTURE_MIN_MOTS:
            continue                      # trop peu de signal pour juger
        # `_appui` lit les deux tables de registre dans les deux sens depuis
        # `_equivalents` : le mot de DEPART d'une substitution demandee n'est
        # pas un mot perdu (« trucs » a survecu sous la forme « choses »).
        perdus = sorted(m for m in sp.contenu if not _appui(m, ss))
        survivants = len(sp.contenu) - len(perdus)
        if len(perdus) < COUVERTURE_MIN_PERDUS:
            continue
        if survivants >= len(sp.contenu) * COUVERTURE_SEUIL:
            continue
        perdues.append((prop, perdus, len(sp.contenu)))

    fautes = []
    total = len(perdues)
    for prop, perdus, n in perdues[:COUVERTURE_MAX_FAUTES]:
        suffixe = "" if total <= COUVERTURE_MAX_FAUTES else \
            " (%d propositions sans contrepartie au total)" % total
        fautes.append(Faute(
            "suppression", GRAVE,
            "proposition de l'entree sans contrepartie en sortie : %d mot(s) "
            "de contenu sur %d perdu(s) — %s%s"
            % (len(perdus), n, ", ".join(perdus[:6]), suffixe),
            _court(prop, 180)))
    return fautes, [p for p, _, _ in perdues]


# --------------------------------------------------------------------------
# Controle 3 — PLAFOND DE DERIVE DE LONGUEUR
# --------------------------------------------------------------------------

def _controle_longueur(entree, sortie, ctrl):
    de = len(entree.split())
    ds = len(sortie.split())
    if de == 0:
        return []
    strict = (ctrl.structure == "prose" and ctrl.context == "general")
    plafond = PLAFOND_STRICT if strict else PLAFOND_LARGE
    fautes = []
    if ds > de * plafond + MARGE_ABSOLUE:
        fautes.append(Faute(
            "derive_longueur", AVERTISSEMENT,
            "sortie plus longue que l'entree (%d -> %d mots, plafond %.2f "
            "+ %d)" % (de, ds, plafond, MARGE_ABSOLUE),
            _court(" ".join(sortie.split()[-30:]), 180)))
    if de > AMPUTATION_MIN_MOTS and ds < de * AMPUTATION_RATIO:
        fautes.append(Faute(
            "derive_longueur", GRAVE,
            "sortie amputee (%d -> %d mots, plancher %.2f)"
            % (de, ds, AMPUTATION_RATIO),
            _court(sortie, 180)))
    return fautes


# --------------------------------------------------------------------------
# Controle 4 — POLARITE PAR PROPOSITION
# --------------------------------------------------------------------------

def _marqueurs(texte):
    return [m.group(0).lower()
            for m in NEG.finditer(normaliser_apostrophes(texte))]


def _phrases_negatives(texte, limite=180):
    gardees = [p for p in _phrases(texte)
               if NEG.search(normaliser_apostrophes(p))]
    return _court(" / ".join(gardees[:2]), limite) if gardees else ""


def _controle_polarite(entree, sortie, ctrl, propositions_perdues=()):
    """Compte les marqueurs de negation de part et d'autre.

    Deux ecarts distincts, parce qu'ils ne veulent pas dire la meme chose :

      - un marqueur PLEIN (« pas », « jamais », « rien », « aucun », « ni »)
        qui apparait ou disparait inverse le sens. C'est la faute la plus
        grave de la taxonomie.
      - un « ne » supplementaire est LEGITIME tant qu'il restaure une elision
        deja portee par l'entree : « je sais pas » -> « je ne sais pas » est
        exactement ce que le professeur enseigne. Au-dela du nombre de
        marqueurs pleins disponibles pour l'appuyer, ce « ne » n'a plus rien a
        restaurer — c'est la negation inseree du POC.

    `propositions_perdues` evite de compter deux fois le meme evenement. Un
    faux depart avorte emporte sa negation avec lui — « je vais je vais pas
    verifier les comptes on va chiffrer la commande » -> « On va chiffrer la
    commande. » Le diagnostic correct est la SUPPRESSION, deja signalee ; la
    reannoncer en « polarite inversee » ferait chercher une inversion qui
    n'existe pas. Mesure sur pairs_mix6.jsonl : 76 des 148 signalements de
    polarite venaient de cette seule famille.

    La deduction ne peut que COMBLER un ecart de retrait, jamais en ouvrir un
    d'ajout — elle est bornee par le compte de la sortie. Sans cette borne elle
    FABRIQUE des inversions, et la mesure l'a montre : « ils ont dit
    franchement pas ouf » -> « ils ont dit que ce n'etait pas terrible » perd
    « ouf » mais garde son « pas ». Deduire ce « pas » avec la proposition
    faisait apparaitre une negation ajoutee la ou rien n'avait bouge. Une
    negation AJOUTEE n'est jamais expliquee par une suppression, et c'est elle
    que le POC a produite : elle reste signalee quoi qu'il arrive.
    """
    me, ms = _marqueurs(entree), _marqueurs(sortie)
    e_ne = sum(1 for x in me if x in _NEG_NE)
    s_ne = sum(1 for x in ms if x in _NEG_NE)
    e_ambigu = sum(1 for x in me if x in _NEG_AMBIGU)
    s_ambigu = sum(1 for x in ms if x in _NEG_AMBIGU)
    e_plein = len(me) - e_ne - e_ambigu
    s_plein = len(ms) - s_ne - s_ambigu

    if e_plein > s_plein and propositions_perdues:
        emportes = sum(sum(1 for x in _marqueurs(p)
                           if x not in _NEG_NE and x not in _NEG_AMBIGU)
                       for p in propositions_perdues)
        e_plein = max(s_plein, e_plein - emportes)

    if s_plein != e_plein:
        sens = "ajoutee" if s_plein > e_plein else "retiree"
        return [Faute(
            "polarite", CRITIQUE,
            "polarite changee : %d -> %d marqueur(s) de negation plein(s) "
            "(negation %s)" % (e_plein, s_plein, sens),
            _phrases_negatives(sortie if s_plein > e_plein else entree))]

    if s_ne > e_ne + e_plein + e_ambigu:
        return [Faute(
            "polarite", CRITIQUE,
            "« ne » ajoute sans elision correspondante dans l'entree "
            "(%d -> %d, %d marqueur(s) disponible(s) pour l'appuyer)"
            % (e_ne, s_ne, e_plein + e_ambigu),
            _phrases_negatives(sortie))]
    return []


# --------------------------------------------------------------------------
# Point d'entree
# --------------------------------------------------------------------------

def verifier(entree, sortie, control=None):
    """Verifie un couple (entree, sortie) et rend la liste des fautes.

    Rend une liste VIDE quand rien n'est signale. Les fautes sont triees par
    gravite decroissante : ce qui change le sens vient en premier.

    `control` : la ligne de controle, sous n'importe laquelle de ses trois
    formes (chaine « [Styling: ...] ... », dict, ou Controle). Elle compte
    reellement — `Context: email` autorise « Bonjour » et « Cordialement »,
    `Structure: lists` desserre le plafond de longueur. Verifier une sortie
    contre le mauvais reglage, c'est la punir d'avoir obei.
    """
    entree = entree or ""
    sortie = sortie or ""
    ctrl = parse_control(control)

    # LA CHAINE VIDE EST UN RESULTAT VALIDE, JAMAIS UNE FAUTE. La spec l'exige
    # (« Si l'entree n'est que du bruit ou du remplissage, renvoie une chaine
    # VIDE. C'est un resultat valide, pas un echec »), les notes d'entrainement le repete
    # au jalon M5. Savoir si l'abstention etait MERITEE demande de lire ; ce
    # n'est pas le travail d'un comparateur de surface.
    if not sortie.strip():
        return []

    couverture, perdues = _controle_couverture(entree, sortie, ctrl)

    fautes = []
    fautes.extend(_controle_invention(entree, sortie, ctrl))
    fautes.extend(_controle_boucle(entree, sortie, ctrl))
    fautes.extend(couverture)
    fautes.extend(_controle_longueur(entree, sortie, ctrl))
    fautes.extend(_controle_polarite(entree, sortie, ctrl, perdues))
    fautes.sort(key=lambda f: _RANG.get(f.gravite, 9))
    return fautes


def _main(argv):
    import json
    import sys
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0])
        print("usage: garde.py <paires.jsonl>")
        return 2
    par_type = collections.Counter()
    n = touchees = 0
    with open(argv[1], encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne:
                continue
            r = json.loads(ligne)
            entree = r.get("entree", r.get("dirty", ""))
            sortie = r.get("sortie", r.get("clean", r.get("out", "")))
            fautes = verifier(entree, sortie, r.get("control"))
            n += 1
            if not fautes:
                continue
            touchees += 1
            print("--- %s" % r.get("id", n))
            for faute in fautes:
                par_type[faute.type] += 1
                print("    %s" % faute)
    print()
    print("%d paires, %d signalees (%.1f %%)"
          % (n, touchees, 100.0 * touchees / n if n else 0.0))
    for cle, k in par_type.most_common():
        print("   %-16s %5d" % (cle, k))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv))
