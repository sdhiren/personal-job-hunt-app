import pytest

from jobhunt.claude_backend import usage_limit_from


@pytest.mark.parametrize(
    ("message", "reason", "resets"),
    [
        (
            "You've hit your session limit · resets 5:10pm (Asia/Calcutta)",
            "You've hit your session limit",
            "5:10pm (Asia/Calcutta)",
        ),
        (
            "You've hit your weekly limit · resets Oct 9, 4pm (Asia/Calcutta)",
            "You've hit your weekly limit",
            "Oct 9, 4pm (Asia/Calcutta)",
        ),
        ("You're out of extra usage", "You're out of extra usage", None),
    ],
)
def test_recognises_limit_messages(message, reason, resets):
    limit = usage_limit_from(message)
    assert limit is not None
    assert (limit.reason, limit.resets) == (reason, resets)


def test_epoch_format_has_a_reset_time():
    limit = usage_limit_from("Claude AI usage limit reached|1759411200")
    assert limit.reason == "Claude AI usage limit reached"
    assert limit.resets


def test_other_errors_are_not_limits():
    assert usage_limit_from("Claude Code timed out") is None
