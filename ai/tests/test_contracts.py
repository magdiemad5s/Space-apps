"""Independent data and inference contracts; run with unittest discovery.

These checks verify implementation properties, not medical validity. Test-set
outcomes are never used for selection or assertions about model quality.
"""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "astra_shield_data" / "synthetic_demo"
DERIVED = {
    "sleep_duration_delta_from_baseline_hours",
    "heart_rate_delta_from_baseline_bpm",
    "hrv_delta_from_baseline_ms",
    "reaction_time_change_from_baseline_pct",
}


def config():
    local = ROOT / "data" / "task_config.json"
    return json.loads((local if local.exists() else SOURCE / "task_config.json").read_text())


def raw_audit_path():
    bundled = ROOT / "data" / "raw_observations.csv"
    return bundled if bundled.exists() else SOURCE / "raw_observations.csv"


def example_payload():
    # Fixture comes from training rows only, never from final evaluation outcomes.
    local = ROOT / "data" / "train.csv"
    if local.exists():
        row = pd.read_csv(local).iloc[0]
    else:
        rows = pd.read_csv(SOURCE / "astra_shield_synthetic_ml.csv")
        row = rows.loc[rows.split.eq("train")].iloc[0]
    cols = config()["tasks"]["next_day_fatigue_classification"]["predictors"]
    result = {c: row[c].item() if hasattr(row[c], "item") else row[c] for c in cols if c not in DERIVED}
    result["journal_text"] = row["journal_text"]
    result["participant_id"] = row["participant_id"]
    result["observation_timestamp_utc"] = row["observation_timestamp_utc"]
    return result


class DataContractTests(unittest.TestCase):
    def test_task_allowlists_do_not_contain_targets_or_identity(self):
        forbidden = {"record_id", "participant_id", "astronaut_id", "split", "mission_day", "is_synthetic", "data_origin",
                     "source", "regime_label_v3", "data_quality_flag", "alert_summary_v3"}
        for name, task in config()["tasks"].items():
            with self.subTest(task=name):
                features = task["predictors"]
                self.assertEqual(len(features), len(set(features)))
                self.assertFalse(forbidden.intersection(features))
                self.assertFalse(any(c.startswith("target_") for c in features))
                self.assertNotIn(task.get("target", task.get("evaluation_target")), features)

    def test_participant_partitions_are_disjoint(self):
        participants = {}
        for split in ["train", "validation", "test"]:
            local = ROOT / "data" / f"{split}.csv"
            if local.exists():
                # Only grouping metadata from test; no test outcomes inspected.
                rows = pd.read_csv(local, usecols=["participant_id", "split"])
                self.assertTrue(rows.split.eq(split).all())
            else:
                rows = pd.read_csv(SOURCE / "astra_shield_synthetic_ml.csv", usecols=["participant_id", "split"])
                rows = rows.loc[rows.split.eq(split)]
            participants[split] = set(rows.participant_id)
        self.assertEqual({k: len(v) for k, v in participants.items()}, {"train": 84, "validation": 18, "test": 18})
        for left, right in [("train", "validation"), ("train", "test"), ("validation", "test")]:
            self.assertFalse(participants[left] & participants[right])

    def test_training_features_use_only_calibration_and_past_days(self):
        frame = pd.read_csv(ROOT / "data" / "train.csv")
        raw = pd.read_csv(raw_audit_path())
        raw = raw.loc[raw.participant_id.isin(frame.participant_id.unique())].copy()
        baseline = raw.loc[raw.mission_day.le(0)].groupby("participant_id")
        self.assertTrue(baseline.size().eq(7).all())
        for col in ["sleep_duration_hours", "resting_heart_rate_bpm", "hrv_rmssd_ms", "reaction_time_median_ms"]:
            expected = frame.participant_id.map(baseline[col].mean())
            np.testing.assert_allclose(frame["baseline_" + col], expected, atol=1e-6, rtol=0)
        raw = raw.sort_values(["participant_id", "mission_day"])
        index = pd.MultiIndex.from_frame(frame[["participant_id", "mission_day"]])
        for base, feature in [
            ("sleep_duration_hours", "prior_3day_mean_sleep_hours"),
            ("resting_heart_rate_bpm", "prior_3day_mean_resting_heart_rate_bpm"),
            ("reaction_time_median_ms", "prior_3day_mean_reaction_time_ms"),
        ]:
            prior = raw.groupby("participant_id")[base].transform(lambda s: s.shift(1).rolling(3).mean())
            expected = pd.Series(prior.to_numpy(), index=pd.MultiIndex.from_frame(raw[["participant_id", "mission_day"]]))
            np.testing.assert_allclose(frame[feature], expected.loc[index], atol=1e-6, rtol=0)


class FeatureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = importlib.import_module("astra_shield_ml.features")

    def prepare(self, payload):
        return self.features.prepare_features(payload)

    def test_feature_order_and_derived_values(self):
        payload = example_payload()
        frame = self.prepare(payload)
        self.assertIsInstance(frame, pd.DataFrame)
        self.assertEqual(frame.shape, (1, 26))
        self.assertEqual(list(frame.columns), config()["tasks"]["next_day_fatigue_classification"]["predictors"])
        self.assertAlmostEqual(frame.iloc[0].sleep_duration_delta_from_baseline_hours,
                               payload["sleep_duration_hours"] - payload["baseline_sleep_duration_hours"], places=5)
        self.assertAlmostEqual(frame.iloc[0].heart_rate_delta_from_baseline_bpm,
                               payload["resting_heart_rate_bpm"] - payload["baseline_resting_heart_rate_bpm"], places=5)
        self.assertAlmostEqual(frame.iloc[0].hrv_delta_from_baseline_ms,
                               payload["hrv_rmssd_ms"] - payload["baseline_hrv_rmssd_ms"], places=5)
        self.assertAlmostEqual(frame.iloc[0].reaction_time_change_from_baseline_pct,
                               100 * (payload["reaction_time_median_ms"] / payload["baseline_reaction_time_median_ms"] - 1), places=5)

    def test_all_training_and_validation_rows_match_serving_features(self):
        # Prevent train/serve skew from feature order, rounding or derivation.
        columns = config()["tasks"]["next_day_fatigue_classification"]["predictors"]
        for split in ["train", "validation"]:
            rows = pd.read_csv(ROOT / "data" / f"{split}.csv")
            prepared = []
            for record in rows.to_dict("records"):
                payload = {c: record[c] for c in self.features.INPUT_FIELDS}
                prepared.append(self.prepare(payload).iloc[0].to_numpy())
            np.testing.assert_allclose(np.vstack(prepared), rows[columns].to_numpy(), atol=1e-6, rtol=0)

    def history_fixture(self):
        rows = pd.read_csv(raw_audit_path())
        rows = rows.loc[rows.participant_id.eq(example_payload()["participant_id"])]
        current = rows.loc[rows.mission_day.eq(20)].iloc[0].to_dict()
        calibration = rows.loc[rows.mission_day.le(0)].to_dict("records")
        recent = rows.loc[rows.mission_day.between(17, 19)].to_dict("records")
        return current, calibration, recent

    def test_history_helper_matches_same_day_published_features(self):
        current, calibration, recent = self.history_fixture()
        payload = self.features.build_request_from_history(current, calibration, recent)
        self.assertNotIn("target_next_day_fatigue_score", payload)
        rows = pd.read_csv(ROOT / "data" / "train.csv")
        expected = rows.loc[rows.participant_id.eq(current["participant_id"]) & rows.mission_day.eq(20)]
        np.testing.assert_allclose(self.prepare(payload).to_numpy(), expected[self.features.FEATURE_COLUMNS].to_numpy(), atol=1e-6, rtol=0)

    def test_history_helper_rejects_future_wrong_person_duplicates_and_missing_days(self):
        current, calibration, recent = self.history_fixture()
        cases = []
        future = deepcopy(recent)
        future[-1]["observation_timestamp_utc"] = current["observation_timestamp_utc"]
        cases.append((calibration, future))
        wrong_person = deepcopy(calibration)
        wrong_person[0]["participant_id"] = "someone_else"
        cases.append((wrong_person, recent))
        duplicate = deepcopy(recent)
        duplicate[-1] = deepcopy(duplicate[0])
        cases.append((calibration, duplicate))
        cases.append((calibration[:-1], recent))
        cases.append((calibration, recent[:-1]))
        gap = deepcopy(recent)
        gap[0]["observation_timestamp_utc"] = calibration[0]["observation_timestamp_utc"]
        cases.append((calibration, gap))
        for i, (base, past) in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.features.build_request_from_history(current, base, past)

    def test_optional_metadata_and_journal_do_not_change_numeric_predictions(self):
        payload = example_payload()
        reduced = {k: v for k, v in payload.items() if k not in {"participant_id", "observation_timestamp_utc", "journal_text"}}
        pd.testing.assert_frame_equal(self.prepare(payload), self.prepare(reduced))

    def test_missing_input_is_rejected(self):
        payload = example_payload()
        del payload["sleep_duration_hours"]
        with self.assertRaises((ValueError, TypeError)):
            self.prepare(payload)

    def test_future_label_or_unknown_field_is_rejected(self):
        for field in ["target_next_day_fatigue_class", "target_timestamp_utc", "mission_phase", "unknown_field"]:
            with self.subTest(field=field):
                payload = example_payload()
                payload[field] = "bad"
                with self.assertRaises((ValueError, TypeError)):
                    self.prepare(payload)

    def test_nonfinite_values_are_rejected(self):
        for number in [float("nan"), float("inf"), -float("inf")]:
            with self.subTest(number=number):
                payload = example_payload()
                payload["resting_heart_rate_bpm"] = number
                with self.assertRaises((ValueError, TypeError)):
                    self.prepare(payload)

    def test_invalid_ranges_and_counts_are_rejected(self):
        for field, number in [("sleep_duration_hours", -1), ("sleep_efficiency_pct", 101),
                              ("baseline_reaction_time_median_ms", 0), ("attention_accuracy_pct", 101),
                              ("reaction_time_lapses_count", 61), ("awakenings_count", 1.5),
                              ("self_report_stress_score", 11)]:
            with self.subTest(field=field):
                payload = example_payload()
                payload[field] = number
                with self.assertRaises((ValueError, TypeError)):
                    self.prepare(payload)

    def test_inconsistent_sleep_opportunity_is_rejected(self):
        payload = example_payload()
        payload.update(sleep_duration_hours=8, sleep_efficiency_pct=99, sleep_onset_delay_minutes=60)
        with self.assertRaises((ValueError, TypeError)):
            self.prepare(payload)


class APIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.api = importlib.import_module("astra_shield_ml.api")
        cls.api.get_service.cache_clear()
        cls.client = TestClient(cls.api.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_health_and_model_info_expose_scope_and_allowlists(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200, response.text)
        health = response.json()
        self.assertEqual(health["tasks_loaded"], 5)
        self.assertFalse(health["clinical_validation"])
        info = self.client.get("/v1/model-info").json()
        self.assertEqual(info["forecast_horizon_hours"], 24)
        self.assertEqual(info["data_origin"], "synthetic")
        self.assertFalse(info["clinical_validation"])
        self.assertEqual(set(info["tasks"]), set(config()["tasks"]))
        for task, spec in config()["tasks"].items():
            self.assertEqual(info["tasks"][task]["predictors"], spec["predictors"])

    def test_label_points_and_actual_tree_shap_additivity(self):
        service = self.api.get_service()
        feature_module = importlib.import_module("astra_shield_ml.features")
        frame = pd.read_csv(ROOT / "data" / "train.csv")
        name = "next_day_fatigue_classification"
        model = service.models[name]
        columns = service.task_config["tasks"][name]["predictors"]
        predicted = np.asarray(model.predict(frame[columns]))
        self.assertEqual(set(predicted), {"low", "moderate", "high"})
        for label in ["low", "moderate", "high"]:
            with self.subTest(predicted_class=label):
                record = frame.iloc[int(np.flatnonzero(predicted == label)[0])].to_dict()
                payload = {c: record[c] for c in feature_module.INPUT_FIELDS}
                payload["journal_text"] = record["journal_text"]
                result = service.predict(payload)
                self.assertEqual(result["label"], label)
                self.assertEqual(result["label"], result["next_day_forecasts"]["fatigue"]["class"])
                self.assertGreaterEqual(result["points"], 0)
                self.assertLessEqual(result["points"], 100)
                self.assertIn("not a clinical risk probability", result["points_definition"])
                probabilities = result["next_day_forecasts"]["fatigue"]["model_class_probabilities"]
                expected_points = round(50 * probabilities["moderate"] + 100 * probabilities["high"], 1)
                self.assertAlmostEqual(result["points"], expected_points, places=6)
                shap = result["explanation"]["tree_shap"]
                self.assertEqual(shap["method"], "TreeSHAP")
                self.assertEqual(shap["explained_class"], label)
                all_values = shap["all_feature_contributions"]
                self.assertEqual({v["feature"] for v in all_values}, set(columns))
                self.assertTrue(np.isfinite([v["shap_value"] for v in all_values]).all())
                self.assertAlmostEqual(shap["base_value"] + sum(v["shap_value"] for v in all_values),
                                       shap["reconstructed_model_output"], places=8)
                if shap["model_output_space"] == "class_probability":
                    self.assertAlmostEqual(shap["reconstructed_model_output"], probabilities[label], places=6)
                else:
                    transformed = model[:-1].transform(feature_module.prepare_features(payload)[columns])
                    native = model.named_steps["model"].estimator_
                    margins = native.predict(transformed, output_margin=True)[0]
                    class_index = list(model.classes_).index(label)
                    self.assertAlmostEqual(shap["reconstructed_model_output"], float(margins[class_index]), places=5)
                self.assertEqual(len(result["reasons"]), 3)
                self.assertEqual(result["reasons"], shap["top_three_reasons"])
                self.assertTrue(all(v["feature"] in columns and v["reason"] for v in result["reasons"]))

    def test_frozen_selection_and_ablation_contract(self):
        report = json.loads((ROOT / "reports" / "validation_metrics.json").read_text())
        self.assertFalse(report["test_used"])
        primary = report["tasks"]["next_day_fatigue_classification"]
        candidates = primary["candidates"]
        self.assertIn("random_forest_balanced", candidates)
        self.assertIn("xgboost_balanced", candidates)
        expected = max(candidates, key=lambda n: candidates[n]["validation_metrics"]["macro_f1"])
        self.assertEqual(primary["selection"]["selected_model"], expected)
        ablation = json.loads((ROOT / "reports" / "ablation_validation_metrics.json").read_text())
        self.assertFalse(ablation["test_used"])
        expected_exclusions = {"self_report_fatigue_score", "reaction_time_median_ms", "reaction_time_lapses_count",
                               "baseline_reaction_time_median_ms", "reaction_time_change_from_baseline_pct", "prior_3day_mean_reaction_time_ms"}
        self.assertEqual(set(ablation["excluded_available_proxies"]), expected_exclusions)
        self.assertFalse(expected_exclusions & set(ablation["remaining_predictors"]))
        self.assertEqual(len(ablation["remaining_predictors"]), 20)

    def test_prediction_matches_frozen_estimator_and_class_mapping(self):
        payload = example_payload()
        response = self.client.post("/v1/predict", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        service = self.api.get_service()
        frame = importlib.import_module("astra_shield_ml.features").prepare_features(payload)
        task = "next_day_fatigue_classification"
        model = service.models[task]
        predictors = service.task_config["tasks"][task]["predictors"]
        expected_class = str(model.predict(frame[predictors])[0])
        expected_probability = dict(zip(model.classes_, model.predict_proba(frame[predictors])[0]))
        actual = result["next_day_forecasts"]["fatigue"]
        self.assertEqual(actual["class"], expected_class)
        self.assertEqual(set(actual["model_class_probabilities"]), {"low", "moderate", "high"})
        for name, value in expected_probability.items():
            self.assertAlmostEqual(actual["model_class_probabilities"][name], value, places=10)
        self.assertAlmostEqual(sum(actual["model_class_probabilities"].values()), 1.0, places=8)
        observed = pd.Timestamp(payload["observation_timestamp_utc"])
        self.assertEqual(pd.Timestamp(result["target_timestamp_utc"]), observed + pd.Timedelta(hours=24))
        self.assertFalse(result["clinical_validation"])
        self.assertEqual(result["forecast_horizon_hours"], 24)
        self.assertIn("physiology", result["current_observation"])
        self.assertIn("journal", result["current_observation"])
        self.assertEqual(result["current_observation"]["journal"]["status"], "experimental")
        self.assertIn("not clinical risk", actual["probability_interpretation"])

    def test_optional_journal_is_absent_without_changing_forecasts(self):
        payload = example_payload()
        with_journal = self.client.post("/v1/predict", json=payload).json()
        del payload["journal_text"]
        response = self.client.post("/v1/predict", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        without_journal = response.json()
        self.assertEqual(without_journal["current_observation"]["journal"]["status"], "not_provided")
        left = without_journal["next_day_forecasts"]
        right = with_journal["next_day_forecasts"]
        self.assertEqual(left["fatigue"]["class"], right["fatigue"]["class"])
        self.assertAlmostEqual(left["fatigue"]["score_estimate"], right["fatigue"]["score_estimate"], places=8)
        self.assertAlmostEqual(left["reaction_time_median_ms"], right["reaction_time_median_ms"], places=8)
        for label, value in left["fatigue"]["model_class_probabilities"].items():
            self.assertAlmostEqual(value, right["fatigue"]["model_class_probabilities"][label], places=10)

    def test_bad_inputs_return_422_not_500(self):
        cases = []
        missing = example_payload(); missing.pop("sleep_duration_hours"); cases.append(missing)
        extra = example_payload(); extra["target_next_day_fatigue_class"] = "high"; cases.append(extra)
        fraction = example_payload(); fraction["awakenings_count"] = 1.5; cases.append(fraction)
        text_number = example_payload(); text_number["sleep_duration_hours"] = "7"; cases.append(text_number)
        impossible = example_payload(); impossible.update(sleep_duration_hours=8, sleep_efficiency_pct=99, sleep_onset_delay_minutes=60); cases.append(impossible)
        naive = example_payload(); naive["observation_timestamp_utc"] = "2026-01-01T18:00:00"; cases.append(naive)
        too_long = example_payload(); too_long["journal_text"] = "x" * 5001; cases.append(too_long)
        for i, payload in enumerate(cases):
            with self.subTest(case=i):
                response = self.client.post("/v1/predict", json=payload)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("detail", response.json())
        for value in [float("nan"), float("inf"), -float("inf")]:
            payload = example_payload(); payload["resting_heart_rate_bpm"] = value
            response = self.client.post("/v1/predict", content=json.dumps(payload), headers={"content-type": "application/json"})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn("detail", response.json())
        malformed = self.client.post("/v1/predict", content='{"broken":', headers={"content-type": "application/json"})
        self.assertEqual(malformed.status_code, 422, malformed.text)

    def test_batch_and_size_limit(self):
        payload = example_payload()
        response = self.client.post("/v1/predict/batch", json={"observations": [payload, payload]})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["predictions"]), 2)
        for observations in [[], [payload] * 65]:
            response = self.client.post("/v1/predict/batch", json={"observations": observations})
            self.assertEqual(response.status_code, 422, response.text)

    def test_prediction_never_calls_fit_and_reuses_loaded_service(self):
        from sklearn.pipeline import Pipeline
        first = self.api.get_service()
        with patch.object(Pipeline, "fit", side_effect=AssertionError("Inference must never fit")):
            response = self.client.post("/v1/predict", json=example_payload())
            self.assertEqual(response.status_code, 200, response.text)
        self.assertIs(first, self.api.get_service())


if __name__ == "__main__":
    unittest.main()
