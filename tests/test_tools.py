import os
import re
import pytest
from unittest.mock import patch, MagicMock
from sophy.tools.tools import (
    get_conversation_history,
    read_file,
    write_new_file,
    search_files,
    search_content,
    run_command,
    edit_file,
    ask_user,
    list_directory,
    get_tree,
    delete_file,
    move_file,
    execute_python,
    explorer,
    web_search,
    visit_webpage,
    final_answer,
    TOOLS,
    EXPLORATION_TOOLS,
    SUB_AGENTS,
)
from sophy.tools.guards import is_compound_command, set_guard_config, ToolDeniedException, confirm, path_expand


def test_is_compound_command():
    assert is_compound_command("ls") is False
    assert is_compound_command("echo hello") is False
    assert is_compound_command("ls && pwd") is True
    assert is_compound_command("ls ; pwd") is True
    assert is_compound_command("ls | grep foo") is True
    assert is_compound_command("echo $(date)") is True


def test_get_conversation_history():
    # Test when no history provider is configured
    res = get_conversation_history(5)
    assert res == "No history provider configured."

    # Test with history provider
    with patch("sophy.tools.tools.get_history_provider") as mock_get_provider:
        mock_provider = MagicMock(return_value="mocked history")
        mock_get_provider.return_value = mock_provider
        res = get_conversation_history(3)
        assert res == "mocked history"
        mock_provider.assert_called_once_with(3)


def test_read_file(tmp_path):
    p = tmp_path / "hello.txt"
    p.write_text("hello world", encoding="utf-8")
    
    content = read_file(str(p))
    assert content == "hello world"


def test_write_new_file(tmp_path):
    p = tmp_path / "new_file.txt"
    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res = write_new_file(str(p), "test content")
    assert "Written" in res
    assert p.read_text(encoding="utf-8") == "test content"

    # Test updating existing file
    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res2 = write_new_file(str(p), "updated content")
    assert "Written" in res2
    assert p.read_text(encoding="utf-8") == "updated content"


def test_search_files(tmp_path):
    (tmp_path / "a.py").write_text("print(1)")
    (tmp_path / "b.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("print(2)")

    res = search_files("*.py", str(tmp_path))
    assert "a.py" in res

    res_none = search_files("nonexistent.*", str(tmp_path))
    assert res_none == "No files found."


def test_search_content(tmp_path):
    (tmp_path / "file1.txt").write_text("apple banana\ncherry date")
    (tmp_path / "file2.py").write_text("banana cream")

    res = search_content("banana", str(tmp_path))
    assert "file1.txt" in res
    assert "file2.py" in res

    res_none = search_content("nonexistent_term", str(tmp_path))
    assert res_none == "No matches found."

    # Test invalid regex handling fallback to escape
    res_regex = search_content("[invalid", str(tmp_path))
    assert res_regex == "No matches found."


def test_run_command():
    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res = run_command("python --version")
    assert "Python" in res or "(no output)" in res


def test_edit_file(tmp_path):
    p = tmp_path / "edit.txt"
    p.write_text("line one\nline two\nline three", encoding="utf-8")

    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res = edit_file(str(p), "line two", "line replacement")
    assert "Edited" in res
    assert "line replacement" in p.read_text(encoding="utf-8")

    # Error cases
    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res_not_found = edit_file(str(p), "nonexistent", "new")
    assert "Error: old_content not found" in res_not_found

    p.write_text("duplicate\nduplicate", encoding="utf-8")
    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res_multiple = edit_file(str(p), "duplicate", "new")
    assert "Error: old_content matches" in res_multiple


def test_list_directory(tmp_path):
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "dir1").mkdir()

    res = list_directory(str(tmp_path))
    assert "file.txt" in res
    assert "dir1" in res

    res_err = list_directory(str(tmp_path / "nonexistent"))
    assert "does not exist" in res_err


def test_get_tree(tmp_path):
    (tmp_path / "file.txt").write_text("content")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "subfile.txt").write_text("subcontent")

    res = get_tree(str(tmp_path))
    assert "file.txt" in res
    assert "sub/" in res
    assert "subfile.txt" in res

    # Test get_tree truncation when entries > max_entries
    large_dir = tmp_path / "large"
    large_dir.mkdir()
    # Create 35 files and 5 subdirs (total 40 entries)
    for i in range(35):
        (large_dir / f"file_{i:02d}.txt").write_text("data")
    for i in range(5):
        (large_dir / f"subdir_{i}").mkdir()

    res_large = get_tree(str(tmp_path), max_entries=10)
    assert "... and" in res_large
    assert "more files" in res_large
    assert "more directories" in res_large


def test_delete_file(tmp_path):
    p = tmp_path / "todelete.txt"
    p.write_text("delete me")

    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res = delete_file(str(p))
    assert "Deleted file" in res
    assert not p.exists()

    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res_err = delete_file(str(tmp_path / "nonexistent.txt"))
    assert "not found" in res_err


def test_move_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("move me")
    dst = tmp_path / "dest" / "dst.txt"

    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res = move_file(str(src), str(dst))
    assert "Moved" in res
    assert not src.exists()
    assert dst.read_text() == "move me"

    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res_err = move_file(str(tmp_path / "nonexistent.txt"), str(dst))
    assert "not found" in res_err


def test_execute_python():
    res = execute_python("print('hello python')")
    assert "hello python" in res

    # Test fallback to dangerous python interpreter on exception or syntax error
    with patch("sophy.tools.guards._can_auto_approve", return_value=True):
        res_err = execute_python("1 / 0")
    assert "division by zero" in res_err or "ZeroDivisionError" in res_err


def test_explorer():
    assert explorer("some task") == ""


def test_default_tools_and_collections():
    assert web_search is not None
    assert visit_webpage is not None
    assert final_answer is not None
    assert len(TOOLS) > 0
    assert len(EXPLORATION_TOOLS) > 0
    assert len(SUB_AGENTS) > 0


def test_ask_user(tmp_path):
    with patch("sophy.interface.base.get_frontend") as mock_get_frontend:
        mock_frontend = MagicMock()
        mock_frontend.get_input_sync.return_value = "user response"
        mock_get_frontend.return_value = mock_frontend

        res = ask_user("What is your name?")
        assert res == "user response"


def test_guards(tmp_path):
    class GuardConfig:
        allow_all_edits = True
        project_dir = str(tmp_path)
        allowed_command_patterns = [re.compile(r"^python\s+.*$")]

    set_guard_config(GuardConfig())

    # Test auto approve edit
    p = tmp_path / "guarded.txt"
    with patch("sophy.interface.base.get_frontend") as mock_frontend:
        res = write_new_file(str(p), "guarded content")
        assert "Written" in res

    # Test auto approve command
    with patch("sophy.interface.base.get_frontend") as mock_frontend:
        res_cmd = run_command("python --version")
        assert "Python" in res_cmd or "(no output)" in res_cmd

    # Test denial when guard config doesn't match and user declines prompt
    set_guard_config(None)
    with patch("sophy.interface.base.get_frontend") as mock_frontend:
        mock_frontend.return_value.prompt_confirm_sync.return_value = False
        with pytest.raises(ToolDeniedException):
            delete_file(str(p))

    # Test acceptance when user confirms prompt
    with patch("sophy.interface.base.get_frontend") as mock_frontend:
        mock_frontend.return_value.prompt_confirm_sync.return_value = True
        res_del = delete_file(str(p))
        assert "Deleted file" in res_del
