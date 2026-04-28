"""Сохранение аватара профиля: квадрат по центру, сжатие JPEG."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from io import BytesIO
from typing import Optional, Tuple

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

PROFILE_SUBDIR = "profile_avatars"
MAX_SIDE = 384
JPEG_QUALITY = 88
MAX_UPLOAD_BYTES = 6 * 1024 * 1024


def profile_avatars_dir(upload_root: str) -> str:
    return os.path.join(upload_root, PROFILE_SUBDIR)


def try_remove_stored_profile_avatar(upload_root: str, public_url: Optional[str]) -> None:
    """Удалить файл по URL вида .../uploads/profile_avatars/<name>.jpg (безопасное имя)."""
    if not public_url or not str(public_url).strip():
        return
    path_part = f"/uploads/{PROFILE_SUBDIR}/"
    s = str(public_url).replace("\\", "/")
    if path_part not in s:
        return
    name = s.split(path_part, 1)[-1].split("?", 1)[0].strip()
    if not name or "/" in name or ".." in name:
        return
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.jpe?g", name, re.IGNORECASE):
        return
    full = os.path.join(profile_avatars_dir(upload_root), name)
    try:
        if os.path.isfile(full):
            os.remove(full)
    except OSError as e:
        logger.warning("profile avatar delete %s: %s", full, e)


def public_profile_avatar_url(api_base_url: str, filename: str) -> str:
    base = (api_base_url or "").rstrip("/")
    return f"{base}/uploads/{PROFILE_SUBDIR}/{filename}"


def _process_square_jpeg(upload_root: str, raw: bytes, user_id: int) -> Tuple[str, str]:
    root = profile_avatars_dir(upload_root)
    os.makedirs(root, exist_ok=True)
    name = f"{user_id}_{uuid.uuid4().hex}.jpg"
    path = os.path.join(root, name)

    img = Image.open(BytesIO(raw))
    img.load()
    try:
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        logger.warning("profile avatar: exif_transpose skipped: %s", e)
    if getattr(img, "readonly", False):
        img = img.copy()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    if side > MAX_SIDE:
        img = img.resize((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)

    img.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return name, path


async def save_profile_avatar_jpeg(upload_root: str, user_id: int, raw: bytes) -> str:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("file_too_large")
    loop = asyncio.get_event_loop()
    filename, _path = await loop.run_in_executor(
        None, lambda: _process_square_jpeg(upload_root, raw, user_id)
    )
    api_base = os.getenv("API_BASE_URL", "https://miniapp.nixbi.ru").strip()
    return public_profile_avatar_url(api_base, filename)
