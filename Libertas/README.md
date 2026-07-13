# Libertas — Unreal Engine 5.7 base project

A minimal, ready-to-open **Unreal Engine 5.7 C++** project set up for team
collaboration with Git + Git LFS. Use it as the starting point for a new game.

## What's included

```
Libertas/
├─ Libertas.uproject            # Project descriptor (EngineAssociation 5.7)
├─ .gitignore                 # Ignores Unreal's generated folders
├─ .gitattributes            # Git LFS for binary assets (+ lockable)
├─ Config/
│  ├─ DefaultEngine.ini       # Renderer, default game mode, hardware target
│  ├─ DefaultGame.ini         # Project name / ID / version
│  ├─ DefaultInput.ini        # Enhanced Input defaults
│  └─ DefaultEditor.ini
├─ Content/                   # Your .uasset / .umap files go here (empty for now)
└─ Source/
   ├─ Libertas.Target.cs        # Game build target
   ├─ LibertasEditor.Target.cs  # Editor build target
   └─ Libertas/
      ├─ Libertas.Build.cs      # Module dependencies
      ├─ Libertas.cpp / .h      # Primary game module
      ├─ LibertasGameModeBase.cpp / .h   # GameMode (sets the default pawn)
      └─ LibertasCharacter.cpp / .h      # Starter third-person character
```

> **Note:** This is the *source* of the project. Unreal generates the binary
> `Content` assets (a default map, etc.), plus the `Binaries/`, `Intermediate/`,
> `Saved/`, and `DerivedDataCache/` folders, the **first time you open it** — so
> those are intentionally absent here and excluded by `.gitignore`.

## Requirements

- **Unreal Engine 5.7** (install via the Epic Games Launcher)
- A C++ toolchain:
  - **Windows:** Visual Studio 2022 with the *Game development with C++* workload
  - **macOS:** Xcode
  - **Linux:** the cross-compile toolchain / clang

## How to open it the first time

1. Double-click `Libertas.uproject`.
   - If it asks which engine version, pick **5.7**.
   - Because this is a C++ project, it will ask to build the module — click **Yes**.
     (First build takes a few minutes.)
2. The editor opens. Create or open a level and **File → Save** it into `Content/`
   — that becomes your first tracked asset.
3. Set it as the startup map under **Edit → Project Settings → Maps & Modes** if
   you want it to load automatically.

If double-clicking doesn't build, right-click `Libertas.uproject` →
**Generate Visual Studio project files**, open the generated `.sln`, and build
the **Development Editor** configuration.

## Starter character & input

`ALibertasCharacter` is a third-person character (camera boom + follow camera)
wired as the GameMode's default pawn, so pressing **Play** spawns a controllable
character. Movement uses **Enhanced Input**, which is asset-driven — the C++
compiles and runs immediately, but the actual key bindings live in editor assets
you create once:

1. In the Content Browser, create three **Input Actions**:
   - `IA_Move` — Value Type **Axis2D (Vector2D)**
   - `IA_Look` — Value Type **Axis2D (Vector2D)**
   - `IA_Jump` — Value Type **Digital (bool)**
2. Create an **Input Mapping Context** `IMC_Default` and map keys to those
   actions (e.g. WASD → `IA_Move` with a 2D swizzle/negate, mouse XY → `IA_Look`,
   Space → `IA_Jump`).
3. Create a **Blueprint subclass** of `LibertasCharacter` (right-click →
   *Blueprint Class* → search `LibertasCharacter`), name it
   `BP_LibertasCharacter`, and in its Details panel assign `IMC_Default`,
   `IA_Move`, `IA_Look`, `IA_Jump` (and a skeletal mesh + anim BP if you have
   one).
4. Point the GameMode at the Blueprint: either set **Default Pawn Class** in a
   `BP_LibertasGameMode`, or in **Project Settings → Maps & Modes**.

Until you assign those assets the character still spawns — it just won't respond
to input (the code null-checks each action, so nothing crashes).

## Renaming the project

The name `Libertas` appears in file names, folders, and code. To rename to
`YourName`:

1. Rename these so the name matches (case-sensitive):
   - `Libertas.uproject` → `YourName.uproject`
   - `Source/Libertas.Target.cs` → `Source/YourName.Target.cs`
   - `Source/LibertasEditor.Target.cs` → `Source/YourNameEditor.Target.cs`
   - folder `Source/Libertas/` → `Source/YourName/`
   - `Source/YourName/Libertas.Build.cs` → `YourName.Build.cs`
   - `Libertas.cpp/.h`, `LibertasGameModeBase.cpp/.h` likewise
2. Find-and-replace `Libertas` → `YourName` and `LIBERTAS_API` → `YOURNAME_API`
   across `Source/` and `Config/DefaultEngine.ini`
   (`GlobalDefaultGameMode=/Script/YourName.YourNameGameModeBase`).
3. Update `"Name": "Libertas"` in the `.uproject`, and `ProjectName` in
   `Config/DefaultGame.ini`.
4. Delete any `Binaries/` and `Intermediate/` folders, then regenerate project
   files and rebuild.

## Version control

`.gitattributes` routes binary assets (`.uasset`, `.umap`, textures, audio,
models) through **Git LFS** and marks them lockable so two people don't edit the
same un-mergeable asset at once. See
[`../unreal-engine-github-setup/SETUP_GUIDE.md`](../unreal-engine-github-setup/SETUP_GUIDE.md)
for the full GitHub Desktop + collaboration workflow.

**Before editing a binary asset:** pull first, then lock it —
`git lfs lock Content/Path/Asset.uasset` — and unlock when you push.
