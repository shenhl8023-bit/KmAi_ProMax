# -*- coding: utf-8 -*-
import os

import pytest

from step_viewer import __main__ as cli


def test_cli_uses_loopback_and_can_disable_browser(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs))
    monkeypatch.setenv("STEP_VIEWER_OPEN_BROWSER", "1")

    cli.main(["--port", "9123", "--no-browser"])

    assert captured["args"] == ("step_viewer.app:app",)
    assert captured["kwargs"] == {"host": "127.0.0.1", "port": 9123, "reload": False}
    assert "STEP_VIEWER_OPEN_BROWSER" not in os.environ


def test_cli_sets_browser_environment_for_selected_port(monkeypatch):
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.delenv("STEP_VIEWER_OPEN_BROWSER", raising=False)
    monkeypatch.delenv("STEP_VIEWER_PORT", raising=False)

    cli.main(["--port", "9124"])

    assert os.environ["STEP_VIEWER_OPEN_BROWSER"] == "1"
    assert os.environ["STEP_VIEWER_PORT"] == "9124"


@pytest.mark.parametrize("port", ["0", "65536"])
def test_cli_rejects_invalid_port(port):
    with pytest.raises(SystemExit):
        cli.parse_args(["--port", port])
