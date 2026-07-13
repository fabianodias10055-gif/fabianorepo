# Setting up a GitHub repo for an Unreal Engine project (GitHub Desktop)

A step-by-step guide to creating a **new** repository that your teammates can
clone, commit, and push to using **GitHub Desktop** — with Git LFS configured
correctly so Unreal's large binary assets don't break the repo.

> **TL;DR of what goes wrong without this guide:** Unreal projects are full of
> huge binary files (`.uasset`, `.umap`, textures, audio). Plain git chokes on
> them — clones become gigabytes, pushes fail past GitHub's 100 MB/file limit,
> and two people editing the same asset silently overwrite each other. The fix
> is **Git LFS** + a proper **`.gitignore`** + **file locking**. All three are
> handled by the template files in `templates/`.

---

## What's in this kit

| File | Where it goes | Purpose |
|------|---------------|---------|
| `templates/gitignore` | root of new repo, renamed `.gitignore` | Excludes Unreal's generated folders (`Binaries`, `Intermediate`, `Saved`, `DerivedDataCache`, …) |
| `templates/gitattributes` | root of new repo, renamed `.gitattributes` | Routes binary assets through Git LFS and marks them lockable |
| `templates/README.md` | root of new repo, renamed `README.md` | Onboarding instructions for your teammates |

---

## Step 1 — Create the new repository on GitHub

1. Go to <https://github.com/new>.
2. Give it a name (e.g. `my-unreal-game`), choose **Private** (recommended for
   game projects), and **do not** initialize with a README yet — you'll add the
   template files locally.
3. Click **Create repository**.

> Prefer an **Organization** over a personal account if more than one or two
> people will contribute. Organizations give you Teams and easier access
> management. You can create one at <https://github.com/organizations/plan>.

## Step 2 — Add collaborators (so others can push)

Pushing requires **write access**. Being able to see or clone a repo is not
enough. Grant it one of two ways:

- **Personal repo:** repo **Settings → Collaborators → Add people**. Each person
  gets an email/GitHub invite they must accept.
- **Organization repo:** add a **Team** (or individuals) under **Settings →
  Collaborators and teams**, with the **Write** role.

Each collaborator needs their own GitHub account signed into GitHub Desktop.

## Step 3 — Put the template files into the project locally

On the machine that has the Unreal project:

1. Copy the three template files into the **root of your Unreal project** (the
   folder that contains the `.uproject` file) and rename them:
   - `gitignore`  → `.gitignore`
   - `gitattributes` → `.gitattributes`
   - `README.md`  → `README.md`
2. In **GitHub Desktop → File → Add local repository**, select the Unreal
   project folder. If it says the folder isn't a git repo, click **create a
   repository here** — GitHub Desktop will run `git init` for you.
3. GitHub Desktop reads `.gitattributes` and **enables Git LFS automatically**
   (it ships with LFS bundled — no separate install needed).

> **Order matters:** make sure `.gitattributes` is committed *before or in the
> same commit as* your assets. If you commit `.uasset` files first and add
> `.gitattributes` later, those earlier files stay in regular git history and
> keep bloating the repo. If that already happened, see Troubleshooting below.

## Step 4 — First commit and publish

1. In GitHub Desktop you'll see the initial file list. Confirm the generated
   folders (`Intermediate`, `Saved`, `Binaries`, `DerivedDataCache`) are **not**
   listed — the `.gitignore` should be hiding them.
2. Enter a summary like `Initial commit: project + LFS setup` and click
   **Commit to main**.
3. Click **Publish repository** and select the repo you created in Step 1 (or
   let GitHub Desktop create it). Keep **"Keep this code private"** checked.
4. After pushing, verify LFS worked: on GitHub, open a `.uasset` file — it
   should say *"Stored with Git LFS"* rather than showing raw binary.

## Step 5 — How teammates clone and contribute

Send each collaborator these instructions (also in `templates/README.md`):

1. Install **GitHub Desktop** and sign in.
2. **File → Clone repository →** pick the repo → **Clone**. LFS assets download
   automatically.
3. Open the `.uproject`; rebuild modules if prompted.
4. To contribute: save in Unreal → **Commit** in GitHub Desktop → **Push origin**.
5. **Pull often** (Fetch origin → Pull) to stay in sync.

---

## The golden rule for teams: binary assets can't merge

`.uasset` and `.umap` files are binary. If two people change the same asset on
different branches, **git cannot merge them** — one person's work is lost. Avoid
this with discipline:

1. **Pull before you start editing.** Always begin from the latest version.
2. **Lock the asset while you work on it.** The `lockable` flag in
   `.gitattributes` enables this:
   ```bash
   git lfs lock   Content/Characters/Hero.uasset   # claim it
   # ... edit in Unreal, commit, push ...
   git lfs unlock Content/Characters/Hero.uasset   # release it
   ```
   See who holds locks with `git lfs locks`.
3. **Commit small and push often** so assets don't stay locked for days.

> GitHub Desktop's GUI doesn't expose LFS locking buttons, so locks are run from
> a terminal (or the Epic-maintained **UnrealGameSync** tool). Many small teams
> instead just agree verbally on who owns which files — that works too, as long
> as everyone pulls first. The `lockable` attribute is there when you need to
> enforce it.

---

## Watch out for GitHub's LFS limits

Free GitHub accounts include only **1 GB of LFS storage** and **1 GB of LFS
bandwidth per month**. Unreal projects blow past this fast.

- Buy a **data pack** (Settings → Billing → Git LFS Data) — each adds 50 GB of
  storage and 50 GB/month bandwidth.
- Hard limits to remember: **100 MB per non-LFS file**, and LFS files up to
  **2 GB** each (plan-dependent). Keep cooked/packaged builds out of the repo
  (the `.gitignore` already excludes them) — ship those via releases instead.

---

## Troubleshooting

**"This file is X MB; GitHub blocks files over 100 MB."**
The file wasn't tracked by LFS before it was committed. Make sure its extension
is listed in `.gitattributes`, then migrate existing history:
```bash
git lfs migrate import --include="*.uasset,*.umap" --everyone
git push --force            # coordinate with the team before force-pushing
```

**Assets committed before `.gitattributes` existed.**
Same fix as above — `git lfs migrate import` rewrites history so those files
move into LFS. Do it early, before many people have cloned.

**Clone is huge / slow.**
Confirm binaries are actually in LFS: `git lfs ls-files` should list your
assets. If it's empty, `.gitattributes` wasn't committed first.

**A merge conflict on a `.uasset`.**
Git can't auto-resolve it. Decide which version wins, then in Unreal re-apply
the changes by hand. Prevent recurrence with the locking workflow above.

**Teammate can't push ("permission denied" / "403").**
They don't have Write access (Step 2) or haven't accepted the invite. Re-check
their role under repo **Settings → Collaborators**.

---

## Quick reference — the whole flow

```
Create repo (private)  ->  Add collaborators (Write access)
        |
Copy .gitignore + .gitattributes + README into project root
        |
Add local repo in GitHub Desktop (LFS auto-enables)
        |
Commit + Publish  ->  verify "Stored with Git LFS" on GitHub
        |
Teammates: Clone in GitHub Desktop  ->  edit  ->  Commit  ->  Push
        |
Discipline: pull first, lock binary assets, push often
```
