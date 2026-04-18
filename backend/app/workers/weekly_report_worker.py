from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta

from app.services.weekly_report_service import send_weekly_reports

ICT = timezone(timedelta(hours=7))
REPORT_WEEKDAY = 0   # Monday
REPORT_HOUR = 8
REPORT_MINUTE = 0


def _seconds_until_next_report() -> float:
    now = datetime.now(ICT)
    days_ahead = (REPORT_WEEKDAY - now.weekday()) % 7
    if days_ahead == 0 and (now.hour, now.minute) >= (REPORT_HOUR, REPORT_MINUTE):
        days_ahead = 7
    target = (now + timedelta(days=days_ahead)).replace(
        hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0
    )
    return (target - now).total_seconds()


async def weekly_report_worker() -> None:
    """Send a weekly P&L summary to all Telegram-connected users every Monday at 8 AM ICT."""
    while True:
        secs = _seconds_until_next_report()
        next_run = datetime.now(ICT) + timedelta(seconds=secs)
        print(f'[weekly_report] next run at {next_run.strftime("%A %Y-%m-%d %H:%M")} ICT '
              f'(in {secs / 3600:.1f}h)')
        await asyncio.sleep(secs)
        try:
            sent = await send_weekly_reports()
            print(f'[weekly_report] done — {sent} reports sent')
        except Exception as e:
            print(f'[weekly_report] error: {e}')
