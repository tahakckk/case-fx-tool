#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python -m pytest -q -p no:cacheprovider tests
