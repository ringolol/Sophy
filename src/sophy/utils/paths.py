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

def get_user_session_dir() -> str:
    """Returns the project-specific user-level sessions directory."""
    abs_path = os.path.abspath(os.getcwd())
    proj_path_str = re.sub(r'[^a-zA-Z0-9]', '_', abs_path)
    return os.path.join(get_sophy_base_dir(), "sessions", proj_path_str)
