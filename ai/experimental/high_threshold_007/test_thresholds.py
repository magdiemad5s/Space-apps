"""Small, hand-auditable tests for post-fit threshold decisions and accounting.

These fixtures contain no project observations, models, or saved probabilities.
They test the decision policy rather than fitting or selecting a threshold.
"""
import unittest

import numpy as np

from run_thresholds import (
    baseline_predictions,
    classification_summary,
    predict_threshold,
)


class ThresholdDecisionTests(unittest.TestCase):
    def test_baseline_is_multiclass_argmax_not_half(self):
        classes = ["high", "low", "moderate"]
        probabilities = np.array([[0.40, 0.35, 0.25], [0.30, 0.29, 0.41]])
        self.assertEqual(baseline_predictions(probabilities, classes).tolist(), ["high", "moderate"])
        self.assertEqual(predict_threshold(probabilities, classes, 0.5).tolist(), ["low", "moderate"])

    def test_exact_high_threshold_is_inclusive(self):
        probabilities = np.array([[0.4, 0.35, 0.25]])
        classes = ["high", "low", "moderate"]
        self.assertEqual(predict_threshold(probabilities, classes, 0.4).tolist(), ["high"])
        above = np.nextafter(0.4, 1.0)
        self.assertEqual(predict_threshold(probabilities, classes, above).tolist(), ["low"])

    def test_labels_follow_class_names_not_assumed_column_order(self):
        # Original order: Low, Moderate, High. All maxima are distinct.
        classes = ["low", "moderate", "high"]
        probabilities = np.array([[0.7, 0.2, 0.1], [0.1, 0.5, 0.4], [0.1, 0.2, 0.7]])
        expected = ["low", "high", "high"]
        for order in ([0, 1, 2], [2, 0, 1], [1, 2, 0]):
            reordered = probabilities[:, order]
            names = [classes[i] for i in order]
            self.assertEqual(predict_threshold(reordered, names, 0.4).tolist(), expected)
            self.assertEqual(baseline_predictions(reordered, names).tolist(), ["low", "moderate", "high"])

    def test_non_high_tie_always_chooses_low(self):
        self.assertEqual(
            predict_threshold(np.array([[0.45, 0.45, 0.1]]), ["moderate", "low", "high"], 0.2).tolist(),
            ["low"],
        )
        self.assertEqual(
            predict_threshold(np.array([[0.1, 0.45, 0.45]]), ["high", "low", "moderate"], 0.2).tolist(),
            ["low"],
        )

    def test_probability_endpoints_and_threshold_endpoints(self):
        probabilities = np.array([[0.0, 1.0, 0.0], [0.6, 0.2, 0.2], [1.0, 0.0, 0.0]])
        classes = ["high", "low", "moderate"]
        self.assertEqual(predict_threshold(probabilities, classes, 0.0).tolist(), ["high", "high", "high"])
        self.assertEqual(predict_threshold(probabilities, classes, 1.0).tolist(), ["low", "low", "high"])

    def test_lowering_threshold_cannot_reduce_high_detections_or_false_alarms(self):
        classes = ["high", "low", "moderate"]
        truth = np.array(["high", "low", "high", "moderate", "high", "low"])
        probabilities = np.array([
            [0.8, 0.1, 0.1],
            [0.7, 0.2, 0.1],
            [0.5, 0.1, 0.4],
            [0.3, 0.1, 0.6],
            [0.2, 0.4, 0.4],
            [0.0, 0.6, 0.4],
        ])
        expected_tp = [0, 1, 2, 3, 3]
        expected_fp = [0, 0, 1, 2, 3]
        previous_positive = set()
        for threshold, tp, fp in zip([1.0, 0.8, 0.5, 0.2, 0.0], expected_tp, expected_fp):
            predicted = predict_threshold(probabilities, classes, threshold)
            positive = set(np.flatnonzero(predicted == "high").tolist())
            self.assertTrue(previous_positive.issubset(positive))
            report = classification_summary(truth, predicted)
            self.assertEqual(report["high_tp"], tp)
            self.assertEqual(report["high_fp"], fp)
            previous_positive = positive

    def test_rejects_out_of_range_or_nonfinite_threshold(self):
        probabilities = np.array([[0.2, 0.3, 0.5]])
        for threshold in [-0.01, 1.01, np.nan, np.inf, -np.inf]:
            with self.subTest(threshold=threshold):
                with self.assertRaises((ValueError, TypeError)):
                    predict_threshold(probabilities, ["high", "low", "moderate"], threshold)

    def test_rejects_invalid_probability_values_or_sums(self):
        cases = [
            np.array([[np.nan, 0.3, 0.7]]),
            np.array([[np.inf, 0.3, 0.7]]),
            np.array([[-0.1, 0.4, 0.7]]),
            np.array([[1.1, -0.1, 0.0]]),
            np.array([[0.2, 0.2, 0.2]]),
        ]
        for probabilities in cases:
            with self.subTest(probabilities=probabilities):
                with self.assertRaises((ValueError, TypeError)):
                    predict_threshold(probabilities, ["high", "low", "moderate"], 0.3)

    def test_rejects_invalid_class_set_or_matrix_shape(self):
        probabilities = np.array([[0.2, 0.3, 0.5]])
        for classes in (["high", "low", "low"], ["high", "low", "unknown"], ["high", "low"]):
            with self.subTest(classes=classes):
                with self.assertRaises((ValueError, TypeError)):
                    predict_threshold(probabilities, classes, 0.3)
        for bad_shape in (np.array([0.2, 0.3, 0.5]), np.array([[0.2, 0.8]])):
            with self.subTest(shape=bad_shape.shape):
                with self.assertRaises((ValueError, TypeError)):
                    predict_threshold(bad_shape, ["high", "low", "moderate"], 0.3)


