#!/usr/bin/env bash
# =============================================================================
# deploy_v4.sh — Instala o Kelevra SalesOps V4 (FastAPI + LangGraph) no Linux
#
# O que faz:
#   1. Valida Python3 e instala dependências virtuais (venv).
#   2. Cria diretórios em /opt/kelevra.
#   3. Copia os arquivos do pipeline V4.
#   4. Instala o arquivo .env
#   5. Configura o serviço Systemd (para rodar 24/7).
#   6. Inicia o serviço do motor SDR.
# =============================================================================
set -euo pipefail

APP_DIR="/opt/kelevra"
PIPELINE_DIR="$APP_DIR/pipeline"
VENV_DIR="$APP_DIR/venv"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Kelevra SalesOps V4 — Deploy na VPS (FastAPI / Systemd)"
echo "    Destino: $APP_DIR"

# 1) Python
if ! command -v python3 &>/dev/null; then
  echo "ERRO: Python3 não encontrado. Instale: apt-get update && apt-get install -y python3 python3-venv"
  exit 1
fi

mkdir -p "$PIPELINE_DIR"

# 2) Venv e Dependências
if [ ! -d "$VENV_DIR" ]; then
  echo "==> Criando ambiente virtual em $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
echo "==> Instalando dependências (requirements_v4.txt)..."
cp -f "$SRC_DIR/../../pipeline/requirements_v4.txt" "$APP_DIR/" || true
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SRC_DIR/../../pipeline/requirements_v4.txt" || echo "AVISO: Falha ao instalar dependências. Instale manualmente depois."

# 3) Copiar arquivos do Pipeline
echo "==> Copiando o código V4..."
cp -f "$SRC_DIR"/../../pipeline/*.py "$PIPELINE_DIR/"

# 4) Variáveis de Ambiente
if [ -f "$SRC_DIR/.env.vps" ]; then
  cp -f "$SRC_DIR/.env.vps" "$PIPELINE_DIR/.env"
  chmod 600 "$PIPELINE_DIR/.env"
  echo "==> .env instalado."
else
  echo "AVISO: .env.vps não encontrado. Lembre-se de configurar $PIPELINE_DIR/.env."
fi

# 5) Systemd Service
echo "==> Configurando Systemd Service (kelevra.service)..."
cp -f "$SRC_DIR/kelevra.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable kelevra.service
systemctl restart kelevra.service

echo "========================================="
echo "✅ Kelevra V4 instalado e rodando!"
echo "Para ver os logs, use: journalctl -fu kelevra"
echo "O motor escuta na porta 8000."
echo "Configure a Evolution API para disparar os Webhooks para http://SEU_IP:8000/webhook/evolution"
echo "========================================="
