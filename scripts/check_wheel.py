"""Smoke-test an installed wheel in an isolated process without Home Assistant."""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    wheel = Path(sys.argv[1]).resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "vallox_digit_s/py.typed" in names
        assert not any(
            name.startswith(("custom_components/", "homeassistant/")) for name in names
        )
    with tempfile.TemporaryDirectory() as target:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                target,
                str(wheel),
            ],
            check=True,
        )
        script = (
            "import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); "
            "from vallox_digit_s import Client, AsyncClient, __version__; "
            "assert not any(x.startswith('homeassistant') for x in sys.modules); "
            "c=Client('socket://example.invalid:8899'); "
            "assert c.status.state == 'unavailable'; c.close(); "
            "sys.argv=['vallox-digit-s', '--help']; "
            "runpy.run_module('vallox_digit_s',run_name='__main__')"
        )
        subprocess.run([sys.executable, "-I", "-c", script, target], check=True)


if __name__ == "__main__":
    main()
