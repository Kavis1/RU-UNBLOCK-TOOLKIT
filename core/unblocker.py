#!/usr/bin/env python3
"""
unblocker.py - Главный оркестратор разблокировки и оптимизации.
Анализирует результаты диагностики и автоматически:
 1. Применяет тюнинг ядра Linux (BBR, fq, somaxconn, 16MB буферы).
 2. Поднимает Zapret (nfqws) для DPI-заблокированных ресурсов.
 3. Поднимает Usque MASQUE CLI (SOCKS5 HTTP/3) для сервисов с геоблоком (OpenAI, Claude, Spotify).
 4. Генерирует правила маршрутизации (Smart Routing) для Xray / Sing-box / PAC.
"""

import os
import json
import logging
from typing import List, Dict, Tuple
from core.checker import ProbeResult, BlockType, RecommendedTool
from core.network_tuner import NetworkTuner
from core.tool_manager import ToolManager

logger = logging.getLogger("ru_unblock.unblocker")


class UnblockOrchestrator:
    """Координирует процесс тюнинга, поднятия сервисов и генерации маршрутов."""

    def __init__(self, config: Dict = None, dry_run: bool = False):
        self.config = config or {}
        self.dry_run = dry_run
        self.tuner = NetworkTuner(dry_run=dry_run)
        self.tool_mgr = ToolManager(config=self.config)

    def apply_kernel_tuning(self) -> Tuple[bool, List[str]]:
        """Применение оптимизаций сетевого стека ядра Linux."""
        logger.info("Применение тюнинга сетевого стека ядра Linux...")
        return self.tuner.apply_tuning()

    def determine_required_tools(self, probe_results: List[ProbeResult]) -> Dict[str, List[str]]:
        """
        Группирует домены по требуемым инструментам разблокировки.
        """
        routing_plan = {
            "zapret": [],          # DPI bypass (YouTube, Discord, Twitter, Rutracker)
            "usque": [],           # MASQUE SOCKS5 (ChatGPT, Claude, Spotify, Netflix, Canva)
            "direct": [],          # Без прокси (Прямой IP)
            "warp_wireguard": []   # Резервный WireGuard туннель
        }

        for res in probe_results:
            tool = res.recommended_tool.value
            if tool in routing_plan:
                routing_plan[tool].append(res.domain)
            else:
                routing_plan["usque"].append(res.domain)

        return routing_plan

    def deploy_required_services(self, routing_plan: Dict[str, List[str]]) -> Dict[str, bool]:
        """
        Запускает необходимые службы в зависимости от того, какие сервисы заблокированы.
        """
        service_status = {}

        # 1. Если есть DPI-блокировки -> Запуск Zapret
        if routing_plan.get("zapret"):
            logger.info(f"Обнаружено {len(routing_plan['zapret'])} DPI-заблокированных доменов. Активация Zapret...")
            stat = self.tool_mgr.status_zapret()
            if not stat.running:
                ok, msg = self.tool_mgr.install_zapret()
                service_status["zapret"] = ok
                logger.info(f"Zapret activation: {ok} ({msg})")
            else:
                service_status["zapret"] = True

        # 2. Если есть Геоблокировки / Черные списки IP -> Запуск Usque MASQUE
        if routing_plan.get("usque"):
            logger.info(f"Обнаружено {len(routing_plan['usque'])} геоблокированных/IP-заблокированных доменов. Активация Usque MASQUE...")
            stat = self.tool_mgr.status_usque()
            if not stat.running:
                ok, msg = self.tool_mgr.install_usque()
                service_status["usque"] = ok
                logger.info(f"Usque activation: {ok} ({msg})")
            else:
                service_status["usque"] = True

        return service_status

    def generate_smart_routing_config(self, routing_plan: Dict[str, List[str]], output_path: str = "smart_routing_rules.json") -> str:
        """
        Генерирует готовый блок правил Smart Routing для Xray / Sing-box / прокси-клиентов.
        """
        xray_routing = {
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": [
                    {
                        "type": "field",
                        "outboundTag": "block",
                        "domain": ["geosite:category-ads-all"]
                    },
                    {
                        "type": "field",
                        "outboundTag": "direct",
                        "domain": [
                            "geosite:category-ru",
                            "domain:ru",
                            "domain:su",
                            "domain:рф"
                        ] + routing_plan.get("direct", [])
                    },
                    {
                        "type": "field",
                        "outboundTag": "warp",
                        "domain": [f"domain:{d}" for d in routing_plan.get("usque", [])]
                    },
                    {
                        "type": "field",
                        "outboundTag": "zapret-direct",
                        "domain": [f"domain:{d}" for d in routing_plan.get("zapret", [])]
                    }
                ]
            },
            "outbounds": [
                {
                    "tag": "warp",
                    "protocol": "socks",
                    "settings": {
                        "servers": [{"address": "127.0.0.1", "port": 40001}]
                    }
                }
            ]
        }

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(xray_routing, f, indent=2, ensure_ascii=False)
            return output_path
        except Exception as e:
            logger.error(f"Не удалось сохранить правила маршрутизации: {e}")
            return ""


if __name__ == "__main__":
    orchestrator = UnblockOrchestrator(dry_run=True)
    success, params = orchestrator.apply_kernel_tuning()
    print("Тюнинг ядра:", success)
