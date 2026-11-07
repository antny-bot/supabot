#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/supabot

git fetch origin

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 최신 커밋과 동일합니다 ($LOCAL_SHA). 빌드를 건너뜁니다."
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 새로운 커밋이 감지되었습니다 ($LOCAL_SHA -> $REMOTE_SHA). 배포를 시작합니다."
git reset --hard origin/main

VERSION="$(git describe --tags --always 2>/dev/null || echo dev)"
GIT_SHA="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"

VERSION="$VERSION" GIT_SHA="$GIT_SHA" docker compose up -d --build
docker image prune -f
