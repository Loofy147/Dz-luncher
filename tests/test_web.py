from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app


def test_business_can_create_publish_and_receive_a_real_form_response(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "web-test-session-secret-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "web-test-pseudonym-secret-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'web.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    application = create_app(engine=engine, session_factory=factory, initialize=False)

    with TestClient(application) as client:
        signup = client.post("/register", data={
            "display_name": "صاحب مشروع", "email": "business@example.dz",
            "password": "correct-horse-battery", "role": "business",
        }, follow_redirects=True)
        assert signup.status_code == 200
        assert "مساحة صاحب المشروع" in signup.text
        me = client.get("/api/me")
        assert me.status_code == 200 and me.json()["role"] == "business"

        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', signup.text)
        assert csrf_match
        csrf = csrf_match.group(1)
        schema = {
            "title": "اختبار توصيل محلي",
            "objective": "معرفة أولويات الزبائن قبل الإطلاق.",
            "description": "استبيان اختبار عبر الواجهة العربية.",
            "reward_per_response_dzd": 0,
            "response_limit": 10,
            "quotas": {},
            "hypotheses": [{"id": "H1", "question_id": "q6", "positive_values": ["option_1"], "threshold": 0.4, "minimum_n": 1, "evidence_type": "declared"}],
            "questions": [
                {"id": "q1", "text": "في أي ولاية تقيم؟", "kind": "single", "options": [{"id": "option_1", "label": "الجزائر"}, {"id": "option_2", "label": "وهران"}]},
                {"id": "q2", "text": "هل استخدمت الخدمة مؤخراً؟", "kind": "single", "options": [{"id": "option_1", "label": "نعم"}, {"id": "option_2", "label": "لا"}], "disqualify_if": ["option_2"]},
                {"id": "q3", "text": "كم مرة استخدمت الخدمة؟", "kind": "number", "lo": 1, "hi": 30, "show_if": {"question_id": "q2", "any_of": ["option_1"]}},
                {"id": "q4", "text": "قيّم التجربة من 1 إلى 5", "kind": "scale", "lo": 1, "hi": 5, "grid": "rating"},
                {"id": "q5", "text": "اختر محايد للتحقق", "kind": "single", "options": [{"id": "option_1", "label": "موافق"}, {"id": "option_2", "label": "محايد"}], "attention_expected": "option_2"},
                {"id": "q6", "text": "هل ستجرب الخدمة؟", "kind": "single", "options": [{"id": "option_1", "label": "نعم"}, {"id": "option_2", "label": "لا"}]},
            ],
        }
        created = client.post("/business/surveys", data={"csrf_token": csrf, "payload_json": json.dumps(schema, ensure_ascii=False)}, follow_redirects=False)
        assert created.status_code == 303
        management_url = created.headers["location"]
        management = client.get(management_url)
        assert management.status_code == 200
        assert "بوابة النشر" in management.text
        slug = management_url.rsplit("/", 1)[-1]
        publish = client.post(f"/business/surveys/{slug}/publish", data={"csrf_token": csrf}, follow_redirects=False)
        assert publish.status_code == 303

        public = client.get(f"/s/{slug}")
        assert public.status_code == 200
        assert 'dir="rtl"' in public.text
        assert "إرسال الإجابة" in public.text
        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', public.text)
        assert csrf_match
        csrf = csrf_match.group(1)
        version_match = re.search(r'id="survey-version-id" value="([^"]+)"', public.text)
        submission_match = re.search(r'id="submission-id" value="([^"]+)"', public.text)
        assert version_match and submission_match
        response_body = {
            "submission_id": submission_match.group(1),
            "survey_version_id": version_match.group(1),
            "seconds": 120,
            "answers": {"q1": "option_1", "q2": "option_1", "q3": "3", "q4": "4", "q5": "option_2", "q6": "option_1"},
        }
        no_csrf = client.post(f"/api/surveys/{slug}/responses", json=response_body)
        assert no_csrf.status_code == 403
        submitted = client.post(f"/api/surveys/{slug}/responses", json=response_body, headers={"X-CSRF-Token": csrf})
        assert submitted.status_code == 200
        assert submitted.json()["status"] in {"accepted", "accepted_flagged"}
        assert submitted.json()["reward_status"] == "not_earned"
        report = client.get(f"/business/surveys/{slug}/report")
        assert report.status_code == 200
        assert "دليل مُصرّح به" in report.text or "declared_only" in report.text

    engine.dispose()
