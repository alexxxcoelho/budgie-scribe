<#
.SYNOPSIS
  Pilote budgie-scribe depuis Windows. Aucun WSL, aucun bash.

.DESCRIPTION
  Tout le pipeline tourne nativement sur Windows :
    - l'entrainement sur la Radeon R9700 via ROCm (rocm-win-venv)
    - la transcription via Cohere/Vulkan
    - la generation et les evaluations

  Le CODE est dans le depot, les DONNEES restent dehors : posez SCRIBE_TRAVAIL,
  ou lancez le script depuis le repertoire de donnees. Rien n'ecrit dans le
  depot — le corpus derive ne se distribue pas (voir NOTICE).

  install-rocm.ps1 installe l'environnement d'entrainement ; DirectML a ete
  abandonne le 2026-09-02, train_dml.py est dans scribe/archive/.

.EXAMPLE
  .\scribe.ps1 etat
  .\scribe.ps1 entrainer -Paires pairs_mix.jsonl -Sortie scribe-v3 -Epoques 2
  .\scribe.ps1 entrainer -Profil mini -Paires pairs_mix.jsonl -Sortie scribe-mini-v1
  .\scribe.ps1 eval-itn  -Modele scribe-mini-v1
  .\scribe.ps1 eval-itn  -Modele scribe-itn
  .\scribe.ps1 eval-ab   -Modele scribe-itn
  .\scribe.ps1 gguf      -Modele scribe-itn -Quant Q4_K_M
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('etat', 'entrainer', 'eval-itn', 'eval-ab', 'gguf', 'generer-itn', 'aide')]
  [string]$Commande = 'aide',

  # Profil du modele de base : nano (0.6B, full SFT — le profil publie),
  # mini (1.7B), standard (4B), large (8B) — les trois derniers en LoRA,
  # fusionne a la sauvegarde. Table dans scribe/entrainement/modeles.py.
  [ValidateSet('nano', 'mini', 'standard', 'large')]
  [string]$Profil  = 'nano',
  [ValidateSet('', 'full', 'lora')]
  [string]$Methode = '',
  [string]$Paires  = 'pairs_mix.jsonl',
  [string]$Sortie  = 'scribe-v3',
  [string]$Modele  = 'scribe-itn',
  [int]   $Epoques = 2,
  [int]   $Limite  = 0,
  [int]   $Cas     = 0,
  [string]$Quant   = 'Q4_K_M',
  [int]   $Nombre  = 10000
)

$ErrorActionPreference = 'Stop'
# Le CODE est dans le depot ; les DONNEES vivent ailleurs et n'y entrent jamais
# (corpus derive de SUMM-RE — voir NOTICE). SCRIBE_TRAVAIL dit ou elles sont ;
# a defaut, le repertoire courant : c'est de la qu'on lance le pipeline.
$SCRIBE  = Join-Path (Split-Path $PSScriptRoot -Parent) 'scribe'
$TRAVAIL = if ($env:SCRIBE_TRAVAIL) { $env:SCRIBE_TRAVAIL } else { (Get-Location).Path }
$SCRATCH = Split-Path $TRAVAIL -Parent
$PY      = Join-Path $SCRATCH 'poc-venv\Scripts\python.exe'       # API, donnees
$PYROCM  = Join-Path $SCRATCH 'rocm-win-venv\Scripts\python.exe'  # GPU, entrainement
$HFHOME  = Join-Path $SCRATCH 'hf'

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function Ok  ($m) { Write-Host $m -ForegroundColor Green }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }

function Assert-Env {
  foreach ($p in @($PY, $PYROCM)) {
    if (-not (Test-Path $p)) { throw "Environnement Python absent : $p" }
  }
  $env:PYTHONIOENCODING = 'utf-8'
  $env:HF_HOME = $HFHOME
  $env:TOKENIZERS_PARALLELISM = 'false'
}

