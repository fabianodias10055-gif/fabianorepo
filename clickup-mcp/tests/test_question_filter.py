"""What reaches the support inbox, and what must never reach it.

The filter had no tests, which is how a paying customer's follow-up was
dropped for a day without anyone noticing. The first test below is that
exact message.
"""
import collect_discord as c


LAWLIET = (
    "But the aim and shoot and reload are still doing the same thing , I "
    "thought since it was an abp fix it will solve for everything so now "
    "I'm stumped"
)


def test_the_message_that_was_dropped():
    """2026-08-18, #general-support, a customer mid-conversation.

    No question mark, no leading question word, and nothing in
    PROBLEM_MARKERS. It went nowhere until STUCK_REPORT was added.
    """
    assert c.looks_like_question(LAWLIET)


def test_first_person_dead_ends_get_through():
    for text in (
        "I put it on the handgun slot and the pickup plays now but I'm stumped",
        "ive been at this for hours and im completely lost with the aim offset",
        "I corrected this part of my code but it's still the same",
        "I tried that and still no luck as it looked like it should do the same",
        "I'm struggling with the animation section of the ledge tutorial",
        "yeah I would love to add a sliding system but i don't know where to add it",
    ):
        assert c.looks_like_question(text), text


def test_praise_and_thanks_still_rejected():
    """The guard that keeps the queue a work list rather than a feed."""
    for text in (
        "thank you so much, this tutorial is amazing and it worked perfectly",
        "great work on the weapon system, love it, keep it up man",
        "Ah ok thank you very much, that solved it for me",
    ):
        assert not c.looks_like_question(text), text


def test_offers_of_help_still_rejected():
    for text in (
        "Nice one! if you need help with the retarget just let me know, happy to help",
        "feel free to ask if anything about the ledge setup is unclear to you",
    ):
        assert not c.looks_like_question(text), text


def test_a_bare_link_is_not_a_question():
    assert not c.looks_like_question("https://discord.com/channels/1/2/3")


def test_ordinary_questions_still_get_through():
    """The paths that already worked must keep working."""
    for text in (
        "How do I migrate the weapon system into my own project on 5.7?",
        "the pickup montage is not playing after I merged it into my project",
        "Does this work with GASP or do I need the third person template",
    ):
        assert c.looks_like_question(text), text


def test_stuck_report_stays_a_narrow_door():
    """Measured over the logged history it admitted eleven messages.

    A rewrite that turns it into a broad rule should fail here rather than
    quietly triple the inbox.
    """
    noise = (
        "well then ... better than nothing",
        "Meh either way it's still fun",
        "sorry I don't know but on the other hand gg is amazing",
        "oh I had found a similar bp from a very old forum",
    )
    admitted = [t for t in noise if c.looks_like_question(t)]
    assert not admitted, admitted
