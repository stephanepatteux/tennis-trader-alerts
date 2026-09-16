#!/usr/bin/env bash
# Idempotent Cloud Agent install: prepare a virtualenv and install deps.
set -euo pipefail

cd "$(dirname "$0")/.."

# The default image ships Python 3.12 but not always the venv/ensurepip module.
# Install it non-interactively if missing (safe/idempotent; no-op once present).
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "python3-venv (ensurepip) missing; installing..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements-dev.txt

echo "Install complete. Python: $(python --version)"
