#!/usr/bin/env bash
# ==============================================================================
# quick_start.sh - Автоматический установщик и запуск ru-unblock-toolkit в 1 строку
# ==============================================================================
set -euo pipefail

REPO_URL="https://github.com/Kavis1/RU-UNBLOCK-TOOLKIT.git"
INSTALL_DIR="/opt/ru-unblock-toolkit"

echo "========================================================"
echo "🚀 Быстрый запуск RU-UNBLOCK-TOOLKIT"
echo "========================================================"

# Проверка root прав
if [ "$(id -u)" -ne 0 ]; then
    echo "⚠️ Запуск требует прав root. Перезапуск через sudo..."
    exec sudo bash "$0" "$@"
fi

# Установка git, python3 и curl если отсутствуют
export DEBIAN_FRONTEND=noninteractive
if ! command -v git >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    echo "📦 Установка базовых системных зависимостей (git, python3, curl)..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y -qq git python3 python3-pip python3-yaml curl iptables
    elif command -v yum >/dev/null 2>&1; then
        yum install -y git python3 python3-pip python3-pyyaml curl iptables
    fi
fi

# Клонирование или обновление репозитория
if [ ! -d "$INSTALL_DIR" ]; then
    echo "📥 Клонирование репозитория в $INSTALL_DIR..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
    echo "🔄 Обновление существующей копии репозитория..."
    cd "$INSTALL_DIR" && git pull --ff-only 2>/dev/null || true
fi

cd "$INSTALL_DIR"
chmod +x unblock.sh scripts/*.sh tools/*/*.sh 2>/dev/null || true

# Установка pip зависимостей если необходимо
if ! python3 -c "import yaml" 2>/dev/null; then
    pip3 install -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null || true
fi

# Запуск с перенаправлением stdin на терминал для интерактивного выбора
if [ -t 0 ]; then
    exec ./unblock.sh "$@"
else
    exec ./unblock.sh "$@" < /dev/tty
fi
