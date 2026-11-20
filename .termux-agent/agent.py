#!/usr/bin/env python3
"""GitHub Issues relay for a user-owned Termux development workspace.
Task issues must start with TERMUX_TASK: and contain one JSON object.
This is a convenience boundary, NOT an OS-level sandbox.
"""
import argparse, json, os, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

API = "https://api.github.com"
PREFIX = "TERMUX_TASK:"
MAX_BODY = 48000
MAX_OUTPUT = 18000
ALLOWED = {"python", "python3", "pytest", "pip", "pip3", "npm", "node", "git", "gradle", "ruff"}

def api(token, method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "Termux-Workspace-Agent/0.1",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read(1200).decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc

def safe_path(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("A relative path is required.")
    parts = Path(value).parts
    if Path(value).is_absolute() or ".." in parts:
        raise ValueError("Absolute paths and parent-directory traversal are forbidden.")
    current = root
    for part in parts:
        if part in ("", "."):
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlinks are not allowed in task paths.")
    candidate = current.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes the configured workspace.")
    return candidate

def run_task(root, task):
    if not isinstance(task, dict):
        raise ValueError("Task must be a JSON object.")
    op = task.get("op")
    if op == "list":
        target = safe_path(root, task.get("path", "."))
        if not target.is_dir():
            raise ValueError("Requested path is not a directory.")
        return json.dumps([{"name": p.name, "type": "directory" if p.is_dir() else "file"}
                           for p in sorted(target.iterdir(), key=lambda x: x.name.lower())[:300]], indent=2)
    if op == "read":
        target = safe_path(root, task.get("path", ""))
        if not target.is_file():
            raise ValueError("File does not exist.")
        if target.stat().st_size > MAX_BODY:
            raise ValueError("File exceeds the 48 KB read limit.")
        return target.read_text(encoding="utf-8", errors="replace")
    if op == "write":
        rel = task.get("path", "")
        target = safe_path(root, rel)
        content = task.get("content")
        if not isinstance(content, str) or len(content.encode()) > MAX_BODY:
            raise ValueError("Content must be text no larger than 48 KB.")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".agent-tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
        return f"Wrote {len(content.encode())} bytes to {rel}"
    if op == "run":
        argv = task.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("run requires argv as an array of strings; shell commands are not accepted.")
        exe = argv[0]
        if exe not in ALLOWED and exe != "./gradlew":
            raise ValueError(f"Executable not allowed: {exe}")
        if exe == "git" and (len(argv) < 2 or argv[1] not in {"status", "diff", "log", "branch", "add", "commit", "pull", "fetch"}):
            raise ValueError("Git subcommand is not permitted.")
        if exe == "npm" and (len(argv) < 2 or argv[1] not in {"install", "ci", "test", "run", "build"}):
            raise ValueError("npm subcommand is not permitted.")
        cwd = safe_path(root, task.get("cwd", "."))
        if not cwd.is_dir():
            raise ValueError("Working directory does not exist.")
        env = {k: v for k, v in os.environ.items() if k not in {"TERMUX_AGENT_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"}}
        env["HOME"] = os.environ.get("HOME", str(Path.home()))
        env["PATH"] = os.environ.get("PATH", "")
        env["TMPDIR"] = os.environ.get("TMPDIR", "/tmp")
        try:
            result = subprocess.run(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                timeout=min(max(int(task.get("timeout", 120)), 1), 600), check=False)
            output = result.stdout or "(no output)"
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + "\n...[output truncated]"
            return f"Exit code: {result.returncode}\n\n{output}"
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            return f"Command timed out.\n{partial[-MAX_OUTPUT:]}"
    raise ValueError("Supported operations: list, read, write, run.")

def process_issue(token, repo, root, issue):
    if not issue.get("title", "").startswith(PREFIX) or issue.get("pull_request"):
        return False
    try:
        task = json.loads(issue.get("body") or "")
        result = run_task(root, task)
        message = "### Termux agent result\n\n~~~text\n" + result[:MAX_OUTPUT] + "\n~~~"
    except Exception as exc:
        message = "### Termux agent error\n\n" + str(exc)[:3000]
    number = issue["number"]
    api(token, "POST", f"/repos/{repo}/issues/{number}/comments", {"body": message})
    api(token, "PATCH", f"/repos/{repo}/issues/{number}", {"state": "closed"})
    print(f"Processed issue #{number}: {issue.get('title','')}", flush=True)
    return True

def main():
    parser = argparse.ArgumentParser(description="Poll a private GitHub repository for Termux tasks.")
    parser.add_argument("--workspace", required=True, help="Project directory the agent may work inside.")
    parser.add_argument("--repo", default=os.environ.get("TERMUX_AGENT_REPO", ""), help="owner/repository")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("TERMUX_AGENT_TOKEN", "")
    if not token or not args.repo or "/" not in args.repo:
        parser.error("Set TERMUX_AGENT_TOKEN and provide --repo owner/repository.")
    root = Path(args.workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    print(f"Termux agent ready. Workspace: {root}; repository: {args.repo}", flush=True)
    while True:
        try:
            issues = api(token, "GET", f"/repos/{args.repo}/issues?state=open&per_page=50")
            for issue in issues:
                process_issue(token, args.repo, root, issue)
        except KeyboardInterrupt:
            print("Stopped.", flush=True)
            return
        except Exception as exc:
            print(f"Polling error: {exc}", file=sys.stderr, flush=True)
        if args.once:
            return
        time.sleep(max(args.interval, 15))

if __name__ == "__main__":
    main()
