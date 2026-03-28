from pathlib import Path
import importlib.util

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


def revise_posts() -> None:
    intents = discord.Intents.none()
    intents.guilds = True

    state = module.load_state()

    class RevisionClient(discord.Client):
        async def on_ready(self) -> None:
            guild = self.get_guild(module.GUILD_ID)
            if guild is None:
                raise RuntimeError(f"Guild {module.GUILD_ID} not found")

            revised = 0
            for spec in module.PROJECTS:
                entry = state.get(spec.slug)
                if not entry:
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

                try:
                    starter_message = await thread.fetch_message(entry["message_id"])
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    print(f"Skipping {spec.slug}: starter message not found")
                    continue

                cover_path = Path(entry["cover_path"])
                if not cover_path.exists():
                    cover_path = module.generate_cover(spec)

                body = module.build_post_body(spec)
                source_channel = guild.get_channel(entry["source_channel_id"])
                if not isinstance(source_channel, discord.TextChannel):
                    print(f"Skipping {spec.slug}: source channel not found")
                    continue

                files, skipped_media = await module.collect_starter_media_files(
                    source_channel,
                    cover_path,
                    max_media=module.MAX_STARTER_MEDIA,
                    max_size=guild.filesize_limit,
                )
                await thread.edit(name=spec.title, reason="Revised project post layout")
                await starter_message.edit(
                    content=body,
                    attachments=files,
                )

                entry["restored_media_count"] = max(0, len(files) - 1)
                entry["skipped_media"] = skipped_media
                entry["status"] = "revised"
                revised += 1
                print(f"Revised {spec.title}: {thread.jump_url}")

            module.save_state(state)
            print(f"Revision finished. revised={revised}")
            await self.close()

    client = RevisionClient(intents=intents)
    client.run(module.TOKEN, log_handler=None)


if __name__ == "__main__":
    revise_posts()
