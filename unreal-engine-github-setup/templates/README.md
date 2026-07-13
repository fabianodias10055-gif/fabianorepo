# <Your Unreal Project Name>

An Unreal Engine project. This repository uses **Git LFS** for binary assets,
so please follow the setup steps before cloning or committing.

## Requirements

- [GitHub Desktop](https://desktop.github.com/) (bundles Git + Git LFS)
- Unreal Engine <version, e.g. 5.4> installed via the Epic Games Launcher

## Getting started (GitHub Desktop)

1. Install **GitHub Desktop** and sign in.
2. **File → Clone repository**, pick this repo, and clone it.
   - Git LFS assets download automatically — no extra steps.
3. Open the `.uproject` file. If prompted to rebuild modules, click **Yes**.

## Making changes

1. Do your work in the Unreal Editor and **save**.
2. In GitHub Desktop, review the changed files, write a short summary, and
   click **Commit to `<branch>`**.
3. Click **Push origin** to share your work.
4. Click **Fetch/Pull** often to get teammates' latest changes.

## Working with binary assets (important)

`.uasset` and `.umap` files **cannot be merged** by git. Before editing one:

- Pull the latest changes first.
- Tell the team, or **lock** the file so no one else edits it at the same time:
  ```
  git lfs lock  Content/Path/To/Asset.uasset
  # ...edit and commit...
  git lfs unlock Content/Path/To/Asset.uasset
  ```

See `unreal-engine-github-setup/SETUP_GUIDE.md` in the template kit for the
full workflow and troubleshooting.
