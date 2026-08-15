#!/usr/bin/env python3
"""
tool_manager.py - Менеджер инструментов обхода блокировок.
Управляет жизненным циклом (установка, запуск, проверка статуса, остановка):
 1. Usque MASQUE CLI (HTTP/3 over QUIC SOCKS5 прокси на 127.0.0.1:40001)
 2. Zapret DPI bypass (nfqws / tpws на уровне iptables/nftables)
 3. Cloudflare WARP (WireGuard wg-quick / warp-svc)
 4. Альтернативы: ByeDPI (ciadpi) и SpoofDPI
"""

import os
import platform
import shutil
import subprocess
import socket
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger("ru_unblock.tool_manager")


@dataclass
class ToolStatus:
    name: str
    installed: bool
    running: bool
    endpoint: str = ""
    details: str = ""


class ToolManager:
    """Управляет установкой и запуском сервисов обхода."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.is_linux = platform.system().lower() == "linux"

        # Порты по умолчанию
        self.usque_port = 40001
        self.byedpi_port = 40002
        self.spoofdpi_port = 40003

    def is_port_open(self, port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
        """Проверяет, слушает ли локальный порт службу."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    # --- 1. Usque MASQUE CLI ---

    def status_usque(self) -> ToolStatus:
        """Проверяет статус Usque MASQUE CLI."""
        installed = shutil.which("usque") is not None or os.path.exists("/usr/local/bin/usque") or os.path.exists("/root/usque")
        running = self.is_port_open(self.usque_port)

        # Проверка systemctl на Linux
        if self.is_linux and not running:
            res = subprocess.run(["systemctl", "is-active", "usque"], capture_output=True, text=True, check=False)
            if "active" in res.stdout:
                running = True

        return ToolStatus(
            name="Usque MASQUE CLI",
            installed=installed,
            running=running,
            endpoint=f"socks5://127.0.0.1:{self.usque_port}",
            details="Cloudflare WARP over HTTP/3 (MASQUE). Обходит блокировки OpenAI, Claude, Spotify, Netflix"
        )

    def install_usque(self) -> Tuple[bool, str]:
        """Устанавливает Usque бинарник и systemd сервис."""
        if not self.is_linux:
            return False, "Установка системного сервиса Usque поддерживается на Linux (Ubuntu/Debian)"

        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "install_usque.sh")
        if os.path.exists(script_path):
            try:
                res = subprocess.run(["bash", script_path], capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    return True, "Usque MASQUE успешно установлен и запущен на порту 40001."
                return False, f"Ошибка установки Usque: {res.stderr}"
            except Exception as e:
                return False, f"Сбой скрипта install_usque.sh: {e}"

        return self._install_usque_direct()

    def _install_usque_direct(self) -> Tuple[bool, str]:
        """Прямая установка usque и создание systemd юнита."""
        service_content = f"""[Unit]
Description=usque WARP MASQUE SOCKS5 (TCP+UDP)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/root
ExecStart=/usr/local/bin/usque socks -b 127.0.0.1 -p {self.usque_port} --udp-timeout 120s
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""
        try:
            with open("/etc/systemd/system/usque.service", "w", encoding="utf-8") as f:
                f.write(service_content)
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "enable", "--now", "usque"], check=False)
            return True, "Usque сервис настроен."
        except Exception as e:
            return False, str(e)

    # --- 2. Zapret DPI Bypass ---

    def status_zapret(self) -> ToolStatus:
        """Проверяет статус Zapret (nfqws/tpws)."""
        installed = os.path.exists("/opt/zapret") or shutil.which("nfqws") is not None
        running = False

        if self.is_linux:
            res = subprocess.run(["pgrep", "-f", "nfqws"], capture_output=True, text=True, check=False)
            if res.stdout.strip():
                running = True
            else:
                res_sys = subprocess.run(["systemctl", "is-active", "zapret"], capture_output=True, text=True, check=False)
                running = "active" in res_sys.stdout

        return ToolStatus(
            name="Zapret DPI Bypass (nfqws)",
            installed=installed,
            running=running,
            endpoint="iptables / NFQUEUE",
            details="Обход DPI на уровне ядра (YouTube 4K, Discord, Twitter) без снижения скорости"
        )

    def install_zapret(self) -> Tuple[bool, str]:
        """Устанавливает zapret из официального репозитория."""
        if not self.is_linux:
            return False, "Zapret поддерживается на Linux (nfqueue/iptables)"

        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "install_zapret.sh")
        if os.path.exists(script_path):
            try:
                res = subprocess.run(["bash", script_path], capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    return True, "Zapret успешно установлен и активирован с пресетами для YouTube/Discord."
                return False, f"Ошибка установки Zapret: {res.stderr}"
            except Exception as e:
                return False, f"Сбой скрипта install_zapret.sh: {e}"

        return False, "Скрипт scripts/install_zapret.sh не найден"

    # --- 3. Cloudflare WARP (WireGuard) ---

    def status_warp_wg(self) -> ToolStatus:
        """Проверяет статус интерфейса WireGuard WARP."""
        running = False
        if self.is_linux:
            res = subprocess.run(["ip", "link", "show", "warp"], capture_output=True, text=True, check=False)
            running = res.returncode == 0

        return ToolStatus(
            name="Cloudflare WARP (WireGuard wg-quick)",
            installed=shutil.which("wg") is not None,
            running=running,
            endpoint="dev warp (table 200 / fwmark 51821)",
            details="Прямой WireGuard туннель к Cloudflare с MSS clamping"
        )

    # --- 4. Альтернативы: ByeDPI & SpoofDPI ---

    def status_byedpi(self) -> ToolStatus:
        """Проверяет статус ByeDPI (ciadpi)."""
        installed = shutil.which("ciadpi") is not None or os.path.exists("/usr/local/bin/ciadpi")
        running = self.is_port_open(self.byedpi_port)
        return ToolStatus(
            name="ByeDPI (ciadpi)",
            installed=installed,
            running=running,
            endpoint=f"socks5://127.0.0.1:{self.byedpi_port}",
            details="Легковесный userspace TCP desync прокси для обхода DPI"
        )

    def status_spoofdpi(self) -> ToolStatus:
        """Проверяет статус SpoofDPI."""
        installed = shutil.which("spoof-dpi") is not None or os.path.exists("/usr/local/bin/spoof-dpi")
        running = self.is_port_open(self.spoofdpi_port)
        return ToolStatus(
            name="SpoofDPI",
            installed=installed,
            running=running,
            endpoint=f"http://127.0.0.1:{self.spoofdpi_port}",
            details="Go-based DPI circumvention HTTP/HTTPS proxy"
        )

    def get_all_statuses(self) -> Dict[str, ToolStatus]:
        """Возвращает статус всех доступных инструментов."""
        return {
            "usque": self.status_usque(),
            "zapret": self.status_zapret(),
            "warp_wg": self.status_warp_wg(),
            "byedpi": self.status_byedpi(),
            "spoofdpi": self.status_spoofdpi()
        }


if __name__ == "__main__":
    mgr = ToolManager()
    for key, stat in mgr.get_all_statuses().items():
        status_icon = "🟢" if stat.running else ("🟡" if stat.installed else "🔴")
        print(f"{status_icon} [{stat.name}] Установлен: {stat.installed} | Работает: {stat.running} ({stat.endpoint})")
