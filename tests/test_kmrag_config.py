# -*- coding: utf-8 -*-
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from backend import agent_config


class KmragConfigTests(unittest.TestCase):
    def test_health_status_has_only_safe_kmrag_fields(self):
        status = agent_config._public_kmrag_config({
            "kmrag_enabled": True,
            "kmrag_base_url": "https://private.example",
            "kmrag_bearer_token": "secret",
        })

        self.assertEqual({"enabled", "configured", "auth_mode"}, set(status))
    def test_public_kmrag_status_and_runtime_env_do_not_expose_credentials(self):
        config = {
            "kmrag_enabled": True,
            "kmrag_base_url": "https://kmrag.example.test",
            "kmrag_api_key": "secret-api-key",
            "kmrag_bearer_token": "secret-bearer-token",
            "kmrag_timeout": 12,
        }

        self.assertEqual(
            {"enabled": True, "configured": True, "auth_mode": "api_key"},
            agent_config._public_kmrag_config(config),
        )
        runtime_env = agent_config._kmrag_runtime_env(config)
        self.assertEqual("https://kmrag.example.test", runtime_env["KMRAG_BASE_URL"])
        self.assertEqual("secret-api-key", runtime_env["KMRAG_API_KEY"])
        self.assertEqual("12", runtime_env["KMRAG_TIMEOUT"])
        self.assertNotIn("kmrag_base_url", agent_config._public_kmrag_config(config))
        self.assertNotIn("secret-api-key", repr(agent_config._public_kmrag_config(config)))

    def test_runtime_env_adds_kmrag_host_to_proxy_bypass(self):
        runtime_env = agent_config._kmrag_runtime_env({
            "kmrag_enabled": True,
            "kmrag_base_url": "https://rag.kmyun.com.cn",
            "kmrag_api_key": "secret-api-key",
            "kmrag_bearer_token": "",
            "kmrag_timeout": 30,
        })

        self.assertIn("rag.kmyun.com.cn", runtime_env["NO_PROXY"])
        self.assertIn("rag.kmyun.com.cn", runtime_env["no_proxy"])


if __name__ == "__main__":
    unittest.main()
