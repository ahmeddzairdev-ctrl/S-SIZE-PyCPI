"""
sys.ssz  –  Python implementation of the S-SIZE system library.
Provides system-level utilities: time, args, exit, etc.
"""
import sys
import os
import time as _time
import platform


def register(env, interpreter) -> None:
    env.define("exit",       lambda code=0: sys.exit(int(code)))
    env.define("getArgs",    lambda: sys.argv[1:])
    env.define("getEnv",     lambda k: os.environ.get(str(k), ""))
    env.define("getCwd",     lambda: os.getcwd())
    env.define("sleep",      lambda ms: _time.sleep(float(ms) / 1000.0))
    env.define("timeMs",     lambda: int(_time.time() * 1000))
    env.define("platform",   lambda: platform.system())
    env.define("pythonVer",  lambda: platform.python_version())
    env.define("sszVer",     lambda: "1.0.0-py")
