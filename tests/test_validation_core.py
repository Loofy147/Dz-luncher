import unittest

from validation_core import (
    Branch,
    Choice,
    Hypothesis,
    Question,
    QualityPolicy,
    Response,
    Survey,
    analysis_records,
    build_report,
    label_hypothesis,
    process_responses,
    pseudo_id,
    response_from_dict,
    survey_from_dict,
    validate_survey,
    validate_response,
    wilson_interval,
)


def survey_fixture(*, quotas=None):
    return Survey(
        project_id="project-alpha",
        version_id="v1",
        questions=(
            Question("wilaya", "ما هي ولايتك؟", "single", options=(
                Choice("alg", "الجزائر"), Choice("oran", "وهران"), Choice("chlef", "الشلف")
            )),
            Question("uses_delivery", "هل استخدمت التوصيل مؤخراً؟", "single", options=(
                Choice("yes", "نعم"), Choice("no", "لا")
            ), disqualify_if=("no",)),
            Question("frequency", "كم مرة؟", "number", required=True, show_if=Branch("uses_delivery", ("yes",)), lo=1, hi=60),
            Question("rating_1", "التقييم 1", "scale", grid="rating", lo=1, hi=5),
            Question("rating_2", "التقييم 2", "scale", grid="rating", lo=1, hi=5),
            Question("rating_3", "التقييم 3", "scale", grid="rating", lo=1, hi=5),
            Question("rating_4", "التقييم 4", "scale", grid="rating", lo=1, hi=5),
            Question("rating_5", "التقييم 5", "scale", grid="rating", lo=1, hi=5),
            Question("attention", "اختر محايداً", "single", options=(
                Choice("agree", "موافق"), Choice("neutral", "محايد"), Choice("disagree", "غير موافق")
            ), attention_expected="neutral"),
            Question("price", "هل تدفع؟", "single", options=(
                Choice("yes", "نعم"), Choice("no", "لا"), Choice("maybe", "ربما")
            )),
            Question("comment", "ملاحظات", "text", required=False),
        ),
        quotas=quotas or {},
    )


def valid_response(submission_id="s1", participant_id="u1", *, device_id="d1", answers=None, seconds=240):
    base = {
        "wilaya": "oran", "uses_delivery": "yes", "frequency": "٣",
        "rating_1": "4", "rating_2": "3", "rating_3": "4", "rating_4": "2", "rating_5": "5",
        "attention": "neutral", "price": "yes", "comment": "التوصيل يحتاج تحسيناً واضحاً",
    }
    if answers:
        base.update(answers)
    return Response(submission_id, participant_id, device_id, seconds, base, "v1")


