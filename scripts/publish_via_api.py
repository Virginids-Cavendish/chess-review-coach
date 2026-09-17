#!/usr/bin/env python3
"""通过 GitHub API 把本地提交历史完整镜像到远端仓库。

为什么需要它：这台机器上 `github.com:443` 连不通（`git push` 直接 SSL_ERROR_SYSCALL），
但 `api.github.com` 是通的。于是改用 Git Data API 走一遍 git 传输协议做的事：

    每个提交 -> blobs -> tree -> commit（带正确的 author/committer 和父提交）-> 更新 ref

因为作者、提交时间、父提交、tree 都按原样重建，重建出来的 **commit sha 与本地完全一致**，
所以以后在能联网的机器上 `git push` 只会得到 "Everything up-to-date"，不会出现历史分叉。

用法：
    python scripts/publish_via_api.py <owner>/<repo> [branch]
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

API = "https://api.github.com"
WORKERS = 8
IDENT = re.compile(r"^(?P<name>.*) <(?P<email>.*)> (?P<ts>\d+) (?P<tz>[+-]\d{4})$")


def run(*args: str) -> bytes:
    return subprocess.run(list(args), capture_output=True, check=True).stdout


def gh_token() -> str:
    return subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()


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
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode()
        return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:500]
        raise SystemExit("API {} {} 失败: HTTP {} {}".format(method, path, error.code, detail))


def parse_identity(text: str) -> Dict[str, str]:
    match = IDENT.match(text)
    if not match:
        raise SystemExit("无法解析作者信息: " + text)
    timestamp = int(match.group("ts"))
    tz = match.group("tz")
    offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
    if tz[0] == "-":
        offset = -offset
    moment = datetime.fromtimestamp(timestamp, timezone(offset))
    return {
        "name": match.group("name"),
        "email": match.group("email"),
        "date": moment.strftime("%Y-%m-%dT%H:%M:%S") + tz[:3] + ":" + tz[3:],
    }


def read_commit(sha: str) -> Dict[str, object]:
    raw = run("git", "cat-file", "commit", sha).decode("utf-8", "replace")
    headers, _, message = raw.partition("\n\n")
    parents: List[str] = []
    data: Dict[str, object] = {"parents": parents, "message": message}
    for line in headers.splitlines():
        if line.startswith("tree "):
            data["tree"] = line[5:].strip()
        elif line.startswith("parent "):
            parents.append(line[7:].strip())
        elif line.startswith("author "):
            data["author"] = parse_identity(line[7:])
        elif line.startswith("committer "):
            data["committer"] = parse_identity(line[10:])
    return data


def tree_entries(commit: str) -> List[Tuple[str, str, str]]:
    out = run("git", "ls-tree", "-r", commit).decode()
    entries: List[Tuple[str, str, str]] = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        mode, _type, sha = meta.split()
        entries.append((path, mode, sha))
    return entries


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("用法: publish_via_api.py <owner>/<repo> [branch]")
    repo = sys.argv[1]
    branch = sys.argv[2] if len(sys.argv) > 2 else "main"

    if subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True
    ).stdout.strip():
        raise SystemExit("工作区不干净，请先提交。")

    commits = run("git", "rev-list", "--reverse", "HEAD").decode().split()
    token = gh_token()
    blob_cache: Dict[str, str] = {}
    print("镜像 {} 个提交到 {} 的 {} 分支\n".format(len(commits), repo, branch))

    head_sha = ""
    for index, commit in enumerate(commits, start=1):
        info = read_commit(commit)
        entries = tree_entries(commit)

        missing = [(p, m, s) for p, m, s in entries if s not in blob_cache]
        if missing:

            def upload(entry: Tuple[str, str, str]) -> Tuple[str, str]:
                path, _mode, local_sha = entry
                content = base64.b64encode(run("git", "cat-file", "blob", local_sha)).decode()
                result = api(
                    token,
                    "POST",
                    "/repos/{}/git/blobs".format(repo),
                    {"content": content, "encoding": "base64"},
                )
                if result["sha"] != local_sha:
                    raise SystemExit("blob 校验失败: {}".format(path))
                return local_sha, result["sha"]

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for local_sha, remote_sha in pool.map(upload, missing):
                    blob_cache[local_sha] = remote_sha
            print("  [{}] 上传 {} 个新 blob（累计 {}）".format(index, len(missing), len(blob_cache)))

        tree = api(
            token,
            "POST",
            "/repos/{}/git/trees".format(repo),
            {
                "tree": [
                    {"path": path, "mode": mode, "type": "blob", "sha": blob_cache[sha]}
                    for path, mode, sha in entries
                ]
            },
        )
        created = api(
            token,
            "POST",
            "/repos/{}/git/commits".format(repo),
            {
                "message": info["message"],
                "tree": tree["sha"],
                "parents": info["parents"],
                "author": info["author"],
                "committer": info["committer"],
            },
        )
        head_sha = created["sha"]
        flag = "✓ sha 一致" if head_sha == commit else "⚠ sha 不同（本地 {}）".format(commit[:8])
        print("  [{}] commit {} {}".format(index, head_sha[:8], flag))

    api(
        token,
        "POST",
        "/repos/{}/git/refs".format(repo),
        {"ref": "refs/heads/{}".format(branch), "sha": head_sha},
    )
    print("\n  ✓ refs/heads/{} -> {}".format(branch, head_sha[:8]))

    # 让本地也知道远端已经同步，这样 git status 不会显示成"落后"
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/{}".format(branch), head_sha], check=False
    )
    local_head = run("git", "rev-parse", "HEAD").decode().strip()
    print("  本地 HEAD: {}".format(local_head[:8]))
    if local_head == head_sha:
        print("  本地与远端完全一致 ✓")
    else:
        print("  本地与远端 sha 不同；之后可用 git fetch 对齐".format(branch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
