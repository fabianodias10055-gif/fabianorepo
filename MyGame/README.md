# MyGame — Unreal Engine 5.7 base project

A minimal, ready-to-open **Unreal Engine 5.7 C++** project set up for team
collaboration with Git + Git LFS. Use it as the starting point for a new game.

## What's included

```
MyGame/
├─ MyGame.uproject            # Project descriptor (EngineAssociation 5.7)
├─ .gitignore                 # Ignores Unreal's generated folders
├─ .gitattributes            # Git LFS for binary assets (+ lockable)
├─ Config/
│  ├─ DefaultEngine.ini       # Renderer, default game mode, hardware target
│  ├─ DefaultGame.ini         # Project name / ID / version
│  ├─ DefaultInput.ini        # Enhanced Input defaults
│  └─ DefaultEditor.ini
├─ Content/                   # Your .uasset / .umap files go here (empty for now)
└─ Source/
   ├─ MyGame.Target.cs        # Game build target
   ├─ MyGameEditor.Target.cs  # Editor build target
   └─ MyGame/
      ├─ MyGame.Build.cs      # Module dependencies
      ├─ MyGame.cpp / .h      # Primary game module
      └─ MyGameGameModeBase.cpp / .h   # Starter GameMode class
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

1. Double-click `MyGame.uproject`.
   - If it asks which engine version, pick **5.7**.
   - Because this is a C++ project, it will ask to build the module — click **Yes**.
     (First build takes a few minutes.)
2. The editor opens. Create or open a level and **File → Save** it into `Content/`
   — that becomes your first tracked asset.
3. Set it as the startup map under **Edit → Project Settings → Maps & Modes** if
   you want it to load automatically.

If double-clicking doesn't build, right-click `MyGame.uproject` →
**Generate Visual Studio project files**, open the generated `.sln`, and build
the **Development Editor** configuration.

## Renaming the project

The name `MyGame` appears in file names, folders, and code. To rename to
`YourName`:

1. Rename these so the name matches (case-sensitive):
   - `MyGame.uproject` → `YourName.uproject`
   - `Source/MyGame.Target.cs` → `Source/YourName.Target.cs`
   - `Source/MyGameEditor.Target.cs` → `Source/YourNameEditor.Target.cs`
   - folder `Source/MyGame/` → `Source/YourName/`
   - `Source/YourName/MyGame.Build.cs` → `YourName.Build.cs`
   - `MyGame.cpp/.h`, `MyGameGameModeBase.cpp/.h` likewise
2. Find-and-replace `MyGame` → `YourName` and `MYGAME_API` → `YOURNAME_API`
   across `Source/` and `Config/DefaultEngine.ini`
   (`GlobalDefaultGameMode=/Script/YourName.YourNameGameModeBase`).
3. Update `"Name": "MyGame"` in the `.uproject`, and `ProjectName` in
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
