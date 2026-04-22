"""
shell.ssz — process launching (used for sszReload in ikemen.ssz).

The real engine uses this to relaunch itself:
  sh.open(exe, args, workdir, wait, show_window)
"""
import subprocess
import sys
import os


def _open(exe="", args="", workdir="", wait=False, show=True) -> int:
    """Launch a process. Returns PID or 0 on failure."""
    try:
        exe_str  = str(exe)  if exe  else sys.executable
        args_str = str(args) if args else ""
        cwd_str  = str(workdir) if workdir else None

        cmd = [exe_str]
        if args_str:
            cmd += args_str.split()

        proc = subprocess.Popen(
            cmd,
            cwd=cwd_str,
            creationflags=0,
        )
        if wait:
            proc.wait()
        return proc.pid
    except Exception as e:
        print(f"[ssz/shell] open failed: {e}", file=sys.stderr)
        return 0


def register(env, interpreter) -> None:
    env.define("open", _open)
