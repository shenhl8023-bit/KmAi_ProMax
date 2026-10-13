import os
import tempfile
import unittest
from pathlib import Path

from backend import agent_profiles


class AgentProfilesTest(unittest.TestCase):
    def setUp(self):
        self._old_project_agents_dir = agent_profiles.PROJECT_AGENTS_DIR
        self._old_user_agents_dir = agent_profiles.USER_AGENTS_DIR
        self._old_enable_user_agents = os.environ.pop("KMAI_ENABLE_USER_AGENTS", None)

    def tearDown(self):
        agent_profiles.PROJECT_AGENTS_DIR = self._old_project_agents_dir
        agent_profiles.USER_AGENTS_DIR = self._old_user_agents_dir
        if self._old_enable_user_agents is None:
            os.environ.pop("KMAI_ENABLE_USER_AGENTS", None)
        else:
            os.environ["KMAI_ENABLE_USER_AGENTS"] = self._old_enable_user_agents

    def test_default_loads_only_project_agents(self):
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as user_dir:
            Path(project_dir, "project-agent.md").write_text("Project prompt", encoding="utf-8")
            Path(user_dir, "user-agent.md").write_text("User prompt", encoding="utf-8")
            agent_profiles.PROJECT_AGENTS_DIR = project_dir
            agent_profiles.USER_AGENTS_DIR = user_dir

            agent_ids = [profile["id"] for profile in agent_profiles.list_agent_profiles()]

        self.assertIn("default", agent_ids)
        self.assertIn("project-agent", agent_ids)
        self.assertNotIn("user-agent", agent_ids)

    def test_user_agents_require_explicit_environment_opt_in(self):
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as user_dir:
            Path(project_dir, "project-agent.md").write_text("Project prompt", encoding="utf-8")
            Path(user_dir, "user-agent.md").write_text("User prompt", encoding="utf-8")
            agent_profiles.PROJECT_AGENTS_DIR = project_dir
            agent_profiles.USER_AGENTS_DIR = user_dir
            os.environ["KMAI_ENABLE_USER_AGENTS"] = "1"

            agent_ids = [profile["id"] for profile in agent_profiles.list_agent_profiles()]

        self.assertIn("project-agent", agent_ids)
        self.assertIn("user-agent", agent_ids)

    def test_kmrag_knowledge_agent_is_discovered_with_its_strict_prompt(self):
        profiles = {
            profile["id"]: profile
            for profile in agent_profiles.list_agent_profiles()
        }

        self.assertEqual("kmrag-knowledge-agent", agent_profiles.KMRAG_AGENT_ID)
        profile = profiles[agent_profiles.KMRAG_AGENT_ID]
        self.assertEqual("KMRAG 知识助手", profile["name"])
        self.assertIn("kmrag_search", profile["prompt"])
        self.assertIn("不得调用 3DMPS", profile["prompt"])


if __name__ == "__main__":
    unittest.main()
