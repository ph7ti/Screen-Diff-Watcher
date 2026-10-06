"""Regressao v0.9.0: `SessionManager.escalating` e metodo, nao property.

O `_update_gate_status` da janela usava a sintaxe antiga do `MonitorController`
(property) e o `TypeError` dentro do slot do `QTimer` abortava o processo no
primeiro tick (`0xC0000409`), sem traceback visivel para o usuario.

O teste chama o metodo real sem Qt (stubs). O import de `main_window` e tardio
(por fixture) para nao importar PyQt6 durante a coleta e nao quebrar os testes
que simulam a ausencia do Qt (`tests/test_gui_countdown.py`, `tests/test_display.py`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from screen_watch.i18n import tr


@pytest.fixture
def main_window_cls():
    # Em runners Linux sem as libs de sistema do Qt (`libEGL.so.1` etc.) o import
    # do PyQt6 falha; nesse caso o teste e pulado (a cobertura fica no Windows).
    pytest.importorskip("PyQt6.QtGui", reason="PyQt6 system libs unavailable")

    from screen_watch.gui.main_window import MainWindow

    return MainWindow


class _StubLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:  # noqa: N802 - API Qt
        self.text = text


class _StubButton:
    def __init__(self) -> None:
        self.text = ""
        self.enabled: bool | None = None

    def setText(self, text: str) -> None:  # noqa: N802 - API Qt
        self.text = text

    def setEnabled(self, value: bool) -> None:  # noqa: N802 - API Qt
        assert isinstance(value, bool), f"expected bool, got {type(value).__name__}"
        self.enabled = value


class _StubController:
    def __init__(self, *, status=None, remaining=0.0, escalating=False) -> None:
        self._status = status
        self._remaining = remaining
        self._escalating = escalating
        self.acked = 0

    def gate_status(self):
        return self._status

    def gate_remaining_s(self):
        return self._remaining

    def escalating(self):
        return self._escalating

    def acknowledge(self):
        self.acked += 1


def _window(controller: _StubController) -> SimpleNamespace:
    return SimpleNamespace(
        _controller=controller,
        gate_label=_StubLabel(),
        btn_mute=_StubButton(),
        btn_ack=_StubButton(),
        _append=lambda _text: None,
        _update_gate_status=lambda: None,
    )


def test_update_gate_status_uses_escalating_method(main_window_cls):
    window = _window(_StubController(status="muted", escalating=True))

    main_window_cls._update_gate_status(window)  # regressao: TypeError com property

    assert window.btn_ack.enabled is True
    expected = f"{tr('status.muted')} — {tr('status.escalating')}"
    assert window.gate_label.text == expected
    assert window.btn_mute.text == tr("main.btn_unmute")


def test_update_gate_status_fresh_state(main_window_cls):
    window = _window(_StubController())

    main_window_cls._update_gate_status(window)

    assert window.btn_ack.enabled is False
    assert window.gate_label.text == ""


def test_acknowledge_calls_escalating_as_method(main_window_cls):
    controller = _StubController(escalating=True)
    window = _window(controller)

    main_window_cls._acknowledge(window)

    assert controller.acked == 1


def test_acknowledge_noop_without_escalation(main_window_cls):
    controller = _StubController(escalating=False)
    window = _window(controller)

    main_window_cls._acknowledge(window)

    assert controller.acked == 0
