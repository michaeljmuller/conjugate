#!/usr/bin/env bash
# Pull the latest commit and restart the stack with it.
#
# Run on the server. Compose is invoked from src/docker/ so it picks up the
# .env sitting next to docker-compose.yml. The stack goes down before the pull
# so the running containers never straddle two commits, and the build stamps
# the freshly pulled commit into the image.
set -euo pipefail

cd "$(dirname "$0")/src/docker"

podman compose down
git pull
podman compose build
podman compose up -d
