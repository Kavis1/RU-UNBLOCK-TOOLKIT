#!/usr/bin/env python3
"""
unblock.py - Главный исполняемый файл комплекса ru-unblock-toolkit.
Многоязычный CLI (RU / EN) с удобным меню выбора по номерам (1-5).
"""

import os
import sys
import argparse
import logging
import yaml

# Гарантируем корректный вывод UTF-8 / Emoji на Windows и Linux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.checker import DomainChecker, BlockType, RecommendedTool
from core.network_tuner import NetworkTuner
from core.tool_manager import ToolManager
from core.unblocker import UnblockOrchestrator
from core.verifier import UnblockVerifier
from core.reporter import Reporter

# Базовые пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
POPULAR_FILE = os.path.join(DATA_DIR, "popular_ru_blocked.txt")
FETCHED_FILE = os.path.join(DATA_DIR, "fetched_blocklist.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("ru_unblock")

# UI Тексты
UI_MESSAGES = {
    "ru": {
        "step1": "Выбор списка сервисов для диагностики и разблокировки",
        "opt1": "1) 🌟 Топ популярных заблокированных сервисов (YouTube, Discord, ChatGPT, Claude, Spotify и др.) [По умолчанию]",
        "opt2": "2) 🌐 Полный список заблокированных ресурсов с GitHub (AntiZapret / AntiFilter)",
        "opt3": "3) 📁 Указать путь к своему файлу со списком доменов",
        "opt4": "4) 🔍 Ввести конкретный домен вручную (например: chatgpt.com)",
        "opt5": "5) 🚪 Выход",
        "prompt": "👉 Выберите вариант [1-5] (Enter = 1): ",
        "enter_file": "Введите путь к файлу: ",
        "enter_domain": "Введите домен: ",
        "selected": "Выбрано доменов для обработки:",
        "step2": "Диагностика сетевой доступности",
        "probing": "⏳ Тестирование DNS, TCP Handshake, TLS SNI и HTTP статусов...",
        "diag_summary": "📊 Итог проверки: Доступно: {ok} | Заблокировано/Ограничено: {blocked}",
        "step3": "Умный подбор инструментов обхода (Decision Engine)",
        "direct_count": "  • Прямой доступ (Direct IP): {n} доменов",
        "zapret_count": "  • Zapret DPI bypass (YouTube / Discord / SNI-блокировки): {n} доменов",
        "usque_count": "  • Usque MASQUE WARP (Геоблок 403 / IP Blackhole / OpenAI / Claude): {n} доменов",
        "check_only_msg": "\n[--check-only] Пропуск этапа применения разблокировки.",
        "step4": "Применение разблокировки и оптимизации сети",
        "tuning_msg": "⚡ Оптимизация сетевого стека ядра Linux (BBR, fq, TCP Fast Open, 16MB буферы)...",
        "tuning_ok": "  ✓ Сетевой стек ядра успешно оптимизирован.",
        "tuning_warn": "  ⚠️ Предупреждение:",
        "deploying_tools": "🛡️  Активация инструментов обхода (Usque MASQUE & Zapret)...",
        "service_active": "АКТИВНА",
        "service_fail": "ОШИБКА ЗАПУСКА",
        "routing_saved": "  ✓ Конфигурация Smart Routing сгенерирована: {path}",
        "step5": "Контрольная проверка работоспособности (Verification)",
        "retesting": "⏳ Повторное тестирование сервисов через настроенные каналы обхода...",
        "step6": "Итоговый отчет о разблокированных сервисах",
        "all_done": "\n🎉 Все операции успешно завершены! Все разблокированные сервисы готовы к работе.\n",
        "empty_list": "❌ Ошибка: Список целевых доменов пуст.",
        "cancelled": "\nОперация отменена пользователем."
    },
    "en": {
        "step1": "Select Target Domain List for Diagnostic & Unblock",
        "opt1": "1) 🌟 Top Popular Restricted Services (YouTube, Discord, ChatGPT, Claude, Spotify, etc.) [Default]",
        "opt2": "2) 🌐 Full Community Blocklist from GitHub (AntiZapret / AntiFilter)",
        "opt3": "3) 📁 Specify Custom Text File with Domains",
        "opt4": "4) 🔍 Test a Single Specific Domain (e.g. chatgpt.com)",
        "opt5": "5) 🚪 Exit",
        "prompt": "👉 Choose an option [1-5] (Enter = 1): ",
        "enter_file": "Enter file path: ",
        "enter_domain": "Enter domain: ",
        "selected": "Target domains selected:",
        "step2": "Network Connectivity Diagnostics",
        "probing": "⏳ Probing DNS, TCP Handshake, TLS SNI, and HTTP statuses...",
        "diag_summary": "📊 Diagnostic Summary: Accessible: {ok} | Blocked/Restricted: {blocked}",
        "step3": "Smart Tool Selection (Decision Engine)",
        "direct_count": "  • Direct Access (Clean IP): {n} domains",
        "zapret_count": "  • Zapret DPI Bypass (YouTube / Discord / SNI filters): {n} domains",
        "usque_count": "  • Usque MASQUE WARP (Geoblock 403 / IP Blackhole / OpenAI / Claude): {n} domains",
        "check_only_msg": "\n[--check-only] Skipping unblock application phase.",
        "step4": "Applying Unblock & Network Optimization",
        "tuning_msg": "⚡ Optimizing Linux Kernel Network Stack (BBR, fq, TCP Fast Open, 16MB buffers)...",
        "tuning_ok": "  ✓ Kernel network stack successfully tuned.",
        "tuning_warn": "  ⚠️ Warning:",
        "deploying_tools": "🛡️  Activating bypass services (Usque MASQUE & Zapret)...",
        "service_active": "ACTIVE",
        "service_fail": "FAILED TO START",
        "routing_saved": "  ✓ Smart Routing configuration generated: {path}",
        "step5": "Post-Unblock Verification Check",
        "retesting": "⏳ Re-testing target domains through configured bypass channels...",
        "step6": "Final Summary Report",
        "all_done": "\n🎉 All operations completed! Unblocked services are ready to use.\n",
        "empty_list": "❌ Error: Target domain list is empty.",
        "cancelled": "\nOperation cancelled by user."
    }
}


def load_config() -> dict:
    """Загружает файл конфигурации config.yaml."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def get_domain_list(choice: str, custom_path: str = None, lang: str = "ru") -> list:
    """Загружает выбранный список доменов."""
    domains = []
    filepath = POPULAR_FILE

    if choice in ["1", "popular"]:
        filepath = POPULAR_FILE
        print(f"📖 Загрузка встроенного списка ({filepath})..." if lang == "ru" else f"📖 Loading built-in list ({filepath})...")
    elif choice in ["2", "github"]:
        if not os.path.exists(FETCHED_FILE):
            print("⏳ Синхронизация списка с GitHub..." if lang == "ru" else "⏳ Syncing blocklist from GitHub...")
            try:
                import scripts.fetch_blocklists as fetcher
                fetcher.main()
            except Exception as e:
                print(f"Fetch warning: {e}")
        filepath = FETCHED_FILE if os.path.exists(FETCHED_FILE) else POPULAR_FILE
        print(f"📖 Загрузка GitHub-списка ({filepath})..." if lang == "ru" else f"📖 Loading GitHub list ({filepath})...")
    elif custom_path and os.path.exists(custom_path):
        filepath = custom_path
        print(f"📖 Загрузка файла ({filepath})..." if lang == "ru" else f"📖 Loading custom file ({filepath})...")
    else:
        if "." in choice:
            return [choice.strip().lower()]

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                d = line.strip().lower()
                if d and not d.startswith("#") and not d.startswith(";"):
                    if "://" in d:
                        d = d.split("://")[1]
                    if "/" in d:
                        d = d.split("/")[0]
                    domains.append(d)
    return list(dict.fromkeys(domains))


def main():
    parser = argparse.ArgumentParser(description="ru-unblock-toolkit: Universal Network Diagnostics & Bypass Suite")
    parser.add_argument("--lang", choices=["ru", "en"], default=None, help="Language (ru/en)")
    parser.add_argument("--list", choices=["popular", "github", "custom"], default=None, help="Target list type")
    parser.add_argument("--file", help="Custom domains list file path")
    parser.add_argument("--domain", help="Single domain to check and unblock")
    parser.add_argument("--check-only", action="store_true", help="Diagnostic only mode without applying unblock")
    parser.add_argument("--dry-run", action="store_true", help="Test run without modifying system state")
    parser.add_argument("--all-tools", action="store_true", help="Pull and enable all tools including alternatives")
    parser.add_argument("--no-tuning", action="store_true", help="Skip Linux kernel network optimization")
    args = parser.parse_args()

    config = load_config()

    # Язык интерфейса
    lang = args.lang or ("en" if "LANG" in os.environ and "ru" not in os.environ.get("LANG", "").lower() and not sys.platform.startswith("win") else "ru")
    msg = UI_MESSAGES[lang]

    reporter = Reporter(use_colors=True, lang=lang)
    reporter.print_banner()

    # --- ШАГ 1: Меню выбора доменов (1-5) ---
    target_domains = []
    if args.domain:
        target_domains = [args.domain.strip().lower()]
    elif args.file:
        target_domains = get_domain_list("custom", args.file, lang=lang)
    elif args.list:
        target_domains = get_domain_list(args.list, lang=lang)
    else:
        reporter.print_step(1, msg["step1"])
        print(f"  {msg['opt1']}")
        print(f"  {msg['opt2']}")
        print(f"  {msg['opt3']}")
        print(f"  {msg['opt4']}")
        print(f"  {msg['opt5']}")
        
        try:
            choice = input(f"\n{msg['prompt']}").strip()
        except (KeyboardInterrupt, EOFError):
            print(msg["cancelled"])
            sys.exit(0)

        if choice == "5":
            print(msg["cancelled"])
            sys.exit(0)
        elif choice == "2":
            target_domains = get_domain_list("github", lang=lang)
        elif choice == "3":
            custom_f = input(msg["enter_file"]).strip()
            target_domains = get_domain_list("custom", custom_f, lang=lang)
        elif choice == "4":
            dom = input(msg["enter_domain"]).strip()
            target_domains = [dom] if dom else get_domain_list("popular", lang=lang)
        else:
            target_domains = get_domain_list("popular", lang=lang)

    if not target_domains:
        print(msg["empty_list"])
        sys.exit(1)

    print(f"✅ {msg['selected']} {len(target_domains)}")

    # --- ШАГ 2: Диагностика ---
    reporter.print_step(2, f"{msg['step2']} ({len(target_domains)})")
    print(msg["probing"])

    checker = DomainChecker(
        timeout=config.get("checker", {}).get("timeout_seconds", 4.0),
        max_workers=config.get("checker", {}).get("concurrent_workers", 15)
    )
    probe_results = checker.check_domains_batch(target_domains)

    blocked_count = sum(1 for p in probe_results if p.status != BlockType.OK)
    print(msg["diag_summary"].format(ok=len(probe_results) - blocked_count, blocked=blocked_count))

    # --- ШАГ 3: Decision Engine ---
    reporter.print_step(3, msg["step3"])
    orchestrator = UnblockOrchestrator(config=config, dry_run=args.dry_run)
    routing_plan = orchestrator.determine_required_tools(probe_results)

    print(msg["direct_count"].format(n=len(routing_plan['direct'])))
    print(msg["zapret_count"].format(n=len(routing_plan['zapret'])))
    print(msg["usque_count"].format(n=len(routing_plan['usque'])))

    if args.check_only:
        print(msg["check_only_msg"])
        verifier = UnblockVerifier()
        dummy_verify = [verifier.verify_probe(p) for p in probe_results]
        reporter.render_summary_table(dummy_verify)
        reporter.export_json(dummy_verify)
        reporter.export_markdown(dummy_verify)
        return

    # --- ШАГ 4: Разблокировка ---
    reporter.print_step(4, msg["step4"])

    # 1. Тюнинг ядра
    if not args.no_tuning:
        print(msg["tuning_msg"])
        ok, details = orchestrator.apply_kernel_tuning()
        if ok:
            print(msg["tuning_ok"])
        else:
            print(f"{msg['tuning_warn']} {details}")

    # 2. Запуск служб
    print(msg["deploying_tools"])
    service_status = orchestrator.deploy_required_services(routing_plan)
    for srv, active in service_status.items():
        state_icon = "🟢" if active else "🔴"
        status_text = msg["service_active"] if active else msg["service_fail"]
        print(f"  {state_icon} [{srv.upper()}]: {status_text}")

    # 3. Сохранение Smart Routing
    rules_file = os.path.join(BASE_DIR, "smart_routing_rules.json")
    saved_path = orchestrator.generate_smart_routing_config(routing_plan, rules_file)
    if saved_path:
        print(msg["routing_saved"].format(path=saved_path))

    # --- ШАГ 5: Контрольная проверка ---
    reporter.print_step(5, msg["step5"])
    print(msg["retesting"])

    verifier = UnblockVerifier(
        socks_port=config.get("tools", {}).get("usque", {}).get("socks_port", 40001),
        timeout=config.get("checker", {}).get("timeout_seconds", 5.0)
    )
    verify_results = verifier.verify_all(probe_results)

    # --- ШАГ 6: Итоговый отчет ---
    reporter.print_step(6, msg["step6"])
    reporter.render_summary_table(verify_results)
    reporter.export_json(verify_results, os.path.join(BASE_DIR, "unblock_report.json"))
    reporter.export_markdown(verify_results, os.path.join(BASE_DIR, "unblock_report.md"))

    print(msg["all_done"])


if __name__ == "__main__":
    main()
