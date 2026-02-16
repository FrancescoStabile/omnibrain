"""
Tests — omnibrain-skill CLI (skill_cli.py).

Verifies:
    - init: scaffolds correct structure with manifest, handlers, tests, README
    - Slug generation
    - Category & permissions defaults/overrides
    - Error on existing directory
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnibrain.skill_cli import _slugify, _title_from_slug, init_skill, main


class TestSlugify:
    def test_basic(self):
        assert _slugify("My Cool Skill") == "my-cool-skill"

    def test_special_chars(self):
        assert _slugify("weather_v2!") == "weather-v2"

    def test_empty_fallback(self):
        assert _slugify("!!!") == "my-skill"

    def test_already_slug(self):
        assert _slugify("email-manager") == "email-manager"


class TestTitleFromSlug:
    def test_basic(self):
        assert _title_from_slug("my-cool-skill") == "My Cool Skill"


class TestInitSkill:
    def test_creates_full_structure(self, tmp_path):
        path = init_skill("test-skill", output_dir=tmp_path)
        assert path.exists()
        assert (path / "skill.yaml").exists()
        assert (path / "handlers" / "poll.py").exists()
        assert (path / "handlers" / "ask.py").exists()
        assert (path / "tests" / "test_handlers.py").exists()
        assert (path / "tests" / "__init__.py").exists()
        assert (path / "README.md").exists()

    def test_manifest_content(self, tmp_path):
        path = init_skill("weather-bot", output_dir=tmp_path, category="productivity")
        manifest = (path / "skill.yaml").read_text()
        assert "name: weather-bot" in manifest
        assert "category: productivity" in manifest
        assert "read_memory" in manifest

    def test_custom_permissions(self, tmp_path):
        path = init_skill(
            "email-bot",
            output_dir=tmp_path,
            permissions=["read_memory", "write_memory", "google_gmail"],
        )
        manifest = (path / "skill.yaml").read_text()
        assert "google_gmail" in manifest

    def test_with_event_handler(self, tmp_path):
        path = init_skill("event-skill", output_dir=tmp_path, with_event_handler=True)
        assert (path / "handlers" / "event.py").exists()
        manifest = (path / "skill.yaml").read_text()
        assert "on_event" in manifest

    def test_no_event_handler_by_default(self, tmp_path):
        path = init_skill("simple-skill", output_dir=tmp_path)
        assert not (path / "handlers" / "event.py").exists()

    def test_raises_on_existing_dir(self, tmp_path):
        init_skill("dupe-skill", output_dir=tmp_path)
        with pytest.raises(FileExistsError):
            init_skill("dupe-skill", output_dir=tmp_path)

    def test_handler_files_are_valid_python(self, tmp_path):
        path = init_skill("syntax-check", output_dir=tmp_path, with_event_handler=True)
        for handler in ["poll.py", "ask.py", "event.py"]:
            code = (path / "handlers" / handler).read_text()
            compile(code, handler, "exec")  # raises SyntaxError if invalid

    def test_test_file_is_valid_python(self, tmp_path):
        path = init_skill("test-check", output_dir=tmp_path)
        code = (path / "tests" / "test_handlers.py").read_text()
        compile(code, "test_handlers.py", "exec")

    def test_readme_contains_skill_name(self, tmp_path):
        path = init_skill("readme-skill", output_dir=tmp_path)
        readme = (path / "README.md").read_text()
        assert "Readme Skill" in readme

    def test_author_in_manifest(self, tmp_path):
        path = init_skill("auth-skill", output_dir=tmp_path, author="francesco")
        manifest = (path / "skill.yaml").read_text()
        assert "author: francesco" in manifest


class TestCLIMain:
    def test_init_success(self, tmp_path):
        rc = main(["init", "cli-test", "--output-dir", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "cli-test" / "skill.yaml").exists()

    def test_init_duplicate(self, tmp_path):
        main(["init", "dup-test", "--output-dir", str(tmp_path)])
        rc = main(["init", "dup-test", "--output-dir", str(tmp_path)])
        assert rc == 1

    def test_no_command_shows_help(self, capsys):
        rc = main([])
        assert rc == 0

    def test_publish_placeholder(self):
        rc = main(["publish"])
        assert rc == 0
