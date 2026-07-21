import tempfile
import unittest
from pathlib import Path

from lyrics_mv import (
    LyricLine,
    _image_background_filter,
    _video_background_filter,
    apply_offset,
    build_ass,
    parse_lrc,
)


class LrcParsingTests(unittest.TestCase):
    def _write_lrc(self, content: str, encoding: str = "utf-8") -> Path:
        temp = tempfile.NamedTemporaryFile(suffix=".lrc", delete=False)
        temp.close()
        path = Path(temp.name)
        path.write_text(content, encoding=encoding)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_parses_metadata_fraction_and_repeated_timestamps(self) -> None:
        path = self._write_lrc(
            "[ti:示例歌曲]\n[offset:250]\n[00:01.5][00:03.050]同一句\n[00:05.00]结束\n"
        )
        result = parse_lrc(path)
        self.assertEqual(result.metadata["ti"], "示例歌曲")
        self.assertAlmostEqual(result.lrc_offset_seconds, 0.25)
        self.assertEqual([line.start for line in result.lines], [1.5, 3.05, 5.0])
        self.assertEqual(result.lines[1].text, "同一句")

    def test_same_timestamp_preserves_bilingual_lines(self) -> None:
        path = self._write_lrc("[00:01.00]你好\n[00:01.00]Hello\n")
        result = parse_lrc(path)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].text, "你好\\NHello")

    def test_gb18030_input(self) -> None:
        path = self._write_lrc("[00:00.00]中文歌词\n", encoding="gb18030")
        result = parse_lrc(path)
        self.assertEqual(result.lines[0].text, "中文歌词")

    def test_offset_is_added_and_negative_time_is_clamped(self) -> None:
        lines = [LyricLine(0.0, "第一句"), LyricLine(2.0, "第二句")]
        shifted = apply_offset(lines, 3.25)
        self.assertEqual([line.start for line in shifted], [3.25, 5.25])
        trimmed = apply_offset(lines, -1.0)
        self.assertEqual([line.start for line in trimmed], [0.0, 1.0])

    def test_ass_contains_shifted_events_and_context(self) -> None:
        ass = build_ass(
            [LyricLine(2.0, "第一句"), LyricLine(5.0, "第二句")],
            width=1920,
            height=1080,
            font_name="Microsoft YaHei",
            font_size=76,
            text_color="#FFFFFF",
            accent_color="#8AD8FF",
            max_line_duration=8.0,
            show_context=True,
        )
        self.assertIn("Dialogue: 2,0:00:02.00", ass)
        self.assertIn("\\pos(960,540)", ass)
        self.assertIn("第一句", ass)
        self.assertIn("第二句", ass)

    def test_image_motion_uses_periodic_zoom(self) -> None:
        value = _image_background_filter(
            width=1920,
            height=1080,
            fps=30,
            loop_seconds=12,
            motion_strength=0.6,
            dim=0.24,
        )
        self.assertIn("2*PI*on/360.000000", value)
        self.assertIn("1-cos", value)
        self.assertIn("black@0.240", value)

    def test_neon_style_and_position_are_written_to_ass(self) -> None:
        ass = build_ass(
            [LyricLine(1.0, "夜色发光")],
            width=1920,
            height=1080,
            font_name="Microsoft YaHei",
            font_size=76,
            text_color="#FFFFFF",
            accent_color="#C8FF3D",
            max_line_duration=8.0,
            show_context=False,
            subtitle_style="neon",
            y_percent=60,
            alignment="right",
        )
        self.assertIn(r"\an6\pos(1690,648)", ass)
        self.assertIn(r"\blur3.2", ass)

    def test_video_background_is_normalized_before_compositing(self) -> None:
        value = _video_background_filter(width=1080, height=1920, fps=30, dim=0.38)
        self.assertIn("scale=1080:1920", value)
        self.assertIn("crop=1080:1920", value)
        self.assertIn("fps=30", value)
        self.assertIn("black@0.380", value)


if __name__ == "__main__":
    unittest.main()
