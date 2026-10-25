# -*- coding: utf-8 -*-
"""本地文件 vs git 已跟踪文件 全量比对"""
import os, subprocess, sys
BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
local = set()
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d != ".git"]
    for f in files:
        p = os.path.relpath(os.path.join(root, f), BASE).replace("\\", "/")
        local.add(p)
out = subprocess.run(["git", "ls-tree", "-r", "HEAD", "--name-only"],
                     cwd=BASE, capture_output=True)
tracked = set(x for x in out.stdout.decode("utf-8").splitlines() if x.strip())
only_local = sorted(local - tracked)
only_git = sorted(tracked - local)
print("本地文件(不含.git): %d" % len(local))
print("git已跟踪: %d" % len(tracked))
print("仅在本地(未上传): %d" % len(only_local))
for p in only_local[:40]:
    print("   -", p)
print("仅在git(本地缺失): %d" % len(only_git))
for p in only_git[:20]:
    print("   +", p)
# 空目录
empt = [r for r, d, f in os.walk(BASE) if not d and not f and ".git" not in r]
print("空目录: %d" % len(empt))
for r in empt[:10]:
    print("   []", os.path.relpath(r, BASE))
