import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import discord
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
COVERS_DIR = DATA_DIR / "project-covers"
STATE_PATH = DATA_DIR / "project-migration-state.json"
MAX_STARTER_MEDIA = 9

load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
FORUM_ID = int(os.getenv("PROJECTS_FORUM_CHANNEL_ID", "0"))

COVERS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ProjectSpec:
    slug: str
    channel_id: int
    title: str
    description: str


PROJECTS: list[ProjectSpec] = [
    ProjectSpec("ledge-climb-system", 1220868234052505610, "Ledge Climb System", "Traversal setup for grabbing ledges, climbing up cleanly, and handling ledge-specific movement refinements."),
    ProjectSpec("ragdoll-system", 1327730494053552148, "Ragdoll System", "Physics-driven ragdoll workflow focused on impact reactions, recovery, and common gameplay edge cases."),
    ProjectSpec("pivot-turn-system", 1162231634444157059, "Pivot Turn System", "Responsive turning setup for sharp direction changes, animation timing, and clean pivot transitions."),
    ProjectSpec("hostage-system", 1192236739411058828, "Hostage System", "Interaction system for grabbing, controlling, and animating hostage-style character scenarios."),
    ProjectSpec("start-to-walk-system", 1197547069523640490, "Start To Walk System", "Locomotion startup system for smoother transitions from idle into directional movement."),
    ProjectSpec("hang-to-swing-system", 1201978995424370749, "Hang To Swing System", "Traversal flow for entering a hanging state and transitioning naturally into a swing."),
    ProjectSpec("vault-mantle-system", 1202704123062001695, "Vault Mantle System", "Obstacle traversal setup for vaulting and mantling with tunable distances, height checks, and timing."),
    ProjectSpec("telekinesis-system", 1179900941340782663, "Telekinesis System", "Gameplay system for levitating, moving, and throwing objects with controlled physics interactions."),
    ProjectSpec("grapple-hook-system", 1230527571997753354, "Grapple Hook System", "Hook-based traversal and pull mechanics for fast movement, targeting, and follow-up transitions."),
    ProjectSpec("rope-system", 1237395658458005625, "Rope System", "Interactive rope gameplay focused on rope logic, traversal behavior, and related fixes."),
    ProjectSpec("root-motion-loco", 1236312819062804531, "Root Motion Loco", "Root-motion locomotion setup covering animation sync, blueprint wiring, and movement polish."),
    ProjectSpec("wall-run-system", 1244283248872263750, "Wall Run System", "Wall-running traversal with entry conditions, movement control, and backup logic references."),
    ProjectSpec("jump-prediction", 1246901914239500310, "Jump Prediction", "Prediction workflow for jump outcomes, timing, and movement logic tied to traversal decisions."),
    ProjectSpec("punch-combat-system", 1247249024747044904, "Punch Combat System", "Melee punch combat setup with hit detection, traces, impact handling, and combat tuning."),
    ProjectSpec("grapple-system", 1260640021887582311, "Grapple System", "Character grapple mechanics for interactions, control flow, and movement-connected combat states."),
    ProjectSpec("zipline-system", 1260640440257089618, "Zipline System", "Zipline traversal setup for entering, moving across, and exiting cable-based movement paths."),
    ProjectSpec("climb-wall-system", 1263912856420614205, "Climb Wall System", "Climbable wall traversal workflow with blueprint references, movement checks, and setup notes."),
    ProjectSpec("weapon-system", 1301171314324930610, "Weapon System", "Weapon handling workflow covering setup, shared project files, and multi-weapon discussion points."),
    ProjectSpec("ladder-system", 1324385408846663791, "Ladder System", "Ladder traversal implementation for entering, climbing, and exiting ladder movement states."),
    ProjectSpec("devlog-gasp-als", 1397981080623255735, "Devlog GASP ALS", "Development log for integrating GASP and ALS, including retargeting and animation blueprint notes."),
    ProjectSpec("narrow-system", 1452496538189430784, "Narrow System", "Traversal setup for moving through narrow spaces with hand placement and directional movement logic."),
]


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


