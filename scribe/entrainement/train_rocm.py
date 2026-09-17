# -*- coding: utf-8 -*-
"""SFT d'un profil BudgieScribe (nano/mini/standard/large) sur ROCm, CUDA ou MPS.

PROFILS ET METHODES — voir `modeles.py`. Le modele de base, la methode
(`full` ou `lora`) et les hyperparametres par defaut viennent du profil
(SCRIBE_PROFIL, `nano` par defaut = le comportement historique) ; SCRIBE_BASE,
SCRIBE_METHODE, SCRIBE_LR, SCRIBE_BATCH, SCRIBE_ACCUM, SCRIBE_LORA_R et
SCRIBE_LORA_ALPHA surchargent. En `lora`, la base est gelee en bf16, seul
l'adaptateur s'entraine, et il est FUSIONNE dans les poids a la sauvegarde :
le dossier ecrit se charge comme un run full.

POURQUOI CE FICHIER
`train_dml.py` passait par torch-directml, qui epingle torch 2.4.1 et n'a pas
les noyaux `_foreach_*` : chaque pas d'optimiseur retombait sur le CPU. Il
tournait en fp32, un exemple a la fois, et mettait 182 min pour 10 281 unites.

ROCm 7.14 existe en roue Windows NATIVE (`torch 2.12.0+rocm7.14.0`). Trois
leviers s'ouvrent, tous recommandes par le playbook AMD :

  bf16 par autocast   les poids restent en fp32 — donc pas de derive des
                      petits gradients — mais les matmuls tournent en bf16.
                      gfx1201 le supporte materiellement.
  vrais lots          DirectML traitait un exemple a la fois ; a sequence
                      courte, le GPU passait son temps a attendre. Les lots
                      sont ici construits par LONGUEUR VOISINE, pour que le
                      remplissage coute le moins possible.
  AdamW fuse          un seul noyau pour tout l'etat de l'optimiseur, au lieu
                      d'une boucle Python par tenseur.

ATTENTION AU CHOIX D'APPAREIL : la machine expose DEUX GPU AMD. `cuda:0` est
l'iGPU (gfx1036), `cuda:1` la R9700 (gfx1201). Prendre le premier venu
entrainerait sur l'iGPU, lentement et sans qu'aucune erreur ne le signale.
"""
import json, math, os, random, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
os.environ.setdefault("HF_HOME", os.path.join(SP, "..", "hf"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modeles                 # profils, SYSTEM, construction du prompt

SEED = 20260901


def choisir_gpu():
    """La carte dediee, jamais l'iGPU — meme si l'iGPU est cuda:0."""
    if not torch.cuda.is_available():
        raise SystemExit("aucun GPU visible par torch")
    forced = os.environ.get("ROCM_DEVICE")
    if forced:
        return int(forced)
    meilleur, taille = 0, -1
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        nom = (p.name or "") + " " + str(getattr(p, "gcnArchName", ""))
        # la R9700 est gfx1201 ; l'iGPU gfx1036 rapporte une memoire PARTAGEE
        # enorme sans en avoir l'usage, donc on ne peut pas trier par taille
        # seule : on cherche la carte discrete par son architecture.
        score = (2 if "gfx12" in nom or "R9700" in nom else 0, p.total_memory)
        if score > (taille if isinstance(taille, tuple) else (-1, -1)):
            meilleur, taille = i, score
    return meilleur


def load_pairs(path, eval_ratio=0.2):
    """Decoupe entrainement/evaluation, avec DEUX regimes selon l'origine.

    Un `held_out` explicite fait foi : les paires synthetiques le portent deja,
    tire PAR FAMILLE, et deux nombres au hasard ne partagent aucune fuite. Le
    decoupage par fichier ne s'applique qu'au reste — sans quoi les 10 000
    paires ITN, qui n'ont que neuf valeurs de `file`, verraient trois familles
    entieres partir en evaluation d'un coup.
    """
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    explicit = [r for r in rows if "held_out" in r]
    implicit = [r for r in rows if "held_out" not in r]

    rng = random.Random(SEED)
    held_files = set()
    if implicit:
        files = sorted({r["file"] for r in implicit})
        rng.shuffle(files)
        held_files = set(files[:max(1, round(len(files) * eval_ratio))])

    train = ([r for r in explicit if not r["held_out"]]
             + [r for r in implicit if r["file"] not in held_files])
    evalset = ([r for r in explicit if r["held_out"]]
               + [r for r in implicit if r["file"] in held_files])
    return train, evalset, held_files


def encode(tok, row, max_len, template):
    """(input_ids, labels), labels masques sur le prompt."""
    prompt = modeles.construire_prompt(tok, row["control"], row["dirty"], template)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    c_ids = tok(row["clean"] + tok.eos_token, add_special_tokens=False)["input_ids"]
    ids = (p_ids + c_ids)[:max_len]
    labels = ([-100] * len(p_ids) + c_ids)[:max_len]
    return ids, labels


def faire_lots(encoded, taille, rng):
    """Lots de longueurs VOISINES, puis melange des lots.

    Grouper au hasard ferait remplir chaque lot jusqu'a la plus longue de ses
    sequences : sur un corpus ou l'ITN fait 30 tokens et une unite SUMM-RE 400,
    le remplissage couterait plus que le calcul. On trie par longueur, on
    decoupe, puis on melange l'ORDRE DES LOTS — le hasard reste, le gaspillage
    part.
    """
    idx = sorted(range(len(encoded)), key=lambda i: len(encoded[i][0]))
    lots = [idx[i:i + taille] for i in range(0, len(idx), taille)]
    rng.shuffle(lots)
    return lots


def coller(encoded, lot, pad_id, dev):
    n = max(len(encoded[i][0]) for i in lot)
    x = torch.full((len(lot), n), pad_id, dtype=torch.long)
    y = torch.full((len(lot), n), -100, dtype=torch.long)
    m = torch.zeros((len(lot), n), dtype=torch.long)
    for k, i in enumerate(lot):
        ids, lab = encoded[i]
        x[k, :len(ids)] = torch.tensor(ids)
        y[k, :len(lab)] = torch.tensor(lab)
        m[k, :len(ids)] = 1
    return x.to(dev), y.to(dev), m.to(dev)


def main():
    prof = modeles.profil_env()
    base = os.environ.get("SCRIBE_BASE") or prof["base"]
    methode = os.environ.get("SCRIBE_METHODE") or prof["methode"]
    if methode not in ("full", "lora"):
        raise SystemExit("SCRIBE_METHODE doit valoir full ou lora, pas %r" % methode)
    template = prof["template"]
    lora_r = int(os.environ.get("SCRIBE_LORA_R", modeles.LORA_DEFAUT["r"]))
    lora_alpha = int(os.environ.get("SCRIBE_LORA_ALPHA", modeles.LORA_DEFAUT["alpha"]))

    pairs_path = os.environ.get("SCRIBE_PAIRS", os.path.join(SP, "pairs_mix.jsonl"))
    out_dir = os.environ.get("SCRIBE_OUT", os.path.join(SP, "scribe-rocm"))
    epochs = float(os.environ.get("SCRIBE_EPOCHS", "2"))
    max_len = int(os.environ.get("SCRIBE_MAXLEN", "512"))
    batch = int(os.environ.get("SCRIBE_BATCH", prof["batch"]))
    accum = int(os.environ.get("SCRIBE_ACCUM", prof["accum"]))
    lr = float(os.environ.get("SCRIBE_LR", prof["lr"]))
    limit = int(os.environ.get("SCRIBE_LIMIT", "0"))
    print("profil : %s | base : %s | methode : %s%s"
          % (prof["nom"], base, methode,
             " (r=%d, alpha=%d)" % (lora_r, lora_alpha) if methode == "lora" else ""))

    # Un juge encore charge retient ~7 Go de VRAM et fait tomber le debit de
    # 25 a 5 unites/s — CINQ FOIS plus lent, sans aucune erreur ni
    # avertissement. Sur 34 Go la place parait suffisante, mais ROCm deborde
    # sur la memoire hote plutot que d'echouer proprement. Mesure le
    # 2026-09-03, une heure perdue avant de comprendre.
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8899/health", timeout=2)
        print("")
        print("!!! un llama-server repond sur :8899 et retient de la VRAM.")
        print("!!! attendez-vous a ~5x plus lent.")
        print("!!! arretez-le d'abord :  .\\juge.ps1 arreter")
        print("", flush=True)
    except Exception:
        pass

    # Choix de l'appareil, generique : CUDA/ROCm (torch les expose tous deux
    # comme `cuda`), sinon MPS (Apple), sinon CPU — le meme script tourne sur
    # la Radeon du projet, sur une carte Nvidia, sur un Mac ou sur HF Jobs.
    if torch.cuda.is_available():
        gi = choisir_gpu()
        dev = torch.device("cuda:%d" % gi)
        p = torch.cuda.get_device_properties(gi)
        print("appareil : cuda:%d %s (%s, %.0f Go)"
              % (gi, p.name, getattr(p, "gcnArchName", "?"), p.total_memory / 1e9))
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        dev = torch.device("mps")
        print("appareil : mps (Apple)")
    else:
        dev = torch.device("cpu")
        print("appareil : cpu — un tour complet prendra des heures")

    torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(base)
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    train, evalset, held = load_pairs(pairs_path)
    if limit:
        train = random.Random(SEED).sample(train, min(limit, len(train)))
    print("entrainement : %d unites | evaluation : %d unites (%d fichiers tenus a l'ecart)"
          % (len(train), len(evalset), len(held)))

    if methode == "full":
        # Poids fp32, matmuls bf16 par autocast : pas de derive des petits
        # gradients. 16 octets/param avec AdamW — reserve aux petits modeles.
        model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.float32).to(dev)
    else:
        # Base gelee en bf16 (2 octets/param), adaptateur LoRA en fp32 sur
        # toutes les projections lineaires. `enable_input_require_grads` est
        # indispensable avec le gradient checkpointing : sinon aucune
        # activation ne requiert de gradient a l'entree du premier bloc et
        # l'adaptateur ne recoit rien — perte constante, aucune erreur.
        from peft import LoraConfig, get_peft_model
        model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16).to(dev)
        model.enable_input_require_grads()
        model = get_peft_model(model, LoraConfig(
            r=lora_r, lora_alpha=lora_alpha, lora_dropout=modeles.LORA_DEFAUT["dropout"],
            target_modules=modeles.LORA_CIBLES, task_type="CAUSAL_LM"))
        model.print_trainable_parameters()   # peft garde l'adaptateur en fp32
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    model.train()
    entrainables = [prm for prm in model.parameters() if prm.requires_grad]
    try:
        opt = torch.optim.AdamW(entrainables, lr=lr, fused=True)
        print("optimiseur : AdamW fuse")
    except (RuntimeError, ValueError):
        opt = torch.optim.AdamW(entrainables, lr=lr)
        print("optimiseur : AdamW standard (fusion indisponible)")

    encoded = [encode(tok, r, max_len, template) for r in train]
    rng = random.Random(SEED)
    lots_par_epoque = math.ceil(len(encoded) / batch)
    total_steps = int(math.ceil(lots_par_epoque / accum) * epochs)
    warmup = max(1, int(0.06 * total_steps))
    print("lots de %d, accumulation %d -> %d pas d'optimiseur (chauffe %d)"
          % (batch, accum, total_steps, warmup))

    def lr_at(step):
        if step < warmup:
            return lr * step / warmup
        q = (step - warmup) / max(1, total_steps - warmup)
        return lr * 0.5 * (1 + math.cos(math.pi * min(1.0, q)))

    t0 = time.time()
    step, vus, logged = 0, 0, []
    for epoch in range(math.ceil(epochs)):
        acc_loss, acc_n = 0.0, 0
        for k, lot in enumerate(faire_lots(encoded, batch, rng)):
            x, y, m = coller(encoded, lot, pad_id, dev)
            # bf16 sur les matmuls, fp32 sur les poids et l'optimiseur.
            with torch.autocast(device_type=dev.type if dev.type != "mps" else "cpu", dtype=torch.bfloat16):
                loss = model(input_ids=x, attention_mask=m, labels=y).loss / accum
            loss.backward()
            acc_loss += float(loss.detach()) * accum
            acc_n += 1
            vus += len(lot)
            if (k + 1) % accum == 0:
                for g in opt.param_groups:
                    g["lr"] = lr_at(step)
                torch.nn.utils.clip_grad_norm_(entrainables, 1.0)
                opt.step()
                opt.zero_grad(set_to_none=True)
                step += 1
                if step % 20 == 0:
                    msg = ("step %4d/%d | perte %.4f | lr %.2e | %.1f min | %.0f unites/s"
                           % (step, total_steps, acc_loss / max(1, acc_n), lr_at(step),
                              (time.time() - t0) / 60, vus / max(1e-9, time.time() - t0)))
                    print(msg, flush=True)
                    logged.append({"step": step, "loss": acc_loss / max(1, acc_n)})
                acc_loss, acc_n = 0.0, 0
            if step >= total_steps:
                break
        if step >= total_steps:
            break

    minutes = (time.time() - t0) / 60
    print("entraine en %.1f min (%.0f unites/s, %d unites vues)"
          % (minutes, vus / max(1e-9, time.time() - t0), vus))
    os.makedirs(out_dir, exist_ok=True)
    model.to("cpu")
    if methode == "lora":
        # L'adaptateur seul d'abord (quelques dizaines de Mo, ce qu'un vLLM
        # charge sur la base), puis la fusion : le dossier de sortie devient
        # un modele complet en bf16, que gguf/eval chargent comme un run full.
        model.save_pretrained(os.path.join(out_dir, "adaptateur"))
        model = model.merge_and_unload()
        model = model.to(torch.bfloat16)
    # use_cache doit repartir a True : le desactiver est un besoin du gradient
    # checkpointing pendant l'entrainement, pas une propriete du modele livre.
    # Oublie une fois, il a fait passer une generation de 4 s a 10 min.
    model.config.use_cache = True
    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    json.dump({"minutes": minutes, "steps": total_steps, "train_units": len(train),
               "device": "%s:%s" % (dev.type, getattr(p, "gcnArchName", "?") if dev.type == "cuda" else "-"),
               "profil": prof["nom"], "base": base, "methode": methode,
               "lora": {"r": lora_r, "alpha": lora_alpha} if methode == "lora" else None,
               "template": template, "lr": lr,
               "batch": batch, "accum": accum,
               "dtype": "bf16-autocast" if methode == "full" else "bf16-base+lora-fp32",
               "log": logged},
              open(os.path.join(out_dir, "run.json"), "w"), indent=2)
    print("modele ecrit -> %s" % out_dir)


if __name__ == "__main__":
    main()
