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
ENV_ACCESS_KEY = "BAIDU_ACCESS_KEY"
ENV_SECRET_KEY = "BAIDU_SECRET_KEY"
DEFAULT_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class FileSettings:
    invoice_path: str = ""
    excel_path: str = ""


def _read_dotenv(dotenv_path: Path | None = None) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from a .env file without external dependencies."""
    candidates = [dotenv_path] if dotenv_path is not None else [Path.cwd() / ".env", DEFAULT_DOTENV_PATH]
    values: dict[str, str] = {}
    for path in candidates:
        if path is None or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip().strip("'\"")
            if key:
                values[key] = value
        break
    return values


def load_env_credentials(dotenv_path: Path | None = None) -> tuple[str, str]:
    """Load Baidu API credentials from environment variables or a local .env file."""
    dotenv = _read_dotenv(dotenv_path)
    access_key = os.environ.get(ENV_ACCESS_KEY) or dotenv.get(ENV_ACCESS_KEY, "")
    secret_key = os.environ.get(ENV_SECRET_KEY) or dotenv.get(ENV_SECRET_KEY, "")
    return access_key.strip(), secret_key.strip()



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


def load_credentials(dotenv_path: Path | None = None) -> tuple[str, str]:
    """Read credentials from the platform keyring, falling back to environment/.env."""
    env_access, env_secret = load_env_credentials(dotenv_path)
    try:
        keyring_access = keyring.get_password(KEYRING_SERVICE, ACCESS_KEY_ACCOUNT) or ""
        keyring_secret = keyring.get_password(KEYRING_SERVICE, SECRET_KEY_ACCOUNT) or ""
        return keyring_access or env_access, keyring_secret or env_secret
    except KeyringError as exc:
        if env_access and env_secret:
            return env_access, env_secret
        raise RuntimeError("无法访问系统凭据库，请检查钥匙串/凭据管理器。") from exc


def save_credentials(access_key: str, secret_key: str) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, ACCESS_KEY_ACCOUNT, access_key)
        keyring.set_password(KEYRING_SERVICE, SECRET_KEY_ACCOUNT, secret_key)
    except KeyringError as exc:
        raise RuntimeError("无法保存到系统凭据库，未将 API 密钥写入磁盘。") from exc
