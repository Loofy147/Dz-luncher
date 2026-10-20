from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.services import _validate_campaign_input
from app.survey_templates import get_survey_template, list_survey_templates


def test_catalog_metadata_is_unique_complete_and_safe_by_default():
    templates = list_survey_templates()
    ids = [template["id"] for template in templates]
    assert len(templates) == 9
    assert len(ids) == len(set(ids))
    for item in templates:
        assert item["name"].strip()
        assert item["decision"].strip()
        assert item["audience"].strip()
        assert item["duration_minutes"] > 0
        assert item["target_completes"] >= item["minimum_interpretable_n"]
        assert item["customization_required"] is True
        assert item["launch_checks"]
        template = get_survey_template(item["id"])
        assert template is not None
        payload = template["payload"]
        assert payload["reward_per_response_dzd"] == 0
        assert payload["response_limit"] == item["target_completes"]
        assert payload["questions"]
        assert payload["description"]
        assert "لا تذكر" in payload["description"]


def test_all_builtin_instruments_pass_the_real_campaign_validation_contract():
    for item in list_survey_templates():
        template = get_survey_template(item["id"])
        assert template is not None
        result = _validate_campaign_input(
            template["payload"],
            campaign_id=f"test-{item['id']}",
            draft_version="draft-v1",
        )
        title, objective, description, reward, limit, schema, hypotheses = result
        assert title == template["payload"]["title"]
        assert objective.strip()
        assert description.strip()
        assert reward == 0
        assert limit == item["target_completes"]
        assert len(schema["questions"]) >= 6
        assert hypotheses


def test_template_payloads_are_returned_as_independent_copies():
    first = get_survey_template("local-delivery")
    second = get_survey_template("local-delivery")
    assert first is not None and second is not None
    first["payload"]["questions"][0]["text"] = "تغيير مؤقت للاختبار"
    first["payload"]["hypotheses"].clear()
    third = get_survey_template("local-delivery")
    assert third is not None
    assert third["payload"]["questions"][0]["text"] != "تغيير مؤقت للاختبار"
    assert third["payload"]["hypotheses"]


def test_business_can_choose_a_template_and_save_it_as_a_private_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "template-test-session-secret-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "template-test-pseudonym-secret-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'template-catalog.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    app = create_app(engine=engine, session_factory=factory, initialize=False)

    with TestClient(app) as client:
        catalogue = client.get("/api/survey-templates")
        assert catalogue.status_code == 200
        assert len(catalogue.json()["templates"]) == 9
        detail = client.get("/api/survey-templates/local-delivery")
        assert detail.status_code == 200
        assert detail.json()["payload"]["title"] == "عادات التوصيل وتجربة الطلب"
        assert client.get("/api/survey-templates/missing").status_code == 404

        signup = client.post(
            "/register",
            data={
                "display_name": "صاحب مشروع",
                "email": "template-owner@example.dz",
                "password": "correct-horse-battery",
                "role": "business",
            },
            follow_redirects=True,
        )
        assert signup.status_code == 200
        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', signup.text)
        assert csrf_match
        csrf = csrf_match.group(1)

        selected = client.get("/business/surveys/new?template=local-delivery")
        assert selected.status_code == 200
        assert "القالب المحدد" in selected.text
        assert "عادات التوصيل وتجربة الطلب" in selected.text
        assert "لا تستقبل مشاركات حقيقية" in selected.text
        assert client.get("/business").status_code == 200
        assert "لا توجد دراسات بعد" in client.get("/business").text

        created = client.post(
            "/business/surveys",
            data={
                "csrf_token": csrf,
                "payload_json": json.dumps(detail.json()["payload"], ensure_ascii=False),
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        management = client.get(created.headers["location"])
        assert management.status_code == 200
        assert "عادات التوصيل وتجربة الطلب" in management.text
        assert "مسودة" in management.text
        assert client.get("/api/surveys").json()["surveys"] == []

    engine.dispose()
