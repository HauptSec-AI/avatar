# Stop and remove the running Avatar container, if any.
$ErrorActionPreference = "SilentlyContinue"

docker rm -f avatar | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Avatar stopped"
} else {
    Write-Host "Avatar was not running"
}
