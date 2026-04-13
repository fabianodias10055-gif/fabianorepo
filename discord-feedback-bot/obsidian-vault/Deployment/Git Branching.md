# Git Branching

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `master` | Production — Railway auto-deploys from this |
| `claude/explain-repo-necessity-tN7hs` | Claude Code session feature branch |

## Workflow

```
1. Claude makes changes on feature branch
2. Push feature branch to remote
3. When ready to deploy: merge feature branch → master
4. Push master → Railway auto-deploys
```

## Deploy Command

```bash
git checkout master
git merge <feature-branch> --no-edit
git push -u origin master
```

## Feature Branch Pattern

Claude Code uses branches named `claude/<description>-<hash>`.
All commits accumulate there, then merge to master when the user says to deploy.

## Commit Message Convention

Messages end with the Claude session URL:
```
Short description of change

Longer explanation if needed.

https://claude.ai/code/session_01XTQnEJ6PD1Ncbmqm4uTQs8
```

## Key Commits This Session

| Hash | Description |
|------|-------------|
| `bc1767c` | YouTube watcher — persist seen IDs + fetch_channel fallback |
| `8fd712c` | Patreon webhook — historical cancellation replay fix |
| `08d0321` | Fix _free_clicks query missing last_click column |
| `97faf06` | Text file attachment reading (txt, md, csv, etc.) |
| `e28f7ed` | Fix empty message 400 error on short Claude replies |
| `55da16f` | Update locodev.dev/uecourse URL + startup link patches |