def slug_to_palette(slug: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    seed = sum(ord(char) for char in slug)
    base = ((seed * 3) % 70 + 20, (seed * 5) % 80 + 70, (seed * 7) % 90 + 130)
    accent = ((seed * 11) % 90 + 140, (seed * 13) % 80 + 90, (seed * 17) % 70 + 30)
    text = (245, 247, 250)
    return base, accent, text


def pick_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: Iterable[str] = (
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposal = word if not current else f"{current} {word}"
        if draw.textlength(proposal, font=font) <= max_width:
            current = proposal
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_cover(spec: ProjectSpec) -> Path:
    width, height = 1600, 900
    base_color, accent_color, text_color = slug_to_palette(spec.slug)
    image = Image.new("RGB", (width, height), base_color)
    draw = ImageDraw.Draw(image)

    for index in range(height):
        blend = index / max(1, height - 1)
        r = int(base_color[0] * (1 - blend) + 10 * blend)
        g = int(base_color[1] * (1 - blend) + 16 * blend)
        b = int(base_color[2] * (1 - blend) + 24 * blend)
        draw.line([(0, index), (width, index)], fill=(r, g, b))

    draw.rounded_rectangle((70, 70, width - 70, height - 70), radius=42, outline=(255, 255, 255, 35), width=3)
    draw.ellipse((1060, 120, 1480, 540), fill=accent_color)
    draw.ellipse((1130, 210, 1420, 500), fill=(255, 255, 255))
    draw.ellipse((1180, 250, 1380, 450), fill=base_color)
    draw.rounded_rectangle((1040, 580, 1470, 760), radius=28, fill=(12, 18, 28))
    draw.rounded_rectangle((1080, 615, 1430, 725), radius=20, outline=(255, 255, 255), width=3)

    tag_font = pick_font(34, bold=True)
    title_font = pick_font(82, bold=True)
    body_font = pick_font(34, bold=False)
    small_font = pick_font(28, bold=False)

    draw.text((120, 120), "LOCODEV PROJECT", font=tag_font, fill=(238, 242, 247))
    title_lines = wrap_text(draw, spec.title, title_font, 760)
    y = 205
    for line in title_lines:
        draw.text((120, y), line, font=title_font, fill=text_color)
        y += 96

    description_lines = wrap_text(draw, spec.description, body_font, 760)
    y += 10
    for line in description_lines:
        draw.text((120, y), line, font=body_font, fill=(225, 230, 236))
        y += 48

    draw.text((120, 720), "Systems, notes, fixes, and updates", font=small_font, fill=(225, 230, 236))
    draw.text((120, 770), f"Source channel: #{spec.slug}", font=small_font, fill=(200, 208, 216))

    path = COVERS_DIR / f"{spec.slug}.png"
    image.save(path, format="PNG")
    return path


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://\\S+", text)


def attachment_is_media(attachment: discord.Attachment) -> bool:
    if attachment.content_type:
        return attachment.content_type.startswith(("image/", "video/"))

    filename = attachment.filename.lower()
    return filename.endswith(
        (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".bmp",
            ".mp4",
            ".mov",
            ".webm",
            ".m4v",
        )
    )


def build_post_body(spec: ProjectSpec) -> str:
    lines = [
        f"**Overview**",
        spec.description,
        "",
        f"**Original Channel**",
        f"<#{spec.channel_id}>",
        "",
        "**What This Post Is For**",
        f"- Keep the {spec.title.lower()} notes, fixes, and updates in one place.",
        "- Give the project a cleaner forum-style home for future replies and updates.",
        "- Use the title post as the main visual header for the project.",
    ]

    lines.extend(
        [
            "",
            "_This forum post is the main home for the original project channel._",
        ]
    )
    return "\n".join(lines)[:1950]


async def collect_channel_content(channel: discord.TextChannel) -> tuple[list[str], list[str]]:
    highlights: list[str] = []
    urls: list[str] = []
    seen_urls: set[str] = set()

    async for message in channel.history(limit=30, oldest_first=True):
        if message.author.bot:
            continue

        content = " ".join(message.content.split())
        if content:
            if len(content) > 180:
                content = content[:177] + "..."
            highlights.append(content)

        for attachment in message.attachments:
            if attachment.url not in seen_urls:
                seen_urls.add(attachment.url)
                urls.append(attachment.url)

        for url in extract_urls(message.content):
            if url not in seen_urls:
                seen_urls.add(url)
                urls.append(url)

        if len(highlights) >= 4 and len(urls) >= 4:
            break

    return highlights[:4], urls[:4]


async def collect_starter_media_files(
    channel: discord.TextChannel,
    cover_path: Path,
    *,
    max_media: int,
    max_size: int,
) -> tuple[list[discord.File], list[str]]:
    files: list[discord.File] = [discord.File(cover_path, filename=cover_path.name)]
    skipped: list[str] = []
    seen_urls: set[str] = set()
    media_added = 0

    async for message in channel.history(limit=40, oldest_first=True):
        for attachment in message.attachments:
            if media_added >= max_media:
                return files, skipped
            if attachment.url in seen_urls:
                continue
            seen_urls.add(attachment.url)
            if not attachment_is_media(attachment):
                continue
            if attachment.size > max_size:
                skipped.append(f"{attachment.filename} (too large)")
                continue
            try:
                files.append(await attachment.to_file(use_cached=True))
                media_added += 1
            except discord.HTTPException:
                skipped.append(f"{attachment.filename} (download failed)")

    return files, skipped


def create_missing_posts() -> None:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True

    state = load_state()

    class MigrationClient(discord.Client):
        async def on_ready(self) -> None:
            guild = self.get_guild(GUILD_ID)
            if guild is None:
                raise RuntimeError(f"Guild {GUILD_ID} not found")

            forum = guild.get_channel(FORUM_ID)
            if not isinstance(forum, discord.ForumChannel):
                raise RuntimeError(f"Forum channel {FORUM_ID} not found")

            existing_names = {thread.name.lower(): thread.id for thread in forum.threads}
            created = 0
            skipped = 0

            for spec in PROJECTS:
                if spec.slug in state:
                    skipped += 1
                    continue

                if spec.title.lower() in existing_names:
                    state[spec.slug] = {
                        "thread_id": existing_names[spec.title.lower()],
                        "title": spec.title,
                        "status": "preexisting",
                    }
                    skipped += 1
                    continue

                source_channel = guild.get_channel(spec.channel_id)
                if not isinstance(source_channel, discord.TextChannel):
                    print(f"Skipping {spec.slug}: source channel not found")
                    continue

                cover_path = generate_cover(spec)
                body = build_post_body(spec)
                files, skipped_media = await collect_starter_media_files(
                    source_channel,
                    cover_path,
                    max_media=MAX_STARTER_MEDIA,
                    max_size=guild.filesize_limit,
                )

                try:
                    created_thread = await forum.create_thread(
                        name=spec.title,
                        content=body,
                        files=files,
                        reason=f"Migrated from #{source_channel.name}",
                    )
                except discord.HTTPException as exc:
                    print(f"Failed creating {spec.slug}: {exc}")
                    continue

                state[spec.slug] = {
                    "thread_id": created_thread.thread.id,
                    "message_id": created_thread.message.id,
                    "title": spec.title,
                    "source_channel_id": spec.channel_id,
                    "cover_path": str(cover_path),
                    "restored_media_count": max(0, len(files) - 1),
                    "skipped_media": skipped_media,
                    "status": "created",
                }
                save_state(state)
                print(f"Created {spec.title}: {created_thread.thread.jump_url}")
                created += 1
                await asyncio.sleep(1)

            print(f"Migration finished. created={created} skipped={skipped}")
            await self.close()

    client = MigrationClient(intents=intents)
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN in .env")
    if not GUILD_ID:
        raise RuntimeError("Missing DISCORD_GUILD_ID in .env")
    if not FORUM_ID:
        raise RuntimeError("Missing PROJECTS_FORUM_CHANNEL_ID in .env")

    create_missing_posts()
