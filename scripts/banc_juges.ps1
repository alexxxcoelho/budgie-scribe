<#
.SYNOPSIS
  Compare des juges locaux a DeepSeek, sur les memes entrees. Windows natif.

.DESCRIPTION
  Pour chaque modele : charge llama-server (Vulkan, GPU), lance bench_juge.py,
  arrete le serveur. Aucun jeton, aucune API distante, aucun cout.

  On part du plus petit et on monte : le but est de trouver le PLUS PETIT
  modele qui tienne, pas le meilleur dans l'absolu.

.EXAMPLE
  .\banc_juges.ps1                       # la serie complete
  .\banc_juges.ps1 -Modeles gemma-26b-a4b-qat
  .\banc_juges.ps1 -Reflexion            # avec la reflexion des modeles
#>
[CmdletBinding()]
param(
  [string[]]$Modeles = @(),
  [switch]$Reflexion,
  [int]$CasQC = 60,
  [int]$Port = 8899,
  [int]$Fils = 4
)

$ErrorActionPreference = 'Stop'
# Le CODE est dans le depot ; les DONNEES vivent ailleurs et n'y entrent jamais
# (corpus derive de SUMM-RE — voir NOTICE). SCRIBE_TRAVAIL dit ou elles sont ;
# a defaut, le repertoire courant : c'est de la qu'on lance le pipeline.
$SCRIBE  = Join-Path (Split-Path $PSScriptRoot -Parent) 'scribe'
$TRAVAIL = if ($env:SCRIBE_TRAVAIL) { $env:SCRIBE_TRAVAIL } else { (Get-Location).Path }
$SCRATCH = Split-Path $TRAVAIL -Parent
$PY      = Join-Path $SCRATCH 'poc-venv\Scripts\python.exe'
if (-not (Test-Path $PY)) { $PY = (Get-Command python).Source }   # le venv est optionnel ici
$LLAMA   = "$env:USERPROFILE\.lmstudio\extensions\backends\llama.cpp-win-x86_64-vulkan-avx2-2.31.2\llama-server.exe"
$MODELS  = "$env:USERPROFILE\.lmstudio\models"

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function Ok  ($m) { Write-Host $m -ForegroundColor Green }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }

# Du plus petit au plus grand. Les deux sous 10B servent de temoin : ils
# repondent a « est-ce que 10B etait vraiment le plancher ? »
$CATALOGUE = [ordered]@{
  'qwen3.5-9b'         = 'lmstudio-community\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_M.gguf'
  'gemma-12b-qat'      = 'lmstudio-community\gemma-4-12B-it-QAT-GGUF\gemma-4-12B-it-QAT-Q4_0.gguf'
  'gemma-12b'          = 'lmstudio-community\gemma-4-12B-it-GGUF\gemma-4-12B-it-Q4_K_M.gguf'
  'gemma-26b-a4b-qat'  = 'lmstudio-community\gemma-4-26B-A4B-it-QAT-GGUF\gemma-4-26B-A4B-it-QAT-Q4_0.gguf'
  'qwen3.8-27b'        = 'lmstudio-community\Qwen3.8-27B-GGUF\Qwen3.8-27B-Q4_K_M.gguf'
  'gemma-31b-qat'      = 'lmstudio-community\gemma-4-31B-it-QAT-GGUF\gemma-4-31B-it-QAT-Q4_0.gguf'
}

if (-not $Modeles) { $Modeles = @($CATALOGUE.Keys) }

function Stop-Serveurs {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Milliseconds 900
}

function Start-Serveur([string]$gguf, [string]$alias) {
  $log = Join-Path $SCRATCH "juge\server_$alias.log"
  New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
  $args = @(
    '--model', $gguf, '--alias', $alias,
    '--host', '127.0.0.1', '--port', $Port,
    '--ctx-size', 32768, '--n-gpu-layers', 999,
    '--parallel', $Fils, '--jinja', '--no-webui', '--flash-attn', 'on'
  )
  Start-Process -FilePath $LLAMA -ArgumentList $args -WindowStyle Hidden `
                -RedirectStandardOutput $log -RedirectStandardError "$log.err"
  # On attend la sante plutot qu'un delai fixe : un 31B met bien plus
  # longtemps a monter en VRAM qu'un 9B.
  foreach ($i in 1..180) {
    Start-Sleep -Seconds 2
    try {
      if ((Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3).status -eq 'ok') {
        Ok ("  serveur pret en {0} s" -f (2 * $i)); return $true
      }
    } catch { }
  }
  Warn "  le serveur n'a pas repondu en 6 min"
  return $false
}

$env:PYTHONIOENCODING = 'utf-8'
$env:BENCH_WORKERS    = "$Fils"
$env:BENCH_THINK      = if ($Reflexion) { '1' } else { '0' }

foreach ($nom in $Modeles) {
  if (-not $CATALOGUE.Contains($nom)) { Warn "inconnu : $nom"; continue }
  $gguf = Join-Path $MODELS $CATALOGUE[$nom]
  if (-not (Test-Path $gguf)) { Warn "absent du disque : $gguf"; continue }
  $go = [math]::Round((Get-Item $gguf).Length / 1GB, 1)

  Info "`n========== $nom ($go Go) =========="
  Stop-Serveurs
  if (-not (Start-Serveur $gguf $nom)) { continue }
  Push-Location $TRAVAIL
  try { & $PY -u (Join-Path $SCRIBE 'bancs\bench_juge.py') $nom $Port $CasQC }
  finally { Pop-Location }
}

Stop-Serveurs
Info "`n=== synthese ==="
Push-Location $TRAVAIL
try { & $PY (Join-Path $SCRIBE 'bancs\synthese_juges.py') } finally { Pop-Location }
