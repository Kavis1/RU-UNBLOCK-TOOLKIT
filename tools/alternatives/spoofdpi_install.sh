#!/usr/bin/env bash
# ==============================================================================
# spoofdpi_install.sh - Установка SpoofDPI
# Go-based инструмент обхода DPI на порту 40003.
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🛡️  Установка альтернативы: SpoofDPI"
echo "========================================================"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ошибка: Требуются права root." >&2
    exit 1
fi

DEST="/usr/local/bin/spoof-dpi"
SERVICE="/etc/systemd/system/spoofdpi.service"
PORT="40003"

ARCH=$(uname -m)
case "$ARCH" in
    x86_64) S_ARCH="amd64" ;;
    aarch64|arm64) S_ARCH="arm64" ;;
    *) echo "Неподдерживаемая архитектура: $ARCH"; exit 1 ;;
esac

echo "Загрузка SpoofDPI..."
URL="https://github.com/xvzc/SpoofDPI/releases/latest/download/spoof-dpi-linux-${S_ARCH}.tar.gz"
TMP_DIR=$(mktemp -d)
if curl -sLf -o "$TMP_DIR/spoof.tar.gz" "$URL"; then
    tar -xzf "$TMP_DIR/spoof.tar.gz" -C "$TMP_DIR"
    install -m 755 "$TMP_DIR/spoof-dpi" "$DEST"
    rm -rf "$TMP_DIR"
else
    echo "❌ Не удалось загрузить SpoofDPI с GitHub."
    exit 1
fi

echo "Создание службы systemd..."
cat > "$SERVICE" << EOF
[Unit]
Description=SpoofDPI Service
After=network.target

[Service]
Type=simple
ExecStart=$DEST -port $PORT -enable-doh -window-size 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable spoofdpi >/dev/null 2>&1 || true
systemctl restart spoofdpi

echo "✅ SpoofDPI успешно запущен на порту 127.0.0.1:$PORT!"
