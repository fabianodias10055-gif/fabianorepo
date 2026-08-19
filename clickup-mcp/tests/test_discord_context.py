"""The lines kept alongside a question so a draft is not written blind."""
import collect_discord as c


def msg(mid, author_id, handle, text, when, reply_to=None):
    m = {
        "id": str(mid),
        "author": {"id": str(author_id), "username": handle},
        "content": text,
        "timestamp": when,
    }
    if reply_to:
        m["message_reference"] = {"message_id": str(reply_to)}
    return m


# #general-chat, 2026-08-12. The question the panel collected was the last
# line, and on its own it names nothing you could search the vault for.
YOGURT = 111
BUDDY = [
    msg(1537095603379773522, YOGURT, "yogurt",
        "if i could make it walk wherever i want it to walk it would be so peak",
        "2026-08-12T13:49:00+00:00"),
    msg(1537095802592165908, YOGURT, "yogurt",
        "The control rig is making it walk, i deleted everything execpt the pelvis",
        "2026-08-12T13:49:30+00:00"),
    msg(1537121191943340142, YOGURT, "yogurt",
        "the ragdoll walks from the locomotor inside the control rig",
        "2026-08-12T15:30:00+00:00"),
    msg(1537121269709799464, YOGURT, "yogurt",
        "I cant change the direction but its good it walks",
        "2026-08-12T15:31:00+00:00"),
]


def test_the_question_that_reads_as_nonsense_alone():
    got = c.preceding_context(BUDDY[-1], BUDDY)
    assert "ragdoll" in got
    assert "control rig" in got
    # Oldest first, so it reads as a conversation rather than backwards.
    assert got.index("so peak") < got.index("ragdoll")


def test_a_parallel_conversation_does_not_ride_along():
    """#general-chat usually has two threads running at once."""
    other = msg(1537121191943340143, 222, "someone_else",
                "anyone know how to fix the mantle height on stairs",
                "2026-08-12T15:30:30+00:00")
    got = c.preceding_context(BUDDY[-1], BUDDY + [other])
    assert "mantle height" not in got
    assert "ragdoll" in got


def test_the_message_they_replied_to_is_kept():
    """Whoever wrote it: a reply without its parent says half of nothing."""
    staff = msg(1537121191943340144, 999, "locodev",
                "Is the locomotor driving the pelvis or the whole rig?",
                "2026-08-12T15:30:40+00:00")
    asked = msg(1537121269709799465, YOGURT, "yogurt",
                "the pelvis only, and it still walks sideways",
                "2026-08-12T15:31:10+00:00",
                reply_to=1537121191943340144)
    got = c.preceding_context(asked, BUDDY + [staff, asked])
    assert "locomotor driving the pelvis" in got


def test_stale_lines_are_left_behind():
    """Two hours by default: yesterday's chat is not this question."""
    old = msg(1537000000000000000, YOGURT, "yogurt",
              "morning everyone hope the update went fine",
              "2026-08-11T09:00:00+00:00")
    got = c.preceding_context(BUDDY[-1], [old] + BUDDY)
    assert "morning everyone" not in got


def test_no_earlier_lines_gives_an_empty_string():
    lone = msg(1537121269709799466, 333, "newcomer",
               "hi, does the ledge system work on 5.7?",
               "2026-08-12T16:00:00+00:00")
    assert c.preceding_context(lone, [lone]) == ""


def test_context_is_one_line_so_the_inbox_header_survives():
    """The parser stops at the first blank line, so a newline would cut
    every field written after it."""
    noisy = msg(1537121191943340145, YOGURT, "yogurt",
                "line one\nline two\n\nline three", "2026-08-12T15:30:50+00:00")
    got = c.preceding_context(BUDDY[-1], [noisy] + BUDDY)
    assert "\n" not in got
