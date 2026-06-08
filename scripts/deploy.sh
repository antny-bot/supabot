#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/supabot

git fetch origin
git reset --hard origin/main

VERSION="$(git describe --tags --always 2>/dev/null || echo dev)"
GIT_SHA="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"

VERSION="$VERSION" GIT_SHA="$GIT_SHA" docker compose up -d --build
docker image prune -f