class SurveySchemaTests(unittest.TestCase):

    def test_parses_json_survey_contract_and_validates_it(self):
        payload = {
            "project_id": "project-json", "version_id": "v1",
            "questions": [
                {"id": "city", "text": "ما هي ولايتك؟", "kind": "single", "options": [
                    {"id": "alg", "label": "الجزائر"}, {"id": "oran", "label": "وهران"}
                ]},
                {"id": "frequency", "text": "كم مرة؟", "kind": "number", "lo": 1, "hi": 30,
                 "show_if": {"question_id": "city", "any_of": ["oran"]}},
            ],
            "quotas": {"city": {"alg": 2}},
        }
        parsed = survey_from_dict(payload)
        self.assertEqual(parsed.project_id, "project-json")
        self.assertEqual(parsed.questions[1].show_if, Branch("city", ("oran",)))

    def test_json_survey_contract_rejects_unknown_fields(self):
        payload = {"project_id": "p", "version_id": "v1", "questions": [], "exec_script": "bad"}
        with self.assertRaises(ValueError):
            survey_from_dict(payload)

    def test_parses_response_json_with_version_binding(self):
        payload = {"submission_id": "s1", "participant_id": "u1", "survey_version_id": "v1",
                   "answers": {"price": "yes"}, "seconds": 20}
        parsed = response_from_dict(payload)
        self.assertEqual(parsed.survey_version_id, "v1")
        self.assertEqual(parsed.answers["price"], "yes")

    def test_valid_schema_is_accepted(self):
        validate_survey(survey_fixture())

    def test_rejects_duplicate_question_ids(self):
        s = survey_fixture()
        broken = Survey(s.project_id, s.version_id, s.questions + (s.questions[0],))
        with self.assertRaises(ValueError):
            validate_survey(broken)

    def test_rejects_branch_to_later_question(self):
        q0 = Question("first", "السؤال الأول", "single", options=(Choice("x", "x"),), show_if=Branch("later", ("x",)))
        q1 = Question("later", "السؤال اللاحق", "single", options=(Choice("x", "x"),))
        with self.assertRaises(ValueError):
            validate_survey(Survey("p", "v1", (q0, q1)))

    def test_rejects_unknown_branch_option(self):
        s = survey_fixture()
        replacement = Question("frequency", "كم مرة؟", "number", show_if=Branch("uses_delivery", ("maybe",)), lo=1, hi=10)
        qs = tuple(replacement if q.id == "frequency" else q for q in s.questions)
        with self.assertRaises(ValueError):
            validate_survey(Survey(s.project_id, s.version_id, qs))

    def test_rejects_quota_for_unknown_option(self):
        with self.assertRaises(ValueError):
            validate_survey(survey_fixture(quotas={"wilaya": {"not-an-option": 5}}))

    def test_rejects_optional_quota_question(self):
        s = survey_fixture()
        replacement = Question("wilaya", "ما هي ولايتك؟", "single", options=(
            Choice("alg", "الجزائر"), Choice("oran", "وهران"), Choice("chlef", "الشلف")
        ), required=False)
        questions = tuple(replacement if q.id == "wilaya" else q for q in s.questions)
        with self.assertRaises(ValueError):
            validate_survey(Survey(s.project_id, s.version_id, questions, {"wilaya": {"oran": 5}}))


class ResponseValidationTests(unittest.TestCase):
    def test_accepts_arabic_indic_numeric_answers(self):
        result = validate_response(survey_fixture(), valid_response())
        self.assertEqual(result.errors, ())
        self.assertFalse(result.screened_out)
        self.assertEqual(result.normalized_answers["frequency"], 3)

    def test_normalizes_arabic_decimal_separator(self):
        result = validate_response(survey_fixture(), valid_response(answers={"frequency": "٣٫٥"}))
        self.assertEqual(result.errors, ())
        self.assertEqual(result.normalized_answers["frequency"], 3.5)

    def test_screening_out_is_not_a_quality_flag(self):
        r = Response("screenout-1", "screenout-user", "device-1", 25, {"wilaya": "oran", "uses_delivery": "no"}, "v1")
        result = validate_response(survey_fixture(), r)
        self.assertTrue(result.screened_out)
        self.assertEqual(result.errors, ())

    def test_rejects_display_label_where_stable_option_id_is_required(self):
        r = valid_response(answers={"uses_delivery": "نعم"})
        result = validate_response(survey_fixture(), r)
        self.assertIn("bad_option:uses_delivery", result.errors)

    def test_rejects_answer_to_hidden_branch(self):
        r = valid_response(answers={"uses_delivery": "no", "frequency": "3"})
        result = validate_response(survey_fixture(), r)
        self.assertTrue(result.errors)
        self.assertTrue(any(e.startswith("branch_violation:frequency") for e in result.errors))

    def test_rejects_infinite_and_out_of_range_numeric_answers(self):
        for value in ("inf", "999"):
            result = validate_response(survey_fixture(), valid_response(answers={"frequency": value}))
            self.assertTrue(result.errors)

    def test_rejects_response_bound_to_different_survey_version(self):
        result = validate_response(survey_fixture(), Response(
            "stale-version", "u1", "d1", 240,
            valid_response().answers, "v0"
        ))
        self.assertIn("survey_version_mismatch", result.errors)


