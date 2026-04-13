# CREATE LINK System

## The Problem It Solves

Before this system, Claude would hallucinate link creation — saying
"✅ Short link created!" while not actually creating anything. The bot had
no way to execute Claude's stated intentions.

## How It Works

### 1. Claude Outputs a Marker

When creating a link, Claude is instructed to output a special marker:
```
[CREATE_LINK: p/bowarrowsystem → https://patreon.com/posts/85419167]
```

### 2. Bot Intercepts the Marker

After receiving Claude's response, the bot scans for the marker pattern:
```python
_cl_matches = re.findall(
    r'\[CREATE_LINK:\s*([^\s→]+)\s*[→>]+\s*(https?://[^\]]+)\]',
    answer
)
```

### 3. Bot Executes the Link Creation

For each match:
```python
prefix, slug = path.split("/", 1)
success = create_link(slug, url, prefix)
if success:
    # Verify it was actually created
    link = get_link(slug, prefix)
    _link_results.append(f"✅ Created: locodev.dev/{prefix}/{slug} → {url}")
else:
    _link_results.append(f"⚠️ Slug `{slug}` already exists or creation failed")
```

### 4. Marker Stripped from Response

The `[CREATE_LINK: ...]` marker is removed from the displayed answer.
The creation result is sent as a follow-up message.

## Slug Collision Prevention

Before Claude responds, the system prompt includes a list of ALL existing links:
```
Existing links (do NOT reuse these slugs):
  p/patreonbasic
  p/uecourse
  download/ledgepremium
  ...
```

Claude is instructed: "Never reuse an existing slug. If asked to create a link
for an existing slug, update it instead using `/update_link`."

## Example Flow

User: "Create a short link for the bow arrow patreon post"

Claude (raw response):
```
I'll create that link now.
[CREATE_LINK: p/bowarrowsystem → https://www.patreon.com/posts/85419167?pr=true]
The link locodev.dev/p/bowarrowsystem will redirect to your Patreon post.
```

Bot processes:
1. Extracts: `p/bowarrowsystem → https://www.patreon.com/posts/85419167?pr=true`
2. Calls `create_link("bowarrowsystem", "https://...", "p")`
3. Strips `[CREATE_LINK: ...]` from displayed text
4. Sends follow-up: `✅ Created: locodev.dev/p/bowarrowsystem → https://...`

## Also Handles Natural Language Patterns

The bot also detects when Claude naturally describes a link in its response:
```python
# Catches "locodev.dev/p/something" patterns in responses
_path_match = re.search(r'locodev\.dev/([^\s→>\n]+)', _raw_msg, re.IGNORECASE)
_url_match = re.search(r'https?://[^\s→>\n]+', _raw_msg)
```
