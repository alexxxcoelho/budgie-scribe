# -*- coding: utf-8 -*-
"""Profils de modeles : la seule table qui sache QUEL modele de base on entraine.

POURQUOI CE FICHIER
Jusqu'au 2026-09-17, `Qwen/Qwen3-0.6B` etait code en dur dans quatre scripts
(train_rocm, eval_synth, eval_itn, gen_rocm). Passer a un 1.7B ou un 4B
demandait de les editer tous, et d'oublier l'un d'eux donnait une evaluation
du mauvais modele sans aucune erreur. Ici : un nom de profil, une table, et
tout le monde lit la meme ligne.

CE QU'UN PROFIL DECIDE
  base        le depot Hugging Face du modele de depart.
  methode     `full` (tous les poids, fp32 + AdamW) ou `lora` (base gelee en
              bf16, adaptateur de rang r sur toutes les projections lineaires,
              fusionne dans les poids a la fin du run).
  lr/batch/accum  regles pour 32 Go de VRAM (la R9700). Surchargeables.
  template    kwargs passes a `apply_chat_template`. Qwen3 raisonne par
              defaut ; on coupe (`enable_thinking=False`) sinon la sortie
              commence par un bloc <think>. C'est ce champ qui absorbera une
              autre famille de modeles (Nemotron, Gemma) sans toucher au reste.

POURQUOI LORA AU-DELA DE NANO
Le full SFT garde les poids en fp32 et l'etat AdamW en fp32 : 16 octets par
parametre. 0.6B -> ~10 Go, ca tient. 1.7B -> ~27 Go plus les activations, et
ROCm deborde sur la RAM hote sans erreur (mesure le 2026-09-03 : 5x plus lent,
zero avertissement). 4B -> 64 Go, 8B -> 128 Go : impossible sur une carte.
LoRA gele la base en bf16 (2 octets/param) et n'optimise que l'adaptateur :
8B -> ~18 Go. Et il preserve ce que la base sait — a 0.6B en full SFT, une
seconde langue ecrasait la premiere (TRAINING.md §0) ; en LoRA, la base reste
intacte sous l'adaptateur.

Le dossier ecrit par un run LoRA est un modele FUSIONNE, chargeable par
`from_pretrained` comme un run full : `gguf`, `eval-itn`, `eval-ab` ne font
pas la difference. L'adaptateur seul est garde dans `<out>/adaptateur/` pour
un service vLLM qui prefere charger base + adaptateur.
"""
import json
import os

SYSTEM = (
    "You are a text normalizer for speech-to-text transcripts. The input begins "
    "with a control line specifying the styling, structure, and context settings; "
    "clean the transcript to match those settings and output only the cleaned text."
)

_QWEN3 = {"enable_thinking": False}

# `depot` : le depot Hugging Face de la famille, sous flowcorp-ch. Un depot
# par famille, les deux langues dedans (BudgieScribe-Nano-fr-Q4_K_M.gguf,
# BudgieScribe-Nano-en-Q4_K_M.gguf). release/models/manifest.json porte les
# memes noms : c'est lui que la CI de publication lit.
PROFILS = {
    # Le profil publie (BudgieScribe-Nano). Full SFT, fp32 : ne pas toucher,
    # les chiffres de MODELS.md en dependent.
    "nano": dict(base="Qwen/Qwen3-0.6B", methode="full", depot="BudgieScribe-Nano",
                 lr=1e-5, batch=8, accum=2, template=_QWEN3),
    "mini": dict(base="Qwen/Qwen3-1.7B", methode="lora", depot="BudgieScribe-Mini",
                 lr=1e-4, batch=8, accum=2, template=_QWEN3),
    "standard": dict(base="Qwen/Qwen3-4B", methode="lora", depot="BudgieScribe",
                     lr=1e-4, batch=4, accum=4, template=_QWEN3),
    "large": dict(base="Qwen/Qwen3-8B", methode="lora", depot="BudgieScribe-Large",
                  lr=1e-4, batch=2, accum=8, template=_QWEN3),
}
NAMESPACE = "flowcorp-ch"


def nom_gguf(profil_nom, lang, quant="Q4_K_M"):
    """Le nom de fichier publie : BudgieScribe-Nano-fr-Q4_K_M.gguf."""
    return "%s-%s-%s.gguf" % (PROFILS[profil_nom]["depot"], lang, quant)

# Rang et alpha de l'adaptateur, communs aux profils LoRA. alpha = 2r est la
# convention la plus courante ; r=32 sur toutes les projections suffit pour
# apprendre un format de sortie, ce qui est tout ce qu'on demande ici.
LORA_DEFAUT = dict(r=32, alpha=64, dropout=0.05)
LORA_CIBLES = ["q_proj", "k_proj", "v_proj", "o_proj",
               "gate_proj", "up_proj", "down_proj"]


def profil(nom):
    if nom not in PROFILS:
        raise SystemExit("profil inconnu : %s (connus : %s)" % (nom, ", ".join(PROFILS)))
    p = dict(PROFILS[nom])
    p["nom"] = nom
    return p


def profil_env():
    """Le profil demande par l'environnement, `nano` sinon — le comportement
    d'avant ce fichier."""
    return profil(os.environ.get("SCRIBE_PROFIL", "nano"))


def lire_run(chemin):
    """Le run.json d'un modele entraine, ou {} pour un depot HF ou un dossier
    d'avant ce fichier (qui ne le portait pas)."""
    try:
        return json.load(open(os.path.join(chemin, "run.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def resoudre(quoi):
    """`base`, `base:<profil>` ou un chemin de modele -> (chemin, profil, template).

    Pour un modele entraine, la base et le template viennent de son run.json :
    un banc lance sur un candidat `mini` compare a la base 1.7B, pas a la 0.6B.
    Un dossier sans run.json (run anterieur) est traite comme `nano`.
    """
    if quoi == "base" or quoi.startswith("base:"):
        p = profil(quoi.split(":", 1)[1]) if ":" in quoi else profil_env()
        return p["base"], p, p["template"]
    run = lire_run(quoi)
    p = profil(run.get("profil", "nano"))
    if run.get("base"):
        p["base"] = run["base"]
    return quoi, p, run.get("template", p["template"])


def construire_prompt(tok, control, dirty, template):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "%s\n%s" % (control, dirty)}]
    return tok.apply_chat_template(messages, tokenize=False,
                                   add_generation_prompt=True, **template)


def charger(quoi, dev):
    """(tokenizer, modele, template) pret pour l'inference.

    Le dtype suit ce qui a ete entraine : un run full est ecrit en fp32 et se
    relit en fp32 (les chiffres publies ont ete mesures ainsi) ; un run LoRA
    fusionne est ecrit en bf16 et se relit en bf16 — un 8B en fp32 ferait
    32 Go et ne tiendrait pas sur la carte. `dtype="auto"` lit le dtype du
    config.json ecrit par save_pretrained. Une base HF brute s'aligne sur la
    methode de son profil.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    chemin, p, template = resoudre(quoi)
    if chemin == p["base"] and not lire_run(quoi):
        dtype = torch.float32 if p["methode"] == "full" else torch.bfloat16
    else:
        dtype = "auto"
    tok = AutoTokenizer.from_pretrained(chemin)
    model = AutoModelForCausalLM.from_pretrained(chemin, dtype=dtype).to(dev)
    model.eval()
    model.config.use_cache = True
    return tok, model, template
