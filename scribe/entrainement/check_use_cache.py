# -*- coding: utf-8 -*-
"""Refuse un checkpoint dont config.json porte use_cache=false.

    python check_use_cache.py <dossier-du-modele>

Le gradient checkpointing laisse `use_cache: false` dans la config sauvegardee.
Converti tel quel en GGUF, le modele repond toujours — dix minutes par phrase
au lieu de quatre secondes — et aucune evaluation par lecture ne le remarque.
Verifier AVANT de convertir, jamais apres coup. Code de sortie 1 = refus.
"""
import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    print(__doc__)
    sys.exit(2)
cfg = Path(sys.argv[1]) / "config.json"
if not cfg.exists():
    print("config.json introuvable dans", sys.argv[1])
    sys.exit(1)
if not json.loads(cfg.read_text(encoding="utf-8")).get("use_cache", False):
    print("REFUS : use_cache=false dans", cfg, "— corrigez avant de convertir.")
    sys.exit(1)
print("use_cache=true :", cfg)
