from wbsgen.ids import assign_id, slugify, unique_id


def test_slugify_ascii():
    assert slugify("API Design", "a-") == "a-api-design"


def test_slugify_handles_punctuation():
    assert slugify("Auth: Login!", "a-") == "a-auth-login"


def test_slugify_japanese_falls_back_to_hash():
    s = slugify("要件定義", "w-")
    assert s.startswith("w-x-") and len(s) == len("w-x-") + 6


def test_slugify_mixed_drops_japanese_keeps_ascii():
    assert slugify("Login画面", "a-") == "a-login"


def test_unique_id_appends_suffix_on_collision():
    existing = {"a-api"}
    assert unique_id("a-api", existing) == "a-api-2"
    existing.add("a-api-2")
    assert unique_id("a-api", existing) == "a-api-3"


def test_assign_id_end_to_end():
    existing: set[str] = set()
    first = assign_id("API", "a-", existing)
    existing.add(first)
    second = assign_id("API", "a-", existing)
    assert first == "a-api"
    assert second == "a-api-2"