function Invoke-Etat {
  Info "`n=== GPU ==="
  Get-CimInstance Win32_VideoController |
    Where-Object { $_.Name -notmatch 'Basic|Meta' } |
    Select-Object Name, DriverVersion | Format-Table -AutoSize

  Info "=== DirectML ==="
  & $PYROCM -c @"
import torch, torch_directml as dml
print('  torch      :', torch.__version__)
print('  appareils  :', dml.device_count())
for i in range(dml.device_count()):
    print('    %d %s' % (i, dml.device_name(i)))
"@

  Info "`n=== Modeles entraines ==="
  # -Filter n'accepte qu'un motif ; on filtre donc apres coup.
  Get-ChildItem -Path $TRAVAIL -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*scribe*' -or $_.Name -like 'night-*' } |
    Sort-Object Name |
    ForEach-Object {
      $run = Join-Path $_.FullName 'run.json'
      $u = if (Test-Path $run) { (Get-Content $run -Raw | ConvertFrom-Json).train_units } else { '?' }
      $mo = [math]::Round((Get-ChildItem $_.FullName -File | Measure-Object Length -Sum).Sum / 1MB)
      '{0,-22} {1,6} unites {2,6} Mo' -f $_.Name, $u, $mo
    }

  Info "`n=== Jeux de paires ==="
  Get-ChildItem -Path $TRAVAIL -Filter 'pairs*.jsonl' -ErrorAction SilentlyContinue |
    ForEach-Object { '{0,-26} {1,7} lignes' -f $_.Name, (Get-Content $_.FullName | Measure-Object -Line).Lines }

  Info "`n=== Solde API ==="
  Push-Location $TRAVAIL; try { & $PY (Join-Path $SCRIBE 'pipeline\budget.py') } finally { Pop-Location }
}

function Invoke-Entrainer {
  $p = Join-Path $TRAVAIL $Paires
  if (-not (Test-Path $p)) { throw "Jeu de paires introuvable : $p" }
  $out = Join-Path $TRAVAIL $Sortie
  Info "Entrainement sur la Radeon (ROCm)"
  Info "  profil  : $Profil$(if ($Methode) { " ($Methode)" })"
  Info "  paires  : $Paires"
  Info "  sortie  : $Sortie"
  Info "  epoques : $Epoques$(if ($Limite) { " | limite : $Limite" })"
  $env:SCRIBE_PAIRS = $p; $env:SCRIBE_OUT = $out
  $env:SCRIBE_PROFIL = $Profil
  if ($Methode) { $env:SCRIBE_METHODE = $Methode } else { Remove-Item Env:SCRIBE_METHODE -ErrorAction SilentlyContinue }
  $env:SCRIBE_EPOCHS = "$Epoques"; $env:SCRIBE_LIMIT = "$Limite"
  Push-Location $TRAVAIL
  try   { & $PYROCM -u (Join-Path $SCRIBE 'entrainement\train_rocm.py') }
  finally { Pop-Location }
  Ok "Modele ecrit dans $out"
}

function Invoke-EvalItn {
  Info "Evaluation ITN — comparaison litterale, aucun cout API"
  Push-Location $TRAVAIL
  try { & $PYROCM -u (Join-Path $SCRIBE 'bancs\eval_itn.py') (Join-Path $TRAVAIL $Modele) $Cas }
  finally { Pop-Location }
}

function Invoke-EvalAb {
  Info "Evaluation A/B en aveugle — passe par l'API, cout ~0,02 `$"
  $evalSet = Join-Path $TRAVAIL 'eval_set.jsonl'
  if (-not (Test-Path $evalSet)) { throw "Jeu d'evaluation absent dans $TRAVAIL (voir scribe/archive/repair_eval.py)" }
  $n = (Get-Content $evalSet | Measure-Object -Line).Lines
  # La base de comparaison est celle du candidat (run.json), pas toujours la
  # 0.6B : une generation « base » par profil, pour ne pas comparer un mini a
  # la sortie de la nano.
  $run = Join-Path $TRAVAIL $Modele 'run.json'
  $profil = if (Test-Path $run) { (Get-Content $run -Raw | ConvertFrom-Json).profil } else { $null }
  if (-not $profil) { $profil = 'nano' }
  $env:SCRIBE_PROFIL = $profil
  $genBase = if ($profil -eq 'nano') { Join-Path $TRAVAIL 'fix_gen_base.jsonl' }
             else { Join-Path $TRAVAIL "fix_gen_base_$profil.jsonl" }
  $gen     = Join-Path $TRAVAIL "gen_$Modele.jsonl"
  $ab      = Join-Path $TRAVAIL "ab_$Modele.jsonl"
  $genPy   = Join-Path $SCRIBE 'entrainement\gen_rocm.py'
  Push-Location $TRAVAIL
  try {
    if (-not (Test-Path $genBase)) { & $PYROCM -u $genPy 'base' $evalSet $genBase $n }
    if (-not (Test-Path $gen))     { & $PYROCM -u $genPy (Join-Path $TRAVAIL $Modele) $evalSet $gen $n }
    & $PY -u (Join-Path $SCRIBE 'bancs\ab_eval.py') $genBase $gen $ab
  } finally { Pop-Location }
}

