#!/usr/bin/env python3
"""
fetch_blocklists.py - Загрузка и синхронизация актуальных списков блокировок с GitHub.
Загружает списки из источников в data/blocklist_sources.json, очищает от мусора,
дедуплицирует и сохраняет в data/fetched_blocklist.txt.
"""

import json
import os
import re
import sys
import urllib.request
from typing import Set, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SOURCES_FILE = os.path.join(DATA_DIR, "blocklist_sources.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "fetched_blocklist.txt")
POPULAR_FILE = os.path.join(DATA_DIR, "popular_ru_blocked.txt")

DOMAIN_REGEX = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-_]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")


def clean_domain(line: str) -> str:
    """Очищает строку и извлекает доменное имя."""
    line = line.strip()
    if not line or line.startswith("#") or line.startswith(";"):
        return ""
    
    # Удаляем схемы (http://, https://) и пути
    if "://" in line:
        line = line.split("://")[1]
    if "/" in line:
        line = line.split("/")[0]
    if ":" in line:
        line = line.split(":")[0]

    domain = line.strip().lower()
    if DOMAIN_REGEX.match(domain):
        return domain
    return ""


def load_local_popular() -> Set[str]:
    """Загружает встроенный список популярных доменов."""
    domains = set()
    if os.path.exists(POPULAR_FILE):
        with open(POPULAR_FILE, "r", encoding="utf-8") as f:
            for line in f:
                d = clean_domain(line)
                if d:
                    domains.add(d)
    return domains


def fetch_remote_sources() -> Set[str]:
    """Загружает домены из удаленных источников."""
    domains = set()
    if not os.path.exists(SOURCES_FILE):
        print(f"Файл источников {SOURCES_FILE} не найден.")
        return domains

    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    sources = config.get("sources", [])
    for src in sources:
        if not src.get("enabled", False) or src.get("type") != "plain_hosts":
            continue

        name = src.get("name", "Unknown")
        url = src.get("url")
        print(f"📥 Загрузка списка '{name}' из {url}...")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ru-unblock-toolkit/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                count = 0
                for line in content.splitlines():
                    d = clean_domain(line)
                    if d:
                        domains.add(d)
                        count += 1
                print(f"  ✓ Получено {count} валидных доменов.")
        except Exception as e:
            print(f"  ❌ Ошибка загрузки {url}: {e}")

    return domains


def main():
    print("=== Синхронизация списков заблокированных доменов ===")
    local_domains = load_local_popular()
    print(f"Локальный список популярных сервисов: {len(local_domains)} доменов.")

    remote_domains = fetch_remote_sources()
    print(f"Удаленные списки: {len(remote_domains)} доменов.")

    all_domains = sorted(list(local_domains.union(remote_domains)))
    print(f"Всего уникальных доменов: {len(all_domains)}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Синхронизировано ru-unblock-toolkit. Всего доменов: {len(all_domains)}\n")
        for d in all_domains:
            f.write(f"{d}\n")

    print(f"💾 Список сохранен в: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
