#!/usr/bin/env bash
# QuantumLabs — tek komutla dev ortami: backend (:8000) + frontend (:3000).
# Ctrl+C ikisini de durdurur.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
VENV="$ROOT/.venv"

# --- backend on-kosullar ---
if [ ! -d "$VENV" ]; then
  echo "HATA: .venv bulunamadi ($VENV)." >&2
  echo "  Kur:  python3 -m venv .venv && source .venv/bin/activate && python -m ensurepip --upgrade && pip install -e ." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

if ! python -m pip --version >/dev/null 2>&1; then
  echo "HATA: bu venv'de pip yok." >&2
  echo "  Coz:  source .venv/bin/activate && python -m ensurepip --upgrade" >&2
  exit 1
fi

if ! python -c "import uvicorn" >/dev/null 2>&1; then
  echo "HATA: uvicorn kurulu degil (backend bagimliliklari eksik)." >&2
  echo "  Kur:  source .venv/bin/activate && pip install -e .  (veya: pip install fastapi uvicorn)" >&2
  exit 1
fi

# --- frontend on-kosul ---
if [ ! -d "$ROOT/web/node_modules" ]; then
  echo "HATA: web/node_modules yok." >&2
  echo "  Kur:  cd web && npm install" >&2
  exit 1
fi

echo "QuantumLabs dev — backend :8000 + frontend :3000   (durdurmak icin Ctrl+C)"

# Ctrl+C / cikis: tum process group'u oldur (uvicorn + npm + next-server).
trap 'echo; echo "[dev.sh] durduruluyor..."; kill 0' SIGINT SIGTERM EXIT

# a) Backend — repo root'tan, --reload
uvicorn api.main:app --reload --port 8000 &

# b) Frontend — web/ icinden
( cd web && npm run dev ) &

# ikisi de bitene (ya da Ctrl+C'ye) kadar bekle
wait
