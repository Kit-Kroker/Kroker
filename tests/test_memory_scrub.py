from sdlc.memory.scrub import scrub


def test_scrub_redacts_api_key():
    out = scrub("used key sk-abcdefghijklmnopqrstuvwx to call the api")
    assert "sk-abcdefghijklmnopqrstuvwx" not in out
    assert "[REDACTED_API_KEY]" in out


def test_scrub_redacts_email():
    out = scrub("contact maksim.shautsou.dev@gmail.com for access")
    assert "maksim.shautsou.dev@gmail.com" not in out
    assert "[REDACTED_EMAIL]" in out


def test_scrub_redacts_password_assignment():
    out = scrub("config had password=hunter2 in it")
    assert "hunter2" not in out


def test_scrub_leaves_ordinary_text_untouched():
    text = "the merge added a retry policy with 3 attempts"
    assert scrub(text) == text
