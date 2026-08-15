#!/usr/bin/env bash
# ==============================================================================
# install_usque.sh - Установка и настройка Usque MASQUE CLI (Cloudflare WARP over HTTP/3)
# Создает локальный SOCKS5 прокси на 127.0.0.1:40001 для разблокировки геоблокированных ресурсов.
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🛡️  Развертывание Usque MASQUE CLI (SOCKS5)"
echo "========================================================"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ошибка: Требуются права root (sudo)." >&2
    exit 1
fi

BIN_DEST="/usr/local/bin/usque"
SERVICE_FILE="/etc/systemd/system/usque.service"
WORK_DIR="/opt/usque"
PORT="40001"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# 1. Проверка или скачивание бинарника
if [ ! -f "$BIN_DEST" ] && [ ! -f "/root/usque" ]; then
    echo "[1/4] Поиск и загрузка бинарника usque..."
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) USQUE_ARCH="amd64" ;;
        aarch64|arm64) USQUE_ARCH="arm64" ;;
        *) echo "Неподдерживаемая архитектура: $ARCH"; exit 1 ;;
    esac

    DOWNLOAD_URL="https://github.com/hrost/usque/releases/latest/download/usque-linux-${USQUE_ARCH}.tar.gz"
    echo "Загрузка: $DOWNLOAD_URL"
    
    if curl -sLf --connect-timeout 10 -o usque.tar.gz "$DOWNLOAD_URL"; then
        tar -xzf usque.tar.gz
        install -m 755 usque "$BIN_DEST"
        rm -f usque.tar.gz
    else
        echo "⚠️ Загрузка архива не удалась, проверяем локальный бинарник /root/usque..."
        if [ -f "/root/usque" ]; then
            cp /root/usque "$BIN_DEST"
            chmod +x "$BIN_DEST"
        else
            echo "❌ Не удалось найти или загрузить usque. Пожалуйста, поместите бинарник в /usr/local/bin/usque"
            exit 1
        fi
    fi
else
    if [ -f "/root/usque" ] && [ ! -f "$BIN_DEST" ]; then
        cp /root/usque "$BIN_DEST"
        chmod +x "$BIN_DEST"
    fi
    echo "[1/4] Бинарник usque уже установлен в $BIN_DEST."
fi

# 2. Создание systemd сервиса
echo "[2/4] Создание службы systemd ($SERVICE_FILE)..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=usque WARP MASQUE SOCKS5 (TCP+UDP)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$WORK_DIR
ExecStart=$BIN_DEST socks -b 127.0.0.1 -p $PORT --udp-timeout 120s
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# 3. Перезапуск службы
echo "[3/4] Запуск службы usque.service..."
systemctl daemon-reload
systemctl enable usque >/dev/null 2>&1 || true
systemctl restart usque

# 4. Проверка работы SOCKS5
echo "[4/4] Проверка SOCKS5 прокси на 127.0.0.1:$PORT..."
sleep 2

if curl -s --max-time 10 --socks5 127.0.0.1:$PORT https://www.cloudflare.com/cdn-cgi/trace | grep -E "^(ip|warp|loc)="; then
    echo "✅ Usque MASQUE успешно запущен и работает через SOCKS5 127.0.0.1:$PORT!"
else
    echo "⚠️ Внимание: Служба запущена, но прямой тест Cloudflare trace не вернул ответ. Проверьте: journalctl -u usque -n 20"
fi