class ThresholdAccountingTests(unittest.TestCase):
    def test_hand_counted_confusion_and_macro_f1(self):
        truth = np.array(["low", "low", "moderate", "moderate", "high", "high"])
        predicted = np.array(["low", "high", "moderate", "high", "moderate", "high"])
        report = classification_summary(truth, predicted)
        self.assertEqual(report["confusion_matrix_labels"], ["low", "moderate", "high"])
        self.assertEqual(report["confusion_matrix"], [[1, 0, 1], [0, 1, 1], [0, 1, 1]])
        self.assertEqual((report["high_tp"], report["high_fp"], report["high_fn"], report["high_tn"]), (1, 2, 1, 2))
        self.assertAlmostEqual(report["high_precision"], 1 / 3)
        self.assertAlmostEqual(report["high_recall"], 1 / 2)
        self.assertAlmostEqual(report["high_f1"], 0.4)
        self.assertAlmostEqual(report["macro_f1"], 47 / 90)

    def test_no_high_predictions_has_undefined_precision_not_false_perfection(self):
        report = classification_summary(np.array(["low", "moderate", "high"]), np.array(["low", "moderate", "moderate"]))
        self.assertIsNone(report["high_precision"])
        self.assertEqual(report["high_recall"], 0)
        self.assertEqual(report["high_f1"], 0)
        self.assertEqual((report["high_tp"], report["high_fp"], report["high_fn"], report["high_tn"]), (0, 0, 1, 2))

    def test_all_high_predictions_show_recall_cost_in_precision(self):
        report = classification_summary(np.array(["low", "moderate", "high", "high"]), np.array(["high"] * 4))
        self.assertEqual(report["high_recall"], 1)
        self.assertEqual(report["high_precision"], 0.5)
        self.assertAlmostEqual(report["high_f1"], 2 / 3)
        self.assertEqual((report["high_tp"], report["high_fp"], report["high_fn"], report["high_tn"]), (2, 2, 0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
