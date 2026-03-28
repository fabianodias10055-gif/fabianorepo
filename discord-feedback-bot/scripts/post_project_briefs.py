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


BRIEFS = {
    "ledge-climb-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This setup is focused on making ledge grabs more reliable by checking more than one possible attachment point instead of relying on a single trace hit.",
            "",
            "**Key nodes and logic**",
            "- `Multi Sphere Trace`: checks multiple potential grab points and gives the system more valid ledge options.",
            "- `Delta Rotator`: measures the rotation difference between the current ledge and the target point.",
            "- Corner-selection logic: uses the rotation difference and parameters to decide which corner animation should play.",
            "- Detectable oriented target points: helps define cleaner ledge attachment targets.",
            "",
            "**Why this matters**",
            "The extra trace coverage and rotation checks make transitions between ledges feel more dependable and help the system pick the right climb or cornering animation.",
        ]
    ),
    "ragdoll-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system blends animation-driven motion with live physics so the character can enter a controllable ragdoll state instead of fully collapsing into uncontrolled simulation.",
            "",
            "**Key nodes and logic**",
            "- `Physical Animation Component`: mixes animation pose data with real-time physics.",
            "- Per-bone or body-part simulation tests: examples mention left arm physical animation and fish-out-of-water style behavior.",
            "- Event Tick / runtime control checks: the notes point to conflicts in the GASP project on UE 5.5.",
            "",
            "**Why this matters**",
            "The goal is to get believable impacts and secondary motion without losing all character control. The notes also highlight compatibility issues and crash/glitch debugging when physics is enabled in the wrong execution path.",
        ]
    ),
    "pivot-turn-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system handles responsive pivot turns by triggering a dedicated turn state, playing root-motion animation at the right moment, and then handing control back to runtime movement.",
            "",
            "**Key nodes and logic**",
            "- One-shot trigger boolean in the character blueprint: used to fire the pivot action once and reset immediately.",
            "- `Anim Notify`: used to stop root motion at the correct timing.",
            "- Animation `Curve` and `Get Curve Value`: smoothly drives rotation rate from low to high values during the turn.",
            "- `Set Root Motion Mode -> Ignore Root Motion`: used after the notify so control returns to gameplay code.",
            "- `AnimGraph` transition rules: move in and out of the sprint turn state.",
            "",
            "**Why this matters**",
            "The curve-driven approach makes the pivot feel smoother, while the notify-based root-motion switch prevents the turn from taking control longer than it should.",
        ]
    ),
    "hostage-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system manages aiming, grabbing, controlling, and killing a hostage while coordinating both the player and victim animation states.",
            "",
            "**Key nodes and logic**",
            "- Aim rotation setup: aligns the character with aim direction and toggles aiming state.",
            "- `Hold Event` and `Hold Function Event`: validates hit actors and routes the selected action parameters.",
            "- `BPI_Interact`: passes animation sequence and montage data in a safer, reusable way.",
            "- `BP_VictimChild`: switches animation mode, plays the montage, and can freeze the final pose on the last frame.",
            "- Kill event flow: checks `IsHolding?` and toggles attack state for execution logic.",
            "",
            "**Why this matters**",
            "The interface-based setup keeps the animation handoff cleaner and reduces movement glitches when two characters have to stay synchronized during the hostage interaction.",
        ]
    ),
    "start-to-walk-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This project is focused on smoother locomotion startups, especially the transition from standing still into movement with better directional feel.",
            "",
            "**Key nodes and logic**",
            "- `AnimGraph` and grounded-state backups: used to tune the transition structure.",
            "- Orientation warping references: helps motion direction feel more aligned with where the player intends to move.",
            "",
            "**Why this matters**",
            "Most of the written notes here point to animation graph structure and linked project/tutorial references, so the main idea is improving how the start animation blends into walking rather than snapping into motion.",
        ]
    ),
    "hang-to-swing-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system covers the transition from a hanging state into a swing state, separating movement handling from animation-state handling.",
            "",
            "**Key nodes and logic**",
            "- `Event Graph`: runtime logic entry point.",
            "- `AnimGraph`: manages the animation transitions between hanging and swinging.",
            "- `Movement Mode` macro: likely centralizes state switching for traversal behavior.",
            "- `Set Ledge Trace Results` function: stores or reuses trace data that supports the transition.",
            "",
            "**Why this matters**",
            "The structure suggests the system relies on clear state separation so the physical traversal logic and animation logic do not fight each other during the handoff from hanging to swinging.",
        ]
    ),
    "vault-mantle-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This project uses trace checks and distance logic to decide when the character should vault or mantle over an obstacle and to prevent clipping through geometry.",
            "",
            "**Key nodes and logic**",
            "- `Line Trace`: gathers forward obstacle information.",
            "- `Sphere Trace`: gives broader collision sampling for candidate obstacles.",
            "- Wall-thickness line trace: helps decide whether the obstacle is valid for traversal.",
            "- `Should Vault` collapsed graph: central decision block for whether the move is allowed.",
            "- Distance-to-wall checks and timeline fixes: refine the move path and reduce glitches.",
            "",
            "**Why this matters**",
            "Using multiple traces lets the system validate the obstacle more reliably, while the distance and thickness checks keep the character from incorrectly vaulting through walls.",
        ]
    ),
    "telekinesis-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system is built around interacting with objects such as a cube through a reusable interface instead of hardcoding the interaction directly inside one blueprint.",
            "",
            "**Key nodes and logic**",
            "- `BP_ThirdPersonCharacter`: handles the player-side control logic.",
            "- `BP_Cube`: example target object that receives telekinesis interactions.",
            "- `Blueprint Interface`: used to keep the interaction more optimized and reusable.",
            "- Interface implementation in `Class Settings`: added on both the character and the interactable object.",
            "",
            "**Why this matters**",
            "The interface approach makes it easier to extend telekinesis beyond one cube and reuse the same interaction contract on other actors without rewriting the whole system.",
        ]
    ),
    "grapple-hook-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system finds grapple targets based on where the camera is aiming, then filters the results so the hook prefers the best reachable point near the player.",
            "",
            "**Key nodes and logic**",
            "- `Multi Sphere Trace`: used from the camera direction to detect multiple possible grapple points.",
            "- Closest-point selection logic: picks the most suitable hit near the player.",
            "- Dedicated grapple target actors: can be placed in the level to define valid hook points.",
            "- Visibility response setup on static meshes: prevents the trace from hitting unwanted surfaces.",
            "",
            "**Why this matters**",
            "The main goal is consistency. Multiple candidates plus filtering gives a more reliable grapple system than a single raw trace hit, especially in busy environments.",
        ]
    ),
    "rope-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system is experimenting with rope or chain-style simulation, where collision setup and constraint placement strongly affect how the rope behaves.",
            "",
            "**Key nodes and logic**",
            "- Individual collision shapes on the mesh: used to improve physical interaction per segment.",
            "- `Physics Constraint` placement: controls how the rope anchors and bends.",
            "- Repeated simulation tests: used to tune the anchor point and overall chain behavior.",
            "",
            "**Why this matters**",
            "The notes show that constraint placement changes the physical result a lot, so the system depends on careful setup rather than one magic node doing all the work.",
        ]
    ),
    "root-motion-loco": "\n".join(
        [
            "**System Brief**",
            "",
            "This locomotion system chooses movement starts and direction changes by combining player input with camera rotation, then uses animation curves to drive movement responsiveness.",
            "",
            "**Key nodes and logic**",
            "- Camera rotation plus input direction checks: determine the intended movement direction.",
            "- Simplified state machine: keeps the locomotion transitions manageable.",
            "- Animation curve values: drive the runtime rotation rate.",
            "- Transition-rule calculations: run early so the correct stand-to-walk animation can be selected.",
            "",
            "**Why this matters**",
            "Matching the animation to both input and camera angle makes the locomotion feel more context-aware, especially when choosing the correct root-motion startup direction.",
        ]
    ),
    "wall-run-system": "\n".join(
        [
            "**System Brief**",
            "",
            "The written notes here are light, but the project structure points to a split between animation handling and runtime movement logic for wall-running.",
            "",
            "**Key nodes and logic**",
            "- `AnimBlueprint` backup: likely stores the wall-run animation-state setup.",
            "- `EventGraph` backup: likely handles runtime entry, exit, and movement state control.",
            "",
            "**Why this matters**",
            "Even without a full text breakdown, the project appears to keep animation and gameplay logic separated so wall-run movement can stay readable and easier to debug.",
        ]
    ),
    "jump-prediction": "\n".join(
        [
            "**System Brief**",
            "",
            "This project appears to be centered on predicting jump outcomes, but the original text channel is mostly media-based and does not contain a full written node breakdown.",
            "",
            "**What we can say from the available info**",
            "- The channel is likely documenting a movement helper for jump timing or landing prediction.",
            "- The technical details are mostly in attachments rather than written messages.",
            "",
            "**Why this matters**",
            "This is one of the cases where the forum post is useful as a cleaner home for the media and future notes, even though the original written explanation is minimal.",
        ]
    ),
    "punch-combat-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system is a melee punch-combat setup with hit detection, hit reactions, and retarget/debug work around the combat flow.",
            "",
            "**Key nodes and logic**",
            "- Character and child blueprint backups: preserve working graph versions while iterating on combat behavior.",
            "- Trace and collision handling: the notes mention visibility-channel issues affecting sphere traces.",
            "- Hit-reaction debugging: there are reports about hit reactions not firing after retargeting.",
            "",
            "**Why this matters**",
            "The core challenge here is making the hit detection and animation response stay reliable after retargeting or controller/preset changes.",
        ]
    ),
    "grapple-system": "\n".join(
        [
            "**System Brief**",
            "",
            "The original text notes for this project are minimal, so most of the technical detail appears to live in the attached media rather than in written explanations.",
            "",
            "**What we can say from the available info**",
            "- The project is centered on grapple mechanics.",
            "- The source channel is mostly visual/reference material instead of a documented node walkthrough.",
            "",
            "**Why this matters**",
            "This forum thread gives the system a better place for future structured notes, because the original text channel does not contain much written technical breakdown yet.",
        ]
    ),
    "zipline-system": "\n".join(
        [
            "**System Brief**",
            "",
            "The surviving written notes in the source channel are mostly support messages about project downloads and tutorial setup rather than the technical graph breakdown itself.",
            "",
            "**What we can say from the available info**",
            "- The project is for entering, moving on, and exiting a zipline path.",
            "- The source discussion includes troubleshooting around project files and versioned downloads.",
            "",
            "**Why this matters**",
            "This thread is now a better place to continue documenting the actual implementation details, because the original text channel leaned more toward support than a node-by-node explanation.",
        ]
    ),
    "climb-wall-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This project appears to focus on climb-wall traversal, but the written source notes are short and mostly point to backups and external blueprint references.",
            "",
            "**Key nodes and logic**",
            "- Backup graph references: suggest iteration on a climb-wall setup.",
            "- External BlueprintUE reference: useful for sharing or reviewing blueprint graphs outside the editor.",
            "",
            "**Why this matters**",
            "The text notes are thin here, so the main value of this thread is giving the project a cleaner home where the implementation can be documented more clearly going forward.",
        ]
    ),
    "weapon-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This blueprint flow handles picking up and dropping a handgun, including state checks, actor attachment changes, and physics simulation when the weapon is released.",
            "",
            "**Key nodes and logic**",
            "- Input action on `F`: starts the pickup/release logic.",
            "- `Branch` on `Has Handgun?`: decides whether the player is dropping or needs a different path.",
            "- `Detach From Actor`: removes the handgun from the player.",
            "- Physics re-enable: lets the dropped weapon behave like an object in the world again.",
            "- `Set Has Handgun?`: updates the held-weapon state.",
            "",
            "**Why this matters**",
            "The state boolean prevents invalid transitions, while the detach and physics steps make the drop behavior look correct in gameplay.",
        ]
    ),
    "ladder-system": "\n".join(
        [
            "**System Brief**",
            "",
            "The written notes for this project are very light, so the implementation details are mostly stored in the media rather than a typed walkthrough.",
            "",
            "**What we can say from the available info**",
            "- The project is aimed at ladder traversal.",
            "- The channel shows test material and follow-up discussion about whether the system was still needed.",
            "",
            "**Why this matters**",
            "This is another project where the forum thread is a better long-term place for a real technical explanation, because the original text channel does not yet contain much written blueprint detail.",
        ]
    ),
    "devlog-gasp-als": "\n".join(
        [
            "**System Brief**",
            "",
            "This devlog is about fixing IK and animation integration issues while combining GASP and ALS-style animation setups.",
            "",
            "**Key nodes and logic**",
            "- Retargeting the whole animation blueprint: proposed as the cleaner fix instead of relying on the sandbox ABP.",
            "- IK troubleshooting: the note directly points to retargeting as the route to stabilizing the IK behavior.",
            "",
            "**Why this matters**",
            "The tradeoff is clear in the notes: retargeting the full animation blueprint is more work up front, but it is a more robust fix than patching around the sandbox setup.",
        ]
    ),
    "narrow-system": "\n".join(
        [
            "**System Brief**",
            "",
            "This system uses traces and IK helpers to drive character movement through narrow spaces while keeping hand placement more stable against the wall.",
            "",
            "**Key nodes and logic**",
            "- IK cube tests: use helper cubes as stable spatial reference points.",
            "- `Line Trace` from the cube toward the wall: finds the surface hit point and normal.",
            "- Hand-placement blocks: separate blocks are used to simulate more natural hand movement while moving forward.",
            "",
            "**Why this matters**",
            "Using stable reference helpers before tracing the wall gives more consistent IK targets and helps the narrow-space movement feel less jittery.",
        ]
    ),
}


def post_briefs() -> None:
    intents = discord.Intents.default()
    intents.guilds = True

    class BriefClient(discord.Client):
        async def on_ready(self) -> None:
            guild = self.get_guild(module.GUILD_ID)
            if guild is None:
                raise RuntimeError(f"Guild {module.GUILD_ID} not found")

            state = module.load_state()
            posted = 0
            updated = 0

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

                content = BRIEFS.get(spec.slug)
                if not content:
                    print(f"Skipping {spec.slug}: no brief text")
                    continue

                existing = None
                async for message in thread.history(limit=20, oldest_first=False):
                    if message.author.id == self.user.id and message.content.startswith("**System Brief**"):
                        existing = message
                        break

                if existing is None:
                    sent = await thread.send(content)
                    entry["brief_message_id"] = sent.id
                    posted += 1
                    print(f"Posted brief for {spec.title}")
                else:
                    await existing.edit(content=content)
                    entry["brief_message_id"] = existing.id
                    updated += 1
                    print(f"Updated brief for {spec.title}")

            module.save_state(state)
            print(f"Done. posted={posted} updated={updated}")
            await self.close()

    client = BriefClient(intents=intents)
    client.run(module.TOKEN, log_handler=None)


if __name__ == "__main__":
    post_briefs()
