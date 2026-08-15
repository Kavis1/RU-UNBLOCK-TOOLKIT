#!/usr/bin/env python3
"""
checker.py - Модуль глубокой сетевой диагностики блокировок.
Тестирует домены и определяет точную причину недоступности:
 - DPI_BLOCKED (TCP RST при передаче SNI / сброс DPI) -> Требуется Zapret DPI bypass
 - GEO_BLOCKED (403 Forbidden / Зарубежная геоблокировка по IP) -> Требуется Usque MASQUE WARP
 - IP_BLACKHOLE (Timeout / Drop пакетов на уровне IP) -> Требуется Usque MASQUE WARP
 - DNS_POISONED (Подмена DNS записей) -> DoH / Usque
 - OK (Сайт открывается напрямую) -> Direct
"""

import socket
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional, Tuple


class BlockType(Enum):
    OK = "OK"                                  # Доступен напрямую
    DPI_BLOCKED = "DPI_BLOCKED"                # Сброс TCP/TLS SNI (Reset by peer)
    GEO_BLOCKED = "GEO_BLOCKED"                # 403 Forbidden / Региональная геоблокировка по IP
    IP_BLACKHOLE = "IP_BLACKHOLE"              # Полный таймаут TCP SYN / IP недоступен
    DNS_POISONED = "DNS_POISONED"              # Не резолвится или подменен IP
    HTTP_REDIRECT_RKN = "HTTP_REDIRECT_RKN"    # Перенаправление на страницу-заглушку провайдера
    UNKNOWN_ERROR = "UNKNOWN_ERROR"            # Прочая сетевая ошибка


class RecommendedTool(Enum):
    DIRECT = "direct"                          # Прямой доступ (без прокси)
    ZAPRET = "zapret"                          # Zapret DPI bypass (nfqws/tpws) или ByeDPI
    USQUE = "usque"                            # Usque MASQUE Cloudflare WARP (SOCKS5 HTTP/3)
    WARP_WG = "warp_wireguard"                 # Классический Cloudflare WARP (WireGuard)


@dataclass
class ProbeResult:
    domain: str
    status: BlockType
    recommended_tool: RecommendedTool
    latency_ms: float
    http_code: Optional[int] = None
    details: str = ""
    ip_resolved: str = ""


