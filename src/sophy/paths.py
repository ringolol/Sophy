import os
import re

def get_sophy_base_dir() -> str:
    """Returns the base directory for sophy (~/.sophy)."""
    return os.path.expanduser("~/.sophy")

def get_config_path() -> str:
    """Returns the path to the config, checking project-level first, then user-level."""
    project_config = ".sophy/config.json"
    user_config = os.path.join(get_sophy_base_dir(), "config.json")
    return project_config if os.path.isfile(project_config) else user_config

def get_session_dir() -> str:
    """Returns the project-level sessions directory."""
    return os.path.join(".sophy", "sessions")

def get_all_session_dirs() -> list[str]:
    """Returns a list of all relevant session directories (project and user-specific)."""
    dirs = [get_session_dir()]
    abs_path = os.path.abspath(os.getcwd())
    proj_path_str = re.sub(r'[^a-zA-Z0-9]', '_', abs_path)
    user_session_dir = os.path.join(get_sophy_base_dir(), "sessions", proj_path_str)
    dirs.append(user_session_dir)
    return dirs
