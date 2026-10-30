"""Checks on the release packaging: versions, PyInstaller spec, Linux files and scripts."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import autotyper

try:
    import yaml
except ImportError:  # PyYAML is only needed for the workflow checks
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "AutoTyper.spec"
WORKFLOWS = ROOT / ".github" / "workflows"
LINUX_DIR = ROOT / "packaging" / "linux"
BASH = None if os.name == "nt" else shutil.which("bash")

BUNDLE_ID = "com.jlaportebot.autotyper"
USAGE_EXIT_CODE = 2
SCRIPT_TIMEOUT = 60


def read_version_from_pyproject():
    match = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    return match.group(1)


class VersionsAgree(unittest.TestCase):
    def test_package_matches_pyproject(self):
        self.assertEqual(autotyper.__version__, read_version_from_pyproject())

    def test_windows_resource_matches_pyproject(self):
        version = read_version_from_pyproject()
        text = (ROOT / "version_info.txt").read_text()
        as_tuple = ", ".join([*version.split("."), "0"])
        self.assertEqual(text.count(f"({as_tuple})"), 2)
        self.assertIn(f"u'FileVersion', u'{version}'", text)
        self.assertIn(f"u'ProductVersion', u'{version}'", text)


class FakePyInstaller:
    """Records the calls a spec file makes to the PyInstaller build classes."""

    def __init__(self):
        self.calls = {}

    def recorder(self, name):
        def record(*args, **kwargs):
            self.calls[name] = (args, kwargs)
            return mock.MagicMock(name=name)

        return record

    def namespace(self):
        names = ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE")
        return {name: self.recorder(name) for name in names}


def evaluate_spec(platform):
    """Run the spec as PyInstaller would on ``platform``; returns the recorded calls."""
    fake = FakePyInstaller()
    namespace = {"__name__": "spec", "__file__": str(SPEC), **fake.namespace()}
    code = compile(SPEC.read_text(encoding="utf-8"), str(SPEC), "exec")
    with mock.patch.object(sys, "platform", platform), mock.patch.object(
        sys, "path", list(sys.path)
    ), mock.patch("os.getcwd", return_value=str(ROOT)):
        exec(code, namespace)
    return fake.calls


class SpecWindows(unittest.TestCase):
    def setUp(self):
        self.calls = evaluate_spec("win32")
        self.exe = self.calls["EXE"][1]

    def test_builds_a_windowed_one_file_exe_with_icon_and_version(self):
        self.assertEqual(self.exe["name"], "AutoTyper")
        self.assertFalse(self.exe["console"])
        self.assertTrue(self.exe["icon"].endswith("autotyper.ico"))
        self.assertTrue(self.exe["version"].endswith("version_info.txt"))
        self.assertNotIn("exclude_binaries", self.exe)

    def test_has_no_bundle_or_collect_step(self):
        self.assertNotIn("BUNDLE", self.calls)
        self.assertNotIn("COLLECT", self.calls)

    def test_needs_no_extra_hidden_imports(self):
        self.assertEqual(self.calls["Analysis"][1]["hiddenimports"], [])


class SpecMacos(unittest.TestCase):
    def setUp(self):
        self.calls = evaluate_spec("darwin")
        self.bundle = self.calls["BUNDLE"][1]
        self.plist = self.bundle["info_plist"]

    def test_builds_an_app_bundle_with_icns_icon(self):
        self.assertEqual(self.bundle["name"], "AutoTyper.app")
        self.assertTrue(self.bundle["icon"].endswith("autotyper.icns"))
        self.assertEqual(self.bundle["bundle_identifier"], BUNDLE_ID)

    def test_bundle_wraps_a_one_dir_executable_without_a_console(self):
        exe = self.calls["EXE"][1]
        self.assertTrue(exe["exclude_binaries"])
        self.assertFalse(exe["console"])
        self.assertIsNone(exe["version"])
        self.assertIn("COLLECT", self.calls)

    def test_info_plist_describes_the_app(self):
        version = autotyper.__version__
        expected = {
            "CFBundleName": "AutoTyper",
            "CFBundleDisplayName": "AutoTyper",
            "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "CFBundleExecutable": "AutoTyper",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "© 2026 jlaportebot",
        }
        for key, value in expected.items():
            self.assertEqual(self.plist[key], value, key)
        self.assertNotIn("CFBundleDocumentTypes", self.plist)

    def test_bundles_the_pyobjc_frameworks(self):
        hidden = self.calls["Analysis"][1]["hiddenimports"]
        self.assertIn("Quartz", hidden)
        self.assertIn("AppKit", hidden)

    def test_bundles_application_services_for_the_accessibility_check(self):
        hidden = self.calls["Analysis"][1]["hiddenimports"]
        self.assertIn("ApplicationServices", hidden)
        self.assertIn("HIServices", hidden)


class SpecLinux(unittest.TestCase):
    def setUp(self):
        self.calls = evaluate_spec("linux")
        self.exe = self.calls["EXE"][1]

    def test_builds_a_windowed_one_file_binary_named_without_extension(self):
        self.assertEqual(self.exe["name"], "AutoTyper")
        self.assertFalse(self.exe["console"])
        self.assertTrue(self.exe["icon"].endswith("autotyper.png"))
        self.assertIsNone(self.exe["version"])
        self.assertNotIn("exclude_binaries", self.exe)

    def test_bundles_python_xlib_and_the_xtest_extension(self):
        hidden = self.calls["Analysis"][1]["hiddenimports"]
        self.assertIn("Xlib", hidden)
        self.assertIn("Xlib.ext.xtest", hidden)

    def test_has_no_bundle_step(self):
        self.assertNotIn("BUNDLE", self.calls)


class SpecAssets(unittest.TestCase):
    def test_every_icon_the_spec_names_is_committed(self):
        for name in ("autotyper.ico", "autotyper.icns", "autotyper.png"):
            self.assertGreater((ROOT / "assets" / name).stat().st_size, 0, name)

    def test_icon_files_have_the_right_magic_bytes(self):
        magic = {
            "autotyper.ico": b"\x00\x00\x01\x00",
            "autotyper.icns": b"icns",
            "autotyper.png": b"\x89PNG",
        }
        for name, prefix in magic.items():
            self.assertTrue((ROOT / "assets" / name).read_bytes().startswith(prefix), name)


class LinuxAppDirFiles(unittest.TestCase):
    def test_desktop_entry_has_the_required_keys(self):
        lines = (LINUX_DIR / "AutoTyper.desktop").read_text().splitlines()
        self.assertEqual(lines[0], "[Desktop Entry]")
        entries = dict(line.split("=", 1) for line in lines[1:] if line)
        self.assertEqual(entries["Type"], "Application")
        self.assertEqual(entries["Name"], "AutoTyper")
        self.assertEqual(entries["Exec"], "AutoTyper")
        self.assertEqual(entries["Icon"], "AutoTyper")
        self.assertEqual(entries["Terminal"], "false")
        self.assertEqual(entries["Categories"], "Utility;Accessibility;")
        self.assertEqual(entries["StartupWMClass"], "AutoTyper")

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-validate missing")
    def test_desktop_entry_passes_the_freedesktop_validator(self):
        result = subprocess.run(
            ["desktop-file-validate", str(LINUX_DIR / "AutoTyper.desktop")],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_apprun_execs_the_bundled_binary(self):
        text = (LINUX_DIR / "AppRun").read_text()
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertIn('exec "$HERE/usr/bin/AutoTyper" "$@"', text)

    @unittest.skipIf(os.name == "nt", "file modes are not meaningful on Windows")
    def test_apprun_and_scripts_are_executable(self):
        for path in (
            LINUX_DIR / "AppRun",
            ROOT / "tools" / "build_appimage.sh",
            ROOT / "tools" / "build_dmg.sh",
            ROOT / "tools" / "smoke_check.sh",
        ):
            self.assertTrue(os.access(path, os.X_OK), path.name)


def run_script(*args):
    return subprocess.run(
        [BASH, *map(str, args)],
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUT,
        cwd=tempfile.gettempdir(),
    )


@unittest.skipUnless(BASH, "bash is not available")
class ShellScripts(unittest.TestCase):
    def test_scripts_have_valid_bash_syntax(self):
        for name in ("build_appimage.sh", "build_dmg.sh", "smoke_check.sh"):
            result = run_script("-n", ROOT / "tools" / name)
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_dmg_script_check_mode_only_checks_syntax(self):
        result = run_script(ROOT / "tools" / "build_dmg.sh", "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("syntax ok", result.stdout)

    @unittest.skipIf(sys.platform == "darwin", "the macOS runner may legitimately build")
    def test_dmg_script_refuses_to_build_off_macos(self):
        result = run_script(ROOT / "tools" / "build_dmg.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must run on macOS", result.stderr)

    def test_appimage_script_needs_an_architecture(self):
        result = run_script(ROOT / "tools" / "build_appimage.sh")
        self.assertEqual(result.returncode, USAGE_EXIT_CODE)
        self.assertIn("usage:", result.stderr)

    def test_appimage_script_rejects_unknown_architectures_before_building(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = run_script(ROOT / "tools" / "build_appimage.sh", "riscv64", out_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported architecture", result.stderr)
            self.assertEqual(os.listdir(out_dir), [])

    def test_appimage_script_rejects_a_binary_of_the_wrong_architecture(self):
        with tempfile.TemporaryDirectory() as out_dir:
            binary = Path(out_dir) / "AutoTyper"
            binary.write_text("#!/bin/sh\n")
            binary.chmod(0o755)
            result = run_script(ROOT / "tools" / "build_appimage.sh", "x86_64", out_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("is not a x86_64 binary", result.stderr)


@unittest.skipUnless(BASH, "bash is not available")
class SmokeCheckScript(unittest.TestCase):
    def check(self, *command):
        return run_script(ROOT / "tools" / "smoke_check.sh", *command)

    def test_passes_when_the_command_prints_the_ok_marker(self):
        result = self.check("echo", "AUTOTYPER_SMOKE_OK platform=test backend=test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AUTOTYPER_SMOKE_OK", result.stdout)

    def test_fails_when_the_marker_is_missing(self):
        result = self.check("echo", "AUTOTYPER_SMOKE_FAIL: no display")
        self.assertEqual(result.returncode, 1)
        self.assertIn("AUTOTYPER_SMOKE_FAIL", result.stdout)
        self.assertIn("did not print AUTOTYPER_SMOKE_OK", result.stderr)

    def test_fails_when_the_command_exits_non_zero_even_with_the_marker(self):
        result = self.check("sh", "-c", "echo AUTOTYPER_SMOKE_OK; exit 3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited with status 3", result.stderr)

    def test_needs_a_command(self):
        result = self.check()
        self.assertEqual(result.returncode, USAGE_EXIT_CODE)


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class Workflows(unittest.TestCase):
    def load(self, name):
        return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))

    def test_every_workflow_parses_and_defines_jobs(self):
        names = sorted(path.name for path in WORKFLOWS.glob("*.yml"))
        self.assertEqual(
            names,
            ["build-linux.yml", "build-macos.yml", "build-windows.yml", "ci.yml", "release.yml"],
        )
        for name in names:
            self.assertTrue(self.load(name)["jobs"], name)

    def test_release_publishes_after_all_three_platforms_build(self):
        jobs = self.load("release.yml")["jobs"]
        self.assertEqual(set(jobs["publish"]["needs"]), {"windows", "linux", "macos"})
        self.assertEqual(set(jobs), {"windows", "linux", "macos", "publish"})

    def test_ci_covers_linux_macos_and_windows(self):
        runners = {job["runs-on"] for job in self.load("ci.yml")["jobs"].values()}
        self.assertTrue({"macos-15", "windows-latest"} <= runners)

    def test_build_matrices_use_native_runners_for_each_architecture(self):
        linux = self.load("build-linux.yml")["jobs"]["build"]["strategy"]["matrix"]["include"]
        macos = self.load("build-macos.yml")["jobs"]["build"]["strategy"]["matrix"]["include"]
        self.assertEqual({item["os"] for item in linux}, {"ubuntu-24.04", "ubuntu-24.04-arm"})
        self.assertEqual({item["os"] for item in macos}, {"macos-15", "macos-15-intel"})

    def test_macos_builds_install_the_application_services_package(self):
        build = self.load("build-macos.yml")["jobs"]["build"]
        release = self.load("release.yml")["jobs"]["macos"]
        for job in (build, release):
            installs = " ".join(str(step.get("run", "")) for step in job["steps"])
            self.assertIn("pyobjc-framework-ApplicationServices", installs)

    def test_linux_ci_installs_python_xlib_before_the_tests(self):
        steps = self.load("ci.yml")["jobs"]["test-linux"]["steps"]
        runs = [str(step.get("run", "")) for step in steps]
        installed = next(i for i, run in enumerate(runs) if "python-xlib" in run)
        tested = next(i for i, run in enumerate(runs) if "unittest" in run)
        self.assertLess(installed, tested)

    def test_linux_ci_installs_the_window_manager_the_integration_tests_use(self):
        steps = self.load("ci.yml")["jobs"]["test-linux"]["steps"]
        installs = " ".join(str(step.get("run", "")) for step in steps)
        self.assertIn("openbox", installs)

    def test_every_matrix_architecture_matches_its_runner(self):
        expected = {
            "ubuntu-24.04": "x86_64",
            "ubuntu-24.04-arm": "aarch64",
            "macos-15": "arm64",
            "macos-15-intel": "x64",
        }
        for name in ("build-linux.yml", "build-macos.yml"):
            matrix = self.load(name)["jobs"]["build"]["strategy"]["matrix"]["include"]
            for item in matrix:
                self.assertEqual(item["arch"], expected[item["os"]], name)


class ReadmeDependencies(unittest.TestCase):
    def test_readme_lists_every_macos_pyobjc_package(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for package in (
            "pyobjc-framework-Quartz",
            "pyobjc-framework-Cocoa",
            "pyobjc-framework-ApplicationServices",
        ):
            self.assertIn(package, readme)


if __name__ == "__main__":
    unittest.main()
