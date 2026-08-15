# Plan: from a panel to a control room

Written against the recorded brainstorm of 2026-08-15. Every idea in it is
sorted here by what it would actually cost, using the numbers the vault
holds today rather than guesses. Nothing below is speculative about the data:
each "already there" was checked, and each "needs" names what is missing.

## Where this already stands

Half the brainstorm exists. Worth knowing before paying for it twice.

| Idea from the recording | Where it lives today |
|---|---|
| Pull YouTube and Discord questions into one place | Questions, 2401 of them, collected every 15 min |
| Merge both into one answering flow | Reply posts to whichever platform it came from |
| Answer from what you already answered | Find existing answer, over 461 proven answers |
| Confidence indicator and sources | Suggest returns a percentage and names the note |
| Edit before sending | The composer, with Retry send when posting fails |
| Answers in your own voice | The AI reads your past answers as its context |
| Knowledge base in the vault | 1445 pieces: 461 answers, 984 documentation sections |
| Per-project knowledge | Systems/, tier folders, 61 of 150 notes written |
| Which systems are documented | Pressure, and the Sync screen |
| People module | People, with the channel each one asks from |
| Shortened links and click telemetry | Links |
| Local-first, 127.0.0.1 | Exactly the architecture the recording lands on |

## The one piece that blocks a third of the list

**Nothing records how an answer was produced.** `/reply` receives an id and
a text. Whether that text came from the vault search, from Claude, or from
typing, and how much was edited before sending, is not written anywhere.

These all wait on it, and none of them are hard once it exists:

- how many answers the AI produced, how many you edited, how many were manual
- average editing rate, and where the AI is trustworthy and where it is not
- time saved, which is the metric the recording keeps coming back to
- "this answer was reused 150 times", and the FAQ suggestion that follows
- the source breakdown: x% approved answers, y% documentation, z% transcripts

**Do this first.** The reply route records, alongside the answer: what the
suggestion offered, its confidence, which note it came from, whether the
sent text differs from it and by how much, and how long the question sat
open. One field per fact, written to the same block the answer already
writes. Everything above becomes arithmetic over data you already have.

Cost: small. Value: it is the difference between a panel that shows work and
one that can prove it saved you a day.

## Cheap, and the data is already here

Nothing new to integrate. Ordered by value per hour of work.

**Videos screen becomes a work queue.** The recording is most concrete here
and it is all computable now: per video, whether the transcript is in the
vault (139 of 159 have it), whether it is tagged to a system (94 are not),
how many of its comments are still open, and a completion bar over those.
Sorted by which video generated the most questions this week.

**Tag the 94 untagged videos.** Measured: 183 of the 184 open YouTube
questions with no system come from exactly those videos. `tag_videos.py`
exists; run it in simulation, correct what it gets wrong, and 183 questions
find their system. This is the single highest ratio of result to effort on
this page.

**Filters the recording asked for**: by video, by confidence, by how the
answer was produced. The last two depend on the provenance above; by video
does not.

**Trending topics and recurring questions.** Group open questions by their
keywords over a window. "This was asked 48 times" is the input to every
suggested action in the recording, and it needs no model, only counting.

**Answers screen**: reuse count, editing rate, and what entered the knowledge
base this week. All arithmetic over provenance.

**Pressure gains the column the recording named**: pressure as demand
against missing documentation, and a trend against last week.

**Overview answers its four questions** once the above exist: how much work
is waiting, how much the assistant did, how much time that saved, what to do
now.

## Needs something new, and is still worth it

**Video description editing, pinned comments.** Already possible: the
YouTube OAuth in the credential store carries `youtube.force-ssl`, which is
write access to your own videos. No new permission, just the code.

**Views, click-through rate, retention.** These are not in the API this
panel uses. YouTube Analytics is a separate API and a separate scope
(`yt-analytics.readonly`), owner-only. Doable, a day of work, and it unlocks
the "CTR is low, here are three thumbnails" ideas. Worth doing after the
free wins above, not before.

**A system for the 1032 orphan Discord questions.** Most open questions have
no system, and unlike the YouTube ones there is no video to tag. They need
the system inferred from their text. Until that exists, every per-project
metric is describing a third of reality. This is the quiet blocker behind
"per-project dashboards".

## What I would not build yet

**Knowledge graph and semantic search.** The recording is right that they are
powerful. They are also the two most expensive items on the list, and the
current keyword search with IDF weighting is finding the right note today
across 1445 entries. Revisit when a search visibly fails, and let the failure
pick the design.

**Plugins and integrations from the start.** A plugin boundary designed
before the second consumer exists is a guess about the second consumer. The
export that feeds the Discord bot is already the seam; when a third thing
needs the knowledge, that seam is where it attaches.

**Scheduling replies, bulk send.** Bulk actions on a queue this size are how
one bad draft reaches fifty people. Worth having, worth having last, and
worth having with a preview of all fifty.

## Order

1. **Record provenance on reply.** Everything counting waits on it.
2. **Tag the 94 videos.** 183 questions find their home.
3. **Videos as a work queue.** Transcript, tag, open comments, completion.
4. **Counting**: recurring questions, reuse, editing rate, time saved.
5. **Overview rewritten** around the four questions, now that it can answer them.
6. **Infer systems for Discord questions.** Unblocks per-project everything.
7. **YouTube Analytics.** Views, CTR, retention, and the actions they imply.
8. **Writing back to YouTube**: descriptions, pinned comments, FAQ.

The first five need no new integration, no new permission and no new
dependency. They are counting things the vault already knows.

## The part of the recording I would keep in front

> "Não tente apenas recriar os dados de outras plataformas. Faça algo que
> nenhuma delas consegue fazer porque não tem todo o contexto."

YouTube Studio will always show views better than this will. What it cannot
do is know that the question under video 12 was already answered in Discord
eight months ago, in your words, and that the answer is three lines away.
When a feature here duplicates something Studio already does, it is worth
asking whether it earns its place; when it joins two sources that no other
tool has together, it is the reason this exists.
