import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_ussd_menu_logic():
    out = subprocess.run(["node", "web/ussd.test.js"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
