# One-time setup: make Firefox trust the mkcert CA
# Run as Administrator

$ErrorActionPreference = 'Stop'

$caPath = Join-Path $PSScriptRoot 'certs' 'rootCA.pem'
if (-not (Test-Path $caPath)) {
    Write-Host "CA-Datei nicht gefunden: $caPath" -ForegroundColor Red
    Write-Host "Bitte starte erst einmal start.ps1, damit das Zertifikat erstellt wird." -ForegroundColor Yellow
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] 'Administrator')
if (-not $isAdmin) {
    Write-Host "Bitte als Administrator ausfuehren (rechtsklick -> Als Administrator ausfuehren)." -ForegroundColor Red
    exit 1
}

$firefoxPaths = @(
    "${env:ProgramFiles}\Mozilla Firefox",
    "${env:ProgramFiles(x86)}\Mozilla Firefox"
)

$firefoxPath = $firefoxPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $firefoxPath) {
    Write-Host "Firefox nicht gefunden." -ForegroundColor Red
    exit 1
}

$distDir = Join-Path $firefoxPath 'distribution'
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

$policyPath = Join-Path $distDir 'policies.json'

$existingPolicy = @{}
if (Test-Path $policyPath) {
    try {
        $existingPolicy = Get-Content $policyPath -Raw | ConvertFrom-Json -AsHashtable
    } catch {}
}

if (-not $existingPolicy.ContainsKey('policies')) {
    $existingPolicy['policies'] = @{}
}
if (-not $existingPolicy['policies'].ContainsKey('Certificates')) {
    $existingPolicy['policies']['Certificates'] = @{}
}

$existingPolicy['policies']['Certificates']['Install'] = @($caPath.Replace('\', '\\'))

$content = $existingPolicy | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($policyPath, $content, (New-Object System.Text.UTF8Encoding $false))

Write-Host "Firefox-Policy geschrieben: $policyPath" -ForegroundColor Green
Write-Host "Bitte Firefox einmal neu starten. Danach wird der Lagerist als vertrauenswuerdig erkannt." -ForegroundColor Yellow
