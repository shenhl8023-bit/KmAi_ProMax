# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class SimilarPartsConfigTests(unittest.TestCase):
    def test_top_k_loads_valid_value_and_falls_back_to_five(self):
        from KmMpsMcpServer.backend import agent_config

        original_path = agent_config.CONFIG_PATH
        original_base = agent_config.CONFIG_BASE_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / "config.ini"
                agent_config.CONFIG_PATH = str(config_path)
                agent_config.CONFIG_BASE_DIR = temp_dir

                config_path.write_text("[SimilarParts]\ntop_k = 4\n", encoding="utf-8")
                self.assertEqual(agent_config._load_config()["similar_parts_top_k"], 4)

                config_path.write_text("[SimilarParts]\ntop_k = 9\n", encoding="utf-8")
                self.assertEqual(agent_config._load_config()["similar_parts_top_k"], 9)

                config_path.write_text("[SimilarParts]\ntop_k = 1001\n", encoding="utf-8")
                self.assertEqual(agent_config._load_config()["similar_parts_top_k"], 5)

                config_path.write_text("[SimilarParts]\ntop_k = invalid\n", encoding="utf-8")
                self.assertEqual(agent_config._load_config()["similar_parts_top_k"], 5)
        finally:
            agent_config.CONFIG_PATH = original_path
            agent_config.CONFIG_BASE_DIR = original_base

    def test_feature_service_settings_and_relative_index_path_are_loaded(self):
        from KmMpsMcpServer.backend import agent_config
        original_path, original_base = agent_config.CONFIG_PATH, agent_config.CONFIG_BASE_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / "config.ini"
                agent_config.CONFIG_PATH, agent_config.CONFIG_BASE_DIR = str(config_path), temp_dir
                config_path.write_text(
                    "[SimilarParts]\nmatching_backend = feature_vector\n"
                    "feature_api_base_url = http://127.0.0.1:12345/\n"
                    "feature_api_timeout_seconds = 25\n"
                    "feature_model_version = deployment-2\n"
                    "feature_index_file = cache/features.sqlite3\n", encoding="utf-8",
                )
                config = agent_config._load_config()
                self.assertEqual(config["similar_parts_matching_backend"], "feature_vector")
                self.assertEqual(config["similar_parts_feature_api_base_url"], "http://127.0.0.1:12345")
                self.assertEqual(config["similar_parts_feature_api_timeout_seconds"], 25)
                self.assertEqual(config["similar_parts_feature_model_version"], "deployment-2")
                self.assertEqual(config["similar_parts_feature_index_file"], str(Path(temp_dir) / "cache/features.sqlite3"))
        finally:
            agent_config.CONFIG_PATH, agent_config.CONFIG_BASE_DIR = original_path, original_base

    def test_win7_lite_mode_and_prebuilt_model_dir_are_loaded(self):
        from KmMpsMcpServer.backend import agent_config

        original_path = agent_config.CONFIG_PATH
        original_base = agent_config.CONFIG_BASE_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / "config.ini"
                agent_config.CONFIG_PATH = str(config_path)
                agent_config.CONFIG_BASE_DIR = temp_dir
                config_path.write_text(
                    "[SimilarParts]\n"
                    "win7_lite_mode = true\n"
                    "prebuilt_model_dir = models\n",
                    encoding="utf-8",
                )
                loaded = agent_config._load_config()
                self.assertTrue(loaded["similar_parts_win7_lite_mode"])
                self.assertEqual(
                    loaded["similar_parts_prebuilt_model_dir"],
                    str(Path(temp_dir) / "models"),
                )
        finally:
            agent_config.CONFIG_PATH = original_path
            agent_config.CONFIG_BASE_DIR = original_base


if __name__ == "__main__":
    unittest.main()
