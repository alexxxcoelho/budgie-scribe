# -*- coding: utf-8 -*-
"""Tests des garde-fous d'inference.

Deux moities, et la seconde compte autant que la premiere.

LES DETECTIONS prouvent que chaque controle attrape la faute pour laquelle il
existe — et, quand c'est le cas, que LUI SEUL l'attrape : la suppression de
proposition et la boucle passent toutes deux sous le plafond de longueur, ce
qui est precisement l'argument des notes d'entrainement pour exiger quatre controles
plutot qu'un.

LES NON-REGRESSIONS prouvent qu'il se tait sur du travail correct. Chacune
rejoue un faux positif REELLEMENT MESURE pendant le POC :

    « six mois »    -> « 6 mois »     ITN legitime          (763 faux positifs)
    « l'as filme »  -> « l'as filmee » accord + U+2019      (325 sur 1 200)
    « euh bah ... » -> « Le chat. »    hesitations          (217 sur un jeu bon)
    bruit           -> « »             chaine vide valide   (spec du format)

Un garde-fou qui crie au loup est desactive en trois jours ; ces quatre tests
sont donc aussi importants que les quatre premiers.

Les donnees de test sont en francais ACCENTUE, y compris l'apostrophe
typographique U+2019 la ou le professeur l'ecrit : verifier le normaliseur avec
des chaines deja normalisees ne verifie rien.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import garde


def types(fautes):
    return sorted({f.type for f in fautes})


# ==========================================================================
# 1. DETECTIONS
# ==========================================================================

class TestInvention(unittest.TestCase):
    """Controle 1 — un mot de contenu apparu de nulle part."""

    def test_mot_de_contenu_invente(self):
        entree = "on se voit demain à la gare pour le dossier"
        sortie = "On se voit demain à la gare avec Sophie pour le dossier."
        fautes = garde.verifier(entree, sortie)
        self.assertEqual(["invention"], types(fautes))
        self.assertEqual(garde.CRITIQUE, fautes[0].gravite)
        self.assertIn("sophie", fautes[0].message)
        # La preuve doit etre CITABLE : la phrase fautive, pas un code.
        self.assertIn("Sophie", fautes[0].preuve)

    def test_valeur_numerique_sortie_de_nulle_part(self):
        """L'entree ne porte aucun nombre : un chiffre en sortie est invente.

        Des que l'entree en porte un, l'ITN compose (« vingt-cinq » -> « 25 »)
        et la verification mecanique n'est plus possible — voir la
        non-regression `test_itn_compose_un_nombre`.
        """
        entree = "on se retrouve demain devant la gare"
        sortie = "On se retrouve demain à 14h30 devant la gare."
        fautes = garde.verifier(entree, sortie)
        self.assertIn("invention", types(fautes))
        self.assertTrue(any("14" in f.message for f in fautes))


class TestPolarite(unittest.TestCase):
    """Controle 4 — la classe de fautes la plus grave."""

    def test_negation_inseree(self):
        """La regression exacte du POC (notes d'entrainement §0.14).

        Tous les mots de la sortie existent en entree, la phrase est fluide,
        et elle dit le contraire. Ni le diff ni le filtre de generation ne
        peuvent la voir : « ne » est un mot-outil, exclu par construction.
        """
        entree = "parce que je sais que dès le moment où je serai de retour"
        sortie = "Parce que je ne sais que dès le moment où je serai de retour."
        fautes = garde.verifier(entree, sortie)
        self.assertEqual(["polarite"], types(fautes))
        self.assertEqual(garde.CRITIQUE, fautes[0].gravite)
        self.assertIn("ne sais", fautes[0].preuve)

    def test_le_diff_seul_est_aveugle_a_la_negation_inseree(self):
        """L'argument des notes d'entrainement, verifie plutot que cite."""
        entree = "parce que je sais que dès le moment où je serai de retour"
        sortie = "Parce que je ne sais que dès le moment où je serai de retour."
        ctrl = garde.parse_control(None)
        self.assertEqual([], garde._controle_invention(entree, sortie, ctrl))
        self.assertEqual([], garde._controle_longueur(entree, sortie, ctrl))
        self.assertNotEqual([], garde._controle_polarite(entree, sortie, ctrl))

    def test_negation_retiree(self):
        """L'inversion marche dans les deux sens : « pas » disparu."""
        entree = "je ne veux pas déplacer la réunion de jeudi"
        sortie = "Je veux déplacer la réunion de jeudi."
        fautes = garde.verifier(entree, sortie)
        self.assertIn("polarite", types(fautes))
        self.assertIn("retiree", fautes[0].message)

    def test_faux_depart_avorte_ne_compte_pas_deux_fois(self):
        """Une negation emportee par une proposition supprimee n'est pas une
        inversion : le bon diagnostic est la SUPPRESSION, deja signalee.

        76 des 148 signalements de polarite sur pairs_mix6.jsonl venaient de
        cette seule famille.
        """
        entree = ("je vais je vais pas vérifier les comptes "
                  "on va chiffrer la commande")
        sortie = "On va chiffrer la commande."
        fautes = garde.verifier(entree, sortie)
        self.assertEqual(["suppression"], types(fautes))

    def test_la_deduction_ne_fabrique_pas_d_inversion(self):
        """La borne sur la deduction, et pourquoi elle existe.

        Ici la proposition perd « ouf » mais GARDE son « pas ». Deduire ce
        « pas » avec la proposition ferait apparaitre une negation ajoutee la
        ou rien n'a bouge — un faux positif fabrique par le garde-fou
        lui-meme, trouve en le mesurant sur pairs_mix6.jsonl.
        """
        entree = ("j'ai deux trois autres potes qui sont allés "
                  "et ils ont dit franchement pas ouf")
        sortie = ("J'ai deux ou trois autres amis qui y sont allés "
                  "et ils ont dit que ce n'était pas terrible.")
        self.assertNotIn("polarite", types(garde.verifier(entree, sortie)))

    def test_negation_inseree_survit_a_une_suppression(self):
        """La deduction ne doit JAMAIS taire une negation ajoutee.

        C'est la faute que le POC a produite et la raison d'etre du controle :
        elle reste signalee meme quand une proposition disparait par ailleurs.
        """
        entree = ("je sais que le dossier est prêt. "
                  "il faut aussi prévenir le client de Bordeaux du décalage.")
        sortie = "Je ne sais que le dossier est prêt."
        fautes = garde.verifier(entree, sortie)
        self.assertIn("polarite", types(fautes))
        self.assertIn("suppression", types(fautes))

    def test_faux_depart_nu_reste_signale_et_c_est_voulu(self):
        """Residu MESURE, epingle plutot que laisse indefini.

        Un faux depart sans marque de reparation, trop court pour declencher
        la couverture, emporte sa negation : le garde-fou signale une polarite
        alors que la sortie est correcte. C'etait le seul signalement sur les
        12 sorties reelles de final_v6.jsonl.

        On le garde. Le faire taire demanderait d'affaiblir le SEUL garde-fou
        automatique sur la classe de fautes la plus grave, pour eteindre un
        signalement par douze. Le biais penche du bon cote ; si quelqu'un
        change d'avis, ce test lui dira exactement ce qu'il troque.
        """
        fautes = garde.verifier("je vais je vais pas le faire on va le faire demain",
                                "On va le faire demain.")
        self.assertEqual(["polarite"], types(fautes))

    def test_elision_restauree_est_legitime(self):
        """« je sais pas » -> « je ne sais pas » : ce que le professeur ENSEIGNE.

        Le « ne » ajoute s'appuie sur le « pas » deja present en entree.
        Punir cette paire serait punir la bonne reponse — le defaut d'outillage
        n°1 du POC (notes d'entrainement §0.14).
        """
        entree = "je sais pas si le dossier est prêt"
        sortie = "Je ne sais pas si le dossier est prêt."
        self.assertEqual([], garde.verifier(entree, sortie))


class TestCouverture(unittest.TestCase):
    """Controle 2 — la suppression silencieuse, invisible au diff."""

    def test_proposition_supprimee(self):
        entree = ("je dois passer à la banque ce matin. "
                  "ensuite je récupère les enfants à l'école. "
                  "et le soir on dîne chez mes parents.")
        sortie = ("Je dois passer à la banque ce matin. "
                  "Le soir, on dîne chez mes parents.")
        fautes = garde.verifier(entree, sortie)
        self.assertEqual(["suppression"], types(fautes))
        self.assertEqual(garde.GRAVE, fautes[0].gravite)
        self.assertIn("école", fautes[0].preuve)

    def test_la_suppression_passe_sous_les_autres_controles(self):
        """Pourquoi ce controle existe, verifie et non affirme.

        Tous les mots de la sortie existent en entree (diff muet), la sortie
        fait 65 % de l'entree (plafond muet), la polarite est intacte. Sans la
        couverture par phrase, une proposition entiere disparait sans un bruit.
        """
        entree = ("je dois passer à la banque ce matin. "
                  "ensuite je récupère les enfants à l'école. "
                  "et le soir on dîne chez mes parents.")
        sortie = ("Je dois passer à la banque ce matin. "
                  "Le soir, on dîne chez mes parents.")
        ctrl = garde.parse_control(None)
        self.assertEqual([], garde._controle_invention(entree, sortie, ctrl))
        self.assertEqual([], garde._controle_longueur(entree, sortie, ctrl))
        self.assertEqual([], garde._controle_polarite(entree, sortie, ctrl))
        couverture, perdues = garde._controle_couverture(entree, sortie, ctrl)
        self.assertNotEqual([], couverture)
        self.assertEqual(1, len(perdues))

    def test_entree_non_ponctuee_reste_decoupable(self):
        """Une entree ASR arrive souvent sans ponctuation forte.

        La virgule doit donc couper autant que le point : la proposition
        perdue ne pese ici qu'un tiers du texte, et sans decoupe fine la
        majorite survivante etoufferait le signal.
        """
        entree = ("il faudrait revoir le planning du projet, "
                  "les délais annoncés posent un vrai problème, "
                  "et prévenir le client de Bordeaux avant vendredi")
        sortie = ("Il faudrait revoir le planning du projet et prévenir "
                  "le client de Bordeaux avant vendredi.")
        fautes = garde.verifier(entree, sortie)
        self.assertEqual(["suppression"], types(fautes))
        self.assertIn("délais", fautes[0].preuve)


class TestBoucle(unittest.TestCase):
    """Controle 1 (second volet) — la boucle degeneree du decodage glouton."""

    def test_boucle_detectee(self):
        entree = "je vais au marché demain et je prendrai des légumes"
        sortie = ("Je vais au marché demain. Je vais au marché demain. "
                  "Je vais au marché demain. Je vais au marché demain.")
        fautes = garde.verifier(entree, sortie)
        self.assertIn("boucle", types(fautes))
        boucle = [f for f in fautes if f.type == "boucle"][0]
        self.assertEqual(garde.GRAVE, boucle.gravite)
        self.assertIn("marche", boucle.preuve)

    def test_boucle_passe_sous_le_plafond_de_longueur(self):
        """La marge absolue de 12 mots, indispensable aux entrees courtes,
        laisse passer une boucle sur une entree courte. C'est le controle de
        boucle qui l'attrape, pas le plafond."""
        entree = "je vais au marché demain et je prendrai des légumes"
        sortie = ("Je vais au marché demain. Je vais au marché demain. "
                  "Je vais au marché demain. Je vais au marché demain.")
        ctrl = garde.parse_control(None)
        self.assertEqual([], garde._controle_longueur(entree, sortie, ctrl))
        self.assertNotEqual([], garde._controle_boucle(entree, sortie, ctrl))

    def test_boucle_deja_presente_dans_l_entree_non_imputee(self):
        """Les boucles viennent du DECODEUR (notes d'entrainement §0.16). Recopier
        fidelement une entree qui boucle n'est pas une faute du modele."""
        entree = ("je vais au marché demain je vais au marché demain "
                  "je vais au marché demain je vais au marché demain")
        sortie = ("Je vais au marché demain. Je vais au marché demain. "
                  "Je vais au marché demain. Je vais au marché demain.")
        self.assertEqual([], garde.verifier(entree, sortie))

    def test_repetition_emphatique_non_signalee(self):
        """« non non non » emphatique : trois repetitions d'un bloc d'un mot,
        loin des 12 tokens exiges. Meme calibrage que le correctif decodeur."""
        entree = "non non non ce n'est pas ce qu'on avait dit"
        sortie = "Non, non, non, ce n'est pas ce qu'on avait dit."
        self.assertEqual([], garde.verifier(entree, sortie))


class TestDeriveLongueur(unittest.TestCase):
    """Controle 3 — le plafond, dans les deux sens."""

    def test_sortie_qui_enfle(self):
        entree = "il faut qu'on avance sur le dossier"
        sortie = ("Il faut que nous avancions sur le dossier, car le dossier "
                  "doit avancer si nous voulons que le dossier avance et que "
                  "l'avancement du dossier soit un dossier qui avance.")
        fautes = garde.verifier(entree, sortie)
        self.assertIn("derive_longueur", types(fautes))

    def test_sortie_amputee(self):
        entree = ("alors donc je pense qu'il faudrait vraiment qu'on revoie "
                  "ensemble le planning du projet parce que les délais "
                  "annoncés la semaine dernière posent un vrai problème "
                  "pour la livraison de janvier")
        sortie = "Le planning est à revoir."
        fautes = garde.verifier(entree, sortie)
        derive = [f for f in fautes if f.type == "derive_longueur"]
        self.assertTrue(derive)
        self.assertEqual(garde.GRAVE, derive[0].gravite)
        self.assertIn("amputee", derive[0].message)


# ==========================================================================
# 2. NON-REGRESSIONS — les quatre faux positifs mesures pendant le POC
# ==========================================================================

class TestNonRegressions(unittest.TestCase):

    def test_itn_six_mois(self):
        """« six mois » -> « 6 mois ». L'ITN convertit LEGITIMEMENT.

        Sans le pont nombre-en-lettres <-> chiffre, `liste_en_prose` remontait
        763 faux positifs (valider_paires.py).
        """
        self.assertEqual([], garde.verifier("six mois", "6 mois"))

    def test_accord_avec_apostrophe_typographique(self):
        """« l'as filme » -> « l’as filmee ».

        Deux pieges d'un coup, et chacun a coute cher :
          - l'accord : la spec autorise « accords, homophones et conjugaisons
            corriges », d'ou la racine grossiere ;
          - l'apostrophe : le professeur ecrit U+2019, l'ASR ecrit U+0027.
            Sans la normalisation, 325 paires reelles sur 1 200 etaient
            accusees d'invention.
        """
        entree = "tu l'as filmé hier soir"
        sortie = "Tu l’as filmée hier soir."
        self.assertIn("’", sortie)          # le piege est bien arme
        self.assertEqual([], garde.verifier(entree, sortie))

    def test_apostrophe_typographique_seule(self):
        """Le meme piege, isole : seule l'apostrophe change de forme."""
        entree = "c'est l'équipe d'Alex qui s'en occupe aujourd'hui"
        sortie = ("C’est l’équipe d’Alex qui s’en occupe "
                  "aujourd’hui.")
        self.assertEqual([], garde.verifier(entree, sortie))

    def test_hesitations_supprimees(self):
        """« euh bah le chat » -> « Le chat. »

        Supprimer les hesitations est la PREMIERE regle de la spec. Les
        compter comme une perte de contenu produisait 217 faux positifs sur un
        jeu connu bon (valider_paires.py).
        """
        self.assertEqual([], garde.verifier("euh bah le chat", "Le chat."))

    def test_chaine_vide_sur_du_bruit(self):
        """Bruit pur -> chaine vide. Resultat VALIDE, jamais une faute."""
        self.assertEqual([], garde.verifier("euh hum enfin voilà bah euh", ""))

    def test_chaine_vide_toujours_valide(self):
        """La regle ne connait pas d'exception, meme sur une entree fournie.

        Juger si l'abstention etait meritee demande de LIRE. Le garde-fou trie,
        il ne tranche pas (notes d'entrainement §0.15).
        """
        entree = ("il faudrait revoir le planning du projet avant vendredi "
                  "et prévenir le client de Bordeaux de ce décalage")
        self.assertEqual([], garde.verifier(entree, ""))
        self.assertEqual([], garde.verifier(entree, "   \n  "))

    def test_normalisation_reelle_semi_formal(self):
        """Une normalisation ordinaire, telle que le produit sortira."""
        entree = ("euh du coup je pense qu'on devrait euh reporter la réunion "
                  "de jeudi à vendredi matin si ça vous va")
        sortie = ("Je pense qu'on devrait reporter la réunion de jeudi à "
                  "vendredi matin, si ça vous va.")
        self.assertEqual([], garde.verifier(entree, sortie))

    def test_auto_correction_tranchee(self):
        """« vendredi, non, jeudi » -> « jeudi » : la fonction phare de Scribe.

        Le mot ecarte disparait de la sortie — c'est voulu. La proposition
        garde assez de contenu pour que la couverture ne s'en emeuve pas.
        """
        entree = "on se voit vendredi non jeudi devant la gare de Bordeaux"
        sortie = "On se voit jeudi devant la gare de Bordeaux."
        self.assertEqual([], garde.verifier(entree, sortie))

    def test_auto_correction_avec_marque(self):
        """« on se retrouve en visio pardon chez toi » -> « chez toi ».

        Ce qui precede la marque de reparation est la valeur ABANDONNEE, et la
        spec ordonne de la supprimer. Sans cette exemption, les familles
        cor-pardon et cor-veux_dire dominaient les signalements de suppression
        sur pairs_mix6.jsonl.
        """
        self.assertEqual([], garde.verifier(
            "on se retrouve en visio pardon chez toi",
            "On se retrouve chez toi."))
        self.assertEqual([], garde.verifier(
            "j'en ai parlé à Vincent je voulais dire Marie",
            "J'en ai parlé à Marie."))

    def test_heure_et_adresse_absorbent_leur_vocabulaire(self):
        """L'ITN consomme les mots qui disent la forme.

        « treize heures moins le quart » -> « 12h45 » perd « heures » et
        « quart » ; une adresse dictee consomme « point » et « slash ». Ce
        sont des conversions demandees, pas des suppressions.
        """
        self.assertEqual([], garde.verifier(
            "On se retrouve à treize heures moins le quart.",
            "On se retrouve à 12h45."))
        self.assertEqual([], garde.verifier(
            "tu trouveras tout sur h t t p s deux points slash slash sncf point eu",
            "Tu trouveras tout sur https://sncf.eu."))

    def test_un_et_une_marquent_bien_un_nombre(self):
        """« un » et « une » sont A LA FOIS mots-outils et nombres.

        Testes contre les mots-outils en premier, ils sortaient du sac avant
        d'avoir marque l'entree comme porteuse d'un nombre, et « une heure »
        -> « 1h » etait accuse d'avoir invente le chiffre 1. L'ordre des tests
        dans `_sac_tokens` est load-bearing ; ce test le tient.
        """
        self.assertTrue(garde.sac("Le magasin ferme à une heure.").porte_nombre)
        self.assertEqual([], garde.verifier("Le magasin ferme à une heure.",
                                            "Le magasin ferme à 1h."))

    def test_synonyme_de_registre(self):
        """« trucs » -> « choses » : substitution que `semi-formal` DEMANDE.

        653 signalements a elle seule sur pairs_mix6.jsonl avant la table.
        Elle doit valoir dans les deux sens : le mot d'arrivee n'est pas
        invente, le mot de depart n'est pas perdu.
        """
        self.assertEqual([], garde.verifier(
            "il nous faut encore deux trucs pour le stand",
            "Il nous faut encore 2 choses pour le stand."))

    def test_itn_compose_un_nombre(self):
        """« vingt-cinq pour cent » -> « 25 % ».

        « 25 » n'est ni « 20 » ni « 5 » : l'ITN COMPOSE. Des que l'entree porte
        un nombre, la verification mecanique de la valeur devient impossible et
        le garde-fou se tait — la fidelite des chiffres est la priorite 1 de la
        LECTURE en M4, pas celle d'un comparateur de surface.
        """
        entree = "on est à vingt-cinq pour cent du budget"
        sortie = "On est à 25 % du budget."
        self.assertEqual([], garde.verifier(entree, sortie))


# ==========================================================================
# 2 bis. NON-REGRESSIONS DE LA REVUE INDEPENDANTE — le garde-fou ne doit pas
#        punir une sortie d'avoir OBEI a la ligne de controle
# ==========================================================================

class TestRegistreEtMotsOutils(unittest.TestCase):
    """Faux positifs CRITIQUES mesures sur pairs_mix7.jsonl (35 518 paires
    deja acceptees par le depot) et sur les 837 paires relues une par une.

    Le garde-fou accusait d'invention la normalisation que la consigne ORDONNE
    — la conjugaison de « on » -> « nous », l'adverbe soutenu, l'accord de
    reprise, la voix passive. Une faute critique sur du travail correct est la
    plus couteuse de toutes : c'est celle qui fait desactiver l'outil.
    """

    def test_on_devient_nous_verbes_irreguliers(self):
        """`Styling: formal` demande ce passage a chaque phrase.

        Pour un verbe REGULIER la tete de quatre caracteres suffit ; pour les
        irreguliers le radical change et rien ne les reliait. 40 signalements
        d'invention sur pairs_mix7.jsonl, tous sur des sorties correctes.
        """
        for entree, sortie in [
                ("on peut faire ça demain", "Nous pouvons faire cela demain."),
                ("on va voir le client demain",
                 "Nous allons voir le client demain."),
                ("on doit livrer le dossier", "Nous devons livrer le dossier."),
                ("on fait le point vendredi",
                 "Nous faisons le point vendredi."),
                ("on veut relancer le fournisseur",
                 "Nous voulons relancer le fournisseur."),
                ("on sait que le budget est serré",
                 "Nous savons que le budget est serré.")]:
            self.assertEqual([], garde.verifier(entree, sortie),
                             "%s -> %s" % (entree, sortie))

    def test_verbe_regulier_ne_demande_aucune_table(self):
        """La table ne liste que les irreguliers, et c'est voulu.

        « prend » et « prenons » partagent leurs quatre premieres lettres :
        les inscrire serait de la place perdue et une exemption de plus.
        """
        self.assertEqual([], garde.verifier(
            "on prend la voiture de service",
            "Nous prenons la voiture de service."))

    def test_la_table_de_registre_se_lit_dans_les_deux_sens(self):
        """Le mot d'arrivee n'est pas invente, le mot de depart n'est pas perdu.

        Le diff demande si « pouvons » a un appui dans l'entree ; la
        couverture demande l'inverse, si « peut » a survecu. Une table lue
        dans un seul sens obligerait a ecrire chaque correspondance deux fois,
        donc a la voir diverger au premier ajout.
        """
        entree = "on peut relancer le fournisseur de Bordeaux avant vendredi"
        sortie = ("Nous pouvons relancer le fournisseur de Bordeaux "
                  "avant vendredi.")
        self.assertEqual([], garde.verifier(entree, sortie))
        self.assertTrue(garde._appui("peut", garde.sac(sortie)))
        self.assertTrue(garde._appui("pouvons", garde.sac(entree)))

    def test_le_registre_n_aveugle_pas_l_invention(self):
        """La contrepartie a exiger de toute exemption.

        Meme phrase, meme normalisation, plus un nom propre venu de nulle
        part : la faute reste signalee. Une exemption qui eteint aussi les
        vraies fautes n'est pas une exemption, c'est une panne.
        """
        fautes = garde.verifier("on peut faire ça demain",
                                "Nous pouvons faire cela demain avec Sophie.")
        self.assertEqual(["invention"], types(fautes))
        self.assertIn("sophie", fautes[0].message)

    def test_adverbe_et_substitutions_lexicales(self):
        """« aussi » -> « egalement » et les cinq autres, mesurees une a une."""
        for entree, sortie in [
                ("il faut aussi prévenir le client",
                 "Il faut également prévenir le client."),
                ("il y a des piscines des fois dans ces lieux",
                 "Il y a des piscines parfois dans ces lieux."),
                ("je propose de faire des recherches sur tous les gens "
                 "qu'on va inviter",
                 "Je propose de faire des recherches sur toutes les "
                 "personnes que nous allons inviter."),
                ("en vrai il n'y a pas besoin de l'accord des parents",
                 "En réalité, il n'y a pas besoin de l'accord des parents."),
                ("genre Interstellar ou Seul sur Mars",
                 "Par exemple, Interstellar ou Seul sur Mars."),
                ("il faut faire des pubs chez les commerçants",
                 "Il faut faire des publicités chez les commerçants.")]:
            self.assertEqual([], garde.verifier(entree, sortie),
                             "%s -> %s" % (entree, sortie))

    def test_accord_de_reprise_au_feminin_pluriel(self):
        """« elle », « ils » et « eux » etaient dans les mots-outils, « elles »
        non. L'accord corrige est autorise par la spec."""
        entree = ("je vois des personnes qui font beaucoup d'achats "
                  "et ils jettent la moitié")
        sortie = ("Je vois des personnes qui font beaucoup d'achats "
                  "et elles jettent la moitié.")
        self.assertEqual([], garde.verifier(entree, sortie))

    def test_voix_passive(self):
        """« est », « sera », « avait » etaient la ; « etre » et « ete » non.

        La voix passive est le mouvement le plus banal de `Styling: formal`
        et elle les consomme tous les deux.
        """
        self.assertEqual([], garde.verifier(
            "on a reporté la livraison du chantier de Bordeaux",
            "La livraison du chantier de Bordeaux a été reportée."))

    def test_quantifieur_et_adverbe_restrictif(self):
        """« peu », « trop », « tres », « moins » etaient dans la liste ;
        « beaucoup », « seulement » et « uniquement » non."""
        self.assertEqual([], garde.verifier(
            "on va se retrouver qu'avec des chercheurs à l'événement",
            "Nous allons nous retrouver uniquement avec des chercheurs "
            "à l'événement."))
        self.assertEqual([], garde.verifier("j'aime trop bien ça",
                                            "J'aime beaucoup ça."))

    def test_plus_comparatif_n_est_pas_une_negation(self):
        """« le canal plus » -> « Canal+ ».

        « plus » reste capture par NEG — « il n'y en a plus » EST une
        negation — mais il sort du compte des marqueurs PLEINS : c'est aussi
        le comparatif le plus courant du francais, et jusqu'a un nom propre.
        19 des 75 signalements de polarite sur pairs_mix7.jsonl, et 18 des 57
        sur des paires relues et declarees BONNES.
        """
        self.assertEqual([], garde.verifier("on le met sur le canal plus",
                                            "On le met sur Canal+."))
        self.assertEqual([], garde.verifier(
            "je ne suis plus dans mon travail je ne suis plus dans mon travail",
            "Je ne suis plus dans mon travail."))

    def test_plus_reste_dans_le_budget_du_ne_restaure(self):
        """Ce que le retrait de « plus » aurait casse s'il etait alle plus loin.

        « on en veut plus » -> « on n'en veut plus » est l'elision que le
        professeur ENSEIGNE. Si « plus » sortait du budget qui legitime un
        « ne » ajoute, on aurait echange une famille de fausses alertes contre
        une autre — c'est pourquoi il quitte le compte des marqueurs pleins
        SANS quitter le fichier.
        """
        self.assertEqual([], garde.verifier(
            "on en veut plus de ce fournisseur",
            "On n'en veut plus de ce fournisseur."))

    def test_ce_que_les_exemptions_font_manquer(self):
        """Le prix, epingle plutot que laisse indefini.

        Ces deux paires sont FAUSSES et le garde-fou se tait desormais. Elles
        font partie des quatre detections perdues sur les 837 paires relues,
        pour 74 fausses alertes evitees. Ce test n'affirme pas que ce silence
        est bien : il affirme qu'il est CONNU. Si quelqu'un veut le reprendre,
        il sait exactement ce qu'il rachete et a quel prix.
        """
        self.assertEqual([], garde.verifier(
            "Ah, bah oui. Plus d'hésitation. Par contre, oui, il va quand "
            "même falloir se creuser la cervelle pour quel film ?",
            "Oui, il va quand même falloir se creuser la cervelle pour "
            "quel film ?"))
        self.assertEqual([], garde.verifier("Que d'alcool fort.",
                                            "Quel alcool fort."))


# ==========================================================================
# 3. LIGNE DE CONTROLE — verifier une sortie contre le mauvais reglage,
#    c'est la punir d'avoir obei
# ==========================================================================

class TestLigneDeControle(unittest.TestCase):

    def test_parse_les_trois_formes(self):
        attendu = garde.Controle("formal", "lists", "email", "fr")
        self.assertEqual(attendu, garde.parse_control(
            "[Styling: formal] [Structure: lists] [Context: email] [Lang: fr]"))
        self.assertEqual(attendu, garde.parse_control(
            {"styling": "formal", "structure": "lists", "context": "email"}))
        self.assertEqual(attendu, garde.parse_control(attendu))
        self.assertEqual(garde.Controle(), garde.parse_control(None))

    def test_email_autorise_la_salutation_et_la_signature(self):
        entree = "on se voit demain à la gare pour le dossier"
        sortie = ("Bonjour,\n\nOn se voit demain à la gare pour le dossier."
                  "\n\nCordialement,")
        courriel = ("[Styling: semi-formal] [Structure: prose] "
                    "[Context: email] [Lang: fr]")
        self.assertEqual([], garde.verifier(entree, sortie, courriel))
        # Et le meme couple, juge contre le mauvais reglage, DOIT se plaindre :
        # c'est ce qui prouve que la ligne de controle est reellement lue.
        general = ("[Styling: semi-formal] [Structure: prose] "
                   "[Context: general] [Lang: fr]")
        self.assertIn("invention", types(garde.verifier(entree, sortie, general)))

    def test_lists_desserre_le_plafond_de_longueur(self):
        """`lists` et `email` ajoutent de la structure : puces, salutation,
        signature. Le plafond doit s'en apercevoir.

        Longueurs construites plutot que redigees : un seuil numerique se
        teste avec des comptes exacts, sinon le test devient une loterie sur
        le nombre de mots d'une phrase d'exemple.
        """
        n = 40
        entree = " ".join(["dossier"] * n)
        sous_lists = int(n * garde.PLAFOND_LARGE + garde.MARGE_ABSOLUE)
        sur_prose = int(n * garde.PLAFOND_STRICT + garde.MARGE_ABSOLUE) + 3
        self.assertLess(sur_prose, sous_lists)          # la bande existe
        sortie = " ".join(["dossier"] * sur_prose)
        ctrl_prose = garde.parse_control("[Structure: prose] [Context: general]")
        ctrl_lists = garde.parse_control("[Structure: lists] [Context: general]")
        self.assertNotEqual([], garde._controle_longueur(entree, sortie, ctrl_prose))
        self.assertEqual([], garde._controle_longueur(entree, sortie, ctrl_lists))


# ==========================================================================
# 4. CONTRAT DE L'API
# ==========================================================================

class TestContrat(unittest.TestCase):

    def test_faute_porte_type_gravite_et_preuve(self):
        fautes = garde.verifier(
            "on se voit demain à la gare",
            "On se voit demain à la gare avec Sophie.")
        self.assertTrue(fautes)
        for faute in fautes:
            self.assertTrue(faute.type)
            self.assertIn(faute.gravite,
                          (garde.CRITIQUE, garde.GRAVE, garde.AVERTISSEMENT))
            self.assertTrue(faute.preuve.strip(),
                            "une faute sans preuve citable ne sert a rien")
            self.assertEqual({"type", "gravite", "message", "preuve"},
                             set(faute.as_dict()))

    def test_fautes_triees_par_gravite(self):
        """Ce qui change le sens se lit en premier."""
        entree = ("je ne veux pas déplacer la réunion de jeudi. "
                  "il faut aussi prévenir le client de Bordeaux du décalage.")
        sortie = "Je veux déplacer la réunion de jeudi."
        fautes = garde.verifier(entree, sortie)
        rangs = [garde._RANG[f.gravite] for f in fautes]
        self.assertEqual(sorted(rangs), rangs)
        self.assertEqual(garde.CRITIQUE, fautes[0].gravite)

    def test_entrees_degenerees_ne_levent_pas_d_exception(self):
        for entree, sortie in [("", ""), ("", "Bonjour."), ("abc", ""),
                               (None, None), ("...", "..."), ("   ", "   "),
                               ("é", "É."), ("6", "six")]:
            self.assertIsInstance(garde.verifier(entree, sortie), list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
