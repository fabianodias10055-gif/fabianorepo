# Context Injection

Claude receives dynamic context injected into the system prompt based on
what's being asked. This makes the bot "smart" about LocoDev data without
Claude needing API access itself.

## How It Works

Before calling the Claude API, the bot builds a `parts` list of context blocks,
then joins them into the system prompt. Each block is wrapped in `[...]`.

## Channel History

Last 6 messages in the channel are included so Claude has conversation context:
```
[Recent conversation:
UserA: how do I fix the climbing bug?
LocoAI: Here's how...
UserB: what about the ledge system?
]
```

## YouTube Video Transcript

If the message contains a YouTube URL, the bot fetches the transcript via
`yt-dlp` (with `youtube-transcript-api` as fallback):
```
[Video transcript for https://youtu.be/XYZ:
...full transcript text...
]
```

Subtitles disabled → fallback tries auto-generated captions → if both fail,
Claude is told "transcript unavailable, answer based on title/description".

## Link Analytics Context (Owner Only)

Triggered when the question mentions a specific link path (e.g., "p/patreonbasic"):
```
[Link Analytics — locodev.dev/p/patreonbasic]
Total clicks: 142
Last 30 days: 38
Top countries: Brazil (21), USA (9)...
```

If no specific link is mentioned but the question is about links/clicks/analytics:
```
[Link Analytics — Top links last 30 days]
  p/patreonbasic: 38 clicks
  download/ledgepremium: 22 clicks
  ...
```

## Patreon Event Context (Owner Only)

Triggered when the question mentions Patreon/subscribers/revenue/members:
```
[Patreon Member Events:
PATREON REVENUE & MEMBER DATA:
ESTIMATED MRR: $XXX.XX/month
Active paid members tracked: N
...
PATREON LINK CLICKS vs CONVERSIONS:
...
]
```

## File Attachments

Text files (.txt, .md, .csv, .log, .srt, .vtt) attached to messages are fetched
and injected as text blocks:
```
[Attachment: transcript.txt]
...file contents up to 150KB...
```

## Replied-To Message

If the user is replying to a previous message, that message's content is included:
```
[Replying to this message:
The original message text here
]
```

## Image Attachments

Images are sent as base64-encoded `image` content blocks in the Claude API
request — Claude can see and describe them natively.
