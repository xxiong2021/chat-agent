import asyncio
from types import SimpleNamespace

from app.channels import telegram


def test_telegram_ignores_updates_without_effective_user():
    update = SimpleNamespace(
        effective_user=None,
        message=SimpleNamespace(text="channel message"),
    )

    assert asyncio.run(telegram.reply_agent(update, None)) is None
