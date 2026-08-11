from app.chunking.tokenizer import estimate_tokens


def test_returns_at_least_one_for_nonempty_text():
    assert estimate_tokens("kisa") >= 1


def test_roughly_char_over_four():
    text = "a" * 400
    assert estimate_tokens(text) == 100


def test_empty_string_returns_at_least_one():
    assert estimate_tokens("") == 1
