# Visual Studio setup for the Libertas C++ project (Unreal Engine 5.7)

`Libertas` is a **C++** Unreal project, so anyone who edits code (not just
Blueprints) needs **Visual Studio** installed with the correct components.
GitHub Desktop syncs the files; Visual Studio **compiles** them. They are two
separate tools each contributor installs once.

> **Blueprint-only contributors** (artists/designers who never touch `.cpp`)
> can often get by without Visual Studio — but they still need someone to have
> built the editor binaries first, and on Windows the engine may prompt them to
> compile. The simplest team rule: **everyone on Windows installs Visual Studio.**

---

## Step 1 — Install Visual Studio 2022 (free)

Download **Visual Studio 2022 Community** (free for individuals, small teams,
and open source) from <https://visualstudio.microsoft.com/downloads/>.

- Use **Visual Studio 2022** for Unreal Engine 5.7 — not VS Code, and not the
  older VS 2019. (VS Code and JetBrains Rider work too; see the bottom.)
- "Visual Studio" ≠ "Visual Studio Code." You need the full **Visual Studio**
  IDE for the C++/Unreal toolchain.

## Step 2 — Select the right workloads and components (the part people miss)

In the Visual Studio Installer, on the **Workloads** tab, check:

- ✅ **Game development with C++**
- ✅ **.NET desktop development**
  (UnrealBuildTool / AutomationTool are C# — the build fails without this.)
- ✅ **Desktop development with C++**

Then switch to the **Individual components** tab and make sure these are ticked
(most come with the workloads above, but confirm):

- ✅ **MSVC v143 - VS 2022 C++ x64/x86 build tools (latest)**
- ✅ **Windows 11 SDK** (or Windows 10 SDK if you're on Windows 10)
- ✅ **C++ profiling tools**
- ✅ **.NET 8.0 Runtime** (UE 5.4+ tooling targets .NET 8)
- ✅ **Unreal Engine installer** (listed under Gaming — installs the UE/VS glue)
- ✅ **IntelliCode** (optional, nice autocompletion)

Click **Install** (several GB — give it time).

> Epic's official, always-current list is here — skim it if a build tool goes
> missing: <https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine>

## Step 3 — Generate the Visual Studio solution

The `.sln` and `.vcxproj` files are **not** committed (they're machine-specific
and in `.gitignore`). Each person generates their own after cloning:

1. Right-click **`Libertas.uproject`** in File Explorer.
2. Choose **Generate Visual Studio project files**.
   - If that entry is missing, open the Epic Games Launcher →
     **Unreal Engine → Library → dropdown next to Launch → Options**, or run it
     from a terminal:
     `"C:\Program Files\Epic Games\UE_5.7\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe" -projectfiles -project="<full path>\Libertas.uproject" -game -engine`
3. A `Libertas.sln` appears next to the `.uproject`. Open it.

## Step 4 — Build and run from Visual Studio

1. In the toolbar set the configuration to **Development Editor** and platform
   to **Win64**.
2. Set **Libertas** as the startup project (right-click it → *Set as Startup
   Project*) if it isn't already.
3. Press **F5** (Debug) or **Ctrl+F5** (Run without debugging). Visual Studio
   compiles the C++ and launches the Unreal Editor with your project loaded.
4. From then on you can also just double-click `Libertas.uproject` to open the
   editor; use Visual Studio when you need to compile, debug, or set breakpoints.

**Common configurations you'll use:**

| Configuration | What it's for |
|---------------|---------------|
| Development Editor | Day-to-day work in the editor (this is the default) |
| DebugGame Editor | Editor with your game code un-optimized for debugging |
| Development / Shipping | Building a standalone game (packaging) |

## Step 5 — Recommended, but optional

- **Visual Studio Tools for Unreal Engine** — Microsoft's official integration
  (ships with VS 2022 17.10+; enable it via the *Unreal Engine installer*
  component in Step 2). Adds UE-aware IntelliSense, Blueprint references, and
  asset info in the editor.
- **UnrealVS extension** — Epic's toolbar for switching build configs and
  building from VS quickly. Installer lives in
  `Engine\Extras\UnrealVS\UnrealVS.vsix` inside your engine install.

## Team consistency: `.editorconfig`

The project ships an **`.editorconfig`** at its root that pins Unreal's C++
conventions (tabs for indentation, UTF-8, trimmed trailing whitespace). Visual
Studio, Rider, and VS Code all honor it automatically, so everyone's diffs stay
clean regardless of personal editor settings. No setup needed — just don't
delete it.

## Prefer JetBrains Rider?

**Rider** (also free for non-commercial use) has excellent Unreal support and
many teams prefer it. You still need the **Visual Studio Build Tools** (the MSVC
compiler + Windows SDK from Step 2) installed for the actual compilation — Rider
uses that toolchain under the hood. Generate project files the same way; Rider
opens the `.uproject` or `.sln` directly.

## Troubleshooting

**"Generate Visual Studio project files" is missing from the right-click menu.**
The engine's shell integration isn't registered. Re-run the Epic Games Launcher,
or verify the file association: Epic Games Launcher → Unreal Engine → Library →
next to your engine version, dropdown → **Options** / **Verify**.

**Build error: `The .NET SDK / MSBuild could not be found` or UBT won't run.**
The **.NET desktop development** workload (and .NET 8 Runtime) is missing —
go back to Step 2 and add it.

**`Windows SDK version X was not found`.**
Install the matching **Windows 11/10 SDK** individual component, or right-click
the solution → **Retarget solution** to an SDK you do have.

**Editor keeps asking to rebuild every launch / "modules are out of date."**
Your binaries are older than your source. Build **Development Editor | Win64** in
Visual Studio once, or click **Yes** when the editor offers to rebuild.

**IntelliSense shows red squiggles everywhere but it compiles fine.**
That's normal on first open — let it finish parsing, or regenerate project files
(Step 3). Installing *Visual Studio Tools for Unreal Engine* improves this a lot.
