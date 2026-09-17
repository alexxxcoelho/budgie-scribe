<#
.SYNOPSIS
  Installe ROCm + PyTorch pour la Radeon R9700, depuis Windows.

.DESCRIPTION
  A LIRE AVANT DE LANCER — ceci est OPTIONNEL.

  DirectML fonctionne deja sur votre carte et donne 4,8x le CPU (2,35 s le pas
  contre 11,24 sur Qwen3-0.6B, seq 512). ROCm sera probablement plus rapide,
  mais rien ne depend de lui.

  POURQUOI CA PASSE PAR WSL, et ce n'est pas un choix :
  PyTorch-ROCm n'existe qu'en roues Linux (manylinux). Il n'y a pas de build
  Windows natif. AMD prescrit elle-meme WSL pour ROCm sur une machine Windows,
  via la bibliotheque ROCDXG introduite avec ROCm 7.2.1 — c'est ce qui expose
  le GPU a Linux a travers /dev/dxg. Le HIP SDK Windows, lui, sert a compiler
  du HIP, pas a faire tourner PyTorch.

  Ce script encapsule les commandes Linux pour que vous n'ayez rien a coller :
  il verifie les prerequis, appelle WSL, et verifie le resultat. Il vous
  demandera votre mot de passe sudo UNE fois, dans la fenetre WSL.

.EXAMPLE
  .\install-rocm.ps1 -Verifier      # diagnostic seul, n'installe rien
  .\install-rocm.ps1                # installe
#>
[CmdletBinding()]
param(
  [switch]$Verifier,
  [string]$Distro = 'Ubuntu-24.04'
)

$ErrorActionPreference = 'Stop'
function Info($m) { Write-Host $m -ForegroundColor Cyan }
function Ok  ($m) { Write-Host $m -ForegroundColor Green }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }
function Bad ($m) { Write-Host $m -ForegroundColor Red }

function Test-Prerequis {
  Info "`n=== Prerequis ==="

  $gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'Radeon' } | Select-Object -First 1
  if ($gpu) { Ok  "  GPU      : $($gpu.Name) — pilote $($gpu.DriverVersion)" }
  else      { Bad "  GPU      : aucune Radeon detectee"; return $false }

  $distros = (wsl --list --quiet) -replace "`0", '' -split "`r?`n" | Where-Object { $_ }
  if ($distros -contains $Distro) { Ok "  WSL      : $Distro presente" }
  else { Bad "  WSL      : $Distro absente (distros : $($distros -join ', '))"; return $false }

  $dxg = wsl -d $Distro -- bash -c 'test -e /dev/dxg && echo oui || echo non'
  if ("$dxg".Trim() -eq 'oui') { Ok "  /dev/dxg : present — le GPU est expose a WSL" }
  else { Bad "  /dev/dxg : absent — WSL ne voit pas le GPU"; return $false }

  $rocm = wsl -d $Distro -- bash -c 'ls -d /opt/rocm* 2>/dev/null | head -1'
  if ("$rocm".Trim()) { Ok "  ROCm     : deja installe ($("$rocm".Trim()))" }
  else { Warn "  ROCm     : absent — c'est ce que ce script installe" }

  $libs = wsl -d $Distro -- bash -c 'ls /usr/lib/wsl/lib/ 2>/dev/null | tr "\n" " "'
  if ("$libs" -match 'hsa|rocdxg') { Ok  "  runtime  : bibliotheques AMD presentes dans /usr/lib/wsl/lib" }
  else { Warn "  runtime  : /usr/lib/wsl/lib ne contient que $("$libs".Trim())" }
  Warn "             (les bibliotheques AMD y sont injectees par le pilote Windows ;"
  Warn "              il faut Adrenalin 26.2.2 ou plus recent)"
  return $true
}

