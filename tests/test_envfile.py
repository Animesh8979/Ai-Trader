from godmode.core.envfile import read_env_file, update_env_file


def test_update_preserves_comments_and_updates_keys(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# my config\nGODMODE_MODE=paper\nFOO=bar\n", encoding="utf-8")

    update_env_file(p, {"FOO": "baz", "NEW_KEY": "123"})

    data = read_env_file(p)
    assert data["FOO"] == "baz"          # updated in place
    assert data["NEW_KEY"] == "123"      # appended
    assert data["GODMODE_MODE"] == "paper"  # untouched
    assert "# my config" in p.read_text(encoding="utf-8")  # comment preserved


def test_update_creates_file_when_absent(tmp_path):
    p = tmp_path / ".env"
    update_env_file(p, {"ANTHROPIC_API_KEY": "secret"})
    assert read_env_file(p)["ANTHROPIC_API_KEY"] == "secret"
