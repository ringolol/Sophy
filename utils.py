import difflib
import functools
import enum


class SupportedModels(enum.Enum):
    qwen_3_5_35b_a3b = "qwen3.5:35b-a3b"
    glm_4_7_flash_30b = "glm-4.7-flash"


class ToolDeniedException(BaseException):
    pass


def confirm(fn):
    """Confirmation decorator"""

    @functools.wraps(fn)
    def guarded_fn(*args, **kwargs):
        print(f"\n--- Agent wants to run: {fn.__name__} ---")
        if fn.__name__ == "write_file":
            path = kwargs.get("file_path", "")
            content = kwargs.get("content", "")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old_lines = f.readlines()
            except FileNotFoundError:
                old_lines = []
            diff = "".join(difflib.unified_diff(
                old_lines, content.splitlines(keepends=True),
                fromfile=f"a/{path}", tofile=f"b/{path}",
            ))
            if diff:
                for line in diff.splitlines():
                    if line.startswith("+"):
                        print(f"\033[32m{line}\033[0m")
                    elif line.startswith("-"):
                        print(f"\033[31m{line}\033[0m")
                    elif line.startswith("@@"):
                        print(f"\033[90m{line}\033[0m")
                    else:
                        print(line)
            else:
                print(f"(new file: {path})")
        else:
            print(f"Args: {kwargs}")
        while (answer := input("Allow? [y/n]: ").strip().lower()) not in ("y", "n"):
            pass
        if answer != "y":
            raise ToolDeniedException("User denied the last tool execution. Be attentive User may ask you to explain or change something about the last task!")
        return fn(*args, **kwargs)

    return guarded_fn