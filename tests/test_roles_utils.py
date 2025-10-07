from roles_utils import normalize_roles


def test_normalize_roles_from_string():
    assert normalize_roles("admin") == ["admin"]


def test_normalize_roles_removes_empty_entries_and_duplicates():
    raw = ["  admin  ", "", "admin", "finance"]
    assert normalize_roles(raw) == ["admin", "finance"]


def test_normalize_roles_handles_nested_iterables():
    raw = ["manager\nteam", [" admin ", None], ("team", "support"), ["support"]]
    assert normalize_roles(raw) == ["manager", "team", "admin", "support"]
