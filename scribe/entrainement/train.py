# -*- coding: utf-8 -*-
"""Point d'entree generique de l'entrainement, par arguments de ligne de commande.

    python train.py --pairs pairs_mix_en.jsonl --out scribe-en-next [--profil nano|mini|standard|large]
                    [--methode full|lora] [--base <repo HF>] [--epochs 2] [--batch N] [--accum N]
                    [--lr X] [--lora-r 32] [--lora-alpha 64] [--max-len 512] [--limit 0]

Enveloppe `train_rocm.py`, qui lit sa configuration dans l'environnement
(SCRIBE_PROFIL, SCRIBE_BASE, SCRIBE_METHODE, SCRIBE_PAIRS, SCRIBE_OUT,
SCRIBE_EPOCHS, SCRIBE_BATCH, SCRIBE_ACCUM, SCRIBE_LR, SCRIBE_LORA_R,
SCRIBE_LORA_ALPHA, SCRIBE_MAXLEN, SCRIBE_LIMIT). Le profil fixe la base, la
methode et les defauts de lr/batch/accum (voir modeles.py) ; une option
donnee explicitement l'emporte. Le choix de l'appareil est generique : CUDA ou
ROCm, sinon MPS, sinon CPU. Les chemins relatifs sont resolus depuis
SCRIBE_TRAVAIL (ou le repertoire courant).
"""
import argparse
import os
import sys

ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ap.add_argument("--pairs", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--profil", default=os.environ.get("SCRIBE_PROFIL", "nano"),
                help="nano (0.6B full) | mini (1.7B lora) | standard (4B lora) | large (8B lora)")
ap.add_argument("--methode", choices=["full", "lora"], help="force la methode du profil")
ap.add_argument("--base", help="depot HF du modele de base, a la place de celui du profil")
ap.add_argument("--epochs", type=float, default=2)
# batch/accum/lr : sans valeur, ce sont les defauts du profil qui s'appliquent.
ap.add_argument("--batch", type=int)
ap.add_argument("--accum", type=int)
ap.add_argument("--lr", type=float)
ap.add_argument("--lora-r", type=int)
ap.add_argument("--lora-alpha", type=int)
ap.add_argument("--max-len", type=int, default=512)
ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()

travail = os.environ.get("SCRIBE_TRAVAIL", os.getcwd())
os.environ["SCRIBE_PAIRS"] = os.path.join(travail, args.pairs) if not os.path.isabs(args.pairs) else args.pairs
os.environ["SCRIBE_OUT"] = os.path.join(travail, args.out) if not os.path.isabs(args.out) else args.out
os.environ["SCRIBE_PROFIL"] = args.profil
os.environ["SCRIBE_EPOCHS"] = str(args.epochs)
os.environ["SCRIBE_MAXLEN"] = str(args.max_len)
os.environ["SCRIBE_LIMIT"] = str(args.limit)
for cle, val in (("SCRIBE_METHODE", args.methode), ("SCRIBE_BASE", args.base),
                 ("SCRIBE_BATCH", args.batch), ("SCRIBE_ACCUM", args.accum),
                 ("SCRIBE_LR", args.lr), ("SCRIBE_LORA_R", args.lora_r),
                 ("SCRIBE_LORA_ALPHA", args.lora_alpha)):
    if val is not None:
        os.environ[cle] = str(val)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_rocm  # noqa: E402  (importe torch et transformers)

train_rocm.main()
