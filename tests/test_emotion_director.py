import unittest

import numpy as np

from emotion_director import AudioFeatures, analyze_samples, evaluate_project, recommend_visual


class EmotionDirectorTests(unittest.TestCase):
    sample_rate = 22_050

    def test_high_bright_signal_scores_more_aroused_than_soft_signal(self) -> None:
        seconds = 24
        time = np.arange(seconds * self.sample_rate) / self.sample_rate
        soft = (0.035 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)

        pulse = ((time * 2) % 1.0 < 0.07).astype(np.float32)
        high = (0.42 * np.sin(2 * np.pi * 2400 * time) + 0.48 * pulse).astype(np.float32)

        soft_features, _ = analyze_samples(soft, self.sample_rate)
        high_features, _ = analyze_samples(high, self.sample_rate)

        self.assertGreater(high_features.arousal, soft_features.arousal)
        self.assertGreater(high_features.brightness, soft_features.brightness)

    def test_energy_sections_find_quiet_and_loud_regions(self) -> None:
        time = np.arange(36 * self.sample_rate) / self.sample_rate
        envelope = np.where(time < 12, 0.03, np.where(time < 26, 0.55, 0.08))
        samples = (envelope * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
        _, sections = analyze_samples(samples, self.sample_rate)

        energies = [section["relativeEnergy"] for section in sections]
        self.assertGreater(max(energies), 0.6)
        self.assertLess(min(energies), 0.3)

    def test_section_automation_improves_structure_score(self) -> None:
        time = np.arange(20 * self.sample_rate) / self.sample_rate
        samples = (0.12 * np.sin(2 * np.pi * 330 * time)).astype(np.float32)
        features, sections = analyze_samples(samples, self.sample_rate)
        recommendation = recommend_visual(features, sections)
        base_project = {
            "visualDirection": recommendation["visualDirection"],
            "background": recommendation["background"],
            "subtitles": recommendation["subtitles"],
        }
        automated_project = {**base_project, "sectionAutomation": recommendation["sectionAutomation"]}

        base = evaluate_project(recommendation, base_project)
        automated = evaluate_project(recommendation, automated_project)
        base_structure = next(item["score"] for item in base["dimensions"] if item["name"] == "段落起伏")
        automated_structure = next(item["score"] for item in automated["dimensions"] if item["name"] == "段落起伏")
        self.assertGreater(automated_structure, base_structure)
        self.assertGreater(automated["overallScore"], base["overallScore"])

    def test_quiet_song_does_not_turn_relative_peak_into_punch_motion(self) -> None:
        features = AudioFeatures(
            duration_seconds=60,
            tempo_bpm=84,
            tempo_confidence=0.5,
            rms_db=-27,
            dynamic_range_db=18,
            spectral_centroid_hz=1200,
            zero_crossing_rate=0.04,
            onset_activity=0.3,
            arousal=0.28,
            brightness=0.2,
            rhythmicity=0.3,
        )
        recommendation = recommend_visual(
            features,
            [{"start": 0, "end": 60, "relativeEnergy": 0.95, "roleGuess": "peak_or_chorus"}],
        )
        self.assertNotIn(recommendation["sectionAutomation"][0]["motionPreset"], {"punch", "neon"})


if __name__ == "__main__":
    unittest.main()
