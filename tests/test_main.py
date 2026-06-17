from __future__ import annotations

from src import main as main_module


def test_test_alert_command_does_not_call_foreup(monkeypatch) -> None:
    called = {"slack": False}

    def fail_if_foreup_is_built(config):
        raise AssertionError("ForeUp should not be used by test-alert")

    def fake_send_test_alert(webhook_url, stream):
        called["slack"] = True
        return True

    monkeypatch.setattr(
        main_module.ForeUpBookingTimesFetcher,
        "from_config",
        fail_if_foreup_is_built,
    )
    monkeypatch.setattr(main_module, "send_test_alert", fake_send_test_alert)

    assert main_module.main(["test-alert"]) == 0
    assert called["slack"]
