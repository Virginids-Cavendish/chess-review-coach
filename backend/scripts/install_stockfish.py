#!/usr/bin/env python3
"""Download the official Stockfish binary into ``backend/engine/bin``.

Keeps the project self-contained: no Homebrew, no system changes, and the app finds the
engine automatically (``config.settings.resolved_stockfish_path``).

    python scripts/install_stockfish.py            # install the pinned version
    python scripts/install_stockfish.py --force    # re-download
    python scripts/install_stockfish.py --tag sf_17

The script fetches the release archive from GitHub. If ``github.com`` is unreachable
(corporate proxies often block it while allowing api.github.com), it falls back to the
GitHub API asset endpoint, which redirects to the same file on the release CDN.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = "official-stockfish/Stockfish"
DEFAULT_TAG = "sf_19"
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEST_DIR = BACKEND_DIR / "engine" / "bin"
USER_AGENT = "chess-review-coach-installer"


def asset_name() -> str:
    """Pick the release asset for this machine."""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Darwin":
        return "stockfish-macos-universal.tar.gz"
    if system == "Linux":
        if machine in ("arm64", "aarch64"):
            return "stockfish-linux-arm64-universal.tar.gz"
        if machine in ("riscv64",):
            return "stockfish-linux-riscv64-universal.tar.gz"
        return "stockfish-linux-x86-64-universal.tar.gz"
    if system == "Windows":
        if machine in ("arm64", "aarch64"):
            return "stockfish-windows-arm64-universal.zip"
        return "stockfish-windows-x86-64-universal.zip"

    raise SystemExit("Unsupported platform: {} {}".format(system, machine))


def release_assets(tag: str) -> dict:
    url = "https://api.github.com/repos/{}/releases/tags/{}".format(REPO, tag)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    return {asset["name"]: asset for asset in payload.get("assets", [])}


def download(url: str, destination: Path, accept: str = "*/*") -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=600) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def fetch_archive(tag: str, name: str, workdir: Path) -> Path:
    archive = workdir / name
    if archive.exists():
        return archive

    direct = "https://github.com/{}/releases/download/{}/{}".format(REPO, tag, name)
    try:
        print("下载 {}".format(direct))
        download(direct, archive)
        return archive
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
        print("直连失败（{}），改用 GitHub API 资源接口…".format(error))

    assets = release_assets(tag)
    if name not in assets:
        raise SystemExit("发布 {} 中没有找到资源 {}。可用：{}".format(tag, name, ", ".join(sorted(assets))))

    api_url = "https://api.github.com/repos/{}/releases/assets/{}".format(REPO, assets[name]["id"])
    print("下载 {}".format(api_url))
    download(api_url, archive, accept="application/octet-stream")
    return archive


def extract(archive: Path, workdir: Path) -> Path:
    target = workdir / "extracted"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(target)
    else:
        with tarfile.open(archive) as handle:
            handle.extractall(target)
    return target


def find_binary(root: Path) -> Path:
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.startswith("stockfish") and path.suffix in ("", ".exe")
    ]
    if not candidates:
        raise SystemExit("压缩包里没有找到 stockfish 可执行文件")
    # Prefer the exact name, then the largest file (universal builds embed NNUE weights).
    exact = [path for path in candidates if path.name in ("stockfish", "stockfish.exe")]
    if exact:
        return exact[0]
    return max(candidates, key=lambda path: path.stat().st_size)


def install(tag: str, force: bool) -> int:
    name = asset_name()
    target = DEST_DIR / ("stockfish.exe" if name.endswith(".zip") else "stockfish")

    if target.exists() and not force:
        print("已存在：{}".format(target))
        print("使用 --force 可以重新下载。")
        return verify(target)

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        archive = fetch_archive(tag, name, workdir)
        root = extract(archive, workdir)
        binary = find_binary(root)
        shutil.copy2(binary, target)
        target.chmod(0o755)

        for license_name in ("Copying.txt", "AUTHORS"):
            source = next(root.rglob(license_name), None)
            if source is not None:
                shutil.copy2(source, DEST_DIR / (license_name if license_name.endswith(".txt") else license_name + ".txt"))

    print("已安装：{}".format(target))
    print("Stockfish 使用 GPL-3.0 许可，许可证文件已一并复制到 {}".format(DEST_DIR))
    return verify(target)


def verify(binary: Path) -> int:
    try:
        result = subprocess.run(
            [str(binary)],
            input="uci\nquit\n",
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print("无法运行 {}: {}".format(binary, error))
        return 1

    banner = next(
        (line for line in result.stdout.splitlines() if line.lower().startswith("id name")),
        "",
    )
    if banner:
        print("验证通过：{}".format(banner))
        return 0
    print("引擎没有响应 UCI 握手，输出：{}".format(result.stdout[:200]))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 Stockfish 到 backend/engine/bin")
    parser.add_argument("--tag", default=DEFAULT_TAG, help="GitHub release tag，例如 sf_19")
    parser.add_argument("--force", action="store_true", help="即使已存在也重新下载")
    args = parser.parse_args()
    return install(args.tag, args.force)


if __name__ == "__main__":
    sys.exit(main())
