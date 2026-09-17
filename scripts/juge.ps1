<#
.SYNOPSIS
  Demarre, arrete et interroge le juge local. Aucun jeton, aucun cout.

.DESCRIPTION
  Le juge tourne sur llama-server, le binaire que LM Studio embarque deja dans
  son backend Vulkan. On l'appelle EN DIRECT, sans passer par l'application :
  l'API de LM Studio exige un jeton, celle de llama-server n'exige rien. C'est
  ce jeton manquant qui bloquait la bascule depuis le debut.

  Le modele retenu est gemma-4-12B-it-QAT (6,5 Go), choisi par mesure et non
  par taille — voir les notes d'entrainement, « choix du juge local ». Il est plus
  coherent que DeepSeek au test du miroir, ne refuse rien du corpus intime,
  et repond six fois plus vite.

.EXAMPLE
  .\juge.ps1 demarrer            # charge gemma-12b-qat sur la Radeon
  .\juge.ps1 etat                # qui repond, et sur quel modele
  .\juge.ps1 essai               # un appel de bout en bout
  .\juge.ps1 arreter
  .\juge.ps1 demarrer -Modele gemma-31b-qat
  .\juge.ps1 demarrer -Appareil Vulkan0   # le defaut : la R9700, jamais l'iGPU
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('demarrer', 'arreter', 'etat', 'essai', 'aide')]
  [string]$Commande = 'aide',

  # gemma-12b-qat par defaut : le plus petit qui tienne, pas le plus gros
  # disponible. Le 31B tranche un peu mieux en A/B mais laisse passer plus de
  # transcriptions verolees, et il est 2,3 fois plus lent.
  [ValidateSet('gemma-12b-qat', 'gemma-12b', 'gemma-31b-qat', 'gemma-26b-a4b-qat',
               'qwen3.8-27b', 'qwen3.5-9b')]
  [string]$Modele = 'gemma-12b-qat',

  [int]$Port = 8899,
  [int]$Fils = 4,
  [int]$Contexte = 32768,

  # La machine expose DEUX appareils Vulkan : la R9700 (Vulkan0) et l'iGPU
  # (Vulkan1), dont la memoire « libre » est la RAM de la machine (46 Go).
  # Sans --device, llama.cpp repartit les couches sur les deux au prorata de
  # la memoire libre : l'essentiel part sur l'iGPU, la R9700 reste vide, et le
  # juge tourne a 5 tok/s au lieu de 65 — sans aucune erreur. Mesure le
  # 2026-09-05 sur le QC anglais (16 s par appel au lieu de 3). C'est le
  # jumeau Vulkan du piege cuda:0 de train_rocm.py.
  [string]$Appareil = 'Vulkan0'
)

$ErrorActionPreference = 'Stop'
# Le CODE est dans le depot ; les DONNEES vivent ailleurs et n'y entrent jamais
# (corpus derive de SUMM-RE — voir NOTICE). SCRIBE_TRAVAIL dit ou elles sont ;
# a defaut, le repertoire courant : c'est de la qu'on lance le pipeline.
$SCRIBE  = Join-Path (Split-Path $PSScriptRoot -Parent) 'scribe'
$TRAVAIL = if ($env:SCRIBE_TRAVAIL) { $env:SCRIBE_TRAVAIL } else { (Get-Location).Path }
$SCRATCH = Split-Path $TRAVAIL -Parent
# LM Studio retire ses anciens backends a chaque mise a jour (le 2.31.2 cable
# ici avait disparu le 2026-09-14 ; restaient 2.27.1, 2.29.1, 2.30.0, 2.37.0).
# On prend le plus recent present plutot qu'un numero qui perime.
$LLAMA   = Get-ChildItem "$env:USERPROFILE\.lmstudio\extensions\backends" -Directory -Filter 'llama.cpp-win-x86_64-vulkan-avx2-*' |
             Sort-Object { [version]($_.Name -replace '^.*-avx2-', '') } -Descending |
             Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName 'llama-server.exe' }
$MODELS  = "$env:USERPROFILE\.lmstudio\models"

$CATALOGUE = @{
  'qwen3.5-9b'        = 'lmstudio-community\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_M.gguf'
  'gemma-12b-qat'     = 'lmstudio-community\gemma-4-12B-it-QAT-GGUF\gemma-4-12B-it-QAT-Q4_0.gguf'
  'gemma-12b'         = 'lmstudio-community\gemma-4-12B-it-GGUF\gemma-4-12B-it-Q4_K_M.gguf'
  'gemma-26b-a4b-qat' = 'lmstudio-community\gemma-4-26B-A4B-it-QAT-GGUF\gemma-4-26B-A4B-it-QAT-Q4_0.gguf'
  'qwen3.8-27b'       = 'lmstudio-community\Qwen3.8-27B-GGUF\Qwen3.8-27B-Q4_K_M.gguf'
  'gemma-31b-qat'     = 'lmstudio-community\gemma-4-31B-it-QAT-GGUF\gemma-4-31B-it-QAT-Q4_0.gguf'
}

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function Ok  ($m) { Write-Host $m -ForegroundColor Green }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }

function Get-Sante {
  try { return (Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3).status }
  catch { return $null }
}

function Get-ModeleCharge {
  try {
    $d = Invoke-RestMethod "http://127.0.0.1:$Port/v1/models" -TimeoutSec 3
    return (Split-Path $d.data[0].id -Leaf)
  } catch { return $null }
}

