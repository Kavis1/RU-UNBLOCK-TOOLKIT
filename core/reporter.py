#!/usr/bin/env python3
"""
reporter.py - Модуль наглядной отчетности с поддержкой RU/EN.
Формирует форматированную консольную таблицу, сводную аналитику
и сохраняет результаты в JSON / Markdown.
"""

import json
import os
import time
from typing import List, Dict
from core.checker import ProbeResult, BlockType, RecommendedTool
from core.verifier import VerifyResult

STRINGS = {
    "ru": {
        "banner_sub": "Комплекс авторазблокировки и оптимизации сети",
        "domain": "Домен",
        "orig_status": "Исходный статус",
        "tool": "Инструмент",
        "result": "Итог",
        "ping": "Пинг",
        "direct": "Direct (Прямой)",
        "accessible": "Доступен",
        "unblocked": "🟢 РАЗБЛОКИРОВАН",
        "error": "🔴 ОШИБКА",
        "summary": "📊 СВОДНЫЙ ОТЧЕТ:",
        "total_checked": "Всего проверено доменов:",
        "originally_ok": "Изначально доступно напрямую:",
        "originally_blocked": "Было заблокировано / ограничено:",
        "successfully_unblocked": "Успешно разблокировано:",
        "json_saved": "💾 Отчет JSON сохранен:",
        "md_saved": "📄 Отчет Markdown сохранен:",
        "md_title": "# Отчет о диагностике и разблокировке сервисов (RU-UNBLOCK-TOOLKIT)",
        "md_date": "Дата проверки",
        "md_total": "Всего проверено",
        "md_blocked": "Заблокировано",
        "md_unblocked": "Успешно разблокировано",
        "md_details": "Детали",
    },
    "en": {
        "banner_sub": "Unblock & Network Optimization Suite",
        "domain": "Domain",
        "orig_status": "Original Status",
        "tool": "Tool Applied",
        "result": "Final Result",
        "ping": "Latency",
        "direct": "Direct (Clean)",
        "accessible": "Accessible",
        "unblocked": "🟢 UNBLOCKED",
        "error": "🔴 FAILED",
        "summary": "📊 SUMMARY REPORT:",
        "total_checked": "Total domains checked:",
        "originally_ok": "Direct / Accessible originally:",
        "originally_blocked": "Blocked / Restricted initially:",
        "successfully_unblocked": "Successfully unblocked:",
        "json_saved": "💾 JSON report saved:",
        "md_saved": "📄 Markdown report saved:",
        "md_title": "# Service Diagnostic & Unblock Report (RU-UNBLOCK-TOOLKIT)",
        "md_date": "Check Date",
        "md_total": "Total Checked",
        "md_blocked": "Blocked",
        "md_unblocked": "Successfully Unblocked",
        "md_details": "Details",
    }
}


