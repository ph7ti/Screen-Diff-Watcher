"""Build de instaladores nativos: Windows (Inno Setup) e Linux (.deb).

Uso::

    python scripts/build_release.py --windows
    python scripts/build_release.py --linux

Roda **no SO alvo** (recusa cross-build). Requer o extra ``build`` (PyInstaller)
e, no Linux, ``dpkg-deb`` (pacote ``dpkg-dev``). No Windows, o ``ISCC.exe`` do
Inno Setup precisa estar no ``PATH`` (``choco install innosetup -y``).

Saidas: bundle PyInstaller em ``dist/screen-watch/`` e o instalador +
``build-info.json`` em ``dist/installers/``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
PACKAGING = REPO_ROOT / "packaging"
DIST = REPO_ROOT / "dist"
BUILD = REPO_ROOT / "build"
INSTALLERS = DIST / "installers"
SPEC = PACKAGING / "screen-watch.spec"
PYPROJECT = REPO_ROOT / "pyproject.toml"

APP_NAME = "screen-watch"
GUI_BIN = "screen-watch-gui"
PACKAGE_ICONS = SRC_DIR / "screen_watch" / "assets" / "icons"

# Nome do wrapper/entrada grafica no Linux (distinto do binario empacotado).
LINUX_GUI_COMMAND = "screen-diff-watcher-gui"

_CAPABILITY_MODULES = ("pynput", "cv2")


def _run(cmd: list[str]) -> None:
    print("$ " + " ".join(str(part) for part in cmd))
    subprocess.run(cmd, check=True)


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def resolve_version() -> str:
    """Versao do pacote, conferindo que o pyproject dinamico aponta para o mesmo attr."""
    sys.path.insert(0, str(SRC_DIR))
    import screen_watch  # noqa: PLC0415

    version = str(screen_watch.__version__)
    data = _load_pyproject()
    project = data.get("project", {})
    if "version" not in project.get("dynamic", []):
        raise SystemExit("pyproject: 'version' nao esta em project.dynamic")
    attr = (
        data.get("tool", {})
        .get("setuptools", {})
        .get("dynamic", {})
        .get("version", {})
        .get("attr")
    )
    if attr != "screen_watch.__version__":
        raise SystemExit(
            "pyproject: [tool.setuptools.dynamic].version.attr inesperado: " f"{attr!r}"
        )
    return version


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def detect_capabilities() -> dict[str, bool]:
    return {name: _has_module(name) for name in _CAPABILITY_MODULES}


def write_build_info(version: str, target: str) -> Path:
    INSTALLERS.mkdir(parents=True, exist_ok=True)
    info = {
        "app": APP_NAME,
        "version": version,
        "target": target,
        "platform": sys.platform,
        "python": platform.python_version(),
        "capabilities": detect_capabilities(),
        "spec": str(SPEC.relative_to(REPO_ROOT)),
    }
    path = INSTALLERS / "build-info.json"
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_pyinstaller() -> Path:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        str(SPEC),
    ]
    _run(cmd)
    bundle = DIST / APP_NAME
    if not bundle.is_dir():
        raise SystemExit(f"bundle PyInstaller nao encontrado: {bundle}")
    return bundle


# -- Windows (Inno Setup) --------------------------------------------------


def _iscc_from_program_files() -> str | None:
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def find_iscc() -> str:
    found = shutil.which("iscc") or shutil.which("ISCC") or _iscc_from_program_files()
    if found is None:
        raise SystemExit(
            "ISCC.exe (Inno Setup) nao encontrado no PATH. "
            "Instale com 'choco install innosetup -y' ou adicione ao PATH."
        )
    return found


def build_windows(version: str, iscc: str) -> Path:
    if sys.platform != "win32":
        raise SystemExit("--windows so roda no Windows (nao ha cross-build).")
    INSTALLERS.mkdir(parents=True, exist_ok=True)
    iss = PACKAGING / "windows" / "screen-diff-watcher.iss"
    _run([iscc, f"/DVersion={version}", f"/O{INSTALLERS}", str(iss)])
    output = INSTALLERS / f"screen-diff-watcher_{version}_windows_x64_setup.exe"
    if not output.is_file():
        raise SystemExit(f"instalador nao gerado: {output}")
    return output


# -- Linux (.deb) ----------------------------------------------------------


def find_dpkg_deb() -> str:
    found = shutil.which("dpkg-deb")
    if found is None:
        raise SystemExit("dpkg-deb nao encontrado; instale o pacote 'dpkg-dev'.")
    return found


def _write_template(template: Path, dest: Path, replacements: dict[str, str], mode: int) -> None:
    text = template.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("@" + key + "@", value)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    dest.chmod(mode)


def _assemble_deb_tree(root: Path, bundle: Path, version: str) -> None:
    linux_tpl = PACKAGING / "linux"

    opt_dir = root / "opt" / APP_NAME
    shutil.copytree(bundle, opt_dir, symlinks=True)

    # Wrappers `exec` (nao symlinks): o PyInstaller resolve `_internal` pelo
    # caminho real do executavel, e um symlink em /usr/bin quebraria isso.
    bin_dir = root / "usr" / "bin"
    for command, binary in ((APP_NAME, APP_NAME), (LINUX_GUI_COMMAND, GUI_BIN)):
        _write_template(
            linux_tpl / "launcher.template",
            bin_dir / command,
            {"BIN": binary},
            mode=0o755,
        )

    _write_template(
        linux_tpl / "screen-diff-watcher.desktop",
        root / "usr" / "share" / "applications" / "screen-diff-watcher.desktop",
        {"BIN": LINUX_GUI_COMMAND},
        mode=0o644,
    )

    icons = PACKAGE_ICONS
    for size in (32, 48, 64):
        source = icons / f"ScreenDiffWatcher_{size}px.png"
        dest = (
            root
            / "usr"
            / "share"
            / "icons"
            / "hicolor"
            / f"{size}x{size}"
            / "apps"
            / "screen-diff-watcher.png"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    _write_template(
        linux_tpl / "control.template",
        root / "DEBIAN" / "control",
        {"VERSION": version},
        mode=0o644,
    )
    postinst = linux_tpl / "postinst"
    dest_postinst = root / "DEBIAN" / "postinst"
    dest_postinst.write_bytes(postinst.read_bytes())
    dest_postinst.chmod(0o755)


def build_linux(version: str, dpkg_deb: str) -> Path:
    if not sys.platform.startswith("linux"):
        raise SystemExit("--linux so roda no Linux (nao ha cross-build).")
    bundle = DIST / APP_NAME
    if not bundle.is_dir():
        raise SystemExit(f"bundle PyInstaller nao encontrado: {bundle}")

    INSTALLERS.mkdir(parents=True, exist_ok=True)
    root = BUILD / f"deb-{APP_NAME}_{version}_amd64"
    if root.exists():
        shutil.rmtree(root)
    _assemble_deb_tree(root, bundle, version)

    output = INSTALLERS / f"{APP_NAME}_{version}_amd64.deb"
    _run([dpkg_deb, "--build", "--root-owner-group", str(root), str(output)])
    if not output.is_file():
        raise SystemExit(f"pacote .deb nao gerado: {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--windows", action="store_true", help="gera o setup.exe (Inno Setup)")
    group.add_argument("--linux", action="store_true", help="gera o pacote .deb")
    args = parser.parse_args(argv)

    version = resolve_version()

    # Recusa cross-build e valida os prerequisitos ANTES do PyInstaller.
    if args.windows:
        if sys.platform != "win32":
            raise SystemExit("--windows so roda no Windows (nao ha cross-build).")
        iscc = find_iscc()
        dpkg_deb = None
        target = "windows"
    else:
        if not sys.platform.startswith("linux"):
            raise SystemExit("--linux so roda no Linux (nao ha cross-build).")
        dpkg_deb = find_dpkg_deb()
        iscc = None
        target = "linux"
    print(f"{APP_NAME} {version} - build {target}")

    run_pyinstaller()
    info = write_build_info(version, target)
    artifact = build_windows(version, iscc) if args.windows else build_linux(version, dpkg_deb)

    print(f"build-info: {info}")
    print(f"artefato:   {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