class QualityPolicyTests(unittest.TestCase):
    def test_single_attention_failure_is_a_soft_flag_not_a_hold(self):
        rows, _ = process_responses(survey_fixture(), [valid_response(answers={"attention": "agree"})], b"x" * 32)
        self.assertEqual(rows[0].status, "accepted_flagged")
        self.assertIn("attention_fail", rows[0].signals)

    def test_repeated_signals_in_same_group_are_not_double_counted(self):
        repeated = "ااااااااااااااااااااااا"
        rows, _ = process_responses(survey_fixture(), [
            valid_response("a", "user-a", device_id="device-a", answers={"comment": repeated}),
            valid_response("b", "user-b", device_id="device-b", answers={"comment": repeated}),
        ], b"x" * 32)
        self.assertEqual(rows[0].status, "accepted_flagged")
        self.assertIn("low_effort_text", rows[0].signals)
        self.assertIn("duplicate_text", rows[0].signals)
        self.assertEqual(rows[0].review_groups.count("text"), 1)

    def test_independent_signal_groups_can_trigger_hold(self):
        r = valid_response(seconds=1, answers={"attention": "agree", "comment": "ااااااااااااااااااااااا"})
        policy = QualityPolicy(min_relative_speed_batch=100, absolute_speed_seconds=0)
        rows, _ = process_responses(survey_fixture(), [r], b"x" * 32, policy)
        self.assertEqual(rows[0].status, "hold")
        self.assertIn("attention_fail", rows[0].signals)
        self.assertIn("low_effort_text", rows[0].signals)

    def test_missing_device_id_does_not_create_shared_device_flag(self):
        rows, _ = process_responses(survey_fixture(), [valid_response(device_id=None)], b"x" * 32)
        self.assertNotIn("shared_device", rows[0].signals)

    def test_short_legitimate_arabic_answer_is_not_low_effort(self):
        rows, _ = process_responses(survey_fixture(), [valid_response(answers={"comment": "لا"})], b"x" * 32)
        self.assertNotIn("low_effort_text", rows[0].signals)

    def test_repeated_submission_id_is_idempotently_deduplicated(self):
        r = valid_response(submission_id="same")
        rows, _ = process_responses(survey_fixture(), [r, r], b"x" * 32)
        self.assertEqual(len(rows), 1)

    def test_same_submission_id_with_different_payload_is_rejected(self):
        a = valid_response(submission_id="same")
        b = valid_response(submission_id="same", answers={"price": "no"})
        with self.assertRaises(ValueError):
            process_responses(survey_fixture(), [a, b], b"x" * 32)

    def test_second_valid_submission_from_same_participant_is_excluded(self):
        a = valid_response(submission_id="a", participant_id="same-user")
        b = valid_response(submission_id="b", participant_id="same-user")
        rows, _ = process_responses(survey_fixture(), [a, b], b"x" * 32)
        self.assertEqual([r.status for r in rows], ["accepted", "excluded_duplicate"])


