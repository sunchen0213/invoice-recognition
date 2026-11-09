"""Application settings and OS-backed credential storage."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

import keyring
from keyring.errors import KeyringError
from platformdirs import user_config_path

APP_NAME = "invoice-recognition"
KEYRING_SERVICE = "invoice-recognition.baidu-ocr"
ACCESS_KEY_ACCOUNT = "access-key"
SECRET_KEY_ACCOUNT = "secret-key"


@dataclass(frozen=True)
class FileSettings:
    invoice_path: str = ""
    excel_path: str = ""


def config_path() -> Path:
    """Return the per-user configuration path, never a path inside the source tree."""
    return user_config_path(APP_NAME) / "config.ini"


def load_file_settings() -> FileSettings:
    parser = configparser.ConfigParser()
    parser.read(config_path(), encoding="utf-8")
    return FileSettings(
        invoice_path=parser.get("FilePath", "InvoicePath", fallback=""),
        excel_path=parser.get("FilePath", "ExcelPath", fallback=""),
    )


def save_file_settings(settings: FileSettings) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    parser["FilePath"] = {
        "InvoicePath": settings.invoice_path,
        "ExcelPath": settings.excel_path,
    }
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load_credentials() -> tuple[str, str]:
    """Read credentials from the platform keyring; no credential is stored in INI."""
    try:
        return (
            keyring.get_password(KEYRING_SERVICE, ACCESS_KEY_ACCOUNT) or "",
            keyring.get_password(KEYRING_SERVICE, SECRET_KEY_ACCOUNT) or "",
        )
    except KeyringError as exc:
        raise RuntimeError("无法访问系统凭据库，请检查钥匙串/凭据管理器。") from exc


def save_credentials(access_key: str, secret_key: str) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, ACCESS_KEY_ACCOUNT, access_key)
        keyring.set_password(KEYRING_SERVICE, SECRET_KEY_ACCOUNT, secret_key)
    except KeyringError as exc:
        raise RuntimeError("无法保存到系统凭据库，未将 API 密钥写入磁盘。") from exc
