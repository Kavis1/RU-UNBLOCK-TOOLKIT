#!/usr/bin/env python3
"""
verifier.py - Модуль контрольной проверки после применения разблокировки.
Повторно тестирует ранее заблокированные домены через активированные инструменты
(Usque SOCKS5 proxy или через Zapret DPI bypass) и фиксирует результат.
"""

import time
import socket
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from core.checker import ProbeResult, BlockType, RecommendedTool


@dataclass
class VerifyResult:
    domain: str
    original_status: BlockType
    tool_used: RecommendedTool
    is_unblocked: bool
    new_latency_ms: float
    http_code: Optional[int] = None
    details: str = ""


class UnblockVerifier:
    """Проверяет работоспособность разблокировки."""

    def __init__(self, socks_port: int = 40001, timeout: float = 5.0, max_workers: int = 15):
        self.socks_port = socks_port
        self.timeout = timeout
        self.max_workers = max_workers

    def _test_via_socks(self, domain: str) -> Tuple[bool, float, Optional[int], str]:
        """Тестирует домен через SOCKS5 прокси Usque MASQUE."""
        start_time = time.time()
        try:
            proxy_handler = urllib.request.ProxyHandler({
                'http': f'socks5://127.0.0.1:{self.socks_port}',
                'https': f'socks5://127.0.0.1:{self.socks_port}'
            })
            opener = urllib.request.build_opener(proxy_handler)
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(
                f"https://{domain}/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"
                }
            )

            with opener.open(req, timeout=self.timeout) as resp:
                elapsed = (time.time() - start_time) * 1000
                code = resp.getcode()
                return True, elapsed, code, "Успешно открыт через Usque MASQUE WARP"

        except urllib.error.HTTPError as e:
            elapsed = (time.time() - start_time) * 1000
            if e.code in [403, 451]:
                return False, elapsed, e.code, f"Сайт по-прежнему возвращает HTTP {e.code}"
            return True, elapsed, e.code, f"Доступен через Usque (HTTP {e.code})"

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return False, elapsed, None, f"Ошибка через Usque SOCKS: {e}"

    def _test_direct_zapret(self, domain: str) -> Tuple[bool, float, Optional[int], str]:
        """Тестирует домен напрямую (когда на хосте активен Zapret nfqws)."""
        start_time = time.time()
        try:
            req = urllib.request.Request(
                f"https://{domain}/",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                elapsed = (time.time() - start_time) * 1000
                return True, elapsed, resp.getcode(), "Успешно открыт напрямую через Zapret DPI bypass"
        except urllib.error.HTTPError as e:
            elapsed = (time.time() - start_time) * 1000
            return True, elapsed, e.code, f"Доступен через Zapret (HTTP {e.code})"
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return False, elapsed, None, f"Недоступен: {e}"

    def verify_probe(self, probe: ProbeResult) -> VerifyResult:
        """Проверяет результат для одного домена."""
        if probe.status == BlockType.OK:
            return VerifyResult(
                domain=probe.domain,
                original_status=probe.status,
                tool_used=RecommendedTool.DIRECT,
                is_unblocked=True,
                new_latency_ms=probe.latency_ms,
                http_code=probe.http_code,
                details="Был доступен изначально"
            )

        if probe.recommended_tool in [RecommendedTool.USQUE, RecommendedTool.WARP_WG]:
            success, latency, code, details = self._test_via_socks(probe.domain)
        else:
            success, latency, code, details = self._test_direct_zapret(probe.domain)

        return VerifyResult(
            domain=probe.domain,
            original_status=probe.status,
            tool_used=probe.recommended_tool,
            is_unblocked=success,
            new_latency_ms=latency,
            http_code=code,
            details=details
        )

    def verify_all(self, probes: List[ProbeResult], callback=None) -> List[VerifyResult]:
        """Параллельно выполняет повторное тестирование всех доменов."""
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_probe = {executor.submit(self.verify_probe, p): p for p in probes}
            for future in as_completed(future_to_probe):
                res = future.result()
                results.append(res)
                if callback:
                    callback(res)
        return results


if __name__ == "__main__":
    from core.checker import DomainChecker
    checker = DomainChecker()
    p = checker.probe_domain("chatgpt.com")
    verifier = UnblockVerifier()
    v = verifier.verify_probe(p)
    print(v)