function Invoke-Gguf {
  $src = Join-Path $TRAVAIL $Modele
  if (-not (Test-Path $src)) { throw "Modele introuvable : $src" }

  # use_cache est verifie AVANT de convertir, pas rappele apres coup. Le laisser
  # a false est invisible — le modele repond, simplement dix minutes au lieu de
  # quatre secondes — et un GGUF errone ne se decouvre alors qu'a l'usage.
  $cfg = Join-Path $src 'config.json'
  if (-not (Test-Path $cfg)) { throw "config.json introuvable dans $src" }
  if (-not ((Get-Content $cfg -Raw | ConvertFrom-Json).use_cache)) {
    throw "use_cache=false dans $cfg — corrigez avant de convertir."
  }

  $llama = Join-Path $SCRATCH 'llamacpp'
  $bin   = Join-Path $SCRATCH 'llamabin\llama-quantize.exe'

  # Les artefacts atterrissent dans le DEPOT, jamais dans %TEMP%. Un GGUF laisse
  # dans le scratchpad disparait au premier nettoyage de disque, avec les 40 min
  # d'entrainement qui l'ont produit — et il reste introuvable entre-temps, les
  # outils de recherche sautant AppData\Local\Temp. `gguf/` est exclu par le
  # .gitignore : le binaire devient durable sans entrer dans l'historique Git.
  $outDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'gguf'
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $f16 = Join-Path $outDir "$Modele-f16.gguf"
  $q   = Join-Path $outDir "$Modele-$Quant.gguf"

  Info "Conversion en GGUF F16"
  Push-Location $llama
  try { & $PY 'convert_hf_to_gguf.py' $src --outfile $f16 --outtype f16 }
  finally { Pop-Location }

  Info "Quantisation en $Quant"
  & $bin $f16 $q $Quant

  # L'empreinte accompagne le binaire : une publication se verifie, elle ne se
  # suppose pas.
  $sha = (Get-FileHash $q -Algorithm SHA256).Hash.ToLower()
  $sha | Set-Content -Path "$q.sha256" -Encoding ascii

  Ok ("GGUF pret : {0}" -f $q)
  Ok ("  {0:N0} octets ({1:N1} Mio)" -f (Get-Item $q).Length, ((Get-Item $q).Length / 1MB))
  Ok ("  sha256 {0}" -f $sha)

  # Un modele entraine sur des donnees personnelles ne se distribue pas, et le
  # script ne peut pas le deviner depuis le GGUF. Il le demande.
  Warn "Avant publication : ce modele a-t-il vu des donnees personnelles ?"
  Warn "Si oui, prefixez le fichier LOCAL-UNIQUEMENT_donnees-perso_ (NOTICE, section 0)."

  # Publication : les octets vont DIRECTEMENT dans le depot HF de la famille
  # (plus de B2), sous le nom publie ; la CI du depot public verifie ensuite le
  # SHA contre models/manifest.json et pousse la carte. Le nom de famille et
  # la langue viennent du run.json du modele.
  $run = Join-Path $src 'run.json'
  $profil = if (Test-Path $run) { (Get-Content $run -Raw | ConvertFrom-Json).profil } else { 'nano' }
  $depot = @{ nano = 'BudgieScribe-Nano'; mini = 'BudgieScribe-Mini'; standard = 'BudgieScribe'; large = 'BudgieScribe-Large' }[$profil]
  $lang = if ($env:SCRIBE_LANG) { $env:SCRIBE_LANG } else { 'fr' }
  Info "Pour publier (hf auth login une fois, token write sur flowcorp-ch) :"
  Info ("  hf upload flowcorp-ch/{0} `"{1}`" {0}-{2}-{3}.gguf" -f $depot, $q, $lang, $Quant)
  Info ("  puis models/manifest.json : sha256 {0}, {1:N0} octets, build {2}" -f $sha, (Get-Item $q).Length, $Modele)
}

function Invoke-GenererItn {
  Info "Generation de $Nombre paires ITN synthetiques (deterministe, gratuit)"
  Push-Location $TRAVAIL
  try { & $PY (Join-Path $SCRIBE 'generateurs\gen_itn.py') $Nombre }
  finally { Pop-Location }
}

function Invoke-Aide {
  Get-Help $PSCommandPath -Detailed
  Write-Host ''
  Info 'Commandes : etat | entrainer | eval-itn | eval-ab | gguf | generer-itn'
}

Assert-Env
switch ($Commande) {
  'etat'        { Invoke-Etat }
  'entrainer'   { Invoke-Entrainer }
  'eval-itn'    { Invoke-EvalItn }
  'eval-ab'     { Invoke-EvalAb }
  'gguf'        { Invoke-Gguf }
  'generer-itn' { Invoke-GenererItn }
  default       { Invoke-Aide }
}
