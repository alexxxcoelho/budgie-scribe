# -*- coding: utf-8 -*-
"""Couche fournisseur : DeepSeek (cloud) ou LM Studio (local), au choix.

Pourquoi elle existe : la nuit du 2026-09-01 s'est arretee sur un solde
DeepSeek a -0,11 $. Un pipeline non surveille ne doit pas dependre d'un seul
fournisseur, surtout quand une alternative locale et gratuite tourne deja sur
la machine.

Selection, dans l'ordre :
  1. la variable d'environnement SCRIBE_PROVIDER, si elle vaut deepseek|lmstudio
  2. LM Studio si un jeton est present dans ~/.budgie/custom_api_keys.json
     sous la cle `lmstudio` ET que le serveur repond
  3. DeepSeek si son solde est positif

`available()` dit lequel est utilisable a l'instant, sans rien consommer ;
`wait_for_provider()` boucle jusqu'a ce qu'un fournisseur reponde, ce qui
permet de lancer la chaine AVANT d'avoir debloque quoi que ce soit.
"""
import json, os, time, urllib.request, urllib.error

KEYS_PATH = os.path.expanduser("~/.budgie/custom_api_keys.json")
LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234")
LMSTUDIO_MODEL = os.environ.get("LMSTUDIO_MODEL", "gemma-4-31b-it-qat")
DEEPSEEK_URL = "https://api.deepseek.com"

# llama-server lance a la main, depuis le backend Vulkan que LM Studio embarque
# deja. C'est le chemin local qui MARCHE : contrairement a l'API de LM Studio,
# il n'exige aucun jeton, et c'est ce jeton manquant qui bloquait la bascule.
LLAMACPP_URL = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:8899")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "gemma-12b-qat")


def _keys():
    try:
        return json.load(open(KEYS_PATH, encoding="utf-8"))
    except Exception:
        return {}


def _get(url, headers, timeout=8):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def deepseek_ok():
    key = _keys().get("deepseek")
    if not key:
        return False, "aucune cle deepseek"
    try:
        d = _get(DEEPSEEK_URL + "/user/balance", {"Authorization": "Bearer " + key})
        if d.get("is_available"):
            bal = (d.get("balance_infos") or [{}])[0].get("total_balance")
            return True, "solde %s USD" % bal
        return False, "solde epuise (%s)" % (d.get("balance_infos") or [{}])[0].get("total_balance")
    except Exception as e:
        return False, "%s" % type(e).__name__


def llamacpp_ok():
    """llama-server repond-il ? /health ne consomme rien et n'exige rien."""
    try:
        d = _get(LLAMACPP_URL + "/health", {}, timeout=3)
        if d.get("status") != "ok":
            return False, "sante = %s" % d.get("status")
    except Exception as e:
        return False, "%s" % type(e).__name__
    # On annonce le modele REELLEMENT charge, pas celui qu'on espere : le champ
    # `model` d'une requete est ignore par llama-server, donc une variable
    # d'environnement perimee mentirait sans jamais faire echouer l'appel.
    try:
        ids = [m.get("id", "") for m in (_get(LLAMACPP_URL + "/v1/models", {}, 3).get("data") or [])]
        charge = os.path.basename(ids[0]) if ids else LLAMACPP_MODEL
    except Exception:
        charge = LLAMACPP_MODEL + " (non confirme)"
    return True, "%s (%s)" % (charge, LLAMACPP_URL)


def lmstudio_ok():
    token = _keys().get("lmstudio")
    if not token:
        return False, "aucun jeton lmstudio"
    try:
        d = _get(LMSTUDIO_URL + "/v1/models", {"Authorization": "Bearer " + token})
        ids = [m.get("id") for m in (d.get("data") or [])]
        return True, "%d modeles (%s…)" % (len(ids), ", ".join(ids[:2]))
    except urllib.error.HTTPError as e:
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, "%s" % type(e).__name__


def available():
    """(nom, detail) du fournisseur utilisable, ou (None, raisons)."""
    forced = os.environ.get("SCRIBE_PROVIDER")
    checks = [("llamacpp", llamacpp_ok), ("lmstudio", lmstudio_ok),
              ("deepseek", deepseek_ok)]
    if forced:
        checks = [c for c in checks if c[0] == forced] or checks
    reasons = []
    for name, check in checks:
        ok, detail = check()
        if ok:
            return name, detail
        reasons.append("%s: %s" % (name, detail))
    return None, " | ".join(reasons)


def wait_for_provider(poll_s=120, log=print):
    """Boucle jusqu'a ce qu'un fournisseur reponde. La chaine peut donc etre
    lancee avant qu'Alex ait recharge DeepSeek ou colle le jeton LM Studio."""
    announced = None
    while True:
        name, detail = available()
        if name:
            log("fournisseur disponible : %s (%s)" % (name, detail))
            return name
        if detail != announced:
            log("aucun fournisseur — %s ; nouvelle tentative toutes les %d s" % (detail, poll_s))
            announced = detail
        time.sleep(poll_s)


def endpoint(provider):
    if provider == "llamacpp":
        return LLAMACPP_URL + "/v1/chat/completions", None, LLAMACPP_MODEL
    if provider == "lmstudio":
        return LMSTUDIO_URL + "/v1/chat/completions", _keys().get("lmstudio"), LMSTUDIO_MODEL
    return DEEPSEEK_URL + "/v1/chat/completions", _keys().get("deepseek"), None


def chat(provider, system, user, model=None, json_mode=False, retries=4, timeout=240):
    """Un appel de conversation, quel que soit le fournisseur.

    LM Studio ne connait pas `reasoning_effort` ; DeepSeek en a besoin pour ne
    pas derouler 2 500 tokens de pensee par unite (mesure : 45 s contre 1,9 s).
    """
    url, key, forced_model = endpoint(provider)
    body = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "model": forced_model or model or "deepseek-v4-flash",
    }
    if provider == "deepseek":
        body["reasoning_effort"] = "none"
    if provider == "llamacpp":
        # Gemma 4 raisonne avant de repondre, et sa reflexion part dans
        # `reasoning_content`, PAS dans `content`. Laissee libre elle epuise le
        # budget sans jamais ecrire le verdict — mesure : 50 s par appel et une
        # reponse vide, contre 3,2 s reflexion coupee, a verdict identique.
        body["chat_template_kwargs"] = {"enable_thinking": False}
        body["reasoning_effort"] = "none"
        body["max_tokens"] = 1500
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(retries):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.load(r)
            text = payload["choices"][0]["message"]["content"].strip()
            return (json.loads(text) if json_mode else text), payload.get("usage", {})
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("echec apres %d tentatives : %s" % (retries, last))


if __name__ == "__main__":
    name, detail = available()
    print("fournisseur :", name or "AUCUN")
    print("detail      :", detail)
    for n, f in [("llamacpp", llamacpp_ok), ("lmstudio", lmstudio_ok),
                 ("deepseek", deepseek_ok)]:
        ok, d = f()
        print("  %-9s %-4s %s" % (n, "OK" if ok else "non", d))
