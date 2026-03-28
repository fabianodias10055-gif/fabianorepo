import asyncio
import importlib.util
import json
from pathlib import Path

import discord
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

IMPORT_STATE_PATH = BASE_DIR / "data" / "random-coding-import-state.json"
SOURCE_CHANNEL_ID = 1166774647749087313


def load_migration_module():
    script_path = BASE_DIR / "scripts" / "migrate_projects_to_forum.py"
    spec = importlib.util.spec_from_file_location("migrate_projects_to_forum", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = load_migration_module()


def load_import_state() -> dict:
    if not IMPORT_STATE_PATH.exists():
        return {}
    return json.loads(IMPORT_STATE_PATH.read_text(encoding="utf-8"))


def save_import_state(state: dict) -> None:
    IMPORT_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


IMPORTS: list[dict] = [
    {"slug": "ledge-climb-system", "message_id": 1482450427650900171, "label": "LedgeSandboxCMCREF"},
    {"slug": "ledge-climb-system", "message_id": 1482083019471720448, "label": "Run Traversal Detection"},
    {"slug": "ledge-climb-system", "message_id": 1480551361904115866, "label": "AddLedgeObjectType.bat"},
    {"slug": "ledge-climb-system", "message_id": 1478531198807572480, "label": "Execution flow of custom timelines"},
    {"slug": "ledge-climb-system", "message_id": 1478530965440565359, "label": "LDLedgeComponent.h"},
    {"slug": "ledge-climb-system", "message_id": 1478530909463642253, "label": "LDLedgeComponent.cpp"},
    {"slug": "ledge-climb-system", "message_id": 1474444259850715161, "label": "Ledge Trace Detection"},
    {"slug": "ledge-climb-system", "message_id": 1408517103056846972, "label": "Ledge System - Backup"},
    {"slug": "ledge-climb-system", "message_id": 1250240017855676516, "label": "Height detection traces"},
    {"slug": "ledge-climb-system", "message_id": 1234845822005284914, "label": "Surface-normal forward trace"},
    {"slug": "ledge-climb-system", "message_id": 1201960623857213470, "label": "Set variables from trace hit result"},
    {"slug": "narrow-system", "message_id": 1486807420293349517, "label": "Hand Sensing Trace Positioning"},
    {"slug": "ragdoll-system", "message_id": 1486802601168339097, "label": "Update Physics Blend Weight only on arms"},
    {"slug": "narrow-system", "message_id": 1463259283461374093, "label": "IK for hands narrow system 1-20"},
    {"slug": "narrow-system", "message_id": 1462866312173977721, "label": "ABP_AnimGraph"},
    {"slug": "narrow-system", "message_id": 1462866284483186913, "label": "ABP_EventGraph"},
    {"slug": "narrow-system", "message_id": 1462866175712170046, "label": "Narrow system blueprint dump"},
    {"slug": "narrow-system", "message_id": 1462805932915560614, "label": "HandSenseTrace"},
    {"slug": "narrow-system", "message_id": 1462803705257656340, "label": "Narrow system timeline setup"},
    {"slug": "narrow-system", "message_id": 1456136124052541660, "label": "Narrow Direction Change"},
    {"slug": "weapon-system", "message_id": 1408454134960619614, "label": "Holster / Unholster Graph Backup Logic"},
    {"slug": "devlog-gasp-als", "message_id": 1461434012059959452, "label": "GASP 5.7 mesh wall-glitch fix"},
]


def build_message_content(import_item: dict, source_message: discord.Message) -> str:
    source_url = f"https://discord.com/channels/{module.GUILD_ID}/{SOURCE_CHANNEL_ID}/{source_message.id}"
    body = (source_message.content or "").strip()

    lines = [
        "**Random Coding Import**",
        f"Imported from <#{SOURCE_CHANNEL_ID}> for `{import_item['label']}`.",
        f"Original message: {source_url}",
    ]

    if body:
        lines.extend(["", body])

    return "\n".join(lines)[:1900]


async def collect_files(message: discord.Message) -> list[discord.File]:
    files: list[discord.File] = []
    for attachment in message.attachments[:10]:
        try:
            files.append(await attachment.to_file(use_cached=True))
        except discord.HTTPException:
            continue
    return files


def import_random_coding() -> None:
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

            migration_state = module.load_state()
            import_state = load_import_state()
            posted = 0
            skipped = 0

            for import_item in IMPORTS:
                source_key = str(import_item["message_id"])
                if source_key in import_state:
                    skipped += 1
                    continue

                entry = migration_state.get(import_item["slug"])
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
                    source_message = await source_channel.fetch_message(import_item["message_id"])
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    skipped += 1
                    continue

                files = await collect_files(source_message)
                content = build_message_content(import_item, source_message)
                sent = await thread.send(content=content, files=files, allowed_mentions=discord.AllowedMentions.none())

                import_state[source_key] = {
                    "slug": import_item["slug"],
                    "label": import_item["label"],
                    "thread_id": thread.id,
                    "reply_message_id": sent.id,
                }
                save_import_state(import_state)
                posted += 1
                print(f"Imported {import_item['label']} -> {import_item['slug']}")
                await asyncio.sleep(1)

            print(f"Random coding import complete. posted={posted} skipped={skipped}")
            await self.close()

    client = ImportClient(intents=intents)
    client.run(module.TOKEN, log_handler=None)


if __name__ == "__main__":
    import_random_coding()
