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
              bf16, adaptateur de rang r sur les projections lineaires que le
              profil declare, fusionne dans les poids a la fin du run).
  lr/batch/accum  regles pour 32 Go de VRAM (la R9700). Surchargeables.
  template    kwargs passes a `apply_chat_template`. Qwen3 raisonne par
              defaut ; on coupe (`enable_thinking=False`) sinon la sortie
              commence par un bloc <think>. C'est ce champ qui absorbera une
              autre famille de modeles (Nemotron, Gemma) sans toucher au reste.

Champs facultatifs, absents des profils Qwen3 — leur defaut reproduit
exactement le comportement d'avant :
  lora_cibles  les projections a adapter. Une architecture hybride a des
               projections que la liste Qwen3 n'atteint pas ; les omettre ne
               leve aucune erreur, ca gele des couches en silence.
  lora_exclure des modules a ecarter d'une liste de cibles large.
  classe       la classe transformers a charger, quand `AutoModelForCausalLM`
               ne convient pas — un modele multimodal construit sa tour de
               vision par defaut, sa classe texte non.
  grad_ckpt    le gradient checkpointing. Un seul profil le coupe, pour une
               raison de version de transformers et non de memoire.

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

# Rang et alpha de l'adaptateur, communs aux profils LoRA. alpha = 2r est la
# convention la plus courante ; r=32 sur toutes les projections suffit pour
# apprendre un format de sortie, ce qui est tout ce qu'on demande ici.
LORA_DEFAUT = dict(r=32, alpha=64, dropout=0.05)

# Les projections qu'adapte un profil Qwen3 : attention et MLP. Sept noms
# courts, sans prefixe de couche — peft les resout par suffixe.
LORA_CIBLES = ["q_proj", "k_proj", "v_proj", "o_proj",
               "gate_proj", "up_proj", "down_proj"]

# Qwen3.5 est HYBRIDE : 18 de ses 24 couches sont a attention lineaire (gated
# delta net — `full_attention_interval: 4`), six seulement a attention pleine.
# Les sept noms ci-dessus n'en atteignent aucune, donc les omettre laisserait
# les trois quarts de la pile sans gradient. Mesure sur le checkpoint : ces dix
# noms resolvent 150 modules (6 x 4 + 18 x 3 + 24 x 3).
#
# Trois voisins sont ecartes a dessein, apres lecture des formes :
#   in_proj_a / in_proj_b  [16, 1024] — seize sorties, un rang de LoRA y est du
#                          bruit ; ce sont les scalaires par tete du delta rule.
#   conv1d                 une vraie nn.Conv1d [6144, 1, 4], pas un Linear.
#   A_log / dt_bias        des parametres, pas des Linear : jamais adaptables.
LORA_CIBLES_QWEN35 = LORA_CIBLES + ["in_proj_qkv", "in_proj_z", "out_proj"]

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
    # Qwen3.5-0.8B. Deux champs inedits ici : `classe` et `grad_ckpt`.
    #
    # `classe` — le depot publie est MULTIMODAL (100 M de tour de vision, 21 M
    # de tete MTP) mais la tache est du texte. `Qwen3_5ForCausalLM` est la
    # meme pile sans ces deux tours : elle declare
    # `_keys_to_ignore_on_load_unexpected = [r"^mtp.*", r"^model.visual.*"]`.
    # On charge donc 752 M, et le prefixe `mtp.*` qu'une liste de cibles par
    # nom court attraperait disparait avec la tete. La variante `-Base` (non
    # instruct) est le bon point de depart pour un SFT.
    #
    # `grad_ckpt=False` n'est pas un reglage de confort, c'est le contournement
    # du blocage : `qwen3_5` n'existe dans AUCUNE transformers 4.x (absent
    # jusqu'a v5.0.0 inclus, present a partir de v5.10.0) et 5.16/5.17 cassent
    # la recomputation du gradient checkpointing sur ce torch (`CheckpointError`,
    # journaux `train_en_v5_echec-*.log` — TRAINING.md §7). Couper le
    # checkpointing supprime le chemin fautif au lieu de le reparer ; un
    # adaptateur sur une base gelee de 752 M tient sans lui. Le lot passe a
    # 4 x 4 pour la meme raison : sans checkpointing c'est la memoire
    # d'activation qui contraint, pas les poids (meme lot effectif que mini).
    "qwen35": dict(base="Qwen/Qwen3.5-0.8B-Base", methode="lora",
                   depot="BudgieScribe-Qwen35", lr=1e-4, batch=4, accum=4,
                   template=_QWEN3, classe="Qwen3_5ForCausalLM", grad_ckpt=False,
                   lora_cibles=LORA_CIBLES_QWEN35),
}
NAMESPACE = "flowcorp-ch"


def nom_gguf(profil_nom, lang, quant="Q4_K_M"):
    """Le nom de fichier publie : BudgieScribe-Nano-fr-Q4_K_M.gguf."""
    return "%s-%s-%s.gguf" % (PROFILS[profil_nom]["depot"], lang, quant)


def profil(nom):
    if nom not in PROFILS:
        raise SystemExit("profil inconnu : %s (connus : %s)" % (nom, ", ".join(PROFILS)))
    p = dict(PROFILS[nom])
    p["nom"] = nom
    return p


# Les quatre champs facultatifs, lus par defaut plutot que par `prof[...]` :
# un profil qui ne les declare pas se comporte comme avant leur existence.

def lora_cibles(prof):
    """Les projections que l'adaptateur couvre. Defaut : la liste Qwen3."""
    return prof.get("lora_cibles", LORA_CIBLES)


def lora_exclure(prof):
    """Les modules a ecarter de `lora_cibles`. Aucun profil actuel n'en a."""
    return prof.get("lora_exclure")


def classe(prof):
    """La classe transformers a charger, ou None pour `AutoModelForCausalLM`."""
    return prof.get("classe")


def grad_ckpt(prof):
    """Le gradient checkpointing, actif sauf mention contraire du profil."""
    return prof.get("grad_ckpt", True)


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
    if classe(p):
        # Meme raison qu'a l'entrainement : la classe par defaut d'un modele
        # multimodal charge aussi sa tour de vision, inutile pour du texte.
        import importlib
        model = getattr(importlib.import_module("transformers"), classe(p)).from_pretrained(
            chemin, dtype=dtype).to(dev)
    else:
        model = AutoModelForCausalLM.from_pretrained(chemin, dtype=dtype).to(dev)
    model.eval()
    model.config.use_cache = True
    return tok, model, template
