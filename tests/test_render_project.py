import json
import tempfile
import unittest
from pathlib import Path

from render_project import project_to_argv


class ProjectBridgeTests(unittest.TestCase):
    def _project(self, background_kind: str = "video") -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        data = {
            "version": 1,
            "audio": {"file": "song.wav", "offsetSeconds": 3.25},
            "lyrics": {"file": "lyrics.lrc"},
            "canvas": {"width": 1080, "height": 1920, "fps": 30},
            "background": {"kind": background_kind, "file": "loop.mp4", "dim": 0.38, "motionStrength": 0.4, "loopSeconds": 12},
            "subtitles": {"style": "neon", "motionPreset": "neon", "displayMode": "single", "fontSize": 68, "letterSpacingEm": 0.08, "yPercent": 54, "align": "center", "textColor": "#FFFFFF", "accentColor": "#C8FF3D", "showContext": False},
            "sectionAutomation": [{"start": 0, "end": 12, "motionPreset": "minimal", "motionIntensity": 0.3}],
            "render": {"crf": 18, "preset": "medium", "audioBitrate": "320k"},
        }
        path = root / "automv-project.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_maps_studio_config_to_renderer_arguments(self) -> None:
        project = self._project()
        argv = project_to_argv(project, dry_run=True)
        self.assertEqual(argv[0], str(project.parent / "song.wav"))
        self.assertIn("--background-video", argv)
        self.assertIn("--subtitle-style", argv)
        self.assertIn("neon", argv)
        self.assertIn("5.44", argv)
        self.assertIn("--motion-preset", argv)
        self.assertIn("--display-mode", argv)
        self.assertIn("single", argv)
        self.assertIn("--section-automation", argv)
        self.assertTrue(any('"motionPreset":"minimal"' in item for item in argv))
        self.assertIn("--dry-run", argv)

    def test_rejects_unknown_background_kind(self) -> None:
        project = self._project("scene3d")
        with self.assertRaisesRegex(ValueError, "background.kind"):
            project_to_argv(project)


if __name__ == "__main__":
    unittest.main()
