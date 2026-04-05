import os


is_debug = bool(os.environ.get("DEBUG", ""))


def print_debug(*args, debug_name="", **kwargs):
    if not is_debug:
        return

    debug_header = "=== DEBUG ==="
    if debug_name:
        debug_header = f"=== DEBUG {debug_name} ==="

    print(debug_header)
    print(*args, **kwargs)
    print("=" * len(debug_header))
