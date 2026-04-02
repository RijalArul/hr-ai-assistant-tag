import discord
from discord.ext import commands

from bot.core.config import get_settings

settings = get_settings()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"[BOT] Logged in as {bot.user} (ID: {bot.user.id})")


def main() -> None:
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
