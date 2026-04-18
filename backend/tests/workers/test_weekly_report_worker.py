from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
import pytest
from app.workers.weekly_report_worker import _seconds_until_next_report

ICT = timezone(timedelta(hours=7))


def test_seconds_until_next_report_is_positive():
    secs = _seconds_until_next_report()
    assert secs > 0


def test_seconds_until_next_report_at_most_one_week():
    secs = _seconds_until_next_report()
    assert secs <= 7 * 24 * 3600


@patch('app.workers.weekly_report_worker.datetime')
def test_seconds_skips_to_next_week_if_already_past_monday_8am(mock_dt):
    # Simulate Monday 9 AM ICT — should skip to NEXT Monday
    monday_9am = datetime(2026, 4, 20, 9, 0, 0, tzinfo=ICT)  # Monday
    mock_dt.now.return_value = monday_9am
    secs = _seconds_until_next_report()
    assert secs > 6 * 24 * 3600  # at least 6 days away


@patch('app.workers.weekly_report_worker.datetime')
def test_seconds_fires_same_day_if_before_8am_monday(mock_dt):
    # Simulate Monday 7 AM ICT — should fire same day
    monday_7am = datetime(2026, 4, 20, 7, 0, 0, tzinfo=ICT)
    mock_dt.now.return_value = monday_7am
    secs = _seconds_until_next_report()
    assert secs < 2 * 3600  # less than 2 hours
