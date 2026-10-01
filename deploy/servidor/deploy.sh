#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Instala o pipeline Kelevra SalesOps no servidor Linux e agenda os
#             disparos via cron (OPÇÃO B).
#
# O que faz:
#   1. Valida o Python3.
#   2. Cria /opt/kelevra/{pipeline,logs}.
#   3. Copia os arquivos .py do pipeline.
#   4. Instala o .env (a partir de .env.servidor, se existir).
#   5. Instala o dispatch.sh (janela aleatória anti-ban).
#   6. Ajusta o fuso para America/Sao_Paulo (janelas de disparo).
#   7. Grava /etc/cron.d/kelevra (3 disparos + inbound sync).
#
# Uso:  sudo bash deploy.sh
#        (ou como root)
# =============================================================================
set -euo pipefail

APP_DIR="${KELEVRA_DIR:-/opt/kelevra}"
PIPELINE_DIR="$APP_DIR/pipeline"
LOG_DIR="$APP_DIR/logs"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Kelevra SalesOps — deploy no servidor (Opção B: cron)"
echo "    Destino: $APP_DIR"

# 1) Python
PY_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PY_BIN" ]; then
  echo "ERRO: Python3 não encontrado. Instale (ex.: apt-get install -y python3) e rode de novo."
  exit 1
fi
echo "    Python: $PY_BIN ($("$PY_BIN" --version 2>&1))"

# 2) Diretórios
mkdir -p "$PIPELINE_DIR" "$LOG_DIR"

# 3) Pipeline (.py)
if ! ls "$SRC_DIR"/pipeline/*.py >/dev/null 2>&1; then
  echo "ERRO: não encontrei pipeline/*.py ao lado do deploy.sh."
  echo "      Extraia o tar.gz e rode: bash deploy.sh"
  exit 1
fi
cp -f "$SRC_DIR"/pipeline/*.py "$PIPELINE_DIR/"
echo "    Copiados: $(ls "$PIPELINE_DIR"/*.py | wc -l) arquivos .py"

# 4) .env
if [ -f "$SRC_DIR/.env.servidor" ]; then
  cp -f "$SRC_DIR/.env.servidor" "$PIPELINE_DIR/.env"
  chmod 600 "$PIPELINE_DIR/.env"
  echo "    .env instalado em $PIPELINE_DIR/.env (chmod 600)"
else
  echo "    AVISO: .env.servidor não encontrado. Crie $PIPELINE_DIR/.env manualmente."
fi

# 5) dispatch.sh
if [ -f "$SRC_DIR/dispatch.sh" ]; then
  cp -f "$SRC_DIR/dispatch.sh" "$APP_DIR/dispatch.sh"
  chmod +x "$APP_DIR/dispatch.sh"
  echo "    dispatch.sh instalado em $APP_DIR/dispatch.sh"
fi

# 6) Arquivos auxiliares (fechados / respondentes)
for f in fechados.txt respondentes.txt; do
  if [ -f "$SRC_DIR/$f" ]; then
    cp -f "$SRC_DIR/$f" "$APP_DIR/$f"
    echo "    $f copiado para $APP_DIR/$f"
  else
    touch "$APP_DIR/$f"
    echo "    $f criado (vazio) em $APP_DIR/$f"
  fi
done

# 7) Fuso horário (Brasília) — para as janelas de disparo baterem com o esperado
if command -v timedatectl >/dev/null 2>&1; then
  timedatectl set-timezone America/Sao_Paulo >/dev/null 2>&1 || true
elif [ -f /usr/share/zoneinfo/America/Sao_Paulo ]; then
  ln -sf /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime || true
fi
echo "    Fuso ajustado para America/Sao_Paulo (se aplicável)"

# 8) Cron
CRON_FILE="/etc/cron.d/kelevra"
cat > "$CRON_FILE" <<EOF
# Kelevra SalesOps — disparos diários + inbound sync.
# Janelas (Brasília): Manhã 08:30 / Tarde 13:30 / Noite 18:30 (+ até 120 min aleatório).
CRON_TZ=America/Sao_Paulo

# Manhã — envia 14 leads
30 8 * * * root $APP_DIR/dispatch.sh 14 120 >> $LOG_DIR/cron_manha.log 2>&1

# Tarde — envia 14 leads
30 13 * * * root $APP_DIR/dispatch.sh 14 120 >> $LOG_DIR/cron_tarde.log 2>&1

# Noite — envia 14 leads
30 18 * * * root $APP_DIR/dispatch.sh 14 120 >> $LOG_DIR/cron_noite.log 2>&1

# Inbound Sync — a cada 30 min (captura respostas da Evolution)
*/30 * * * * root cd $PIPELINE_DIR && $PY_BIN inbound_sync.py >> $LOG_DIR/inbound_sync.log 2>&1

# Follow-up automático — (opcional) descomente para ativar o 2º toque
# */30 * * * * root cd $PIPELINE_DIR && $PY_BIN followup_pipeline.py --send --limit 5 >> $LOG_DIR/followup.log 2>&1
EOF
chmod 644 "$CRON_FILE"
echo "    Cron instalado em $CRON_FILE"

echo ""
echo "==> Pronto!"
echo "    Teste manual (dry-run):  cd $PIPELINE_DIR && $PY_BIN sdr_pipeline.py --limit 3"
echo "    Ver logs:                tail -f $LOG_DIR/dispatch_all.log"
echo ""
echo "    IMPORTANTE: desative as tarefas do Windows (no notebook) para não haver"
echo "    dois motores disputando os mesmos leads."
