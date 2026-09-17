# -*- coding: utf-8 -*-
"""Evaluation des blocs synthetiques — comparaison litterale, aucun juge.

L'ITN et les auto-corrections sont les deux seuls blocs du projet dont la
verite terrain est EXACTE : la paire a ete fabriquee en partant de la valeur,
donc la sortie attendue est connue au caractere pres. On mesure par egalite de
chaines, pas par lecture, et ca ne coute rien.

Trois chiffres, qui ne disent pas la meme chose :

  EXACT     la sortie est identique a l'attendu. Barre haute.
  VALEURS   tous les nombres attendus sont la, aucun nombre etranger n'apparait.
            Barre de SURETE : « 14 h 30 » au lieu de « 14h30 » se trompe de
            forme, pas de fait.
  TRANCHE   pour les auto-corrections : la valeur ABANDONNEE a-t-elle disparu ?
            C'est la question propre a ce bloc — un modele qui repond
            « vendredi, non pardon, jeudi » a tout garde, donc il a echoue,
            meme si la valeur retenue est bien la.

Usage : eval_synth.py <modele|base> <paires.jsonl> [n]
"""
import collections, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
os.environ.setdefault("HF_HOME", os.path.join(SP, "..", "hf"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrainement"))
import modeles                 # profils, chargement, construction du prompt

SYSTEM = modeles.SYSTEM     # gen_rocm l'importe d'ici
NUM = re.compile(r"\d[\d  ]*(?:,\d+)?")
# Les marqueurs qui separent la valeur abandonnee de la valeur retenue.
# Une table par langue, choisie par le champ `lang` de chaque paire : les
# generateurs anglais (gen_correction_en.py) utilisent les marqueurs de la
# spec du format (« no wait », « sorry », « make that », « I mean »...).
MARQUEURS_PAR_LANGUE = {
    "fr": re.compile(
        r"\b(non pardon|pardon|excuse-moi|enfin non|enfin plut\w+|enfin|"
        r"ou alors plut\w+|ou plut\w+|je veux dire|je voulais dire|"
        r"c'est-\w-dire|non non|non)\b", re.I),
    "en": re.compile(
        r"\b(no wait make that|no wait|no sorry|sorry|my mistake|correction|"
        r"well actually|no actually|i mean actually|actually|or rather|"
        r"or actually|make that|rather|i mean to say|i meant|i mean|that is|"
        r"no no|no)\b", re.I),
}
MARQUEURS = MARQUEURS_PAR_LANGUE["fr"]


def choisir_gpu():
    if not torch.cuda.is_available():
        return None
    if os.environ.get("ROCM_DEVICE"):
        return int(os.environ["ROCM_DEVICE"])
    best, score = 0, (-1, -1)
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        nom = (p.name or "") + " " + str(getattr(p, "gcnArchName", ""))
        s = (2 if "gfx12" in nom or "R9700" in nom else 0, p.total_memory)
        if s > score:
            best, score = i, s
    return best


def nombres(s):
    out = []
    for m in NUM.finditer(s):
        v = m.group(0).replace(" ", "").replace(" ", "").rstrip(",")
        if v:
            out.append(v)
    return collections.Counter(out)


def valeur_abandonnee(dirty, lang="fr"):
    """Le segment AVANT le marqueur de correction — ce qui doit disparaitre."""
    m = MARQUEURS_PAR_LANGUE.get(lang, MARQUEURS).search(dirty)
    if not m:
        return None
    avant = dirty[:m.start()].strip()
    mots = [w for w in re.findall(r"[\w'’-]+", avant) if len(w) > 2]
    return mots[-1].lower() if mots else None


def main():
    which = sys.argv[1]
    paires = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_correction.jsonl")
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    gi = choisir_gpu()
    if gi is None:
        dev, ou = "cpu", "CPU"
        torch.set_num_threads(os.cpu_count())
    else:
        dev = torch.device("cuda:%d" % gi)
        ou = torch.cuda.get_device_properties(gi).name

    rows = [json.loads(l) for l in open(paires, encoding="utf-8")]
    rows = [r for r in rows if r.get("held_out")]
    if limit:
        rows = rows[:limit]

    # `base`, `base:<profil>` ou un dossier entraine (sa base et son dtype
    # viennent de son run.json) — voir modeles.charger.
    tok, model, template = modeles.charger(which, dev)
    path = modeles.resoudre(which)[0]     # nomme le fichier de resultats
    print("%s sur %s : %d cas tenus a l'ecart de %s"
          % (which, ou, len(rows), os.path.basename(paires)), flush=True)

    stats = collections.Counter()
    par_fam = collections.defaultdict(collections.Counter)
    fautes = []
    t0 = time.time()
    for i, r in enumerate(rows):
        prompt = modeles.construire_prompt(tok, r["control"], r["dirty"], template)
        ids = tok(prompt, return_tensors="pt").to(dev)
        with torch.no_grad():
            out = model.generate(**ids,
                                 max_new_tokens=min(140, int(1.3 * ids.input_ids.shape[1]) + 32),
                                 do_sample=False, use_cache=True,
                                 pad_token_id=tok.eos_token_id)
        got = tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()
        fam = r["file"].split("-", 1)[-1]
        want = r["clean"]

        exact = got.strip() == want.strip()
        nw, ng = nombres(want), nombres(got)
        valeurs = (nw == ng)
        invente = bool(ng - nw)

        # TRANCHE : la valeur abandonnee a-t-elle disparu de la sortie ?
        ab = valeur_abandonnee(r["dirty"], r.get("lang", "fr"))
        tranche = None
        if ab and ab not in want.lower():
            tranche = ab not in got.lower()

        for cle, val in (("exact", exact), ("valeurs", valeurs), ("invente", invente)):
            stats[cle] += val
            par_fam[fam][cle] += val
        stats["n"] += 1
        par_fam[fam]["n"] += 1
        if tranche is not None:
            stats["tranche_n"] += 1
            stats["tranche_ok"] += tranche
            par_fam[fam]["tranche_n"] += 1
            par_fam[fam]["tranche_ok"] += tranche
        if not exact and len(fautes) < 80:
            fautes.append({"famille": fam, "entree": r["dirty"],
                           "attendu": want, "obtenu": got,
                           "a_tranche": tranche})
        if (i + 1) % 100 == 0:
            print("   %d/%d (%.1f min)" % (i + 1, len(rows), (time.time() - t0) / 60), flush=True)

    n = max(1, stats["n"])
    print("\n=== %s — %d cas ===" % (which, n))
    print("EXACT            %4d  %5.1f%%" % (stats["exact"], 100 * stats["exact"] / n))
    print("VALEURS justes   %4d  %5.1f%%" % (stats["valeurs"], 100 * stats["valeurs"] / n))
    print("NOMBRE INVENTE   %4d  %5.1f%%" % (stats["invente"], 100 * stats["invente"] / n))
    if stats["tranche_n"]:
        print("A TRANCHE        %4d/%-4d %5.1f%%   <-- la valeur abandonnee a disparu"
              % (stats["tranche_ok"], stats["tranche_n"],
                 100 * stats["tranche_ok"] / stats["tranche_n"]))
    print()
    print("%-20s %5s %8s %9s %9s" % ("famille", "n", "exact", "valeurs", "tranche"))
    for fam in sorted(par_fam):
        c = par_fam[fam]
        tr = ("%7.0f%%" % (100 * c["tranche_ok"] / c["tranche_n"])) if c["tranche_n"] else "      -"
        print("%-20s %5d %7.0f%% %8.0f%% %9s"
              % (fam, c["n"], 100 * c["exact"] / c["n"], 100 * c["valeurs"] / c["n"], tr))

    dst = os.path.join(SP, "evalsynth_%s_%s.json"
                       % (os.path.basename(str(path)).replace("/", "_"),
                          os.path.basename(paires).replace(".jsonl", "")))
    json.dump({"model": str(path), "paires": paires, "stats": dict(stats),
               "par_famille": {k: dict(v) for k, v in par_fam.items()},
               "fautes": fautes[:60]},
              open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if fautes:
        print("\n=== 4 fautes ===")
        for f in fautes[:4]:
            print("  [%s] %s" % (f["famille"], f["entree"][:95]))
            print("      attendu : %s" % f["attendu"][:95])
            print("      obtenu  : %s" % f["obtenu"][:95])
    print("\n-> %s" % dst)


if __name__ == "__main__":
    main()
