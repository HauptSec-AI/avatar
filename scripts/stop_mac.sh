#!/usr/bin/env bash
# Stop and remove the running Avatar container, if any.
set -euo pipefail

if docker rm -f avatar >/dev/null 2>&1; then
  echo "Avatar stopped"
else
  echo "Avatar was not running"
fi
