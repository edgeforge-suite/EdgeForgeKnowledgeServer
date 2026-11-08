from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path, PurePosixPath

DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_ZIP_ENTRIES = 2_000
DEFAULT_MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PDF_PAGES = 500
DEFAULT_MAX_PDF_EXTRACTED_TEXT_CHARS = 2_000_000
_DISABLED_ENV_VALUES = {"", "0", "false", "no", "off"}

logger = logging.getLogger(__name__)


def shared_mode_enabled() -> bool:
    raw = os.environ.get("EDGEFORGE_SHARED_MODE")
    if raw is None:
        return False
    return raw.strip().lower() not in _DISABLED_ENV_VALUES


def allowed_roots_from_env() -> list[Path]:
    raw = os.environ.get("EDGEFORGE_KS_ALLOWED_ROOTS")
    if raw is None or not raw.strip():
        if shared_mode_enabled():
            raise RuntimeError(
                "EDGEFORGE_KS_ALLOWED_ROOTS is required when EDGEFORGE_SHARED_MODE "
                "is enabled; set one or more allowed document roots."
            )
        return [Path.cwd().resolve()]
    roots = [
        Path(part.strip()).expanduser().resolve()
        for part in raw.split(os.pathsep)
        if part.strip()
    ]
    if not roots and shared_mode_enabled():
        raise RuntimeError(
            "EDGEFORGE_KS_ALLOWED_ROOTS is required when EDGEFORGE_SHARED_MODE "
            "is enabled; set one or more allowed document roots."
        )
    return roots or [Path.cwd().resolve()]


def resolve_allowed_path(file_path: str, allowed_roots: list[Path]) -> Path:
    candidate = Path(file_path).expanduser().resolve()
    for root in allowed_roots:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    root_values = [str(root) for root in allowed_roots]
    logger.warning(
        "Rejected ingest path %r outside allowed roots: %r",
        str(candidate),
        root_values,
    )
    raise ValueError("file_path must resolve under an allowed root")


def enforce_file_size(path: Path, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
    size = path.stat().st_size
    if size > max_file_bytes:
        raise ValueError(f"file exceeds maximum allowed size of {max_file_bytes} bytes")


def enforce_zip_resource_limits(path: Path, *, label: str) -> None:
    """Reject ZIP-based parser inputs that exceed conservative metadata limits."""

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"{label} parser resource limit check failed: file is not a valid ZIP archive"
        ) from exc

    if len(infos) > DEFAULT_MAX_ZIP_ENTRIES:
        raise ValueError(
            f"{label} parser resource limit exceeded: ZIP entry count {len(infos)} "
            f"exceeds maximum {DEFAULT_MAX_ZIP_ENTRIES}"
        )

    total_uncompressed = 0
    for info in infos:
        _validate_zip_entry_path(info.filename, label=label)
        if info.file_size > DEFAULT_MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"{label} parser resource limit exceeded: ZIP entry '{info.filename}' "
                f"uncompressed size {info.file_size} exceeds maximum "
                f"{DEFAULT_MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES}"
            )
        total_uncompressed += info.file_size
        if total_uncompressed > DEFAULT_MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"{label} parser resource limit exceeded: total uncompressed size "
                f"{total_uncompressed} exceeds maximum "
                f"{DEFAULT_MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES}"
            )


def _validate_zip_entry_path(name: str, *, label: str) -> None:
    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if (
        not name
        or normalized.startswith("/")
        or "\\" in name
        or ".." in parts
        or (parts and ":" in parts[0])
    ):
        raise ValueError(
            f"{label} parser resource limit exceeded: suspicious ZIP entry path '{name}'"
        )
