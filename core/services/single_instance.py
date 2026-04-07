from __future__ import annotations

import ctypes
from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


ERROR_ALREADY_EXISTS = 183


class _NamedMutex:
    def __init__(self, name: str) -> None:
        self.name = name
        self._handle = None

    def acquire(self) -> bool:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise OSError("Failed to create single-instance mutex")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if not self._handle:
            return
        kernel32 = ctypes.windll.kernel32
        kernel32.CloseHandle(self._handle)
        self._handle = None


class SingleInstanceService(QObject):
    def __init__(
        self,
        server_name: str = "JarvisAi_Unity_22_instance",
        *,
        mutex_name: str | None = None,
    ) -> None:
        super().__init__()
        self.server_name = server_name
        self._mutex = _NamedMutex(mutex_name or f"{server_name}_mutex")
        self._server = QLocalServer(self)
        self._show_handler: Callable[[], None] | None = None
        self._pending_show = False
        self._listening = False

    def ensure_primary_instance(self) -> bool:
        if not self._mutex.acquire():
            self.request_show_existing_instance()
            return False
        if not self._start_server():
            self._mutex.release()
            raise RuntimeError("Unable to start single-instance server")
        return True

    def attach_show_handler(self, handler: Callable[[], None]) -> None:
        self._show_handler = handler
        if self._pending_show:
            self._pending_show = False
            QTimer.singleShot(0, handler)

    def request_show_existing_instance(self, retries: int = 12, delay_ms: int = 40) -> bool:
        payload = b"show\n"
        for attempt in range(max(1, retries)):
            socket = QLocalSocket()
            socket.connectToServer(self.server_name)
            if socket.waitForConnected(max(1, delay_ms)):
                socket.write(payload)
                socket.flush()
                socket.waitForBytesWritten(max(1, delay_ms))
                socket.disconnectFromServer()
                socket.deleteLater()
                return True
            socket.abort()
            socket.deleteLater()
            if attempt + 1 < retries:
                QThread.msleep(max(1, delay_ms))
        return False

    def stop(self) -> None:
        if self._server.isListening():
            self._server.close()
        QLocalServer.removeServer(self.server_name)
        self._mutex.release()
        self._listening = False

    def _start_server(self) -> bool:
        if self._listening:
            return True
        if self._server.isListening():
            self._listening = True
            return True
        QLocalServer.removeServer(self.server_name)
        if not self._server.listen(self.server_name):
            QLocalServer.removeServer(self.server_name)
            if not self._server.listen(self.server_name):
                return False
        self._server.newConnection.connect(self._handle_new_connection)
        self._listening = True
        return True

    def _handle_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda socket=socket: self._consume_socket(socket))
            socket.disconnected.connect(socket.deleteLater)

    def _consume_socket(self, socket: QLocalSocket) -> None:
        try:
            raw = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip().lower()
        except RuntimeError:
            return
        if not raw:
            raw = "show"
        if raw.startswith("show"):
            self._emit_show_requested()
        socket.disconnectFromServer()

    def _emit_show_requested(self) -> None:
        self._pending_show = True
        if self._show_handler is not None:
            self._pending_show = False
            QTimer.singleShot(0, self._show_handler)