function Invoke-Demarrer {
  if (Get-Sante) { Warn "un serveur repond deja sur le port $Port — .\juge.ps1 arreter d'abord"; return }
  $gguf = Join-Path $MODELS $CATALOGUE[$Modele]
  if (-not (Test-Path $gguf)) { throw "modele absent du disque : $gguf" }
  $go = [math]::Round((Get-Item $gguf).Length / 1GB, 1)
  Info "chargement de $Modele ($go Go) sur la Radeon"
  # Un journal PAR MODELE, et non un fichier unique : Start-Process echoue en
  # silence si sa cible de redirection est encore tenue par le serveur qu'on
  # vient d'arreter, et le processus demarre alors SANS AUCUN ARGUMENT — il
  # reste a 60 Mo, ne charge rien, et la boucle d'attente tourne six minutes
  # pour rien. Un nom distinct par modele supprime la collision.
  $log = Join-Path $SCRATCH ("juge\serveur_{0}.log" -f $Modele)
  New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
  Remove-Item $log, "$log.err" -Force -ErrorAction SilentlyContinue
  Start-Process -FilePath $LLAMA -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
    -ArgumentList @('--model', $gguf, '--alias', $Modele, '--host', '127.0.0.1',
                    '--port', $Port, '--ctx-size', $Contexte, '--n-gpu-layers', 999,
                    '--device', $Appareil,
                    '--parallel', $Fils, '--jinja', '--no-webui', '--flash-attn', 'on')
  foreach ($i in 1..180) {
    Start-Sleep -Seconds 2
    if (Get-Sante) { Ok ("  pret en {0} s — http://127.0.0.1:{1}" -f (2 * $i), $Port); return }
  }
  Warn "  pas de reponse apres 6 min — voir $log"
}

function Invoke-Arreter {
  # On n'arrete QUE le serveur qui ecoute sur notre port. D'autres llama-server
  # tournent sur cette machine et ne nous appartiennent pas : celui de LM
  # Studio, et depuis le 2026-09-05 celui que Budgie lance lui-meme
  # (resources\scribe-runtime\llama-server.exe, dans l'instance de dev
  # d'Alex). Un Stop-Process sur le nom les tuerait tous.
  $pid_ = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
          Select-Object -First 1 -ExpandProperty OwningProcess
  if (-not $pid_) { Warn "aucun serveur n'ecoute sur le port $Port"; return }
  $p = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
  if (-not $p -or $p.ProcessName -ne 'llama-server') {
    Warn "le port $Port est tenu par '$($p.ProcessName)' (pid $pid_), pas par llama-server — rien fait"
    return
  }
  Stop-Process -Id $pid_ -Force
  Ok "serveur arrete (pid $pid_, port $Port)"
}

function Invoke-Etat {
  $sante = Get-Sante
  if (-not $sante) { Warn "aucun juge local — .\juge.ps1 demarrer"; }
  else { Ok "juge local : $(Get-ModeleCharge) sur http://127.0.0.1:$Port" }
  Info "`n=== ce que voit la couche fournisseur ==="
  $py = Join-Path $SCRATCH 'poc-venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { $py = (Get-Command python).Source }
  $env:PYTHONIOENCODING = 'utf-8'
  Push-Location $TRAVAIL
  try { & $py (Join-Path $SCRIBE 'pipeline\llm.py') } finally { Pop-Location }
}

function Invoke-Essai {
  if (-not (Get-Sante)) { throw "aucun juge local — .\juge.ps1 demarrer" }
  Info "un appel de bout en bout, en mode JSON"
  $corps = @{
    model = $Modele
    messages = @(
      @{ role = 'system'; content = 'Reponds uniquement par un objet JSON {"verdict": "..."}.' },
      @{ role = 'user';   content = 'La phrase « Il fait beau. » est-elle bien formee ? verdict = oui ou non.' }
    )
    temperature = 0
    max_tokens = 200
    response_format = @{ type = 'json_object' }
    chat_template_kwargs = @{ enable_thinking = $false }
    reasoning_effort = 'none'
  } | ConvertTo-Json -Depth 6
  try {
    $t = Measure-Command {
      # Le corps part en OCTETS UTF-8 explicites. Invoke-RestMethod encode
      # sinon la chaine avec la page de codes ANSI de la machine, et tout
      # accent francais devient de l'UTF-8 invalide : llama-server repond 500.
      $script:r = Invoke-RestMethod "http://127.0.0.1:$Port/v1/chat/completions" `
                    -Method Post -ContentType 'application/json; charset=utf-8' `
                    -Body ([System.Text.Encoding]::UTF8.GetBytes($corps)) -TimeoutSec 120
    }
  } catch {
    # llama-server refuse net quand ses N slots sont tous pris. Ce n'est pas
    # une panne, c'est une file pleine : le dire, plutot que de laisser une
    # exception reseau faire croire que le serveur est tombe.
    Warn "  le serveur n'a pas pris l'appel : $($_.Exception.Message)"
    Warn "  s'il tourne deja un banc, ses $Fils slots sont occupes."
    Warn "  reessayez apres, ou relancez avec -Fils 8"
    return
  }
  Ok ("  {0:N2} s — {1} tokens" -f $t.TotalSeconds, $r.usage.completion_tokens)
  Write-Host "  $($r.choices[0].message.content)"
}

switch ($Commande) {
  'demarrer' { Invoke-Demarrer }
  'arreter'  { Invoke-Arreter }
  'etat'     { Invoke-Etat }
  'essai'    { Invoke-Essai }
  default    { Get-Help $PSCommandPath -Detailed }
}
