#!/usr/bin/env bash
# ==============================================================================
# tune_kernel.sh - Оптимизация сетевого стека ядра Linux (BBR, fq, TCP Fast Open)
# Настраивает буферы сокетов, уменьшает задержки и защищает от bufferbloat.
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "⚡ Оптимизация сетевого стека Linux (sysctl)"
echo "========================================================"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ошибка: Скрипт должен быть запущен с правами root (sudo)." >&2
    exit 1
fi

CONF_FILE="/etc/sysctl.d/99-network-tuning.conf"

echo "[1/4] Загрузка модуля ядра tcp_bbr..."
modprobe tcp_bbr 2>/dev/null || true

echo "[2/4] Запись параметров в $CONF_FILE..."
cat > "$CONF_FILE" << 'EOF'
# ====================================================================
# Оптимизация ядра Linux от ru-unblock-toolkit (BBR, fq, TCP Fast Open)
# ====================================================================

# Алгоритм BBR + планировщик очередей Fair Queuing
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr

# TCP Fast Open (0-RTT подключение для ускорения открытия сайтов)
net.ipv4.tcp_fastopen = 3

# Расширенные буферы сокетов (16 МБ max)
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# Тюнинг задержек и защита от Bufferbloat
net.ipv4.tcp_notsent_lowat = 16384
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15

# Очереди соединений и файловые дескрипторы
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 16384
fs.file-max = 2097152
EOF

echo "[3/4] Применение параметров sysctl --system..."
sysctl --system >/dev/null 2>&1 || sysctl -p "$CONF_FILE"

echo "[4/4] Проверка активных параметров:"
echo "  • Алгоритм CC: $(sysctl -n net.ipv4.tcp_congestion_control)"
echo "  • Планировщик qdisc: $(sysctl -n net.core.default_qdisc)"
echo "  • TCP Fast Open: $(sysctl -n net.ipv4.tcp_fastopen)"
echo "  • Max RMem: $(sysctl -n net.core.rmem_max) bytes"

echo "✅ Оптимизация ядра успешно завершена!"
