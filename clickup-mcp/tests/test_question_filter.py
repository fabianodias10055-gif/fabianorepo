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


def test_a_forum_title_is_the_question():
    """#support-hub, 2026-02-03, opened with a video and no words.

    The collector falls back to the post title when the body alone fails,
    so these two assertions are the contract that fallback depends on.
    """
    body = ""
    title = "Ledge System doesn't work on 5.7"
    assert not c.looks_like_question(body)
    assert c.looks_like_question(title + ". " + body)


# ---- one filter, two platforms ----
import question_filter as qf


def test_a_youtube_question_is_shorter_than_a_chat_one():
    """Comments are terser. The 25 floor killed 33 real ones like these."""
    for text in ("will this work in alsv4?", "Wow is this replicated?",
                 "Is this tut ue5.3?", "where are the anims from"):
        assert qf.classify(text, qf.MIN_COMMENT) == qf.QUESTION, text
        # And the same text is correctly too thin to be a chat message.
        assert qf.classify(text, qf.MIN_CHAT) != qf.QUESTION, text


def test_the_youtube_filter_used_to_miss_these():
    """No question mark, no leading question word, still a support request."""
    for text in ("Press F logic doesn't work for me in 5.4",
                 "my problem is that when I drop a physic item it goes through the floor",
                 "starting at 10:05, did not mentioned or show how it was been fixed"):
        assert qf.classify(text, qf.MIN_COMMENT) == qf.QUESTION, text


def test_praise_comes_back_labelled_instead_of_discarded():
    for text in ("Thank you so much bro keep up the great work",
                 "Best tutorial, thank you", "You are a legend, thank you so much!"):
        assert qf.classify(text, qf.MIN_COMMENT) == qf.PRAISE, text


def test_a_complaint_wearing_a_compliment_is_still_a_question():
    """The guard is for messages that are ONLY praise, so it runs last."""
    text = ("Is it really not possible to do this with the hands attaching to "
            "the box, the whole sliding makes it look so bad. Awesome tutorial tho")
    assert qf.classify(text, qf.MIN_COMMENT) == qf.QUESTION


def test_a_bare_youtube_link_is_not_a_question():
    """Its own query string used to pass the question-mark test."""
    assert qf.classify("Tutorial: https://www.youtube.com/watch?v=fJHAtQmrj4U",
                       qf.MIN_COMMENT) == ""


def test_the_two_collectors_share_one_implementation():
    """They drifted once. This fails if a second copy appears."""
    import collect_discord, collect_youtube
    assert collect_discord._classify is qf.classify
    assert collect_youtube.qf.classify is qf.classify


def test_a_soft_request_for_a_better_solution_is_a_question():
    """No problem word, no question mark, opens with "if": all three gates
    missed it, and it fell through as chatter. It is asking for help as
    plainly as "how do I". This is the message the panel visibly dropped."""
    text = ("if u can think of a better solution for it, lemme know, "
            "id really appreciate it")
    assert qf.classify(text, qf.MIN_COMMENT) == qf.QUESTION


def test_asking_for_suggestions_or_a_better_way_is_a_question():
    for text in ("any suggestions on how to make the arena bigger",
                 "is there a better way to spawn enemies here",
                 "if anyone has a better approach let me know"):
        assert qf.classify(text, qf.MIN_COMMENT) == qf.QUESTION, text


def test_a_problem_report_that_contains_an_offer_phrase_survives():
    """The offer gate used to run before the problem test, so a real report
    that happened to include "let me know if you need" died on the offer."""
    text = "It doesn't work when I equip; let me know if you need more details"
    assert qf.classify(text, qf.MIN_COMMENT) == qf.QUESTION


def test_a_plain_offer_of_help_is_still_dropped():
    """The offer's own "need help" words must not read as the request it is
    describing. These carry no problem or request of their own."""
    for text in ("if you need help, we're here happy to help anytime",
                 "let me know if you need anything, glad to assist"):
        assert qf.classify(text, qf.MIN_COMMENT) == "", text
