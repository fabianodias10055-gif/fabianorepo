import asyncio
import csv
import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import discord
from discord import app_commands
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data"
TESTIMONIALS_PATH = OUTPUT_DIR / "testimonials.json"
MESSAGE_LINK_RE = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)"
)
CHANNEL_LINK_RE = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)(?:/(\d+))?"
)

load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
MAX_MESSAGES_PER_CHANNEL = int(os.getenv("MAX_MESSAGES_PER_CHANNEL", "250"))
PROJECTS_FORUM_CHANNEL_ID = os.getenv("PROJECTS_FORUM_CHANNEL_ID")
CREATOR_ALIASES = tuple(
    alias.strip().lower()
    for alias in os.getenv("CREATOR_ALIASES", "locodev,locodevbot,loco").split(",")
    if alias.strip()
)
OUTPUT_DIR.mkdir(exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord-feedback-bot")

