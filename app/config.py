import os


def upstream_base() -> str:
    return os.environ.get("FX_UPSTREAM_BASE", "https://api.frankfurter.dev").rstrip("/")
