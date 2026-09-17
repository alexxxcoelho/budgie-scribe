# -*- coding: utf-8 -*-
"""Banc du PROFESSEUR — un modele local peut-il produire le cote propre ?

JUGER ET ENSEIGNER SONT DEUX TACHES DIFFERENTES
`gemma-12b-qat` a ete mesure comme JUGE (§0.17, §0.18) : il classe. Le
professeur, lui, PRODUIT le texte que le modele copiera mot pour mot. Une
erreur de juge ecarte une bonne paire ; une erreur de professeur enseigne une
faute a 5 000 exemplaires. Le banc doit donc etre plus severe, pas moins.

DEUX FAMILLES DE MESURE, ET ELLES NE PESENT PAS PAREIL

  INVARIANTS DETERMINISTES — sans arbitre, et indifferents a la spec.
    valeurs      tout nombre de l'entree se retrouve en sortie ; aucun nombre
                 etranger. C'est la faute la plus grave : un montant faux passe
                 inapercu a la relecture.
    invention    un mot de contenu apparait sans contrepartie dans l'entree.
    amputation   la sortie perd une part substantielle de l'entree — un
                 professeur qui resume est disqualifie.
    polarite     une negation retournee ou ajoutee.
    langue       la sortie doit rester dans la langue de l'entree.
    obeissance   l'entree contient un ordre ou une question ; la sortie y
                 repond au lieu de la normaliser.
    vide         sortie vide sur une entree qui porte du contenu.

  COMPARAISON A DEEPSEEK — similarite, pas verite.
    Restreinte aux cas SANS NOMBRE. La spec a change le 2026-09-02 (l'ITN est
    passe de « ne pas y toucher » a « convertir ») et les cotes propres de
    DeepSeek datent d'avant. Sur un cas numerique, l'ecart viendrait de la
    REGLE, pas du modele. Sans nombre, les deux specs coincident.

Usage : bench_prof.py <nom> [n] [port]
"""
import collections, json, os, queue, re, sys, threading, time, unicodedata
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
import spec
from valider_paires import mots, racine, HESITATIONS, NOMBRES_MOTS, SYNONYMES

URL = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:8899") + "/v1/chat/completions"
WORKERS = int(os.environ.get("PROF_WORKERS", "4"))
SEED = 20260903

NUM = re.compile(r"\d[\d  ]*(?:,\d+)?")
NEG = re.compile(r"\b(ne|n'|pas|jamais|aucun|aucune|rien|personne|plus|ni)\b", re.I)
ANGLAIS = re.compile(r"\b(the|and|with|this|that|from|have|will|would|about|"
                     r"because|there|which|these|those)\b", re.I)


def valeurs(s):
    """Valeurs numeriques, espaces de milliers retires."""
    out = []
    for m in NUM.finditer(s):
        v = m.group(0).replace(" ", "").replace(" ", "").rstrip(",")
        if v:
            out.append(v)
    return collections.Counter(out)


