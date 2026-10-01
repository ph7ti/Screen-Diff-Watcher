from __future__ import annotations

from screen_watch.config.schema import TargetConfig
from screen_watch.gui.labels import selection_label, target_label
from screen_watch.persistence.selection import Selection


def test_target_label_shows_app_hint_roi_and_mode():
    target = TargetConfig(
        name="painel",
        window_handle=1,
        roi_relative=(120, 340, 400, 80),
        window_title_hint="ERP",
        mode="advanced",
    )
    assert target_label(target) == "[YAML] painel — ERP — Região 120,340 400x80 — advanced"


def test_target_label_without_hint():
    target = TargetConfig(
        name="painel", window_handle=1, roi_relative=(1, 2, 3, 4), mode="light"
    )
    assert target_label(target) == "[YAML] painel — Região 1,2 3x4 — light"


def test_selection_label_prefers_app_name():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(10, 20, 30, 40),
        app_name="WhatsApp",
        window_title_hint="WhatsApp Beta",
        mode="light",
    )
    assert selection_label(selection, "whatsapp") == "Seleção WhatsApp — Região 10,20 30x40 — light"


def test_selection_label_falls_back_to_stem():
    selection = Selection(
        window_handle=1, origin_at_selection=(0, 0), roi_relative=(1, 2, 3, 4), mode="default"
    )
    assert selection_label(selection, "arquivo") == "Seleção arquivo — Região 1,2 3x4 — default"


def test_selection_label_prefixed_by_name():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(10, 20, 30, 40),
        app_name="Software XYZ",
        mode="advanced",
        name="verificando download",
    )
    assert selection_label(selection, "verificando-download") == (
        "verificando download - Seleção Software XYZ — Região 10,20 30x40 — advanced"
    )


def test_selection_label_without_name_is_unchanged():
    selection = Selection(
        window_handle=1,
        origin_at_selection=(0, 0),
        roi_relative=(10, 20, 30, 40),
        app_name="WhatsApp",
        mode="light",
    )
    assert selection_label(selection, "whatsapp") == "Seleção WhatsApp — Região 10,20 30x40 — light"


def test_target_label_prefers_label_over_name():
    target = TargetConfig(
        name="painel",
        window_handle=1,
        roi_relative=(120, 340, 400, 80),
        window_title_hint="ERP",
        mode="advanced",
        label="Verificando Download",
    )
    assert target_label(target) == (
        "[YAML] Verificando Download — ERP — Região 120,340 400x80 — advanced"
    )


def test_target_label_falls_back_to_name_without_label():
    target = TargetConfig(
        name="painel", window_handle=1, roi_relative=(1, 2, 3, 4), mode="light"
    )
    assert target_label(target) == "[YAML] painel — Região 1,2 3x4 — light"
