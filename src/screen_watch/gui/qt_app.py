"""Fabrica do `QApplication` compartilhado (plano, Fase C1).

Mantem uma referencia global ao `QApplication` criado pelo CLI/overlay, para que a
GUI use `app.exec()` no mesmo objeto e o CLI nao derrube o app ao sair. Qt e
importado dentro da funcao: a coleta de testes nao depende de display (doc P12).
"""

from __future__ import annotations

_QT_APP = None


def ensure_app():
    """Devolve o `QApplication` ativo, criando-o (uma unica vez) se necessario."""
    from PyQt6.QtCore import Qt  # noqa: PLC0415
    from PyQt6.QtWidgets import QApplication  # noqa: PLC0415

    global _QT_APP

    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([])
        _QT_APP = app
    return app
