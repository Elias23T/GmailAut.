# Arma .release/correoia-<fecha>-<commit>.tar.gz con la interfaz compilada (web/), el backend
# sin entorno virtual y las plantillas de deploy/cpanel. El servidor no necesita Node; las
# dependencias Python se instalan alla en un venv por version.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$commit = (git -C $root rev-parse --short HEAD).Trim()
if (git -C $root status --porcelain) { Write-Warning 'Hay cambios sin commit; el paquete incluye los archivos tal como estan ahora.' }
$name = 'correoia-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $commit
$releaseDir = Join-Path $root '.release'
$stage = Join-Path $releaseDir $name
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$frontend = Join-Path $root 'frontend'
Push-Location $frontend
try {
    if (!(Test-Path -LiteralPath 'node_modules')) { npm ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'npm ci fallo.' } }
    $env:VITE_API_BASE_URL = '/api'
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'La compilacion del frontend fallo.' }
} finally {
    Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
    Pop-Location
}
$web = Join-Path $stage 'web'
Copy-Item -Recurse -Path (Join-Path $frontend 'dist') -Destination $web
Copy-Item -Path (Join-Path $root 'deploy/cpanel/.htaccess') -Destination $web

$backend = Join-Path $stage 'backend'
robocopy (Join-Path $root 'backend') $backend /E /XD .venv __pycache__ .pytest_cache *.egg-info /XF .env *.env *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'No se pudo copiar el backend.' }
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'scripts') | Out-Null
Copy-Item -Path (Join-Path $root 'scripts/configure_production.py') -Destination (Join-Path $stage 'scripts')
Copy-Item -Recurse -Path (Join-Path $root 'deploy/cpanel') -Destination (Join-Path $stage 'deploy')

Set-Content -Path (Join-Path $stage 'RELEASE') -Value $name -NoNewline
$package = Join-Path $releaseDir "$name.tar.gz"
# tar de Windows: el de Git interpreta "C:" como un host remoto.
& (Join-Path $env:SystemRoot 'System32\tar.exe') -czf $package -C $stage .
if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprimir el paquete.' }
Remove-Item -Recurse -Force -Path $stage
Write-Host "Paquete: $package ($([math]::Round((Get-Item $package).Length / 1MB, 1)) MB)"
