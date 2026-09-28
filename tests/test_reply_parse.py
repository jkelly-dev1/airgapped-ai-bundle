"""The paid run's reply parser reads the first complete JSON object.

One span from the first "{" to the last "}" fails on a reply that carries two
objects, or a braced word in prose before the object.
"""

from scripts.real_run import parse


def test_the_first_object_is_read_when_the_reply_carries_two():
    assert parse('{"a": 1}\n{"b": 2}') == {"a": 1}


def test_a_braced_word_in_prose_before_the_object_is_skipped():
    assert parse('Result {see below}: {"a": 1}') == {"a": 1}
    # A truncated reply is not an object, and the complete object nested
    # inside it (a fragment of it) is not the reply either.
    from scripts.real_run import first_json_object
    assert first_json_object('{"a": {"b": 1}, "c": [') is None
    assert first_json_object('Result {see below}: {"a": {"b": 1}}') == {"a": {"b": 1}}