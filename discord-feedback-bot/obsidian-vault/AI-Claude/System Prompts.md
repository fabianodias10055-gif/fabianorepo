# Claude System Prompts

## When Claude Responds

The bot's Claude integration activates when:
- Someone @mentions the bot
- Someone replies to one of the bot's messages

## Base System Prompt

The system prompt tells Claude it's **LocoAI**, the LocoDev Discord assistant.
It covers:
- What LocoDev is (Unreal Engine 5 gamedev community)
- Patreon tiers (LocoBasic / LocoStandard / LocoPremium)
- Products available
- How to answer questions helpfully

## Owner-Only Context

When the message comes from the server owner, additional context blocks are injected:

### Patreon Context
- Estimated MRR
- New subs / cancels / trials (last 30 days)
- Recent events (last 7 days)
- Patreon link click correlation

### Link Analytics Context
- Stats for specific link mentioned in the question
- Or aggregate stats if no specific link mentioned
- Country breakdown

## Link Creation Rules (Injected into System Prompt)

When Claude needs to create short links, the system prompt includes:

```
You can create short links using: [CREATE_LINK: prefix/slug → https://url]

Rules:
- Slugs must be lowercase, no spaces, no special chars except hyphens
- Check the existing links list before choosing a slug
- Never reuse an existing slug
- Keep slugs short and descriptive

Existing links:
  p/patreonbasic → https://patreon.com/locodev
  p/uecourse → https://blueprint.locodev.dev/...
  ...
```

## Conversation History

The bot maintains per-channel conversation history (last 6 turns) for context:
```python
self._conversation_history: dict[int, list[dict]] = {}
```

Messages are prepended to the history so Claude remembers context within a channel.

## Model Used

`claude-sonnet-4-6` (or latest Sonnet) via the Anthropic Messages API.

See also:
- [[Context Injection]]
- [[CREATE LINK System]]
- [[File Attachments]]
