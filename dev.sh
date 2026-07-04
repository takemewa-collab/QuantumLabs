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

# --- port on-kontrolu: 8000/3000 dolu mu? (auto-kill YOK; karar kullaniciya) ---
check_port() {
  local port="$1" pids
  pids="$(lsof -ti:"$port" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    pids="$(echo "$pids" | tr '\n' ' ' | sed 's/ *$//')"
    echo "ERROR: Port $port in use by PID $pids — run: kill $pids" >&2
    return 1
  fi
  return 0
}

port_busy=0
check_port 8000 || port_busy=1
check_port 3000 || port_busy=1
if [ "$port_busy" -eq 1 ]; then
  exit 1
fi

echo "QuantumLabs dev — backend :8000 + frontend :3000   (durdurmak icin Ctrl+C)"

BACK=""
FRONT=""

# Ctrl+C / cikis: mesaji TAM 1 kez bas, iki alt sureci (torunlar dahil) oldur, bekle.
shutdown() {
  trap - INT TERM EXIT          # re-entry engelle -> mesaj tekrar etmesin
  echo
  echo "[dev.sh] shutting down..."
  # once torunlar (npm->next-server, uvicorn reload worker), sonra ana surecler.
  [ -n "$FRONT" ] && pkill -P "$FRONT" 2>/dev/null
  [ -n "$BACK" ] && pkill -P "$BACK" 2>/dev/null
  kill "$BACK" "$FRONT" 2>/dev/null
  wait "$BACK" "$FRONT" 2>/dev/null
  return 0
}
trap shutdown INT TERM EXIT

# a) Backend — repo root'tan, --reload
uvicorn api.main:app --reload --port 8000 &
BACK=$!

# b) Frontend — web/ icinden
( cd web && npm run dev ) &
FRONT=$!

# ikisi de bitene (ya da Ctrl+C'ye) kadar bekle
wait