def appelle(modele, systeme, user, essais=3):
    corps = json.dumps({
        "model": modele,
        "messages": [{"role": "system", "content": systeme},
                     {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": 1200,
        # Gemma raisonne dans `reasoning_content` : laissee libre, la reflexion
        # epuise le budget et `content` revient vide.
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "none",
    }).encode("utf-8")
    for k in range(essais):
        try:
            req = urllib.request.Request(
                URL, data=corps, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                p = json.load(r)
            return (p["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            if k == essais - 1:
                return None
            time.sleep(1.5 * (k + 1))


def controle(r):
    """Les trois axes de la ligne de consigne, tels qu'ils sont dans la paire."""
    m = dict(re.findall(r"\[(\w+): ([\w-]+)\]", r["control"]))
    return (m.get("Styling", "semi-formal"), m.get("Structure", "prose"),
            m.get("Context", "general"))


def main():
    nom = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    paires = [json.loads(l) for l in open(os.path.join(SP, "pairs_mix4.jsonl"),
                                          encoding="utf-8")]
    verdicts = {json.loads(l)["id"]: (json.loads(l).get("verdict") or "").upper()
                for l in open(os.path.join(SP, "verdicts_reel_binaire.jsonl"),
                              encoding="utf-8")}
    # On ne mesure QUE sur des entrees dont on sait qu'elles sont propres :
    # juger un professeur sur une transcription verolee mesurerait le bruit.
    base = [r for r in paires
            if r.get("source") == "summre" and verdicts.get(r["id"]) == "OK"]
    import random
    base = random.Random(SEED).sample(base, min(n, len(base)))
    print("\n=== professeur %s — %d entrees, toutes jugees OK ===" % (nom, len(base)),
          flush=True)

    q = queue.Queue()
    for r in base:
        q.put(r)
    out, lock = [], threading.Lock()

    def worker():
        while True:
            try:
                r = q.get_nowait()
            except queue.Empty:
                return
            st, sr, cx = controle(r)
            systeme = spec.teacher_prompt(st, sr, cx)
            got = appelle(nom, systeme, "%s\n%s" % (r["control"], r["dirty"]))
            with lock:
                out.append((r, got))
                k = len(out)
            if k % 30 == 0:
                print("   %d/%d" % (k, len(base)), flush=True)

    t0 = time.time()
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    c = collections.Counter()
    fautes = collections.defaultdict(list)
    for r, got in out:
        c["n"] += 1
        if got is None:
            c["erreur_reseau"] += 1
            continue
        d, g = r["dirty"], got
        if not g.strip() and d.strip():
            c["vide"] += 1
            fautes["vide"].append(r["id"])
            continue

        # VALEURS — la faute la plus grave.
        # Un chiffre absent de l'entree n'est une invention QUE si l'entree ne
        # dictait pas ce nombre en lettres : « six mois » -> « 6 mois » est la
        # conversion ITN exigee par la spec depuis le 2026-09-02, pas une
        # valeur inventee. Sans ce garde-fou, on compte comme faute grave le
        # respect de la regle — piege verifie sur 093c_EBPZ_204#028.
        vd, vg = valeurs(d), valeurs(g)
        dicte_en_lettres = bool(set(mots(d)) & NOMBRES_MOTS)
        if (vg - vd) and not dicte_en_lettres:
            c["valeur_inventee"] += 1
            fautes["valeur_inventee"].append((r["id"], sorted((vg - vd).elements())[:3]))

        # INVENTION lexicale
        md, mg = set(mots(d)), set(mots(g))
        rd = {racine(x) for x in md}
        inv = {x for x in (mg - md) - HESITATIONS - NOMBRES_MOTS
               if racine(x) not in rd and SYNONYMES.get(x) not in md}
        # les formules d'e-mail sont exigees par la consigne
        if "email" in r["control"]:
            inv -= {"bonjour", "cordialement"}
        if inv:
            c["invention"] += 1
            fautes["invention"].append((r["id"], sorted(inv)[:4]))

        # AMPUTATION — un professeur qui resume est disqualifie
        if len(g.split()) < 0.6 * len(d.split()):
            c["amputation"] += 1
            fautes["amputation"].append((r["id"], "%d -> %d mots"
                                         % (len(d.split()), len(g.split()))))

        # POLARITE
        if abs(len(NEG.findall(d)) - len(NEG.findall(g))) > max(1, 0.4 * len(NEG.findall(d))):
            c["polarite"] += 1
            fautes["polarite"].append(r["id"])

        # LANGUE — bascule vers l'anglais
        if len(ANGLAIS.findall(g)) > len(ANGLAIS.findall(d)) + 2:
            c["langue"] += 1
            fautes["langue"].append(r["id"])

        # OBEISSANCE — l'entree pose une question, la sortie y repond
        if "?" in d and len(g.split()) > 1.6 * len(d.split()):
            c["obeissance_possible"] += 1

        c["ok"] += 1 if not ((vg - vd) and not dicte_en_lettres) and not inv else 0

    n_ = max(1, c["n"])
    print("\n  --- %s ---" % nom)
    print("  entrees mesurees        %5d" % c["n"])
    for cle, libelle in (("valeur_inventee", "VALEUR inventee   <-- la faute grave"),
                         ("invention", "invention lexicale"),
                         ("amputation", "amputation (<60 % des mots)"),
                         ("polarite", "polarite de negation"),
                         ("langue", "bascule en anglais"),
                         ("vide", "sortie vide a tort"),
                         ("erreur_reseau", "erreur reseau")):
        print("  %-32s %4d  %5.1f %%" % (libelle, c[cle], 100.0 * c[cle] / n_))
    print("  %-32s %4d  %5.1f %%" % ("sans aucune faute grave", c["ok"],
                                     100.0 * c["ok"] / n_))
    print("  duree                   %5.1f min" % ((time.time() - t0) / 60))

    dst = os.path.join(SP, "prof_%s.jsonl" % nom.replace("/", "_").replace(":", "_"))
    with open(dst, "w", encoding="utf-8") as f:
        for r, got in out:
            f.write(json.dumps({"id": r["id"], "control": r["control"],
                                "dirty": r["dirty"], "deepseek": r["clean"],
                                "out": got}, ensure_ascii=False) + "\n")
    json.dump({"modele": nom, "stats": dict(c),
               "fautes": {k: v[:8] for k, v in fautes.items()}},
              open(dst.replace(".jsonl", ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for cle in ("valeur_inventee", "invention", "amputation"):
        if fautes[cle]:
            print("\n  exemples de %s :" % cle)
            for x in fautes[cle][:3]:
                print("    %s" % (x,))
    print("\n  -> %s" % dst)


if __name__ == "__main__":
    main()
