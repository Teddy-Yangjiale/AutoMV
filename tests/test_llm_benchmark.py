import unittest

from llm_benchmark import build_benchmark_prompt, score_plan


class LlmBenchmarkTests(unittest.TestCase):
    def test_request_forbids_hallucinated_lyrics(self) -> None:
        prompt = build_benchmark_prompt(
            {
                "file_name": "月光(1).wav",
                "duration_seconds": 250.0,
                "lyrics_available": False,
            },
            4,
        )
        self.assertIn("不得声称知道具体歌词", prompt)
        self.assertIn("中央低细节负空间", prompt)

    def test_high_quality_plan_scores_full_points(self) -> None:
        candidate = {
            "name": "A",
            "why_it_fits": "Flexible and restrained",
            "image_prompt_en": (
                "Elegant cinematic abstract landscape with clean central negative space and a low-detail center, "
                "visual interest placed at the distant edges, restrained palette, atmospheric depth, "
                "16:9 composition, designed for slow seamless looping zoom and drifting motion, no text"
            ),
            "negative_prompt_en": "no text, no logo, no watermark, no UI, no border",
            "recommended_loop_seconds": 12,
            "recommended_motion_strength": 0.5,
            "recommended_background_dim": 0.24,
        }
        plan = {
            "evidence_limitations": "No lyrics are available, so the meaning is uncertain.",
            "creative_direction": {
                "core_concept": "restrained abstraction",
                "typography_advice": "elegant centered type",
                "motion_advice": "slow loop",
                "color_palette": ["#10131F"],
            },
            "background_candidates": [
                dict(
                    candidate,
                    name=str(index),
                    image_prompt_en=candidate["image_prompt_en"] + f" visual variation {index}",
                )
                for index in range(4)
            ],
        }
        score, notes = score_plan(plan, 4)
        self.assertEqual(score, 100)
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
