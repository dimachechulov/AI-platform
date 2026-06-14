#!/usr/bin/env python3
"""
Выставляет condition.value = null у переходов с type=llm_routing в таблице bot_config (ключ nodes).

Схема БД не меняется — правится JSON в config_value.

Запуск из корня репозитория AI-platform:

  PYTHONPATH=. python scripts/strip_llm_routing_condition_values.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# корень: AI-platform/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import models as m  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(m.BotConfig).where(m.BotConfig.config_key == "nodes")
            ).all()
        )
        updated = 0
        for row in rows:
            try:
                nodes = json.loads(row.config_value)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(nodes, list):
                continue
            changed = False
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                transitions = node.get("transitions")
                if not isinstance(transitions, list):
                    continue
                for tr in transitions:
                    if not isinstance(tr, dict):
                        continue
                    cond = tr.get("condition")
                    if not isinstance(cond, dict):
                        continue
                    if cond.get("type") == "llm_routing" and cond.get("value") is not None:
                        cond["value"] = None
                        changed = True
            if changed:
                row.config_value = json.dumps(nodes, ensure_ascii=False)
                updated += 1
        if updated:
            db.commit()
        print(f"Обновлено записей bot_config (nodes): {updated} из {len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