class DomainChecker:
    """Диагностирует сетевую доступность и классифицирует метод обхода."""

    def __init__(self, timeout: float = 4.0, max_workers: int = 15):
        self.timeout = timeout
        self.max_workers = max_workers

    def probe_domain(self, domain: str) -> ProbeResult:
        """Выполняет глубокую проверку домена."""
        domain = domain.strip().lower()
        if not domain or domain.startswith("#"):
            return ProbeResult(domain, BlockType.OK, RecommendedTool.DIRECT, 0.0, details="Comment")

        start_time = time.time()
        ip_addr = ""

        # 1. DNS Resolution
        try:
            ip_addr = socket.gethostbyname(domain)
            if ip_addr in ["127.0.0.1", "0.0.0.0"]:
                elapsed = (time.time() - start_time) * 1000
                return ProbeResult(
                    domain=domain,
                    status=BlockType.DNS_POISONED,
                    recommended_tool=RecommendedTool.USQUE,
                    latency_ms=elapsed,
                    ip_resolved=ip_addr,
                    details="DNS подменен на loopback"
                )
        except socket.gaierror as e:
            elapsed = (time.time() - start_time) * 1000
            return ProbeResult(
                domain=domain,
                status=BlockType.DNS_POISONED,
                recommended_tool=RecommendedTool.USQUE,
                latency_ms=elapsed,
                details=f"DNS NXDOMAIN: {e}"
            )

        # 2. Raw TCP + TLS Handshake Test (Для детекции DPI RST)
        tcp_connected = False
        tls_success = False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((ip_addr, 443))
            tcp_connected = True

            # Оборачиваем в TLS с передачей SNI
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            tls_sock = ctx.wrap_socket(sock, server_hostname=domain)
            tls_sock.settimeout(self.timeout)
            tls_success = True
            tls_sock.close()

        except ConnectionResetError:
            elapsed = (time.time() - start_time) * 1000
            return ProbeResult(
                domain=domain,
                status=BlockType.DPI_BLOCKED,
                recommended_tool=RecommendedTool.ZAPRET,
                latency_ms=elapsed,
                ip_resolved=ip_addr,
                details="TCP RST при передаче TLS SNI (DPI блокировка)"
            )
        except ssl.SSLError as e:
            elapsed = (time.time() - start_time) * 1000
            err_str = str(e).lower()
            if "reset" in err_str or "eof" in err_str or "alert" in err_str:
                return ProbeResult(
                    domain=domain,
                    status=BlockType.DPI_BLOCKED,
                    recommended_tool=RecommendedTool.ZAPRET,
                    latency_ms=elapsed,
                    ip_resolved=ip_addr,
                    details=f"Сброс TLS рукопожатия: {e}"
                )
        except (socket.timeout, TimeoutError):
            elapsed = (time.time() - start_time) * 1000
            if not tcp_connected:
                return ProbeResult(
                    domain=domain,
                    status=BlockType.IP_BLACKHOLE,
                    recommended_tool=RecommendedTool.USQUE,
                    latency_ms=elapsed,
                    ip_resolved=ip_addr,
                    details="Таймаут соединения (IP заблокирован провайдером)"
                )
        except Exception:
            pass

        # 3. HTTP Request & Geoblock probe
        try:
            req = urllib.request.Request(
                f"https://{domain}/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                }
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as response:
                code = response.getcode()
                final_url = response.geturl().lower()
                elapsed = (time.time() - start_time) * 1000

                if "warning.rt.ru" in final_url or "block" in final_url and "rkn" in final_url:
                    return ProbeResult(
                        domain=domain,
                        status=BlockType.HTTP_REDIRECT_RKN,
                        recommended_tool=RecommendedTool.ZAPRET,
                        latency_ms=elapsed,
                        http_code=code,
                        ip_resolved=ip_addr,
                        details="Редирект на страницу блокировки"
                    )

                return ProbeResult(
                    domain=domain,
                    status=BlockType.OK,
                    recommended_tool=RecommendedTool.DIRECT,
                    latency_ms=elapsed,
                    http_code=code,
                    ip_resolved=ip_addr,
                    details="Доступен напрямую"
                )

        except urllib.error.HTTPError as e:
            elapsed = (time.time() - start_time) * 1000
            code = e.code
            if code in [403, 451]:
                return ProbeResult(
                    domain=domain,
                    status=BlockType.GEO_BLOCKED,
                    recommended_tool=RecommendedTool.USQUE,
                    latency_ms=elapsed,
                    http_code=code,
                    ip_resolved=ip_addr,
                    details=f"Геоблокировка сервиса (HTTP {code} Forbidden/Sanctions)"
                )
            return ProbeResult(
                domain=domain,
                status=BlockType.OK,
                recommended_tool=RecommendedTool.DIRECT,
                latency_ms=elapsed,
                http_code=code,
                ip_resolved=ip_addr,
                details=f"Ответ сервера HTTP {code}"
            )

        except urllib.error.URLError as e:
            elapsed = (time.time() - start_time) * 1000
            reason_str = str(e.reason).lower()

            if "reset" in reason_str or "connection reset" in reason_str:
                return ProbeResult(
                    domain=domain,
                    status=BlockType.DPI_BLOCKED,
                    recommended_tool=RecommendedTool.ZAPRET,
                    latency_ms=elapsed,
                    ip_resolved=ip_addr,
                    details="Connection reset by peer (DPI)"
                )
            elif "timed out" in reason_str or "timeout" in reason_str:
                return ProbeResult(
                    domain=domain,
                    status=BlockType.IP_BLACKHOLE,
                    recommended_tool=RecommendedTool.USQUE,
                    latency_ms=elapsed,
                    ip_resolved=ip_addr,
                    details="Таймаут соединения (IP Blackhole)"
                )
            else:
                return ProbeResult(
                    domain=domain,
                    status=BlockType.UNKNOWN_ERROR,
                    recommended_tool=RecommendedTool.USQUE,
                    latency_ms=elapsed,
                    ip_resolved=ip_addr,
                    details=f"Сетевой сбой: {e.reason}"
                )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return ProbeResult(
                domain=domain,
                status=BlockType.UNKNOWN_ERROR,
                recommended_tool=RecommendedTool.USQUE,
                latency_ms=elapsed,
                details=str(e)
            )

    def check_domains_batch(self, domains: List[str], callback=None) -> List[ProbeResult]:
        """Параллельно тестирует список доменов."""
        results = []
        cleaned = [d.strip() for d in domains if d.strip() and not d.strip().startswith("#")]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_domain = {executor.submit(self.probe_domain, domain): domain for domain in cleaned}
            for future in as_completed(future_to_domain):
                res = future.result()
                results.append(res)
                if callback:
                    callback(res)

        return results


if __name__ == "__main__":
    test_list = ["youtube.com", "chatgpt.com", "yandex.ru", "discord.com", "spotify.com"]
    checker = DomainChecker()
    print("Запуск тестовой проверки...")
    for res in checker.check_domains_batch(test_list):
        print(f"[{res.status.value}] {res.domain} -> Рекомендация: {res.recommended_tool.value} ({res.latency_ms:.1f}ms) | {res.details}")
