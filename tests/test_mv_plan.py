import json
import unittest

from lyrics_mv import LyricLine
from mv_plan import build_user_prompt, extract_json, validate_plan


class MvPlanTests(unittest.TestCase):
    def test_prompt_protects_center_and_includes_shifted_timeline(self) -> None:
        prompt = build_user_prompt(
            [LyricLine(3.25, "第一句")],
            title="测试歌曲",
            artist="测试歌手",
            aspect_ratio="16:9",
            candidate_count=4,
        )
        self.assertIn("中央 45%", prompt)
        self.assertIn("严禁出现任何文字", prompt)
        self.assertIn("[00:03.25] 第一句", prompt)
        self.assertIn("输出 4 个", prompt)

    def test_extracts_fenced_json(self) -> None:
        value = extract_json('```json\n{"project_title": "demo"}\n```')
        self.assertEqual(value["project_title"], "demo")

    def test_prompt_can_reconcile_audio_profile_with_lyrics(self) -> None:
        prompt = build_user_prompt(
            [LyricLine(1.0, "雨落下来")],
            title="测试",
            artist="",
            aspect_ratio="16:9",
            candidate_count=2,
            audio_profile={"features": {"tempo_bpm": 86.2}, "acousticEmotion": "私密低能"},
        )
        self.assertIn('"tempo_bpm": 86.2', prompt)
        self.assertIn("音乐表层 + 歌词深层", prompt)

    def test_validates_minimum_candidate_shape(self) -> None:
        plan = {
            "project_title": "demo",
            "creative_direction": {},
            "background_candidates": [
                {
                    "name": "A",
                    "why_it_fits": "x",
                    "image_prompt_en": "x",
                    "negative_prompt_en": "x",
                    "recommended_loop_seconds": 12,
                    "recommended_motion_strength": 0.5,
                    "recommended_background_dim": 0.2,
                }
            ],
        }
        validate_plan(plan, 1)
        json.dumps(plan)


if __name__ == "__main__":
    unittest.main()
