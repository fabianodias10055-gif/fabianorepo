# Unreal Engine + GitHub Desktop setup kit

Everything you need to set up a **new** GitHub repository so a team can commit
and push an **Unreal Engine** project using **GitHub Desktop** — with Git LFS
configured correctly for large binary assets.

## Start here

📖 **[SETUP_GUIDE.md](./SETUP_GUIDE.md)** — the full step-by-step guide
(create the repo → add collaborators → configure LFS → publish → teammate
workflow → troubleshooting).

🛠️ **[VISUAL_STUDIO_SETUP.md](./VISUAL_STUDIO_SETUP.md)** — for C++ contributors:
installing Visual Studio 2022 with the right workloads, generating project
files, and building/debugging the project.

## Template files (`templates/`)

Copy these into the **root of your Unreal project** (next to the `.uproject`)
and rename them:

| Template | Rename to | What it does |
|----------|-----------|--------------|
| `templates/gitignore` | `.gitignore` | Ignores Unreal's generated folders |
| `templates/gitattributes` | `.gitattributes` | Sends binary assets to Git LFS + makes them lockable |
| `templates/README.md` | `README.md` | Onboarding notes for collaborators |

## Why LFS is non-negotiable for Unreal

Unreal stores art, audio, levels, and blueprints as large **binary** files.
Plain git can't diff or merge them and GitHub rejects files over 100 MB. Git
LFS keeps the big binaries on a side server and stores only small pointers in
git history, so clones stay fast and pushes succeed. The `.gitattributes`
template turns this on automatically.
