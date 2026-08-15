#!/usr/bin/env bash
# ==============================================================================
# byedpi_install.sh - Установка ByeDPI (ciadpi)
# Легковесный userspace TCP desync прокси на порту 40002.
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🛡️  Установка альтернативы: ByeDPI (ciadpi)"
echo "========================================================"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ошибка: Требуются права root." >&2
    exit 1
fi

DEST="/usr/local/bin/ciadpi"
SERVICE="/etc/systemd/system/byedpi.service"
PORT="40002"

ARCH=$(uname -m)
case "$ARCH" in
    x86_64) BYE_ARCH="x86_64" ;;
    aarch64|arm64) BYE_ARCH="aarch64" ;;
    *) echo "Неподдерживаемая архитектура: $ARCH"; exit 1 ;;
esac

echo "Загрузка ciadpi..."
URL="https://github.com/hufrea/byedpi/releases/latest/download/byedpi-12-${BYE_ARCH}.tar.gz"
TMP_DIR=$(mktemp -d)
if curl -sLf -o "$TMP_DIR/byedpi.tar.gz" "$URL"; then
    tar -xzf "$TMP_DIR/byedpi.tar.gz" -C "$TMP_DIR"
    install -m 755 "$TMP_DIR/ciadpi-${BYE_ARCH}" "$DEST" || install -m 755 "$TMP_DIR/ciadpi" "$DEST"
    rm -rf "$TMP_DIR"
else
    echo "❌ Не удалось загрузить ByeDPI с GitHub."
    exit 1
fi

echo "Создание службы systemd..."
cat > "$SERVICE" << EOF
[Unit]
Description=ByeDPI SOCKS5 Proxy
After=network.target

[Service]
Type=simple
ExecStart=$DEST -i 127.0.0.1 -p $PORT --disorder 1 --auto=torst --fake -1 --ttl 8
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable byedpi >/dev/null 2>&1 || true
systemctl restart byedpi

echo "✅ ByeDPI успешно запущен на SOCKS5 127.0.0.1:$PORT!"
