import asyncio
from pathlib import Path
import importlib.util
import json

import discord
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def load_migration_module():
    script_path = BASE_DIR / "scripts" / "migrate_projects_to_forum.py"
    spec = importlib.util.spec_from_file_location("migrate_projects_to_forum", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = load_migration_module()
VIDEO_LINKS_PATH = BASE_DIR / "data" / "project-video-links.json"


def build_video_replies(videos: list[dict]) -> list[str]:
    if not videos:
        return []

    intro_lines = [
        "These are the original Discord video attachments from the source channel.",
        "They are linked here because some of them were too large to restore directly into the title post.",
    ]
    entry_lines = [f"{index}. {item.get('filename', f'video-{index}')}\n{item.get('url', '')}" for index, item in enumerate(videos, start=1)]
    messages: list[str] = []
    current = "**Original Video Links**\n\n" + "\n".join(intro_lines)

    for entry in entry_lines:
        proposal = current + "\n\n" + entry
        if len(proposal) <= 2000:
            current = proposal
            continue

        messages.append(current)
        current = "**Original Video Links (continued)**\n\n" + entry

    messages.append(current)
    return messages


def post_video_links() -> None:
    class VideoLinkClient(discord.Client):
        async def on_ready(self) -> None:
            guild = self.get_guild(module.GUILD_ID)
            if guild is None:
                raise RuntimeError(f"Guild {module.GUILD_ID} not found")

            state = module.load_state()
            video_links = json.loads(VIDEO_LINKS_PATH.read_text(encoding="utf-8"))
            posted = 0
            updated = 0
            skipped = 0

            for spec in module.PROJECTS:
                videos = video_links.get(spec.slug, [])
                if not videos:
                    skipped += 1
                    continue

                entry = state.get(spec.slug)
                if not entry:
                    skipped += 1
                    continue

                thread = guild.get_thread(entry["thread_id"])
                if thread is None:
                    try:
                        thread = await guild.fetch_channel(entry["thread_id"])
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        print(f"Skipping {spec.slug}: thread not found")
                        continue

                if not isinstance(thread, discord.Thread):
                    print(f"Skipping {spec.slug}: target is not a thread")
                    continue

                contents = build_video_replies(videos)
                if not contents:
                    skipped += 1
                    continue

                existing_messages: list[discord.Message] = []
                known_ids = entry.get("video_links_message_ids") or []
                if not known_ids and entry.get("video_links_message_id"):
                    known_ids = [entry["video_links_message_id"]]

                for message_id in known_ids:
                    try:
                        existing_messages.append(await thread.fetch_message(message_id))
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        continue

                if not existing_messages:
                    async for message in thread.history(limit=20, oldest_first=True):
                        if message.author.id == self.user.id and message.content.startswith("**Original Video Links"):
                            existing_messages.append(message)

                saved_ids: list[int] = []
                for index, content in enumerate(contents):
                    if index < len(existing_messages):
                        message = existing_messages[index]
                        await message.edit(content=content)
                        updated += 1
                    else:
                        message = await thread.send(content)
                        posted += 1

                    saved_ids.append(message.id)
                    await asyncio.sleep(1)

                for extra_message in existing_messages[len(contents):]:
                    try:
                        await extra_message.delete()
                    except (discord.Forbidden, discord.HTTPException):
                        pass

                entry["video_links_message_id"] = saved_ids[0]
                entry["video_links_message_ids"] = saved_ids
                module.save_state(state)
                print(f"Synced video links for {spec.title} ({len(saved_ids)} message(s))")

            print(f"Done. posted={posted} updated={updated} skipped={skipped}")
            await self.close()

    intents = discord.Intents.none()
    intents.guilds = True
    client = VideoLinkClient(intents=intents)
    client.run(module.TOKEN, log_handler=None)


if __name__ == "__main__":
    post_video_links()
