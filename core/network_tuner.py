#!/usr/bin/env python3
"""
network_tuner.py - Модуль оптимизации сетевого стека ядра Linux.
Применяет BBR congestion control, fq qdisc, TCP Fast Open и 16MB буферы сокетов
для устранения просадок скорости и буферблоата на мобильных и нестабильных сетях.
"""

import os
import platform
import subprocess
import logging
from typing import Dict, Tuple, List

logger = logging.getLogger("ru_unblock.network_tuner")

SYSCTL_PARAMS = {
    # Алгоритм BBR + планировщик очередей Fair Queuing
    "net.core.default_qdisc": "fq",
    "net.ipv4.tcp_congestion_control": "bbr",

    # TCP Fast Open (0-RTT подключение для ускорения открытия сайтов)
    "net.ipv4.tcp_fastopen": "3",

    # Расширенные буферы сокетов (16 МБ max)
    "net.core.rmem_max": "16777216",
    "net.core.wmem_max": "16777216",
    "net.ipv4.tcp_rmem": "4096 87380 16777216",
    "net.ipv4.tcp_wmem": "4096 65536 16777216",

    # Тюнинг задержек и защита от Bufferbloat
    "net.ipv4.tcp_notsent_lowat": "16384",
    "net.ipv4.tcp_tw_reuse": "1",
    "net.ipv4.tcp_fin_timeout": "15",

    # Очереди соединений и файловые дескрипторы
    "net.core.somaxconn": "65535",
    "net.ipv4.tcp_max_syn_backlog": "16384",
    "fs.file-max": "2097152",
}

SYSCTL_CONF_PATH = "/etc/sysctl.d/99-network-tuning.conf"


class NetworkTuner:
    """Управляет оптимизацией сетевого стека ядра Linux."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.is_linux = platform.system().lower() == "linux"

    def check_bbr_supported(self) -> bool:
        """Проверяет доступность BBR в ядре Linux."""
        if not self.is_linux:
            return False
        try:
            res = subprocess.run(
                ["sysctl", "net.ipv4.tcp_available_congestion_control"],
                capture_output=True, text=True, check=False
            )
            return "bbr" in res.stdout
        except Exception:
            return False

    def load_bbr_module(self) -> bool:
        """Загружает модуль tcp_bbr через modprobe при необходимости."""
        if not self.is_linux or self.dry_run:
            return True
        try:
            subprocess.run(["modprobe", "tcp_bbr"], check=False)
            return True
        except Exception as e:
            logger.warning(f"Не удалось загрузить модуль tcp_bbr: {e}")
            return False

    def apply_tuning(self) -> Tuple[bool, List[str]]:
        """
        Записывает параметры в /etc/sysctl.d/99-network-tuning.conf и применяет их.
        Возвращает (успех, список примененных параметров).
        """
        applied = []
        if not self.is_linux:
            logger.info("Система не является Linux (Windows/macOS). Пропуск применения sysctl.")
            return True, ["(Simulated on non-Linux platform)"]

        if os.geteuid() != 0 and not self.dry_run:
            logger.error("Для применения тюнинга ядра требуются права root (sudo).")
            return False, ["Требуются права root (sudo)"]

        self.load_bbr_module()

        content = "# Автоматически сгенерировано ru-unblock-toolkit (Оптимизация сетевого стека ядра)\n"
        for k, v in SYSCTL_PARAMS.items():
            content += f"{k} = {v}\n"
            applied.append(f"{k} = {v}")

        if self.dry_run:
            logger.info(f"[DRY-RUN] Запись настроек в {SYSCTL_CONF_PATH}")
            return True, applied

        try:
            with open(SYSCTL_CONF_PATH, "w", encoding="utf-8") as f:
                f.write(content)

            # Применяем sysctl --system
            res = subprocess.run(["sysctl", "--system"], capture_output=True, text=True, check=False)
            if res.returncode == 0:
                logger.info("Тюнинг ядра Linux (BBR, fq, TCP Fast Open, 16MB буферы) успешно применен.")
                return True, applied
            else:
                logger.warning(f"sysctl --system завершился с предупреждением: {res.stderr}")
                return True, applied
        except Exception as e:
            logger.error(f"Ошибка при сохранении {SYSCTL_CONF_PATH}: {e}")
            return False, [str(e)]

    def get_current_status(self) -> Dict[str, str]:
        """Возвращает текущие значения ключевых параметров ядра."""
        status = {}
        if not self.is_linux:
            return {k: "N/A (Non-Linux)" for k in SYSCTL_PARAMS}

        for param in ["net.ipv4.tcp_congestion_control", "net.core.default_qdisc", "net.ipv4.tcp_fastopen", "net.core.rmem_max"]:
            try:
                res = subprocess.run(["sysctl", "-n", param], capture_output=True, text=True, check=False)
                status[param] = res.stdout.strip()
            except Exception:
                status[param] = "unknown"
        return status


if __name__ == "__main__":
    tuner = NetworkTuner()
    print("Проверка BBR:", tuner.check_bbr_supported())
    success, params = tuner.apply_tuning()
    print(f"Статус применения: {success}")
    for p in params:
        print(f"  + {p}")
