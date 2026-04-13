# File Attachments

## Supported File Types

| Extension | Content Type | Use Case |
|-----------|-------------|---------|
| `.txt` | Plain text | Transcripts, notes |
| `.md` | Markdown | Documentation |
| `.csv` | Comma-separated | Data, spreadsheets |
| `.log` | Log files | Error logs, server logs |
| `.srt` | SubRip subtitle | Video captions |
| `.vtt` | WebVTT subtitle | Video captions |

## Size Limit

**150 KB** — files larger than this are truncated. A note is appended:
```
[...truncated at 150 KB]
```

## How It Works

When a message with an attached text file arrives:

1. Bot detects it via `_is_text_attachment(attachment)`
2. Downloads via aiohttp `GET attachment.url`
3. Decodes as UTF-8 (with `errors="replace"` for binary garbage)
4. Injects into the prompt as:

```
[Attachment: filename.txt]
...file contents...
```

5. Multiple files are all injected, each with their filename header

## Images vs Text

Images (PNG/JPG/GIF/WEBP) are sent as base64-encoded `image` content blocks
to the Claude API — Claude can visually process them.

Text files are injected as plain text into the prompt — Claude reads them
as part of the conversation.

## Default Prompt When No Question Given

If someone attaches a file without typing a question:
```
Please read the attached file(s) and summarize or answer any question about them.
```

## Example Use Case

User attaches `transcript.txt` (YouTube video transcript) and asks:
"Can you summarize this and pull out the key UE5 tips?"

Bot:
1. Downloads transcript.txt
2. Injects content into prompt as `[Attachment: transcript.txt]\n...`
3. Claude reads the full transcript and answers the question

## Referenced Attachments

The bot also checks the **replied-to message** for attachments.
If you reply to a message that has a file attached, the bot fetches that too.
