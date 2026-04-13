# LocoDev Bot — Knowledge Vault

This vault documents everything about the **LocoDev Discord Bot** — architecture, integrations, bugs fixed, and operational knowledge built up through development.

## Navigate by Category

| Category | What's inside |
|----------|--------------|
| [[Architecture/Overview]] | How the bot is structured, key files, data storage |
| [[Architecture/File Map]] | Every file and what it does |
| [[Architecture/Environment Variables]] | All env vars the bot needs |
| [[Deployment/Railway Setup]] | How to deploy, volume, port, redeploy |
| [[Deployment/Git Branching]] | Branch workflow, merging to master |
| [[Patreon/Webhook Handler]] | Event types, signature, full processing flow |
| [[Patreon/Deduplication & Idempotency]] | How duplicate webhooks are blocked |
| [[Patreon/Events & Roles]] | Discord role assignment per Patreon event |
| [[Patreon/Free Trials]] | Trial detection, conversion tracking |
| [[Patreon/Revenue & MRR]] | How MRR is estimated from the event log |
| [[Discord/Channel IDs]] | All channel IDs used by the bot |
| [[Discord/Role System]] | Tier roles, fix_roles command |
| [[Discord/Pushover Notifications]] | Which events trigger mobile push alerts |
| [[Shortener/How It Works]] | Link DB schema, URL format, prefixes |
| [[Shortener/Analytics]] | Click tracking, country geo-lookup |
| [[Shortener/UTM Tracking]] | UTM params, conversion correlation |
| [[Shortener/Link Management]] | Create/update/delete, startup patches |
| [[YouTube/Unreal Engine Watcher]] | RSS polling, persistence, notifications |
| [[AI-Claude/System Prompts]] | What context Claude receives |
| [[AI-Claude/Context Injection]] | Link analytics, Patreon events injected dynamically |
| [[AI-Claude/CREATE LINK System]] | How the bot creates links via chat |
| [[AI-Claude/File Attachments]] | Reading txt/md/csv attachments |
| [[Bug Fixes/Session Log]] | Every bug found and fixed, with root cause |

## Quick Reference

- **Live URL**: locodev.dev
- **Bot name**: LocoAI (LocoDev#8301)
- **Guild ID**: 1158395981835010098
- **Platform**: Railway (us-west2)
- **Main files**: `bot.py`, `shortener.py`
- **Persistent storage**: `/app/data/` (Railway volume)
