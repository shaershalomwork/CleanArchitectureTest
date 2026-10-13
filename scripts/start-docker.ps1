[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers, then try again.' }

    if (-not (Test-Path -LiteralPath '.env')) {
        $certPassword = [Guid]::NewGuid().ToString('N')
        $adminPassword = [Guid]::NewGuid().ToString('N')
        @("HTTPS_CERT_PASSWORD=$certPassword", "KEYCLOAK_ADMIN_PASSWORD=$adminPassword") |
            Set-Content -LiteralPath '.env' -Encoding ascii
    }
    $passwordLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^HTTPS_CERT_PASSWORD=' } | Select-Object -First 1
    if (-not $passwordLine) { throw 'HTTPS_CERT_PASSWORD is missing from .env.' }
    $certPassword = $passwordLine.Substring('HTTPS_CERT_PASSWORD='.Length)
    New-Item -ItemType Directory -Path '.local/https' -Force | Out-Null
    dotnet dev-certs https --export-path .local/https/api.pfx --password $certPassword
    if ($LASTEXITCODE -ne 0) { throw 'Could not export the development HTTPS certificate.' }
    dotnet dev-certs https --trust
    if ($LASTEXITCODE -ne 0) { throw 'Could not trust the development HTTPS certificate.' }

    docker compose up --build --detach --wait --wait-timeout 240
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose startup failed. Run docker compose logs to inspect the error.' }

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing 'https://localhost:7001/openapi/v1.json'
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $ready) { throw 'The API did not become ready. Run docker compose logs api.' }
    Write-Host 'API: https://localhost:7001/scalar/v1'
    Write-Host 'Test login: demo / Demo-local-2026!'
    Write-Host 'Keycloak admin: http://localhost:8080/admin (admin password is in .env)'
} finally {
    Pop-Location
}
