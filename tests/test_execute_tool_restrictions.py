from pathlib import Path
from neo.tools.miscellaneous_tools import (
    MAX_TIMEOUT_SECONDS,
    executeTool,
    has_long_running_python_code,
    is_continuous_or_long_running,
)


def test_blocks_detach_and_background_commands():
    assert is_continuous_or_long_running("nohup python app.py")
    assert is_continuous_or_long_running("Start-Process python -ArgumentList app.py")
    assert is_continuous_or_long_running("python app.py &")
    assert not is_continuous_or_long_running("python app.py && echo done")


def test_blocks_long_running_python_scripts(tmp_path: Path):
    loop_script = tmp_path / "loop.py"
    loop_script.write_text("while True:\n    pass\n", encoding="utf-8")
    assert has_long_running_python_code(loop_script) is not None

    res = executeTool(f"python {loop_script}", ask_confirm=False)
    assert "Execution rejected" in res

    sleep_script = tmp_path / "slow.py"
    sleep_script.write_text(f"import time\ntime.sleep({MAX_TIMEOUT_SECONDS + 5})\n", encoding="utf-8")
    assert has_long_running_python_code(sleep_script) is not None


def test_timeout_kills_process_tree(tmp_path: Path):
    # A script that sleeps longer than timeout=1 without triggering static sleep check
    script = tmp_path / "wait.py"
    script.write_text("import time\nt = 3\ntime.sleep(t)\n", encoding="utf-8")

    res = executeTool(f"python {script}", timeout=1, ask_confirm=False)
    assert "timed out after 1 seconds" in res


def test_short_command_succeeds():
    res = executeTool("python -c \"print('ok')\"", ask_confirm=False)
    assert res == "ok"

