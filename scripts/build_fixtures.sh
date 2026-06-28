#!/usr/bin/env bash
# Build perso.wasm and copy policy.json for integration tests.
#
# Uses the perso core repo to compile the WASM engine and grabs the
# spec policy (policies/example.json) that the 18 test cases were
# written against.
#
# Usage:
#   ./scripts/build_fixtures.sh
#
# Optional env vars:
#   PERSO_REPO_PATH  — path to a local clone of github.com/teknokeras/perso
#                      (default: ../perso relative to this SDK repo)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FIXTURES_DIR="${REPO_ROOT}/tests/fixtures"

# Locate the perso core repo
PERSO_REPO="${PERSO_REPO_PATH:-$(cd "${REPO_ROOT}/../perso" 2>/dev/null && pwd || echo "")}"

if [[ -z "${PERSO_REPO}" || ! -d "${PERSO_REPO}" ]]; then
    echo "ERROR: perso core repo not found."
    echo "  Expected: ${REPO_ROOT}/../perso"
    echo "  Or set PERSO_REPO_PATH=/path/to/perso"
    exit 1
fi

echo "[build_fixtures] Using perso repo: ${PERSO_REPO}"
echo "[build_fixtures] Output:           ${FIXTURES_DIR}"

# Build the WASM binary using the policy-compiler crate
cd "${PERSO_REPO}"

echo "[build_fixtures] Building policy_runtime.wasm (this takes ~30s on first run)..."
# Note: the policy is NOT embedded into the WASM binary — it is passed to init()
# at runtime. The build command just compiles the evaluation engine.
cargo run -p policy-compiler -- build \
    --output dist/policy_runtime.wasm

# Copy artifacts into tests/fixtures/
mkdir -p "${FIXTURES_DIR}"
cp "${PERSO_REPO}/dist/policy_runtime.wasm" "${FIXTURES_DIR}/perso.wasm"
cp "${PERSO_REPO}/policies/example.json"    "${FIXTURES_DIR}/policy.json"

echo "[build_fixtures] Done."
echo "  ${FIXTURES_DIR}/perso.wasm"
echo "  ${FIXTURES_DIR}/policy.json"
echo ""
echo "Run the integration tests with:"
echo "  pytest tests/test_integration.py -v"
