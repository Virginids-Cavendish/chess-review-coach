#!/usr/bin/env python3
"""通过 GitHub API 把当前提交上传到空仓库。

为什么需要这个脚本：这台机器上 `github.com:443` 连不通（`git push` 会失败），但
`api.github.com` 是通的。于是改用 Git Data API 直接创建 blob → tree → commit → ref，
效果和 push 完全一样，只是走 HTTP API 而不是 git 传输协议。

用法：
    python scripts/publish_via_api.py <owner>/<repo> [branch]

要求：本机已提交（工作区干净），并且 `gh auth token` 可用。
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.github.com"
WORKERS = 8


def gh_token() -> str:
    token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
    return token.stdout.strip()


def api(token: str, method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "chess-review-coach-publisher",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode()
        return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:400]
        raise SystemExit("API {} {} 失败: HTTP {} {}".format(method, path, error.code, detail))


def committed_files() -> list[tuple[str, str, str]]:
    """返回 [(path, mode, blob_sha)]，全部来自 HEAD 提交本身。"""
    out = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    files = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        mode, _type, sha = meta.split()
        files.append((path, mode, sha))
    return files


def blob_bytes(sha: str) -> bytes:
    return subprocess.run(["git", "cat-file", "blob", sha], capture_output=True, check=True).stdout


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("用法: publish_via_api.py <owner>/<repo> [branch]")
    repo = sys.argv[1]
    branch = sys.argv[2] if len(sys.argv) > 2 else "main"

    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
    if status.strip():
        raise SystemExit("工作区不干净，请先提交：\n" + status)

    message = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True, check=True
    ).stdout.strip()
    files = committed_files()
    print("准备上传 {} 个文件到 {}\n".format(len(files), repo))

    token = gh_token()

    def upload(entry: tuple[str, str, str]) -> tuple[str, str, str]:
        path, mode, local_sha = entry
        content = base64.b64encode(blob_bytes(local_sha)).decode()
        result = api(token, "POST", "/repos/{}/git/blobs".format(repo),
                     {"content": content, "encoding": "base64"})
        remote_sha = result["sha"]
        if remote_sha != local_sha:
            # 内容一致时 GitHub 算出来的 sha 必然相同；不同说明传输出了问题。
            raise SystemExit("内容校验失败: {}（本地 {} / 远端 {}）".format(path, local_sha[:8], remote_sha[:8]))
        return path, mode, remote_sha

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        uploaded = list(pool.map(upload, files))
    print("  ✓ {} 个 blob 上传完成，且远端 sha 与本地提交逐字节一致".format(len(uploaded)))

    tree = api(token, "POST", "/repos/{}/git/trees".format(repo), {
        "tree": [
            {"path": path, "mode": mode, "type": "blob", "sha": sha}
            for path, mode, sha in uploaded
        ]
    })
    print("  ✓ tree: {}".format(tree["sha"][:8]))

    commit = api(token, "POST", "/repos/{}/git/commits".format(repo),
                 {"message": message, "tree": tree["sha"], "parents": []})
    print("  ✓ commit: {}".format(commit["sha"][:8]))

    api(token, "POST", "/repos/{}/git/refs".format(repo),
        {"ref": "refs/heads/{}".format(branch), "sha": commit["sha"]})
    print("  ✓ 分支 {} 指向该提交".format(branch))

    return 0


if __name__ == "__main__":
    sys.exit(main())
