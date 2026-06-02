from __future__ import annotations

import platform
import sys


def main() -> int:
    try:
        import apsw
    except Exception as exc:
        print(f"apsw import failed: {exc}", file=sys.stderr)
        return 1

    try:
        import sqlite_vec
    except Exception as exc:
        print(f"sqlite_vec import failed: {exc}", file=sys.stderr)
        return 1

    conn = apsw.Connection(":memory:")
    try:
        conn.enable_load_extension(True)
        conn.load_extension(sqlite_vec.loadable_path())
        conn.enable_load_extension(False)
    except Exception as exc:
        print("sqlite-vec runtime check failed", file=sys.stderr)
        print(f"python: {sys.executable}", file=sys.stderr)
        print(f"platform: {platform.platform()}", file=sys.stderr)
        print(f"apsw: {getattr(apsw, '__file__', '')}", file=sys.stderr)
        print(f"sqlite_vec: {getattr(sqlite_vec, '__file__', '')}", file=sys.stderr)
        print(f"sqlite_vec_loadable: {sqlite_vec.loadable_path()}", file=sys.stderr)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print("sqlite-vec runtime check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
