from __future__ import annotations

import pytest

from screen_watch.resources import icon_path, icon_paths

EXPECTED_NAMES = [
    "ScreenDiffWatcher_32px.png",
    "ScreenDiffWatcher_48px.png",
    "ScreenDiffWatcher_64px.png",
    "ScreenDiffWatcher.png",
]


def test_icon_paths_lists_small_then_base():
    paths = icon_paths()
    assert [p.name for p in paths] == EXPECTED_NAMES
    assert all(p.is_file() and p.stat().st_size > 0 for p in paths)


@pytest.mark.parametrize("size,name", [(32, 32), (48, 48), (64, 64)])
def test_icon_path_returns_exact_size(size, name):
    path = icon_path(size)
    assert path is not None
    assert path.name == f"ScreenDiffWatcher_{name}px.png"


def test_icon_path_falls_back_to_base():
    assert icon_path().name == "ScreenDiffWatcher.png"
    assert icon_path(16).name == "ScreenDiffWatcher.png"


def test_icons_are_valid_images():
    from PIL import Image

    for path in icon_paths():
        with Image.open(path) as image:
            image.verify()


def test_tray_icon_image_uses_project_icon():
    from screen_watch.gui.tray import _icon_image

    image = _icon_image()
    assert image.size == (32, 32)
