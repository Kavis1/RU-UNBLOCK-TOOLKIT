#!/usr/bin/env bash
# ==============================================================================
# warp_wireguard.sh - Настройка прямого интерфейса WireGuard WARP с fwmark и MSS clamping
# (Реализация классического Cloudflare WARP без MASQUE)
# ==============================================================================
set -euo pipefail

WARP_IF=warp
TABLE=200
PREF=200
MARK=51821
DIR=/etc/wireguard
CONF=$DIR/$WARP_IF.conf
EP="162.159.192.1:2408"
MTU=1280

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ошибка: Требуются права root." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard-tools iproute2 curl ca-certificates iptables iptables-persistent jq >/dev/null

mkdir -p "$DIR"
chmod 700 "$DIR"
cd "$DIR"

if [ ! -f "$CONF" ]; then
    echo "Регистрация нового аккаунта Cloudflare WARP..."
    PRIV=$(wg genkey)
    PUB=$(printf '%s' "$PRIV" | wg pubkey)
    TOS=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
    DATA="{\"key\":\"${PUB}\",\"install_id\":\"\",\"fcm_token\":\"\",\"tos\":\"${TOS}\",\"model\":\"PC\",\"type\":\"Android\",\"locale\":\"en_US\"}"
    
    REG=$(curl -s --fail --max-time 25 -X POST "https://api.cloudflareclient.com/v0a2158/reg" \
        -H "User-Agent: okhttp/3.12.1" -H "CF-Client-Version: a-6.10-2158" \
        -H "Content-Type: application/json" --data "$DATA" || true)

    PEER_PUB=$(printf '%s' "$REG" | jq -r '.config.peers[0].public_key' 2>/dev/null)
    V4=$(printf '%s' "$REG" | jq -r '.config.interface.addresses.v4' 2>/dev/null)
    V6=$(printf '%s' "$REG" | jq -r '.config.interface.addresses.v6' 2>/dev/null)

    if [ -z "$PEER_PUB" ] || [ "$PEER_PUB" = "null" ] || [ -z "$V4" ] || [ "$V4" = "null" ]; then
        echo "❌ Ошибка: Не удалось зарегистрировать аккаунт WARP через API."
        exit 1
    fi

    ADDR="${V4}/32, ${V6}/128"
    { echo "PRIV=$PRIV"; echo "ADDR=$ADDR"; echo "PUB=$PEER_PUB"; } > "$DIR/warp-creds.env"
    chmod 600 "$DIR/warp-creds.env"
else
    . "$DIR/warp-creds.env"
    PEER_PUB="$PUB"
fi

cat > "$CONF" << EOF
[Interface]
PrivateKey = $PRIV
Address = $ADDR
MTU = $MTU
Table = $TABLE
PostUp = ip rule add fwmark $MARK lookup $TABLE pref $PREF 2>/dev/null || true
PostUp = ip -6 rule add fwmark $MARK lookup $TABLE pref $PREF 2>/dev/null || true
PostUp = iptables -t nat -C POSTROUTING -o %i -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -o %i -j MASQUERADE
PreDown = ip rule del fwmark $MARK lookup $TABLE pref $PREF 2>/dev/null || true
PreDown = ip -6 rule del fwmark $MARK lookup $TABLE pref $PREF 2>/dev/null || true
PreDown = iptables -t nat -D POSTROUTING -o %i -j MASQUERADE 2>/dev/null || true

[Peer]
PublicKey = $PEER_PUB
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = $EP
PersistentKeepalive = 25
EOF

chmod 600 "$CONF"
systemctl enable wg-quick@$WARP_IF >/dev/null 2>&1 || true
systemctl restart wg-quick@$WARP_IF
sleep 2

# MSS Clamping
iptables -t mangle -C OUTPUT -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || \
  iptables -t mangle -A OUTPUT -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

iptables -t mangle -C POSTROUTING -o $WARP_IF -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || \
  iptables -t mangle -A POSTROUTING -o $WARP_IF -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

echo "✅ Cloudflare WARP wg-quick успешно поднят!"