class Reporter:
    """Генерирует понятные отчеты о разблокированных ресурсах на RU/EN."""

    def __init__(self, use_colors: bool = True, lang: str = "ru"):
        self.use_colors = use_colors
        self.lang = lang if lang in ["ru", "en"] else "ru"
        self.t = STRINGS[self.lang]

        # ANSI Escape Codes
        self.C_RESET = "\033[0m" if use_colors else ""
        self.C_BOLD = "\033[1m" if use_colors else ""
        self.C_GREEN = "\033[32m" if use_colors else ""
        self.C_RED = "\033[31m" if use_colors else ""
        self.C_YELLOW = "\033[33m" if use_colors else ""
        self.C_CYAN = "\033[36m" if use_colors else ""
        self.C_BLUE = "\033[34m" if use_colors else ""

    def print_banner(self):
        """Выводит стартовый баннер."""
        banner = f"""
{self.C_CYAN}{self.C_BOLD}========================================================================
🚀 RU-UNBLOCK-TOOLKIT | {self.t['banner_sub']}
   Kernel BBR/fq/TFO | Usque MASQUE + Zapret DPI Bypass
========================================================================{self.C_RESET}
"""
        print(banner)

    def print_step(self, number: int, title: str):
        """Выводит заголовок шага выполнения."""
        print(f"\n{self.C_BOLD}{self.C_BLUE}▶ [{number}] {title}{self.C_RESET}")
        print(f"{self.C_BLUE}{'-' * 60}{self.C_RESET}")

    def render_summary_table(self, verify_results: List[VerifyResult]):
        """Выводит красивую таблицу результатов в консоль."""
        total = len(verify_results)
        unblocked_count = sum(1 for rate in verify_results if rate.is_unblocked and rate.original_status != BlockType.OK)
        initially_blocked = sum(1 for rate in verify_results if rate.original_status != BlockType.OK)
        already_ok = total - initially_blocked

        # Header
        col_domain = 28
        col_orig = 18
        col_tool = 16
        col_status = 18
        col_ping = 10

        header = (
            f"{self.t['domain']:<{col_domain}} | "
            f"{self.t['orig_status']:<{col_orig}} | "
            f"{self.t['tool']:<{col_tool}} | "
            f"{self.t['result']:<{col_status}} | "
            f"{self.t['ping']:<{col_ping}}"
        )
        sep = "-" * len(header)

        print("\n" + f"{self.C_BOLD}{header}{self.C_RESET}")
        print(sep)

        for res in sorted(verify_results, key=lambda x: (x.original_status == BlockType.OK, x.domain)):
            if res.original_status == BlockType.OK:
                status_str = f"{self.C_GREEN}🟢 DIRECT{self.C_RESET}"
                tool_str = self.t["direct"]
                orig_str = self.t["accessible"]
            elif res.is_unblocked:
                status_str = f"{self.C_GREEN}{self.t['unblocked']}{self.C_RESET}"
                tool_str = res.tool_used.value.upper()
                orig_str = res.original_status.value
            else:
                status_str = f"{self.C_RED}{self.t['error']}{self.C_RESET}"
                tool_str = res.tool_used.value.upper()
                orig_str = res.original_status.value

            ping_str = f"{res.new_latency_ms:.0f} ms"
            
            print(
                f"{res.domain:<{col_domain}} | "
                f"{orig_str:<{col_orig}} | "
                f"{tool_str:<{col_tool}} | "
                f"{status_str:<{col_status + (len(self.C_GREEN)+len(self.C_RESET) if self.use_colors else 0)}} | "
                f"{ping_str:<{col_ping}}"
            )

        print(sep)

        # Вывод статистики
        success_rate = (unblocked_count / initially_blocked * 100) if initially_blocked > 0 else 100.0
        print(f"\n{self.C_BOLD}{self.t['summary']}{self.C_RESET}")
        print(f"  • {self.t['total_checked']} {self.C_CYAN}{total}{self.C_RESET}")
        print(f"  • {self.t['originally_ok']} {self.C_GREEN}{already_ok}{self.C_RESET}")
        print(f"  • {self.t['originally_blocked']} {self.C_YELLOW}{initially_blocked}{self.C_RESET}")
        print(f"  • {self.t['successfully_unblocked']} {self.C_GREEN}{unblocked_count} / {initially_blocked} ({success_rate:.1f}%){self.C_RESET}")
        print()

    def export_json(self, verify_results: List[VerifyResult], filepath: str = "unblock_report.json"):
        """Сохраняет результаты в JSON."""
        data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "language": self.lang,
            "total_checked": len(verify_results),
            "results": [
                {
                    "domain": r.domain,
                    "original_status": r.original_status.value,
                    "tool_used": r.tool_used.value,
                    "is_unblocked": r.is_unblocked,
                    "latency_ms": round(r.new_latency_ms, 2),
                    "http_code": r.http_code,
                    "details": r.details
                }
                for r in verify_results
            ]
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"{self.t['json_saved']} {filepath}")
        except Exception as e:
            print(f"Error saving JSON: {e}")

    def export_markdown(self, verify_results: List[VerifyResult], filepath: str = "unblock_report.md"):
        """Сохраняет результаты в Markdown."""
        total = len(verify_results)
        unblocked = sum(1 for r in verify_results if r.is_unblocked and r.original_status != BlockType.OK)
        blocked = sum(1 for r in verify_results if r.original_status != BlockType.OK)

        md = f"""{self.t['md_title']}

**{self.t['md_date']}:** `{time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}`  
**{self.t['md_total']}:** `{total}` | **{self.t['md_blocked']}:** `{blocked}` | **{self.t['md_unblocked']}:** `{unblocked}`

---

| {self.t['domain']} | {self.t['orig_status']} | {self.t['tool']} | {self.t['result']} | {self.t['ping']} (ms) | {self.t['md_details']} |
|---|---|---|---|---|---|
"""
        for r in sorted(verify_results, key=lambda x: (x.original_status == BlockType.OK, x.domain)):
            status_icon = "🟢 OK" if r.is_unblocked else "🔴 Fail"
            md += f"| `{r.domain}` | `{r.original_status.value}` | `{r.tool_used.value}` | {status_icon} | {r.new_latency_ms:.0f} ms | {r.details} |\n"

        md += "\n---\n*Generated by ru-unblock-toolkit.*\n"

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"{self.t['md_saved']} {filepath}")
        except Exception as e:
            print(f"Error saving Markdown: {e}")


if __name__ == "__main__":
    rep = Reporter(lang="ru")
    rep.print_banner()
