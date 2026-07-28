# HoyoVoice one-time setup (Windows). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Refresh-Path {
    # pull PATH changes made by installers into THIS session
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host "== checking prerequisites"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "winget required (ships with Windows 10/11 App Installer)"; exit 1
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    # PATH refresh wasn't enough — locate the winget-installed binary and
    # add its bin dir to the user PATH (persistently) + this session
    $ffbin = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" `
        -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty DirectoryName
    if ($ffbin) {
        Write-Host "adding ffmpeg to PATH: $ffbin"
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($userPath -notlike "*$ffbin*") {
            [Environment]::SetEnvironmentVariable("Path", "$userPath;$ffbin", "User")
        }
        $env:Path += ";$ffbin"
    }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: ffmpeg still not found after install. Install it manually"
    Write-Host "(https://www.gyan.dev/ffmpeg/builds/, add its bin folder to PATH),"
    Write-Host "then re-run setup.ps1 in a new terminal."
    exit 1
}
Write-Host "ffmpeg: $((Get-Command ffmpeg).Source)"

# find Python 3.11+ (3.13 preferred, matching the macOS setup)
$py = $null
foreach ($cand in @("python3.13", "python3.12", "python3.11", "python")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) {
        $v = & $cand -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        if ($v -eq "True") { $py = $cand; break }
    }
}
if (-not $py) {
    winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements
    Write-Host "Python installed — open a NEW terminal and re-run setup.ps1"; exit 1
}
Write-Host "using $py"

Write-Host "== creating venv + installing python deps"
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
& .venv\Scripts\python.exe -m pip install --upgrade pip -q
# kokoro-onnx bundles espeak-ng via espeakng-loader — no system install needed
& .venv\Scripts\python.exe -m pip install -q `
    kokoro-onnx onnxruntime sounddevice soundfile pillow numpy `
    flask vaderSentiment rapidocr-onnxruntime winsdk

Write-Host "== downloading Silero VAD model"
if (-not (Test-Path "tools\silero_vad.onnx")) {
    Invoke-WebRequest -Uri "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx" `
        -OutFile "tools\silero_vad.onnx"
}

Write-Host "== downloading Kokoro TTS model (~340 MB total)"
New-Item -ItemType Directory -Force -Path "models" | Out-Null
$kokoroBase = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
if (-not (Test-Path "models\kokoro-v1.0.onnx")) {
    Invoke-WebRequest -Uri "$kokoroBase/kokoro-v1.0.onnx" -OutFile "models\kokoro-v1.0.onnx"
}
if (-not (Test-Path "models\voices-v1.0.bin")) {
    Invoke-WebRequest -Uri "$kokoroBase/voices-v1.0.bin" -OutFile "models\voices-v1.0.bin"
}

New-Item -ItemType Directory -Force -Path "captures", "tts_out" | Out-Null
if (-not (Test-Path "voices.json")) { Copy-Item "voices.example.json" "voices.json" }

Write-Host "== verifying capture device"
$devs = (ffmpeg -hide_banner -f dshow -list_devices true -i dummy 2>&1) | Out-String
if ($devs -match "(?i)shadowcast") {
    Write-Host "capture card found"
} else {
    Write-Host "WARNING: no ShadowCast device found — plug in your capture card (any UVC device works; pick it in the dashboard)"
}

Write-Host ""
Write-Host "Setup complete. Start with: python hoyovoice.py start"
Write-Host "Dashboard: http://127.0.0.1:8470  (allow it through Windows Firewall if prompted)"
