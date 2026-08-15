#!/usr/bin/env bash
# ==============================================================================
# install_zapret.sh - Установка и настройка Zapret DPI Bypass (nfqws)
# Разблокировка YouTube 4K, Discord, Twitter и DPI-фильтрованных сайтов на уровне ядра Linux.
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🛡️  Установка и настройка Zapret DPI Bypass"
echo "========================================================"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ошибка: Требуются права root (sudo)." >&2
    exit 1
fi

ZAPRET_DIR="/opt/zapret"
USER_HOSTS="/opt/zapret/ipset/zapret-hosts-user.txt"

# 1. Установка системных зависимостей
echo "[1/4] Установка пакетов (iptables, ipset, libnetfilter-queue)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl iptables ipset libnetfilter-queue1 netfilter-persistent >/dev/null 2>&1 || true

# 2. Скачивание / обновление репозитория Zapret
if [ ! -d "$ZAPRET_DIR" ]; then
    echo "[2/4] Клонирование репозитория Zapret в $ZAPRET_DIR..."
    git clone --depth 1 https://github.com/bol-van/zapret.git "$ZAPRET_DIR"
else
    echo "[2/4] Репозиторий Zapret уже существует в $ZAPRET_DIR. Обновление..."
    cd "$ZAPRET_DIR" && git pull --ff-only || true
fi

cd "$ZAPRET_DIR"

# 3. Инициализация бинарников nfqws
if [ ! -f "$ZAPRET_DIR/binaries/x86_64/nfqws" ] && [ ! -f "$ZAPRET_DIR/nfq/nfqws" ]; then
    echo "Компиляция / установка бинарников zapret..."
    ./install_bin.sh || true
fi

# 4. Настройка конфигурации для обхода замедления YouTube и блокировки Discord
echo "[3/4] Настройка конфигурации /opt/zapret/config..."
cat > "$ZAPRET_DIR/config" << 'EOF'
# Конфигурация Zapret от ru-unblock-toolkit
FWTYPE=iptables
MODE=nfqws
MODE_HTTP=1
MODE_HTTP_KEEPALIVE=0
MODE_HTTPS=1
MODE_QUIC=1

# Стратегии десинхронизации DPI
NFQWS_OPT_DESYNC="--dpi-desync=fake,multisplit --dpi-desync-split-pos=2 --dpi-desync-fooling=md5sig,badseq --dpi-desync-fake-tls=/opt/zapret/files/fake/tls_clienthello_www_google_com.bin"
NFQWS_OPT_DESYNC_HTTP="--dpi-desync=split2 --dpi-desync-split-pos=2"
NFQWS_OPT_DESYNC_HTTPS="--dpi-desync=fake,multisplit --dpi-desync-split-pos=2 --dpi-desync-fooling=md5sig,badseq --dpi-desync-fake-tls=/opt/zapret/files/fake/tls_clienthello_www_google_com.bin"
NFQWS_OPT_DESYNC_QUIC="--dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic=/opt/zapret/files/fake/quic_initial_google.bin"

# Списки хостов
MODE_FILTER=none
DESYNC_MARK=0x40000000
EOF

# Скопируем список доменов
mkdir -p "$ZAPRET_DIR/ipset"
if [ -f "$(dirname "$0")/../data/popular_ru_blocked.txt" ]; then
    cp "$(dirname "$0")/../data/popular_ru_blocked.txt" "$USER_HOSTS"
fi

# 5. Запуск службы zapret
echo "[4/4] Активация и запуск службы zapret..."
if [ -f "$ZAPRET_DIR/init.d/sysv/zapret" ]; then
    cp "$ZAPRET_DIR/init.d/sysv/zapret" /etc/init.d/zapret
    chmod 755 /etc/init.d/zapret
fi

if [ -f "$ZAPRET_DIR/init.d/systemd/zapret.service" ]; then
    cp "$ZAPRET_DIR/init.d/systemd/zapret.service" /etc/systemd/system/zapret.service
    systemctl daemon-reload
    systemctl enable zapret >/dev/null 2>&1 || true
    systemctl restart zapret || /etc/init.d/zapret restart || true
fi

echo "✅ Zapret DPI Bypass успешно установлен и запущен!"
