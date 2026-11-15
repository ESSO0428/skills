from pathlib import Path
import unittest

from channel_distill.classify import classify_inventory, classify_video as _classify_video, load_topic_rules

RULES = load_topic_rules(Path(__file__).parents[1] / "examples" / "topic-rules.ml-course.json")


def classify_video(record):
    return _classify_video(record, RULES)


class ClassifyVideoTests(unittest.TestCase):
    def test_without_rules_every_title_stays_unknown(self):
        self.assertIsNone(load_topic_rules(None))
        self.assertIsNone(load_topic_rules(Path("does-not-exist.json")))
        labels = _classify_video({"title": "類神經網路訓練不起來怎麼辦：局部最小值與鞍點"})
        self.assertEqual([(label["topic"], label["priority"]) for label in labels], [("unknown", "unknown")])
        classified = classify_inventory({"v1": {"video_id": "v1", "title": "Validation overfitting"}})
        self.assertEqual(classified["v1"]["topic_priority"], "unknown")

    def test_policy_gradient_is_not_core_optimization_by_title_alone(self):
        labels = classify_video({"title": "DRL Lecture 1: Policy Gradient (Review)"})
        self.assertNotIn("P0", [label["priority"] for label in labels])

    def test_english_core_research_lectures_are_not_left_unknown(self):
        roadmap = classify_video({"title": "[ML 2021 (English version)] Lecture 3: Roadmap of Improving Model"})
        optimization = classify_video({"title": "[ML 2021 (English version)] Lecture 4: What to do when optimization fails? (1/4)"})
        self.assertIn("training-diagnosis", [label["topic"] for label in roadmap])
        self.assertIn("optimization", [label["topic"] for label in optimization])
        self.assertTrue(all(label["priority"] == "P0" for label in roadmap + optimization))

    def test_explicit_ml_principles_remain_core_despite_generative_ai_series_prefix(self):
        labels = classify_video({"title": "【生成式AI】快速了解機器學習基本原理 (1/2)"})
        self.assertIn("ml-fundamentals", [label["topic"] for label in labels])
        self.assertIn("P0", [label["priority"] for label in labels])

    def test_unrelated_title_stays_unknown(self):
        labels = classify_video({"title": "AI 新聞雜談"})

        self.assertEqual(labels[0]["topic"], "unknown")
        self.assertEqual(labels[0]["priority"], "unknown")

    def test_explicit_training_diagnostics_get_p0_with_reasons(self):
        labels = classify_video({"title": "類神經網路訓練不起來怎麼辦：局部最小值與鞍點"})

        self.assertEqual(labels[0]["topic"], "optimization")
        self.assertEqual(labels[0]["priority"], "P0")
        self.assertGreater(labels[0]["confidence"], 0.5)
        self.assertIn("title", labels[0]["reason"])

    def test_one_video_can_match_multiple_research_topics(self):
        labels = classify_video({"title": "Validation 與 overfitting：loss function 的選擇"})

        self.assertEqual({label["topic"] for label in labels}, {"evaluation", "generalization", "loss-functions"})
        self.assertEqual({label["priority"] for label in labels}, {"P0"})

    def test_architecture_keyword_does_not_become_p0(self):
        labels = classify_video({"title": "Self-Attention 與 Transformer"})

        self.assertEqual({label["priority"] for label in labels}, {"P1"})

    def test_generic_machine_learning_mention_is_not_sufficient_for_p0(self):
        labels = classify_video({"title": "機器學習系所活動公告"})

        self.assertEqual(labels[0]["priority"], "unknown")

    def test_classification_populates_topics_and_best_priority_without_mutating_input(self):
        original = {"v1": {"video_id": "v1", "title": "Transformer 與 validation", "topics": []}}

        classified = classify_inventory(original, RULES)

        self.assertEqual({label["priority"] for label in classified["v1"]["topics"]}, {"P0", "P1"})
        self.assertEqual(classified["v1"]["topic_priority"], "P0")
        self.assertEqual(original["v1"]["topics"], [])

    def test_specialized_titles_do_not_get_generic_p0_evaluation_or_regularization(self):
        titles = [
            "GAN Lecture 10 (2018): Evaluation & Concluding Remarks",
            "Evaluation of Generative Models",
            "Meta Learning – Metric-based (1/3)",
            "大型語言模型評估的幾件事",
            "ASR WITH WORD EMBEDDING REGULARIZATION AND FUSED DECODING",
        ]

        for title in titles:
            with self.subTest(title=title):
                labels = classify_video({"title": title})
                self.assertNotIn("P0", {label["priority"] for label in labels})
                self.assertEqual(min(label["priority"] for label in labels), "P2")


if __name__ == "__main__":
    unittest.main()
