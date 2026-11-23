"""Small, dependency-free, per-machine INI configuration loader."""

from configparser import ConfigParser, Error as IniError
import os
from pathlib import Path, PureWindowsPath


class LocalConfig:
    def __init__(self, base_dir, environ=None):
        self.base_dir = Path(base_dir).resolve()
        self.environ = os.environ if environ is None else environ
        explicit = self.environ.get("DMTDB_CONFIG")
        self.filename = Path(explicit).expanduser() if explicit else self.base_dir / "config.local.ini"
        if not self.filename.is_absolute():
            self.filename = self.base_dir / self.filename
        self.filename = self.filename.resolve()
        self.parser = ConfigParser(interpolation=None)
        if explicit and not self.filename.is_file():
            raise ValueError("DMTDB_CONFIG does not name an existing file")
        if self.filename.exists():
            try:
                with self.filename.open(encoding="utf-8-sig") as stream:
                    self.parser.read_file(stream)
            except (IniError, OSError):
                raise ValueError("Cannot read local configuration; check INI syntax and permissions") from None

    def get(self, section, key, default="", env=None):
        if env and env in self.environ:
            return self.environ[env]
        return self.parser.get(section, key, fallback=str(default))

    def path(self, key, default, env=None, optional=False):
        value = self.get("paths", key, default, env).strip()
        if not value:
            if optional:
                return None
            raise ValueError(f"paths.{key} must not be empty")
        if os.name != "nt" and (PureWindowsPath(value).drive or "\\" in value):
            raise ValueError(f"paths.{key} contains a Windows path on a non-Windows host")
        result = Path(value).expanduser()
        anchor = self.base_dir if env and env in self.environ else self.filename.parent
        if not result.is_absolute():
            result = anchor / result
        return result.resolve()

    def boolean(self, section, key, default=False, env=None):
        value = self.get(section, key, str(default), env).strip().lower()
        if value not in {"true", "false", "yes", "no", "1", "0", "on", "off"}:
            raise ValueError(f"{section}.{key} must be a boolean")
        return value in {"true", "yes", "1", "on"}
