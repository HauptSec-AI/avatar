# Build and run Avatar as a single Docker container. Stops any existing
# container first, then rebuilds. Run from anywhere; it finds the repo root.
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found - install Docker Desktop first"
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is not running - start Docker Desktop first"
    exit 1
}
if (-not (Test-Path ".env")) {
    Write-Error ".env not found in $RepoRoot - follow README.md setup instructions first"
    exit 1
}

docker rm -f avatar 2>$null | Out-Null
docker build -t avatar .
docker run -d --name avatar --env-file .env -p 8000:8000 avatar

Write-Host "Avatar running at http://localhost:8000 (admin at http://localhost:8000/admin)"