function Install-Rocm {
  Info "`n=== Installation ==="
  Warn "WSL vous demandera votre mot de passe sudo. Il reste dans la fenetre WSL,"
  Warn "il ne transite ni par ce script ni par quoi que ce soit d'autre."

  $script = @'
set -e
cd /tmp
echo "--- depot AMD ---"
wget -q https://repo.radeon.com/amdgpu-install/latest/ubuntu/noble/amdgpu-install_all.deb -O amdgpu-install.deb || \
  wget -q https://repo.radeon.com/amdgpu-install/6.4.2/ubuntu/noble/amdgpu-install_6.4.60402-1_all.deb -O amdgpu-install.deb
sudo apt-get update -qq
sudo apt-get install -y ./amdgpu-install.deb
echo "--- ROCm pour WSL (sans DKMS : le noyau vient de Windows) ---"
sudo amdgpu-install -y --usecase=wsl,rocm --no-dkms
echo "--- PyTorch ROCm 7.x (PAS 6.2 : anterieure a RDNA 4) ---"
python3 -m venv --system-site-packages ~/rocm-venv 2>/dev/null || true
~/rocm-venv/bin/pip install -q --upgrade pip
~/rocm-venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/rocm7.0
echo "--- verification ---"
~/rocm-venv/bin/python -c "
import torch
print('torch', torch.__version__, '| HIP', getattr(torch.version,'hip',None))
print('GPU visible :', torch.cuda.is_available())
for i in range(torch.cuda.device_count()): print(' ', i, torch.cuda.get_device_name(i))
"
'@
  $tmp = Join-Path $env:TEMP 'install_rocm_wsl.sh'
  # LF obligatoire : bash refuse les fins de ligne Windows.
  [IO.File]::WriteAllText($tmp, ($script -replace "`r`n", "`n"))
  $wslPath = "/mnt/" + $tmp.Substring(0,1).ToLower() + $tmp.Substring(2).Replace('\','/')
  wsl -d $Distro -- bash $wslPath
}

function Test-Resultat {
  Info "`n=== Banc de mesure ==="
  $bench = @'
~/rocm-venv/bin/python - <<"PY"
import torch, time
if not torch.cuda.is_available():
    print("GPU non visible depuis PyTorch — ROCm n'est pas operationnel"); raise SystemExit(1)
d = torch.device("cuda")
for n in (2048,):
    a = torch.randn(n, n, device=d, requires_grad=True)
    b = torch.randn(n, n, device=d, requires_grad=True)
    for _ in range(3):
        (a @ b).sum().backward(); a.grad = None; b.grad = None
    torch.cuda.synchronize(); t = time.time()
    for _ in range(10):
        (a @ b).sum().backward(); a.grad = None; b.grad = None
    torch.cuda.synchronize(); dt = (time.time() - t) / 10
    print("matmul %d avant+arriere : %.3f s  (%.0f GFLOP/s)" % (n, dt, 2*n**3*3/dt/1e9))
print()
print("Repere DirectML mesure sur cette machine : 0,030 s  (1733 GFLOP/s)")
print("Repere CPU 8 coeurs                      : 0,140 s  ( 367 GFLOP/s)")
PY
'@
  $tmp = Join-Path $env:TEMP 'bench_rocm.sh'
  [IO.File]::WriteAllText($tmp, ($bench -replace "`r`n", "`n"))
  $wslPath = "/mnt/" + $tmp.Substring(0,1).ToLower() + $tmp.Substring(2).Replace('\','/')
  wsl -d $Distro -- bash $wslPath
}

if (-not (Test-Prerequis)) { Bad "`nPrerequis non remplis — rien n'a ete installe."; exit 1 }
if ($Verifier) { Info "`n(-Verifier : diagnostic seul, rien n'a ete installe)"; exit 0 }
Install-Rocm
Test-Resultat
Ok "`nSi le banc bat DirectML, dites-le moi et je bascule l'entrainement sur ROCm."
Warn "Sinon, on reste sur DirectML : il tourne nativement sous Windows, sans WSL."
