#!/usr/bin/env bash
# ==============================================================================
# unblock.sh - Главная команда запуска ru-unblock-toolkit в 1 клик
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Проверка наличия Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "📦 Установка Python 3..."
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-yaml curl iptables
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3 python3-pip python3-pyyaml curl iptables
    fi
fi

# Установка зависимостей при необходимости
if [ -f "requirements.txt" ] && ! python3 -c "import yaml" 2>/dev/null; then
    echo "📦 Установка Python зависимостей..."
    pip3 install -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null || true
fi

# Запуск основного оркестратора
python3 "$SCRIPT_DIR/unblock.py" "$@"
