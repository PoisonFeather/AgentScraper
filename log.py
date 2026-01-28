import os
import textwrap
from datetime import datetime

def ts():
    return datetime.now().strftime("%H:%M:%S")

def trunc(s: str, n: int = 900):
    if s is None:
        return ""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[:n] + f"\n... [truncated {len(s)-n} chars]"

def section(title: str):
    print(f"\n[{ts()}] ===== {title} =====")

def kv(k: str, v):
    print(f"[{ts()}] {k}: {v}")

def block(label: str, content: str, width: int = 120):
    print(f"[{ts()}] -- {label} --")
    wrapped = "\n".join(textwrap.wrap(content, width=width, replace_whitespace=False))
    print(wrapped)

def enabled(name: str, default="0"):
    return os.getenv(name, default) == "1"