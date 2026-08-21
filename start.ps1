$env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
$port = if ($env:LAGER_PORT) { $env:LAGER_PORT } else { 8000 }

$ip = '127.0.0.1'
try {
    $socket = New-Object System.Net.Sockets.Socket([System.Net.Sockets.AddressFamily]::InterNetwork, [System.Net.Sockets.SocketType]::Dgram, [System.Net.Sockets.ProtocolType]::Udp)
    $socket.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket, [System.Net.Sockets.SocketOptionName]::SendTimeout, 1000)
    $socket.Connect('8.8.8.8', 80)
    $ip = $socket.LocalEndPoint.ToString().Split(':')[0]
    $socket.Close()
} catch {
    try {
        $ip = ([System.Net.Dns]::GetHostAddresses($env:COMPUTERNAME) | Where-Object { $_.AddressFamily -eq 'InterNetwork' -and $_.ToString() -ne '127.0.0.1' } | Select-Object -First 1).ToString()
    } catch {}
}

Set-Location $PSScriptRoot
New-Item -ItemType Directory -Path 'certs' -Force | Out-Null

# Daily database backup
$dbPath = Join-Path (Join-Path $PSScriptRoot 'data') 'lager.db'
$backupDir = Join-Path $PSScriptRoot 'backups'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backupFile = Join-Path $backupDir ("lager_{0}.zip" -f (Get-Date -Format 'yyyy-MM-dd'))
if ((Test-Path $dbPath) -and -not (Test-Path $backupFile)) {
    Write-Host "Erstelle taegliches Backup: $backupFile" -ForegroundColor Cyan
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory((Get-Item $dbPath).DirectoryName, $backupFile, [System.IO.Compression.CompressionLevel]::Optimal, $false)
}

$certFile = Join-Path (Join-Path $PSScriptRoot 'certs') 'cert.pem'
$keyFile = Join-Path (Join-Path $PSScriptRoot 'certs') 'key.pem'

$hasMkcert = $null -ne (Get-Command mkcert -ErrorAction SilentlyContinue)
$regenerate = $false

if (-not (Test-Path $certFile) -or -not (Test-Path $keyFile)) {
    $regenerate = $true
} else {
    # Check existing certificate SAN for current IP
    try {
        $openssl = 'C:\Program Files\Git\usr\bin\openssl.exe'
        if (-not (Test-Path $openssl)) {
            $openssl = 'C:\Program Files\Git\mingw64\bin\openssl.exe'
        }
        $existing = & $openssl x509 -in $certFile -noout -text 2>$null | Out-String
        if (-not $existing.Contains("IP Address:$ip")) {
            $regenerate = $true
        }
    } catch {}
}

if ($regenerate) {
    if ($hasMkcert) {
        Write-Host "Erstelle vertrauenswuerdiges HTTPS-Zertifikat mit mkcert fuer $ip ..." -ForegroundColor Cyan
        mkcert -install | Out-Null
        mkcert -key-file $keyFile -cert-file $certFile $ip 127.0.0.1 localhost | Out-Null
    } else {
        $openssl = 'C:\Program Files\Git\usr\bin\openssl.exe'
        if (-not (Test-Path $openssl)) {
            $openssl = 'C:\Program Files\Git\mingw64\bin\openssl.exe'
        }
        if (Test-Path $openssl) {
            Write-Host "Erstelle self-signed HTTPS-Zertifikat fuer $ip ..." -ForegroundColor Cyan
            $cnf = @"
extensions = v3_req
[v3_req]
subjectAltName = IP:127.0.0.1, IP:$ip, DNS:localhost
"@
            $cnfPath = Join-Path (Join-Path $PSScriptRoot 'certs') 'req.cnf'
            $cnf | Set-Content -Path $cnfPath -Encoding UTF8
            & $openssl req -x509 -newkey rsa:2048 -keyout $keyFile -out $certFile -days 365 -nodes -subj '/CN=Der Lagerist' -req_exts v3_req -extensions v3_req -config $cnfPath 2>&1 | Out-Null
            Remove-Item -Path $cnfPath -ErrorAction SilentlyContinue
            Write-Host "Hinweis: mkcert ist nicht installiert. Das selbstsignierte Zertifikat fuehrt zu Browser-Warnungen." -ForegroundColor Yellow
        }
    }
}

$protocol = if ((Test-Path $certFile) -and (Test-Path $keyFile)) { 'https' } else { 'http' }

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  Der Lagerist wird gestartet" -ForegroundColor Cyan
Write-Host "  Host-URL: ${protocol}://${ip}:${port}/host" -ForegroundColor Yellow
Write-Host "  Client-URL: ${protocol}://${ip}:${port}/client" -ForegroundColor Yellow
Write-Host "====================================================" -ForegroundColor Cyan

# Start text UI in a second window
$uiPath = Join-Path $PSScriptRoot 'backend\console_ui.py'
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if ($python) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:Path = `'$env:Path`'; cd `'$PSScriptRoot`'; & `'$python`' `'$uiPath`'"
}

if ($protocol -eq 'https') {
    python -m uvicorn backend.app:asgi_app --host 0.0.0.0 --port $port --ssl-keyfile $keyFile --ssl-certfile $certFile --no-use-colors
} else {
    python -m uvicorn backend.app:asgi_app --host 0.0.0.0 --port $port --no-use-colors
}
