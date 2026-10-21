"""Create the EasyTextDiff Windows portable folder without changing global packages."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "src"
# Running this repository script does not require installing the application.
sys.path.insert(0, str(SOURCE))
from easytextdiff.branding import APP_NAME, DISPLAY_NAME, VERSION


BUILD_DEPS = PROJECT / ".build_deps"
PACKAGING = PROJECT / ".packaging"
OUTPUT = PROJECT / "dist"


def _verify_paths(output: Path = OUTPUT) -> None:
    """Validate all build destinations before PyInstaller can replace files."""
    for path in (BUILD_DEPS, PACKAGING):
        if not path.resolve().is_relative_to(PROJECT):
            raise RuntimeError(f"Build path escapes the project: {path}")
    if output.resolve() != output:
        raise RuntimeError("The output directory must not be redirected by a link.")
    portable = output / APP_NAME
    if portable.resolve() != portable:
        raise RuntimeError("The portable directory must not be redirected by a link.")
    if PROJECT.resolve().is_relative_to(portable):
        raise RuntimeError("The build destination must not replace the source project.")
    if output.parent == output:
        raise RuntimeError("Choose an output directory below the filesystem root.")
    for directory in ("src", "scripts", "tests", ".github", "docs", "assets"):
        if output.is_relative_to(PROJECT / directory):
            raise RuntimeError("The output directory must not be inside shipped source directories.")


def _copy_dependency_notices(destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError(f"Python license is missing: {python_license}")
    shutil.copy2(python_license, destination / "Python-LICENSE.txt")
    versions = [f"Python {sys.version.split()[0]}"]
    for name in ("PyQt5", "PyQt5-Qt5", "PyQt5-sip"):
        distribution = importlib.metadata.distribution(name)
        versions.append(f"{name} {distribution.version}")
        component_dir = destination / name
        component_dir.mkdir(exist_ok=True)
        metadata = distribution.read_text("METADATA")
        if metadata:
            (component_dir / "PACKAGE-METADATA.txt").write_text(metadata, encoding="utf-8")
        for entry in distribution.files or ():
            if not any(word in Path(str(entry)).name.lower()
                       for word in ("license", "copying", "notice")):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                target = component_dir / source.name
                if target.exists():
                    target = component_dir / str(entry).replace("/", "_").replace("\\", "_")
                shutil.copy2(source, target)

    # Some PyQt5 wheels omit the GPL text. The repository includes the same
    # unmodified GPLv3 license, so clean clones do not need a local source tarball.
    pyqt_license = destination / "PyQt5" / "LICENSE"
    if not pyqt_license.is_file():
        shutil.copy2(PROJECT / "LICENSE.txt", pyqt_license)

    # A previously downloaded PyQt source archive is optional. Preserve it when
    # available; building from a clean clone never downloads or requires it.
    source_archives = sorted((PACKAGING / "third_party_sources").glob("PyQt5-*.tar.gz"))
    if source_archives:
        source_dir = destination / "source_archives"
        source_dir.mkdir(exist_ok=True)
        for archive in source_archives:
            shutil.copy2(archive, source_dir / archive.name)
            with tarfile.open(archive, "r:gz") as package:
                for member in package.getmembers():
                    basename = Path(member.name).name
                    if member.isfile() and basename.upper() in {
                        "LICENSE", "LICENSE.GPL3", "LICENSE.GPLV3", "COPYING"
                    }:
                        content = package.extractfile(member)
                        if content is not None:
                            (destination / "PyQt5" / basename).write_bytes(content.read())
    (destination / "VERSIONS.txt").write_text("\n".join(versions) + "\n", encoding="utf-8")
    (destination / "SOURCE-LOCATIONS.txt").write_text(
        "Application source: ../source/\n"
        "Python source and license: https://www.python.org/downloads/source/\n"
        "PyQt5 source: https://pypi.org/project/PyQt5/#files\n"
        "Qt source: https://download.qt.io/archive/qt/5.15/5.15.2/\n"
        "SIP source: https://pypi.org/project/PyQt5-sip/#files\n",
        encoding="utf-8",
    )
    return versions


def _copy_application_source(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    source_extensions = {
        ".py", ".txt", ".ico", ".qss", ".md", ".rst", ".toml", ".cfg",
        ".ini", ".yaml", ".yml", ".json", ".svg", ".png",
    }
    source_names = {"LICENSE", "COPYING", "NOTICE", ".gitignore", ".gitattributes", ".editorconfig"}
    for path in sorted(PROJECT.iterdir()):
        if path.is_symlink():
            continue
        if path.is_file() and (path.suffix.lower() in source_extensions
                               or path.name in source_names):
            shutil.copy2(path, destination / path.name)
    for directory in ("src", "scripts", "tests", ".github", "docs", "assets"):
        source = PROJECT / directory
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(
                source, destination / directory, dirs_exist_ok=True,
                ignore=_source_ignore,
            )


def _source_ignore(directory: str, names: list[str]) -> set[str]:
    excluded = {
        ".git", ".build_deps", ".build_cache", ".packaging", ".qa", ".venv",
        "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".coverage", "build", "dist", "output",
    }
    return {
        name for name in names
        if name in excluded or name.endswith((".pyc", ".pyo", ".egg-info", ".dist-info"))
        or (Path(directory) / name).is_symlink()
    }


def _build_environment() -> dict[str, str]:
    environment = os.environ.copy()
    if importlib.util.find_spec("PyInstaller") is not None:
        return environment
    if not (BUILD_DEPS / "PyInstaller" / "__main__.py").is_file():
        raise RuntimeError(
            "PyInstaller is not installed. Run python -m pip install "
            "-r requirements.txt -r requirements-build.txt in your build environment. "
            "Alternatively install requirements-build.txt with pip "
            f"--target \"{BUILD_DEPS}\" --cache-dir \"{PROJECT / '.build_cache'}\"."
        )
    environment["PYTHONPATH"] = str(BUILD_DEPS) + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    return environment


def main(argv=None) -> int:
    if sys.platform != "win32":
        raise RuntimeError("Build this portable package on Windows.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT,
                        help=f'Directory containing the generated {APP_NAME} folder (default: dist)')
    args = parser.parse_args(argv)
    output = Path(os.path.abspath(args.output.expanduser()))
    portable = output / APP_NAME
    _verify_paths(output)
    application = SOURCE / "easytextdiff" / "__main__.py"
    if not application.is_file():
        raise RuntimeError(f"Application source is not ready: {application}")
    environment = _build_environment()
    PACKAGING.mkdir(exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--windowed", "--onedir", "--name", APP_NAME,
        "--distpath", str(output),
        "--workpath", str(PACKAGING / "work"),
        "--specpath", str(PACKAGING / "spec"),
        "--paths", str(SOURCE),
    ]
    icon = PROJECT / "assets" / "app.ico"
    if icon.is_file():
        command += ["--icon", str(icon)]
    command.append(str(application))
    subprocess.run(command, cwd=PROJECT, env=environment, check=True)
    executable = portable / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise RuntimeError("PyInstaller did not produce the expected executable.")
    versions = _copy_dependency_notices(portable / "third_party")
    _copy_application_source(portable / "source")
    application_license = PROJECT / "LICENSE.txt"
    if application_license.is_file():
        shutil.copy2(application_license, portable / "LICENSE.txt")
    chinese_readme = PROJECT / "README_zh.txt"
    if chinese_readme.is_file():
        shutil.copy2(chinese_readme, portable / "README_zh.txt")
    (portable / "START-HERE.txt").write_text(
        f"{DISPLAY_NAME} {APP_NAME} {VERSION}\n\n"
        f"双击 {APP_NAME}.exe 即可使用，目标电脑不需要安装 Python。\n"
        f"请完整保留 {APP_NAME} 文件夹，包括 _internal 子文件夹；复制或分享时"
        "请携带整个文件夹。\n\n"
        "默认可以直接在左右两侧粘贴文本，也可以打开两个文件。\n"
        "按 Ctrl+Enter 开始比较，按 F7 / F8 跳转到上一处 / 下一处差异。\n"
        "详细用法请参阅 README_zh.txt。\n\n"
        "应用源码和测试在 source/，依赖许可和源码位置在 third_party/。\n"
        "本应用按 GNU GPL 第 3 版或更新版本发布，许可全文见 LICENSE.txt。\n\n"
        + "\n".join(versions) + "\n",
        encoding="utf-8",
    )
    print(f"Portable application: {executable}")
    print(f"Keep the complete {APP_NAME} folder when copying or sharing the application.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
