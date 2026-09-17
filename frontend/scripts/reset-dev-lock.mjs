#!/usr/bin/env node
/**
 * 清理 Next.js 开发服务器上次异常退出时留下的锁文件。
 *
 * Next 16 会把当前 dev server 的 PID 写在 .next/dev/lock 里。如果那个进程被强制结束
 * （Ctrl-C 两次、终端被关掉、后台任务被回收），锁文件会留下来，之后 `next dev` 只会
 * 报一句 "Another next dev server is already running" 就退出——页面看起来就"打不开"了。
 *
 * 这个脚本在每次 `npm run dev` 之前运行：
 *   * 没有锁文件            -> 什么都不做
 *   * 锁里的进程还活着      -> 打印中文提示并退出，避免两个 dev server 抢同一个端口
 *   * 锁里的进程已经不存在  -> 删掉过期锁文件，继续启动
 */

import { existsSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const lockPath = resolve(projectRoot, ".next/dev/lock");

function processAlive(pid) {
  if (!pid) return false;
  try {
    // 信号 0 只检查进程是否存在，不会真的发信号。
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

if (!existsSync(lockPath)) {
  process.exit(0);
}

let info = {};
try {
  info = JSON.parse(readFileSync(lockPath, "utf8"));
} catch {
  rmSync(lockPath, { force: true });
  console.log("已清理损坏的 Next 锁文件。");
  process.exit(0);
}

if (processAlive(info.pid)) {
  console.error("");
  console.error(`已经有一个 Next 开发服务器在运行（PID ${info.pid}，端口 ${info.port ?? "?"}）。`);
  console.error(`直接打开 http://localhost:${info.port ?? 3000} 即可。`);
  console.error("");
  console.error("如果你想重启它，先结束旧进程：");
  console.error(`    kill ${info.pid}`);
  console.error("然后再运行 npm run dev。");
  console.error("");
  process.exit(1);
}

rmSync(lockPath, { force: true });
console.log(`已清理上次残留的锁文件（旧进程 PID ${info.pid ?? "未知"} 已不存在）。`);
