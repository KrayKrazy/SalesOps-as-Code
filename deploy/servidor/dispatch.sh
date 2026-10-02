#!/usr/bin/env bash
# =============================================================================
# dispatch.sh — executa UM disparo do SDR Kelevra com janela aleatória (anti-ban).
#
# Uso:  dispatch.sh [limit] [window_minutes]
#   limit          = nº de leads a enviar (padrão 14)
#   window_minutes = janela de aleatoriedade em minutos (padrão 120)
#
# Espelha o comportamento do dispatch.ps1 do Windows:
#   1. Dorme um tempo aleatório (0..window_min) antes de disparar.
#   2. Roda sdr_pipeline.py --send --limit <limit>.
#   3. Grava o log em logs/dispatch_<timestamp>.log e dispatch_all.log.
# =============================================================================
export TZ=America/Sao_Paulo
set -uo pipefail

LIMIT="${1:-14}"
WINDOW_MIN="${2:-120}"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$APP_DIR/pipeline"
LOG_DIR="$APP_DIR/logs"
PY_BIN="${PY_BIN:-$(command -v python3 || command -v python)}"

mkdir -p "$LOG_DIR"

# Janela aleatória (0..window_min*60 segundos) — anti-ban
SLEEP_SEC=0
if [ "$WINDOW_MIN" -gt 0 ] 2>/dev/null; then
  SLEEP_SEC=$(( RANDOM % (WINDOW_MIN * 60) ))
fi

STAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
LOG="$LOG_DIR/dispatch_${STAMP}.log"

echo "[$STAMP] Janela aleatória: dormindo ${SLEEP_SEC}s antes do disparo (limit=$LIMIT)" | tee "$LOG"
sleep "$SLEEP_SEC"

cd "$PIPELINE_DIR"
"$PY_BIN" sdr_pipeline.py --send --limit "$LIMIT" --score >> "$LOG" 2>&1

{
  echo ""
  echo "===== $STAMP | Limit=$LIMIT | WindowMin=$WINDOW_MIN | SleepSec=$SLEEP_SEC ====="
  cat "$LOG"
} >> "$LOG_DIR/dispatch_all.log"
