from __future__ import annotations

import os
import uuid

from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest

from core.services.single_instance import SingleInstanceService


def _pump(app: QGuiApplication, ms: int = 100) -> None:
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


def test_second_launch_requests_show_on_existing_instance() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    server_name = f"JarvisAi_Unity_test_{uuid.uuid4().hex}"
    mutex_name = f"{server_name}_mutex"

    primary = SingleInstanceService(server_name=server_name, mutex_name=mutex_name)
    assert primary.ensure_primary_instance() is True

    triggered: list[str] = []
    primary.attach_show_handler(lambda: triggered.append("show"))

    secondary = SingleInstanceService(server_name=server_name, mutex_name=mutex_name)
    assert secondary.ensure_primary_instance() is False

    _pump(app, 200)

    assert triggered == ["show"]

    primary.stop()


def test_show_request_can_be_sent_directly_to_primary_instance() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    server_name = f"JarvisAi_Unity_test_{uuid.uuid4().hex}"
    mutex_name = f"{server_name}_mutex"

    primary = SingleInstanceService(server_name=server_name, mutex_name=mutex_name)
    assert primary.ensure_primary_instance() is True

    triggered: list[str] = []
    primary.attach_show_handler(lambda: triggered.append("show"))

    sender = SingleInstanceService(server_name=server_name, mutex_name=f"{mutex_name}_sender")
    assert sender.request_show_existing_instance() is True

    _pump(app, 200)

    assert triggered == ["show"]

    primary.stop()


def test_empty_socket_payload_does_not_reveal_primary_instance() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    server_name = f"JarvisAi_Unity_test_{uuid.uuid4().hex}"
    mutex_name = f"{server_name}_mutex"

    primary = SingleInstanceService(server_name=server_name, mutex_name=mutex_name)
    assert primary.ensure_primary_instance() is True

    triggered: list[str] = []
    primary.attach_show_handler(lambda: triggered.append("show"))

    socket = QLocalSocket()
    socket.connectToServer(server_name)
    assert socket.waitForConnected(200)
    socket.disconnectFromServer()

    _pump(app, 200)

    assert triggered == []

    primary.stop()
