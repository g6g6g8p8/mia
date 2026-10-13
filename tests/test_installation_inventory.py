"""Inventory never follows user links or emits credentials/other app commands."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("installation_inventory", Path(__file__).resolve().parents[1] / "scripts/installation_inventory.py")
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class InstallationInventoryTests(unittest.TestCase):
    def test_unverified_path_is_not_authority_and_linked_tree_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            personal = home / "personal"
            personal.mkdir()
            (personal / "pyproject.toml").write_text('name = "mia-personal-ai"\n')
            candidate = home / "mia-onboarding"
            candidate.symlink_to(personal, target_is_directory=True)
            self.assertEqual(inventory.candidate(candidate)["inspection"], "skipped-linked-path")
            other = home / "unverified"
            other.mkdir()
            result = inventory.candidate(other)
            self.assertEqual(result["identification"], "unverified-candidate")
            self.assertFalse(result["cleanup_authorized_by_inventory"])

    def test_managed_metadata_never_discloses_private_values_or_escapes_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mia"
            root.mkdir()
            secret = "DO-NOT-EMIT-SECRET"
            (root / "installation.json").write_text(json.dumps({"manager_protocol": 2, "port": 8123, "host": "127.0.0.1", "api_key": secret}))
            (root / "manager.py").write_text("")
            (root / "machine.env").write_text("MIA_AI_API_KEY=" + secret)
            (root / "active.json").write_text(json.dumps({"version": "0.2.0a12", "data": "../vault", "api_key": secret}))
            result = inventory.candidate(root)
            self.assertEqual(result["identification"], "managed-mia")
            self.assertEqual(len(result["databases"]), 1)
            self.assertNotIn(secret, json.dumps(result))
            self.assertEqual(result["version"], "0.2.0a12")

    def test_service_arguments_and_environment_are_not_emitted(self):
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            services = home / "Library/LaunchAgents"
            services.mkdir(parents=True)
            secret = "DO-NOT-EMIT-SECRET"
            (services / "local.mia.123456abcdef.plist").write_bytes(plistlib.dumps({"ProgramArguments": ["python", "/private/mia/manager.py", "--api-key", secret], "EnvironmentVariables": {"SECRET": secret}}))
            (services / "com.other-app.plist").write_text(secret)
            result = inventory.registrations(home)
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["mia_program_marker"])
            self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn("ProgramArguments", json.dumps(result))

    def test_legacy_a11_identifies_effective_data_and_runtime_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mia"
            root.mkdir()
            (root / "installation.json").write_text(json.dumps({"format": 1, "host": "127.0.0.1", "port": 8123, "python": "/usr/bin/python3"}))
            (root / "active.json").write_text(json.dumps({"version": "0.2.0a11", "release": "releases/trusted-release", "data": "data/restored-previous"}))
            (root / "manager.py").write_text('"""Conscious native operations. Old manager."""\nclass Manager:\n    app = "mia.app:app"\n')
            with patch.object(inventory, "probe", side_effect=AssertionError("runtime must not execute")):
                result = inventory.candidate(root)
            self.assertEqual(result["identification"], "managed-mia-legacy-candidate")
            self.assertEqual(result["application_runtime_candidate"]["path"], str(root / "releases/trusted-release/venv/bin/python"))
            self.assertEqual(result["bootstrap_python_candidate"]["path"], "/usr/bin/python3")
            self.assertEqual(result["databases"][-1]["path"], str(root / "data/restored-previous/mia.db"))
            self.assertFalse(result["cleanup_authorized_by_inventory"])

    def test_invalid_legacy_active_paths_remain_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "installation.json").write_text(json.dumps({"format": 1, "host": "127.0.0.1", "port": 8123, "python": "/usr/bin/python3"}))
            (root / "active.json").write_text(json.dumps({"version": "0.2.0a11", "release": "../other-product", "data": "data/initial"}))
            (root / "manager.py").write_text('"""Conscious native operations. Old manager."""\nclass Manager:\n    app = "mia.app:app"\n')
            self.assertEqual(inventory.candidate(root)["identification"], "unverified-candidate")

    def test_manual_runtime_path_is_reported_without_running_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text('name = "mia-personal-ai"\n')
            (root / "mia").mkdir()
            (root / "mia/__init__.py").write_text('__version__ = "0.2.0a11"\n')
            with patch.object(inventory, "probe", return_value={"available": False}) as query:
                result = inventory.candidate(root)
            self.assertEqual(query.call_args.args[0][0], "git")
            self.assertEqual(result["application_runtime_candidate"]["path"], str(root / ".venv/bin/python"))
            self.assertIsNone(result["bootstrap_python_candidate"])
            self.assertEqual(result["checkout_version"], "0.2.0a11")
            self.assertEqual(result["installed_runtime_version"], "not-executed")

    def test_container_query_omits_commands_env_and_other_products(self):
        fields = ["abcdef", "mia-pilot-mia-1", "mia:test", "Up 1 hour", "127.0.0.1:8123->8123/tcp", "mia"]
        other = ["other", "cabeca-api", "cabeca:test", "Up 1 day", "", "cabeca-api"]
        output = "\n".join("\t".join(json.dumps(field) for field in row) for row in (fields, other))
        with patch.object(inventory, "probe", return_value={"available": True, "completed": True, "output": output}) as query:
            result = inventory.containers()
        self.assertEqual([item["name"] for item in result["mia_candidates"]], ["mia-pilot-mia-1"])
        self.assertNotIn("cabeca", json.dumps(result))
        arguments = query.call_args.args[0]
        self.assertEqual(arguments[:3], ["docker", "ps", "-a"])
        self.assertNotIn(".Command", arguments[-1])
        self.assertNotIn(".Env", arguments[-1])
        self.assertFalse(result["mia_candidates"][0]["cleanup_authorized_by_inventory"])

    def test_listener_only_emits_pid_and_executable_name(self):
        with patch.object(inventory, "probe", return_value={"available": True, "completed": True, "output": "p123\ncPython\nu1000\n"}) as query:
            result = inventory.listeners(8123)
        self.assertEqual(result["processes"], [{"pid": 123, "executable_name": "Python", "uid": 1000}])
        self.assertEqual(query.call_args.args[0][-1], "-Fpcu")


if __name__ == "__main__":
    unittest.main()
