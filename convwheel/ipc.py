"""Связь между копиями программы: повторный запуск ConvWheel просит уже работающую
открыть окно настроек (полезно, если значок спрятан за «чёлкой» MacBook или в трее Windows).

macOS/Linux — Unix-сокет в папке настроек, Windows — TCP только на 127.0.0.1
(порт записывается в файл; наружу ничего не открывается).
"""
from __future__ import annotations

import os
import socket
import threading
from typing import Callable

from .platform_utils import IS_WIN, config_dir

TOKEN = b"convwheel:"


def _sock_path() -> str:
    return str(config_dir() / "agent.sock")


def _port_file():
    return config_dir() / "agent.port"


def send(command: str, timeout: float = 1.5) -> bool:
    """Отправить команду работающей копии. True — если она ответила."""
    try:
        if IS_WIN:
            port = int(_port_file().read_text().strip())
            s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        else:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(_sock_path())
        with s:
            s.sendall(TOKEN + command.encode() + b"\n")
            return s.recv(16).startswith(b"ok")
    except Exception:
        return False


class Server(threading.Thread):
    def __init__(self, on_command: Callable[[str], None]):
        super().__init__(name="cw-ipc", daemon=True)
        self.on_command = on_command
        self._srv: socket.socket | None = None

    def start(self):
        try:
            if IS_WIN:
                self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._srv.bind(("127.0.0.1", 0))
                _port_file().write_text(str(self._srv.getsockname()[1]))
            else:
                path = _sock_path()
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._srv.bind(path)
                os.chmod(path, 0o600)
            self._srv.listen(4)
        except OSError:
            self._srv = None
            return
        super().start()

    def run(self):
        while self._srv is not None:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(2)
                    data = conn.recv(256)
                    if data.startswith(TOKEN):
                        self.on_command(data[len(TOKEN):].decode(errors="replace").strip())
                        conn.sendall(b"ok\n")
                except OSError:
                    pass

    def close(self):
        srv, self._srv = self._srv, None
        if srv:
            try:
                srv.close()
            except OSError:
                pass
