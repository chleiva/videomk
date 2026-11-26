from engine import engagement


def test_flag_off_and_photos_give_nothing(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_PROMPT", "0")
    assert engagement.block("explain entropy", 2) == ""
    monkeypatch.setenv("ENGAGEMENT_PROMPT", "1")
    assert engagement.block("my trip", 2, photos=True) == ""


def test_hook_rule_depends_on_length(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_PROMPT", "1")
    assert "first 2 seconds" in engagement.block("a topic", 0.25)
    assert "cold open" in engagement.block("a topic", 8)
    assert "under 8 seconds" in engagement.block("a topic", 2)


def test_vague_rule_only_for_tiny_prompts_and_language(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_PROMPT", "1")
    assert "VAGUE REQUEST" in engagement.block("explain entropy", 2)
    assert "VAGUE REQUEST" not in engagement.block("How does CRISPR gene editing actually work? Cover the bacterial origin and one approved therapy", 4)
    assert "en este video" in engagement.block("explica la inflación", 2, "es")
    assert len(engagement.block("x", 2)) < 2800
