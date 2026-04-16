#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT_DIR}/data"
MIRROR_DIR="${DATA_DIR}/raw-mirror"
LOG_DIR="${DATA_DIR}/logs"
INVENTORY_PATH="${DATA_DIR}/content-inventory.json"
BASE_URL="${1:-https://www.kcpestexperts.com/}"

mkdir -p "${MIRROR_DIR}" "${LOG_DIR}"

echo "Starting crawl: ${BASE_URL}"
echo "Mirror output: ${MIRROR_DIR}"

if command -v wget >/dev/null 2>&1; then
  # Mirror website content for offline review/migration.
  wget \
    --mirror \
    --convert-links \
    --adjust-extension \
    --page-requisites \
    --no-parent \
    --timeout=20 \
    --tries=3 \
    --wait=1 \
    --random-wait \
    --limit-rate=400k \
    --directory-prefix="${MIRROR_DIR}" \
    --domains="www.kcpestexperts.com" \
    --reject-regex=".*\\?.*" \
    --execute robots=off \
    "${BASE_URL}" \
    2>&1 | tee "${LOG_DIR}/wget.log"
else
  echo "wget not found, using Python crawler fallback"
  python3 "${ROOT_DIR}/tools/crawl_site.py" \
    --base-url "${BASE_URL}" \
    --output-dir "${MIRROR_DIR}" \
    2>&1 | tee "${LOG_DIR}/python-crawler.log"
fi

python3 "${ROOT_DIR}/tools/extract-content.py" \
  --mirror-dir "${MIRROR_DIR}" \
  --base-url "${BASE_URL}" \
  --output "${INVENTORY_PATH}"

echo "Inventory created at: ${INVENTORY_PATH}"