class QuotaPrivacyAndEvidenceTests(unittest.TestCase):
    def test_quotas_count_only_accepted_responses(self):
        s = survey_fixture(quotas={"wilaya": {"oran": 1}})
        rows, counts = process_responses(s, [
            valid_response("a", "u1", device_id="dev-a", answers={"attention": "agree", "comment": "ااااااااااااااااااااااا"}),
            valid_response("b", "u2", device_id="dev-b", answers={"comment": "اقتراح إضافي لتحسين سرعة الخدمة"}),
            valid_response("c", "u3", device_id="dev-c", answers={"wilaya": "oran", "comment": "أحتاج خيارات دفع متنوعة وسهلة"}),
        ], b"x" * 32, QualityPolicy(min_relative_speed_batch=100, absolute_speed_seconds=0))
        self.assertEqual(rows[0].status, "hold")
        self.assertEqual(rows[1].status, "accepted")
        self.assertEqual(rows[2].status, "quota_full")
        self.assertEqual(counts["wilaya"]["oran"], 1)

    def test_project_scoped_pseudonymization(self):
        secret = b"z" * 32
        self.assertEqual(pseudo_id("user-1", secret, "project-a"), pseudo_id("user-1", secret, "project-a"))
        self.assertNotEqual(pseudo_id("user-1", secret, "project-a"), pseudo_id("user-1", secret, "project-b"))

    def test_rejects_weak_pseudonym_secret(self):
        with self.assertRaises(ValueError):
            pseudo_id("user-1", b"short", "project-a")

    def test_default_business_export_omits_free_text_and_identifiers(self):
        s = survey_fixture()
        rows, _ = process_responses(s, [valid_response()], b"x" * 32)
        exported = analysis_records(rows, s, b"x" * 32)
        self.assertEqual(len(exported), 1)
        self.assertNotIn("participant_id", exported[0])
        self.assertNotIn("device_id", exported[0])
        self.assertNotIn("comment", exported[0]["answers"])
        self.assertEqual(exported[0]["answers"]["frequency"], 3)
        self.assertNotIn("submission_id", exported[0])

    def test_report_rejects_rows_from_a_different_survey_version(self):
        s = survey_fixture()
        rows, _ = process_responses(s, [valid_response()], b"x" * 32)
        wrong_version = Survey(s.project_id, "v2", s.questions, s.quotas)
        with self.assertRaisesRegex(ValueError, "processed_response_survey_version_mismatch"):
            build_report(rows, wrong_version, [])

    def test_export_rejects_rows_from_a_different_survey_version(self):
        s = survey_fixture()
        rows, _ = process_responses(s, [valid_response()], b"x" * 32)
        wrong_version = Survey(s.project_id, "v2", s.questions, s.quotas)
        with self.assertRaisesRegex(ValueError, "processed_response_survey_version_mismatch"):
            analysis_records(rows, wrong_version, b"x" * 32)

    def test_declared_support_is_not_demand_validation(self):
        result = label_hypothesis(k=80, n=100, threshold=0.6, minimum_n=30, evidence_type="declared")
        self.assertEqual(result["label"], "supported")
        self.assertEqual(result["evidence_scope"], "declared_only")
        self.assertFalse(result["demand_validation_eligible"])
        self.assertIn("not demand validation", result["qualification"])

    def test_small_segment_is_inconclusive(self):
        result = label_hypothesis(k=18, n=20, threshold=0.5, minimum_n=30, evidence_type="declared")
        self.assertEqual(result["label"], "inconclusive")

    def test_survey_report_cannot_promote_answers_to_transactional_evidence(self):
        s = survey_fixture()
        rows, _ = process_responses(s, [valid_response()], b"x" * 32)
        with self.assertRaisesRegex(ValueError, "non_declared_evidence_requires_external_provenance"):
            build_report(rows, s, [Hypothesis(
                id="sales-claim", question_id="price", positive_values=("yes",),
                threshold=0.4, minimum_n=1, evidence_type="transactional"
            )])

    def test_wilson_interval_edge_cases(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))
        with self.assertRaises(ValueError):
            wilson_interval(4, 3)

    def test_quota_cap_never_exceeded_in_large_batch(self):
        s = survey_fixture(quotas={"wilaya": {"oran": 5}})
        responses = [
            valid_response(f"s{i}", f"u{i}", device_id=f"d{i}", answers={
                "wilaya": "oran", "comment": f"اقتراح رقم {i} لتحسين الخدمة"
            })
            for i in range(30)
        ]
        rows, counts = process_responses(s, responses, b"x" * 32)
        self.assertEqual(counts["wilaya"]["oran"], 5)
        self.assertEqual(sum(row.status in {"accepted", "accepted_flagged"} for row in rows), 5)
        self.assertEqual(sum(row.status == "quota_full" for row in rows), 25)

    def test_build_report_carries_sample_flow_and_evidence_scope(self):
        s = survey_fixture()
        rows, _ = process_responses(s, [
            valid_response("s1", "u1", device_id="d1", answers={"price": "yes", "comment": "أرغب في معرفة السعر والخيارات"}),
            valid_response("s2", "u2", device_id="d2", answers={"price": "yes", "comment": "مناسب إذا كانت الخدمة سريعة"}),
            valid_response("s3", "u3", device_id="d3", answers={"price": "no", "comment": "لا أحتاج هذه الخدمة حالياً"}),
        ], b"x" * 32)
        report = build_report(rows, s, [Hypothesis(
            id="price-interest", question_id="price", positive_values=("yes",),
            threshold=0.4, minimum_n=2, evidence_type="declared"
        )])
        self.assertEqual(report["accepted_n"], 3)
        self.assertEqual(report["sample_flow"]["accepted"], 3)
        self.assertEqual(report["sample_flow"]["hold"], 0)
        self.assertEqual(report["hypotheses"][0]["evidence_scope"], "declared_only")
        self.assertFalse(report["hypotheses"][0]["demand_validation_eligible"])


if __name__ == "__main__":
    unittest.main()
