import subprocess
import sys


def test_worker_module_is_a_separate_no_side_effect_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "productpulse.worker"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "worker_entrypoint_ready" in result.stderr
    assert "no job handlers registered" in result.stderr

