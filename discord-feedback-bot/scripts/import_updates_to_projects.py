import asyncio
import importlib.util
import json
import re
from pathlib import Path

import discord
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

IMPORT_STATE_PATH = BASE_DIR / "data" / "updates-import-state.json"
SOURCE_DUMP_PATH = BASE_DIR / "data" / "updates-channel-messages.json"
SOURCE_CHANNEL_ID = 1158417344050237472


def load_migration_module():
    script_path = BASE_DIR / "scripts" / "migrate_projects_to_forum.py"
    spec = importlib.util.spec_from_file_location("migrate_projects_to_forum", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = load_migration_module()


RULES: list[tuple[str, list[str]]] = [
    ("vault-mantle-system", [r"\bvault\b", r"\bmantle\b"]),
    ("grapple-hook-system", [r"grapple hook"]),
    ("rope-system", [r"rope locomotion", r"chain, cable and rope", r"\brope\b"]),
    ("wall-run-system", [r"wall run", r"wall-run"]),
    ("punch-combat-system", [r"punch combat", r"\bpunch\b"]),
    ("hostage-system", [r"\bhostage\b"]),
    ("hang-to-swing-system", [r"hang to swing", r"hang and swing", r"bar hang and swing"]),
    ("climb-wall-system", [r"climb wall"]),
    ("jump-prediction", [r"jump based on speed", r"jump prediction"]),
    ("start-to-walk-system", [r"start to walk", r"start to run", r"stand to run", r"walk to stop", r"directional start walk"]),
    ("root-motion-loco", [r"root motion locomotion"]),
    ("pivot-turn-system", [r"\bpivot\b"]),
    ("narrow-system", [r"\bnarrow\b"]),
    ("weapon-system", [r"weapon pickup", r"\bweapon\b", r"holster", r"unholster", r"inventory system"]),
    ("ragdoll-system", [r"\bragdoll\b"]),
    ("telekinesis-system", [r"telekinesis"]),
    ("ladder-system", [r"\bladder\b"]),
    ("zipline-system", [r"\bzipline\b"]),
    ("grapple-system", [r"\bgrapple\b"]),
    ("ledge-climb-system", [r"\bledge\b"]),
    ("devlog-gasp-als", [r"\bgasp\b", r"\bals\b"]),
]

MANUAL_IMPORTS: dict[str, str] = {
    "1480337303229431871": "ledge-climb-system",
}


def load_import_state() -> dict:
    if not IMPORT_STATE_PATH.exists():
        return {}
    return json.loads(IMPORT_STATE_PATH.read_text(encoding="utf-8"))


def save_import_state(state: dict) -> None:
    IMPORT_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


def load_dump() -> list[dict]:
    return json.loads(SOURCE_DUMP_PATH.read_text(encoding="utf-8"))


def pick_slug(message: dict) -> str | None:
    message_id = str(message["id"])
    if message_id in MANUAL_IMPORTS:
        return MANUAL_IMPORTS[message_id]

    text = (message.get("content") or "") + " " + " ".join(att.get("filename", "") for att in message.get("attachments", []))
    haystack = text.lower()

    for slug, patterns in RULES:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return slug

    return None


def build_message_content(source_message: discord.Message, slug: str, fallback_urls: list[str]) -> str:
    source_url = f"https://discord.com/channels/{module.GUILD_ID}/{SOURCE_CHANNEL_ID}/{source_message.id}"
    body = (source_message.content or "").strip()
    lines = [
        "**Updates Import**",
        f"Imported from <#{SOURCE_CHANNEL_ID}> into `{slug}`.",
        f"Original message: {source_url}",
    ]

    if body:
        lines.extend(["", body])

    if fallback_urls:
        lines.extend(["", "**Original Attachment Links**"])
        lines.extend(fallback_urls)

    return "\n".join(lines)[:1900]


async def collect_files(message: discord.Message, max_size: int) -> tuple[list[discord.File], list[str]]:
    files: list[discord.File] = []
    fallback_urls: list[str] = []

    for attachment in message.attachments[:10]:
        if attachment.size > max_size:
            fallback_urls.append(attachment.url)
            continue

        try:
            files.append(await attachment.to_file(use_cached=True))
        except discord.HTTPException:
            fallback_urls.append(attachment.url)

    return files, fallback_urls


def import_updates() -> None:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True

    class ImportClient(discord.Client):
        async def on_ready(self) -> None:
            guild = self.get_guild(module.GUILD_ID)
            if guild is None:
                raise RuntimeError(f"Guild {module.GUILD_ID} not found")

            source_channel = guild.get_channel(SOURCE_CHANNEL_ID)
            if not isinstance(source_channel, discord.TextChannel):
                raise RuntimeError(f"Source channel {SOURCE_CHANNEL_ID} not found")

            dump = load_dump()
            migration_state = module.load_state()
            import_state = load_import_state()
            posted = 0
            skipped = 0

            for source in reversed(dump):
                if source.get("author", {}).get("username", "").lower() != "locodev":
                    continue
                if not source.get("attachments"):
                    continue

                source_key = str(source["id"])
                if source_key in import_state:
                    skipped += 1
                    continue

                slug = pick_slug(source)
                if not slug:
                    skipped += 1
                    continue

                entry = migration_state.get(slug)
                if not entry:
                    skipped += 1
                    continue

                thread = guild.get_thread(entry["thread_id"])
                if thread is None:
                    try:
                        thread = await guild.fetch_channel(entry["thread_id"])
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        skipped += 1
                        continue

                if not isinstance(thread, discord.Thread):
                    skipped += 1
                    continue

                try:
                    source_message = await source_channel.fetch_message(source["id"])
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    skipped += 1
                    continue

                files, fallback_urls = await collect_files(source_message, guild.filesize_limit)
                content = build_message_content(source_message, slug, fallback_urls)

                try:
                    sent = await thread.send(content=content, files=files, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    skipped += 1
                    continue

                import_state[source_key] = {
                    "slug": slug,
                    "thread_id": thread.id,
                    "reply_message_id": sent.id,
                }
                save_import_state(import_state)
                posted += 1
                print(f"Imported {source_key} -> {slug}")
                await asyncio.sleep(1)

            print(f"Updates import complete. posted={posted} skipped={skipped}")
            await self.close()

    client = ImportClient(intents=intents)
    client.run(module.TOKEN, log_handler=None)


if __name__ == "__main__":
    import_updates()
