#!/usr/bin/env python3
"""
Собирает favicon.ico из public/applogo/Logo192.jpg (рядом кладёт Logo192.ico)
и дублирует в nginx/static/favicon.ico для отдачи с корня домена (см. nginx.conf.template).

Зависимость: Pillow (см. корневой requirements.txt проекта).

  python miniapp_tg/scripts/build_applogo_ico.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Нужен Pillow: pip install Pillow", file=sys.stderr)
    sys.exit(1)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="JPEG applogo → ICO (рядом + nginx/static)")
    parser.add_argument(
        "--jpeg",
        type=Path,
        help="Исходный JPEG (по умолчанию miniapp_tg/public/applogo/Logo192.jpg)",
    )
    parser.add_argument(
        "--skip-nginx",
        action="store_true",
        help="Не копировать в nginx/static/favicon.ico",
    )
    args = parser.parse_args()

    root = repo_root_from_script()
    jpeg = args.jpeg or (root / "miniapp_tg" / "public" / "applogo" / "Logo192.jpg")
    if not jpeg.is_file():
        print(f"Не найден файл: {jpeg}", file=sys.stderr)
        return 1

    ico_next_to_jpeg = jpeg.with_suffix(".ico")
    nginx_ico = root / "nginx" / "static" / "favicon.ico"

    # Размеры для .ico (Яндекс/браузеры; 256 — верхний предел для классического ICO)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    img = Image.open(jpeg).convert("RGBA")
    ico_next_to_jpeg.parent.mkdir(parents=True, exist_ok=True)
    img.save(ico_next_to_jpeg, format="ICO", sizes=sizes)
    print(f"OK: {ico_next_to_jpeg}")

    if not args.skip_nginx:
        nginx_ico.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ico_next_to_jpeg, nginx_ico)
        print(f"OK: {nginx_ico} (копия для nginx /favicon.ico)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
