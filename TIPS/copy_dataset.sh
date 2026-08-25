#!/bin/bash

# Volume에서 src로 테스트 데이터셋 복사

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOLUME_DIR="${SCRIPT_DIR}/volume"
SRC_DIR="${SCRIPT_DIR}/src"

echo "Copying testsets from volume to src..."
echo ""

# lle_testset 복사
echo "[1/2] Copying lle_testset..."
cp -r "${VOLUME_DIR}/lle_testset" "${SRC_DIR}/"
echo "  ✓ lle_testset copied"

# ob_testset 복사
echo "[2/2] Copying ob_testset..."
cp -r "${VOLUME_DIR}/ob_testset" "${SRC_DIR}/"
echo "  ✓ ob_testset copied"

echo ""
echo "Done! Testsets are ready in ${SRC_DIR}"
