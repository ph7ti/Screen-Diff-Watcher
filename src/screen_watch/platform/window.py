"""Wrapper fino sobre `pywinctl` (+ Win32) para janelas.

Regra (doc, secao 5.2 e 18.4): nenhum outro modulo importa `pywinctl`. Identificacao
de janela e sempre por `handle`; o titulo e apenas hint humano.

`list_app_windows()` devolve apenas janelas de aplicativos "reais" (visiveis, nao
ocultas pelo DWM, nao tool windows, com titulo), no estilo do Gerenciador de
Tarefas, cada uma com um `app_name` amigavel (FileDescription do executavel).
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass, replace
from typing import Any

pywinctl: Any
try:
    import pywinctl
except (Exception, SystemExit) as exc:
    # Depende do ambiente (ex.: sem X11). O `pymonctl`/`ewmhlib` chega a chamar
    # `sys.exit(1)` quando o servidor grafico nao atende, por isso `SystemExit`
    # tambem e tratado (nao e subclasse de `Exception`).
    pywinctl = None
    _PYWINCTL_ERROR: BaseException | None = exc
else:
    _PYWINCTL_ERROR = None

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# `ctypes.windll` so existe no Windows; o `getattr` evita erro do mypy no Linux
# (os caminhos que usam `_WINDLL` continuam guardados por `IS_WINDOWS`).
_WINDLL: Any = getattr(ctypes, "windll", None)


def _require_pywinctl():
    """Devolve o modulo `pywinctl` ou explica a ausencia de ambiente grafico.

    A fronteira de plataforma fica encapsulada aqui (nada de `sys.platform` fora
    de `platform/`); a causa original do import fica encadeada em `_PYWINCTL_ERROR`.
    """
    if pywinctl is None:
        raise RuntimeError(
            "pywinctl indisponivel neste ambiente (sem servidor grafico/X11?)"
        ) from _PYWINCTL_ERROR
    return pywinctl


_GWL_EXSTYLE = -20
_GW_OWNER = 4
_GA_ROOT = 2
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Classes da shell/desktop que nao sao "aplicativos" para o usuario.
_SHELL_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow",
}

_exe_description_cache: dict[str, str] = {}
_pid_name_cache: dict[int, str] = {}


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    rect: tuple[int, int, int, int]  # (x, y, w, h), espaco logico
    is_minimized: bool
    exists: bool
    app_name: str = ""  # nome amigavel do app (estilo Gerenciador de Tarefas)


def _flag(win: Any, name: str) -> bool:
    value = getattr(win, name, False)
    return bool(value() if callable(value) else value)


def _to_info(win: Any) -> WindowInfo:
    handle = win.getHandle()
    if isinstance(handle, str):
        try:
            handle = int(handle, 0)
        except ValueError:
            pass
    return WindowInfo(
        handle=handle,
        title=getattr(win, "title", "") or "",
        rect=(int(win.left), int(win.top), int(win.width), int(win.height)),
        is_minimized=_flag(win, "isMinimized"),
        exists=_flag(win, "isAlive"),
    )


def list_windows() -> list[WindowInfo]:
    """Lista as janelas visiveis. Janelas que falham ao inspecionar sao omitidas."""
    infos: list[WindowInfo] = []
    for win in _require_pywinctl().getAllWindows():
        try:
            infos.append(_to_info(win))
        except Exception:
            continue
    return infos


def find_window_by_handle(handle: int) -> WindowInfo | None:
    """Localiza a janela pelo handle. Nunca usa titulo como chave."""
    for win in _require_pywinctl().getAllWindows():
        try:
            info = _to_info(win)
        except Exception:
            continue
        if info.handle == handle:
            return info
    return None


def activate_window(handle: int) -> bool:
    """Traz a janela para o primeiro plano (usado pelo passo `activate`)."""
    for win in _require_pywinctl().getAllWindows():
        try:
            info = _to_info(win)
        except Exception:
            continue
        if info.handle == handle:
            try:
                return bool(win.activate())
            except Exception:
                return False
    return False


def is_window_active(handle: int) -> bool:
    """True se `handle` e a janela em foco (guarda contra foco roubado)."""
    for win in _require_pywinctl().getAllWindows():
        try:
            info = _to_info(win)
        except Exception:
            continue
        if info.handle == handle:
            return _flag(win, "isActive")
    return False


def app_window_label(info: WindowInfo) -> str:
    """Rotulo do seletor: nome do app primeiro, depois o titulo da janela."""
    name = info.app_name or info.title or "(sem titulo)"
    _, _, width, height = info.rect
    if info.title and info.title != name:
        return f"{name} — {info.title}  [{width}x{height}]"
    return f"{name}  [{width}x{height}]"


def list_app_windows() -> list[WindowInfo]:
    """Janelas de aplicativos para o seletor da GUI (sem ruido de janelas ocultas)."""
    result: list[WindowInfo] = []
    for win in _require_pywinctl().getAllWindows():
        try:
            info = _to_info(win)
        except Exception:
            continue
        if not _is_app_window(info):
            continue
        result.append(replace(info, app_name=friendly_app_name(info.handle, info.title)))
    return result


def friendly_app_name(handle: int, title: str = "") -> str:
    """Nome do app dono da janela (FileDescription), com fallbacks seguros."""
    if not IS_WINDOWS:
        return title
    hwnd = _as_hwnd(handle)
    if hwnd is None:
        return title
    pid = _window_pid(hwnd)
    if pid is None:
        return title
    cached = _pid_name_cache.get(pid)
    if cached is not None:
        return cached
    name = _build_app_name(pid, title)
    _pid_name_cache[pid] = name
    return name


# -- Win32 (somente Windows) ---------------------------------------------
_configured = False


def _configure() -> None:
    global _configured
    if _configured or not IS_WINDOWS:
        return
    try:
        user32 = _WINDLL.user32
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        if hasattr(user32, "GetWindowLongPtrW"):
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t

        kernel32 = _WINDLL.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        version = _WINDLL.version
        version.GetFileVersionInfoSizeW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [
            wintypes.LPVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.UINT),
        ]
        version.VerQueryValueW.restype = wintypes.BOOL

        dwmapi = _WINDLL.dwmapi
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        _configured = True
    except (AttributeError, OSError):  # pragma: no cover - depende do Windows
        log.warning("could not configure the Win32 window APIs")


def _as_hwnd(handle: Any) -> int | None:
    if isinstance(handle, int):
        return handle or None
    try:
        return int(handle, 0) or None
    except (TypeError, ValueError):
        return None


def _build_app_name(pid: int, title: str) -> str:
    exe = _process_image_path(pid)
    if not exe:
        return title
    description = _file_description(exe)
    if description:
        return description
    stem = exe.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    return stem[:-4] if stem.lower().endswith(".exe") else stem


def _is_app_window(info: WindowInfo) -> bool:
    if not info.exists or info.is_minimized:
        return False
    width, height = info.rect[2], info.rect[3]
    if width <= 32 or height <= 32:
        return False
    if not info.title.strip():
        return False
    if not IS_WINDOWS:
        return True

    _configure()
    hwnd = _as_hwnd(info.handle)
    if hwnd is None:
        return False
    if not _is_visible(hwnd) or _is_cloaked(hwnd) or _is_tool_window(hwnd):
        return False
    if not _is_root(hwnd):
        return False
    owner = _owner_window(hwnd)
    if owner is not None and _is_visible(owner):
        return False
    return _class_name(hwnd) not in _SHELL_CLASSES


def _is_visible(hwnd: int) -> bool:
    try:
        return bool(_WINDLL.user32.IsWindowVisible(wintypes.HWND(hwnd)))
    except (AttributeError, OSError):
        return True


def _is_tool_window(hwnd: int) -> bool:
    try:
        user32 = _WINDLL.user32
        getter = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        return bool(int(getter(wintypes.HWND(hwnd), _GWL_EXSTYLE)) & _WS_EX_TOOLWINDOW)
    except (AttributeError, OSError, ValueError):
        return False


def _is_cloaked(hwnd: int) -> bool:
    try:
        value = ctypes.c_int(0)
        _WINDLL.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), _DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
        )
        return value.value != 0
    except (AttributeError, OSError):
        return False


def _class_name(hwnd: int) -> str:
    try:
        buffer = ctypes.create_unicode_buffer(256)
        _WINDLL.user32.GetClassNameW(wintypes.HWND(hwnd), buffer, len(buffer))
        return buffer.value
    except (AttributeError, OSError):
        return ""


def _window_pid(hwnd: int) -> int | None:
    try:
        pid = wintypes.DWORD(0)
        _WINDLL.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return int(pid.value) or None
    except (AttributeError, OSError):
        return None


def _owner_window(hwnd: int) -> int | None:
    try:
        owner = _WINDLL.user32.GetWindow(wintypes.HWND(hwnd), _GW_OWNER)
        return int(owner) if owner else None
    except (AttributeError, OSError):
        return None


def _is_root(hwnd: int) -> bool:
    """True se a janela e de nivel superior (nao e filha de outra)."""
    try:
        root = _WINDLL.user32.GetAncestor(wintypes.HWND(hwnd), _GA_ROOT)
        return int(root) == hwnd
    except (AttributeError, OSError):
        return True


def _process_image_path(pid: int) -> str | None:
    try:
        kernel32 = _WINDLL.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value or None
            return None
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):
        return None


def _file_description(exe: str) -> str:
    cached = _exe_description_cache.get(exe)
    if cached is not None:
        return cached
    description = _query_version_string(exe, "FileDescription") or _query_version_string(
        exe, "ProductName"
    )
    _exe_description_cache[exe] = description
    return description


def _query_version_string(exe: str, key: str) -> str:
    try:
        version = _WINDLL.version
        size = version.GetFileVersionInfoSizeW(exe, None)
        if not size:
            return ""
        data = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(exe, 0, size, data):
            return ""
        translation_ptr = ctypes.c_void_p()
        translation_len = wintypes.UINT()
        if not version.VerQueryValueW(
            data,
            "\\VarFileInfo\\Translation",
            ctypes.byref(translation_ptr),
            ctypes.byref(translation_len),
        ):
            return ""
        if translation_len.value < 4 or not translation_ptr.value:
            return ""
        words = ctypes.cast(translation_ptr, ctypes.POINTER(wintypes.WORD))
        language, codepage = words[0], words[1]
        sub_block = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{key}"
        value_ptr = ctypes.c_void_p()
        value_len = wintypes.UINT()
        if not version.VerQueryValueW(
            data, sub_block, ctypes.byref(value_ptr), ctypes.byref(value_len)
        ):
            return ""
        return ctypes.wstring_at(value_ptr.value) if value_ptr.value else ""
    except (AttributeError, OSError, ValueError):
        return ""
