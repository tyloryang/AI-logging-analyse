import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from routers import agent_config


class InstalledSkillDiscoveryCase(unittest.TestCase):
    def test_discovers_superpowers_metadata_and_project_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = root / ".agents" / "skills"
            super_skill = skill_root / "brainstorming"
            project_skill = skill_root / "local-helper"
            super_skill.mkdir(parents=True)
            project_skill.mkdir(parents=True)
            (super_skill / "SKILL.md").write_text(
                "---\nname: brainstorming\ndescription: Refine ideas before implementation\n---\n",
                encoding="utf-8",
            )
            (project_skill / "SKILL.md").write_text(
                "---\nname: local-helper\ndescription: >\n  Local helper\n  for this project\n---\n",
                encoding="utf-8",
            )
            manifest = skill_root / ".superpowers-manifest.json"
            github_manifest = skill_root / ".github-high-star-manifest.json"
            manifest.write_text(
                json.dumps({
                    "repository": "https://github.com/obra/superpowers",
                    "ref": "main",
                    "commit": "abc123",
                    "skills": ["brainstorming"],
                }),
                encoding="utf-8",
            )

            with (
                patch.object(agent_config, "_PROJECT_ROOT", root),
                patch.object(agent_config, "_INSTALLED_SKILL_ROOTS", (skill_root,)),
                patch.object(agent_config, "_SUPERPOWERS_MANIFEST", manifest),
                patch.object(agent_config, "_GITHUB_HIGH_STAR_MANIFEST", github_manifest),
            ):
                found = agent_config._discover_installed_skills()

        by_name = {item["name"]: item for item in found}
        self.assertEqual(by_name["brainstorming"]["source"], "Superpowers")
        self.assertEqual(by_name["brainstorming"]["source_commit"], "abc123")
        self.assertEqual(by_name["local-helper"]["source"], "Project")
        self.assertEqual(by_name["local-helper"]["desc"], "Local helper for this project")

    def test_discovers_github_high_star_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = root / ".agents" / "skills"
            github_skill = skill_root / "openai-docs"
            github_skill.mkdir(parents=True)
            (github_skill / "SKILL.md").write_text(
                "---\nname: openai-docs\ndescription: Use official OpenAI docs\n---\n",
                encoding="utf-8",
            )
            github_manifest = skill_root / ".github-high-star-manifest.json"
            github_manifest.write_text(
                json.dumps({
                    "stars_checked_at": "2026-07-12",
                    "sources": [{
                        "name": "OpenAI Skills",
                        "repository": "https://github.com/openai/skills",
                        "ref": "main",
                        "commit": "def456",
                        "stars": 23552,
                        "license": "See individual skill directories",
                        "icon": "O",
                        "skills": ["openai-docs"],
                    }],
                }),
                encoding="utf-8",
            )

            with (
                patch.object(agent_config, "_PROJECT_ROOT", root),
                patch.object(agent_config, "_INSTALLED_SKILL_ROOTS", (skill_root,)),
                patch.object(agent_config, "_SUPERPOWERS_MANIFEST", skill_root / "missing.json"),
                patch.object(agent_config, "_GITHUB_HIGH_STAR_MANIFEST", github_manifest),
            ):
                found = agent_config._discover_installed_skills()

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["source"], "OpenAI Skills")
        self.assertEqual(found[0]["source_kind"], "github-high-star")
        self.assertEqual(found[0]["source_stars"], 23552)
        self.assertEqual(found[0]["source_commit"], "def456")

    def test_sync_preserves_enabled_and_tool_binding(self):
        installed = {
            "id": "installed:brainstorming",
            "icon": "⚡",
            "name": "brainstorming",
            "desc": "Updated description",
            "tags": ["Superpowers", "Installed", "SKILL.md"],
            "enabled": True,
            "tool_name": "",
            "installed": True,
            "installed_path": ".agents/skills/brainstorming",
            "source": "Superpowers",
            "source_repo": "repo",
            "source_ref": "main",
            "source_commit": "new",
        }
        records = [{
            **installed,
            "desc": "Old description",
            "enabled": False,
            "tool_name": "query_error_logs",
            "source_commit": "old",
        }]

        with patch.object(agent_config, "_discover_installed_skills", return_value=[installed]):
            changed = agent_config._sync_installed_skills(records)

        self.assertTrue(changed)
        self.assertFalse(records[0]["enabled"])
        self.assertEqual(records[0]["tool_name"], "query_error_logs")
        self.assertEqual(records[0]["source_commit"], "new")


if __name__ == "__main__":
    unittest.main()
