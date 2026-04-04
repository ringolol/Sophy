import os


is_debug = bool(os.environ.get("DEBUG", ""))


def print_debug(*args, **kwargs):
    if not is_debug:
        return
    print("=== DEBUG ===")
    print(*args, **kwargs)
    print("=============")
