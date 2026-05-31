#!/usr/bin/env bash
# 운영 데이터 백업 스크립트
# 사용법: ./scripts/backup.sh [백업 대상 디렉터리]
# 기본 대상: ./backups/YYYYMMDD_HHMMSS/

set -euo pipefail

DATA_DIR="${DATA_DIR:-./data}"
BACKUP_ROOT="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${DEST}"

for file in orders.json users.json; do
    src="${DATA_DIR}/${file}"
    if [[ -f "${src}" ]]; then
        cp "${src}" "${DEST}/${file}"
        echo "✅ 백업: ${src} → ${DEST}/${file}"
    else
        echo "⚠️  파일 없음 (건너뜀): ${src}"
    fi
done

echo "📦 백업 완료: ${DEST}"
