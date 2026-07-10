#!/usr/bin/env bash
# Build and run Avatar as a single Docker container. Stops any existing
# container first, then rebuilds. Run from anywhere; it finds the repo root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

command -v docker >/dev/null || { echo "Docker not found — install Docker Desktop first"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running — start Docker Desktop first"; exit 1; }
[ -f .env ] || { echo ".env not found in $REPO_ROOT — follow README.md setup instructions first"; exit 1; }

docker rm -f avatar >/dev/null 2>&1 || true
docker build -t avatar .
docker run -d --name avatar --env-file .env -p 8000:8000 avatar

echo "Avatar running at http://localhost:8000 (admin at http://localhost:8000/admin)"
