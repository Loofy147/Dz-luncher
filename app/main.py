from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.models import RewardLedgerEntry, SurveyCampaign, SurveyResponse
from app.security import (
    SESSION_COOKIE, SESSION_TTL_SECONDS, SessionIdentity, create_session,
    destroy_session, load_identity, verify_csrf,
)
from app.services import (
    ServiceError, authenticate_user, business_campaigns, campaign_report, create_draft,
    get_public_campaign, participant_rewards, publish_campaign, public_campaigns,
    register_user, submit_response, update_draft,
)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _safe_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


async def _form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", "replace")
    values = parse_qs(body, keep_blank_values=True, max_num_fields=300)
    return {key: entries[-1] for key, entries in values.items() if entries}


def _identity(request: Request) -> SessionIdentity | None:
    return load_identity(request.app.state.session_factory, request.cookies.get(SESSION_COOKIE))


def _require_identity(request: Request, *, role: str | None = None) -> SessionIdentity:
    identity = _identity(request)
    if identity is None:
        raise ServiceError("سجّل الدخول أولاً للمتابعة.", 401, "authentication_required")
    if role and identity.role not in {role, "admin"}:
        raise ServiceError("هذه الصفحة غير متاحة لنوع حسابك.", 403, "role_required")
    return identity


def _csrf(request: Request, identity: SessionIdentity, form: dict[str, str] | None = None) -> None:
    candidate = request.headers.get("x-csrf-token") or (form or {}).get("csrf_token")
    if not verify_csrf(identity, candidate):
        raise ServiceError("انتهت صلاحية نموذج الأمان. حدّث الصفحة وأعد المحاولة.", 403, "csrf_failed")


def _render(request: Request, name: str, context: dict | None = None, status_code: int = 200) -> HTMLResponse:
    identity = _identity(request)
    values = {"request": request, "user": identity, "csrf_token": identity.csrf_token if identity else "", **(context or {})}
    return TEMPLATES.TemplateResponse(request=request, name=name, context=values, status_code=status_code)


def _set_session_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, value, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=os.getenv("APP_ENV", "development").lower() == "production",
        samesite="lax", path="/",
    )


def create_app(*, engine=None, session_factory=None, initialize: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if application.state.initialize_schema and os.getenv("APP_ENV", "development").lower() != "production":
            initialize_schema(application.state.engine)
        if os.getenv("APP_ENV", "development").lower() == "production":
            from app.security import session_secret
            from app.services import _pseudonym_secret
            session_secret()
            _pseudonym_secret()
        yield

    app = FastAPI(title="Dz-luncher | منصة الاستبيانات والتحقق", docs_url=None, redoc_url=None, lifespan=lifespan)
    if engine is None:
        engine = make_engine()
    if session_factory is None:
        session_factory = make_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.initialize_schema = initialize
    app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            host = request.headers.get("host", "").lower()
            if origin:
                try:
                    origin_host = urlsplit(origin).netloc.lower()
                except ValueError:
                    origin_host = ""
                if not host or origin_host != host:
                    return JSONResponse({"error": {"code": "cross_origin_write_blocked", "message": "Cross-origin writes are not allowed."}}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'")
        if request.url.scheme == "https" or os.getenv("APP_ENV", "development").lower() == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code)
        return _render(request, "error.html", {"title": "تعذر إكمال العملية", "message": exc.message, "status_code": exc.status_code}, exc.status_code)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        message = str(exc) if os.getenv("APP_ENV", "development").lower() != "production" else "تعذر التحقق من البيانات المدخلة."
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": {"code": "invalid_request", "message": message}}, status_code=422)
        return _render(request, "error.html", {"title": "بيانات غير صالحة", "message": message, "status_code": 422}, 422)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "dz-luncher", "mode": os.getenv("APP_ENV", "development")}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        campaigns = public_campaigns(request.app.state.session_factory)
        return _render(request, "index.html", {"campaigns": campaigns, "title": "استبيانات موثوقة وقرارات أفضل"})

    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request):
        if _identity(request):
            return RedirectResponse("/", status_code=303)
        return _render(request, "auth.html", {"mode": "register", "title": "إنشاء حساب"})

    @app.post("/register")
    async def register_action(request: Request):
        if _identity(request):
            raise ServiceError("أنت مسجّل الدخول بالفعل.", 409, "already_authenticated")
        form = await _form(request)
        user = register_user(request.app.state.session_factory, email=form.get("email", ""), password=form.get("password", ""),
                             display_name=form.get("display_name", ""), role=form.get("role", "participant"))
        signed, _csrf_token = create_session(request.app.state.session_factory, user)
        target = "/business" if user.role in {"business", "admin"} else "/"
        response = RedirectResponse(target, status_code=303)
        _set_session_cookie(response, signed)
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if _identity(request):
            return RedirectResponse("/", status_code=303)
        return _render(request, "auth.html", {"mode": "login", "title": "تسجيل الدخول"})

    @app.post("/login")
    async def login_action(request: Request):
        if _identity(request):
            raise ServiceError("أنت مسجّل الدخول بالفعل.", 409, "already_authenticated")
        form = await _form(request)
        user = authenticate_user(request.app.state.session_factory, email=form.get("email", ""), password=form.get("password", ""))
        signed, _csrf_token = create_session(request.app.state.session_factory, user)
        target = "/business" if user.role in {"business", "admin"} else "/"
        response = RedirectResponse(target, status_code=303)
        _set_session_cookie(response, signed)
        return response

    @app.post("/logout")
    async def logout_action(request: Request):
        identity = _require_identity(request)
        form = await _form(request)
        _csrf(request, identity, form)
        destroy_session(request.app.state.session_factory, request.cookies.get(SESSION_COOKIE))
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/business", response_class=HTMLResponse)
    def business_home(request: Request):
        identity = _require_identity(request, role="business")
        campaigns = business_campaigns(request.app.state.session_factory, identity.user_id)
        return _render(request, "business_dashboard.html", {"campaigns": campaigns, "title": "مساحة المشاريع"})

    @app.get("/business/surveys/new", response_class=HTMLResponse)
    def new_survey_page(request: Request):
        _require_identity(request, role="business")
        return _render(request, "survey_builder.html", {
            "title": "إنشاء استبيان", "mode": "create", "slug": "", "initial_questions": None,
            "initial_quotas": "{}", "initial_hypotheses": "[]", "campaign": None,
        })

    @app.post("/business/surveys")
    async def create_survey_action(request: Request):
        identity = _require_identity(request, role="business")
        form = await _form(request)
        _csrf(request, identity, form)
        try:
            payload = json.loads(form.get("payload_json", "{}"))
        except json.JSONDecodeError as exc:
            raise ServiceError("تعذر قراءة بيانات الاستبيان. راجع النموذج.", 422, "invalid_form_json") from exc
        campaign = create_draft(request.app.state.session_factory, identity.user_id, payload)
        return RedirectResponse(f"/business/surveys/{campaign.slug}", status_code=303)

    @app.get("/business/surveys/{slug}/edit", response_class=HTMLResponse)
    def edit_survey_page(request: Request, slug: str):
        identity = _require_identity(request, role="business")
        with request.app.state.session_factory() as session:
            campaign = session.scalar(select(SurveyCampaign).where(SurveyCampaign.slug == slug))
            if campaign is None:
                raise ServiceError("الاستبيان غير موجود.", 404, "survey_not_found")
            if campaign.owner_id != identity.user_id:
                raise ServiceError("لا تملك صلاحية تعديل هذا الاستبيان.", 403, "owner_required")
            if campaign.status != "draft":
                raise ServiceError("لا يمكن تغيير نسخة منشورة؛ ستتوفر إدارة الإصدارات لاحقاً.", 409, "published_version_immutable")
            schema = json.loads(campaign.draft_schema_json)
            values = {"title": campaign.title, "objective": campaign.objective, "description": campaign.description,
                      "reward_per_response_dzd": campaign.reward_per_response_dzd, "response_limit": campaign.response_limit}
            payload = {**values, "questions": schema.get("questions", []), "quotas": schema.get("quotas", {}),
                       "hypotheses": json.loads(campaign.hypotheses_json)}
        return _render(request, "survey_builder.html", {
            "title": "تعديل مسودة", "mode": "edit", "slug": slug, "initial_questions": _safe_json(payload["questions"]),
            "initial_quotas": _safe_json(payload["quotas"]), "initial_hypotheses": _safe_json(payload["hypotheses"]),
            "campaign": values, "initial_payload": _safe_json(payload),
        })

    @app.post("/business/surveys/{slug}/edit")
    async def update_survey_action(request: Request, slug: str):
        identity = _require_identity(request, role="business")
        form = await _form(request)
        _csrf(request, identity, form)
        try:
            payload = json.loads(form.get("payload_json", "{}"))
        except json.JSONDecodeError as exc:
            raise ServiceError("تعذر قراءة بيانات الاستبيان.", 422, "invalid_form_json") from exc
        update_draft(request.app.state.session_factory, identity.user_id, slug, payload)
        return RedirectResponse(f"/business/surveys/{slug}", status_code=303)

    @app.post("/business/surveys/{slug}/publish")
    async def publish_survey_action(request: Request, slug: str):
        identity = _require_identity(request, role="business")
        form = await _form(request)
        _csrf(request, identity, form)
        publish_campaign(request.app.state.session_factory, identity.user_id, slug)
        return RedirectResponse(f"/business/surveys/{slug}", status_code=303)

    @app.get("/business/surveys/{slug}", response_class=HTMLResponse)
    def survey_management_page(request: Request, slug: str):
        identity = _require_identity(request, role="business")
        with request.app.state.session_factory() as session:
            campaign = session.scalar(select(SurveyCampaign).where(SurveyCampaign.slug == slug))
            if campaign is None:
                raise ServiceError("الاستبيان غير موجود.", 404, "survey_not_found")
            if campaign.owner_id != identity.user_id:
                raise ServiceError("لا تملك صلاحية الاطلاع على هذا الاستبيان.", 403, "owner_required")
            accepted_n = sum(1 for _ in session.scalars(select(SurveyResponse.id).where(
                SurveyResponse.survey_id == campaign.id,
                SurveyResponse.status.in_(("accepted", "accepted_flagged")),
            )))
            ledger_entries = list(session.scalars(select(RewardLedgerEntry).where(RewardLedgerEntry.survey_id == campaign.id)))
            ledger = {"available_dzd": sum(x.available_delta_dzd for x in ledger_entries),
                      "obligated_dzd": sum(x.obligated_delta_dzd for x in ledger_entries),
                      "paid_dzd": sum(x.paid_delta_dzd for x in ledger_entries)}
        return _render(request, "survey_management.html", {
            "title": campaign.title, "campaign": campaign, "accepted_n": accepted_n, "ledger": ledger,
            "public_url": str(request.base_url).rstrip("/") + f"/s/{campaign.slug}",
        })

    @app.get("/business/surveys/{slug}/report", response_class=HTMLResponse)
    def report_page(request: Request, slug: str):
        identity = _require_identity(request, role="business")
        report = campaign_report(request.app.state.session_factory, slug=slug, owner_id=identity.user_id)
        return _render(request, "report.html", {"title": "تقرير الاستبيان", "report": report})

    @app.get("/s/{slug}", response_class=HTMLResponse)
    def take_survey_page(request: Request, slug: str):
        campaign, version, data = get_public_campaign(request.app.state.session_factory, slug)
        identity = _identity(request)
        if data["remaining"] <= 0:
            raise ServiceError("اكتمل عدد المشاركات لهذه الحملة.", 409, "campaign_full")
        return _render(request, "take_survey.html", {
            "title": campaign.title, "campaign": campaign, "schema": data["schema"],
            "accepted_n": data["accepted_n"], "remaining": data["remaining"],
            "requires_login": identity is None, "submission_id": uuid_hex(),
        })

    @app.get("/rewards", response_class=HTMLResponse)
    def rewards_page(request: Request):
        identity = _require_identity(request)
        rewards = participant_rewards(request.app.state.session_factory, identity.user_id)
        return _render(request, "rewards.html", {"title": "مكافآتي", "rewards": rewards})

    @app.get("/api/surveys")
    def list_surveys_api(request: Request):
        return {"surveys": public_campaigns(request.app.state.session_factory)}

    @app.get("/api/surveys/{slug}")
    def survey_api(request: Request, slug: str):
        campaign, version, data = get_public_campaign(request.app.state.session_factory, slug)
        return {"slug": campaign.slug, "title": campaign.title, "objective": campaign.objective,
                "version_id": version.version_id, "reward_per_response_dzd": campaign.reward_per_response_dzd,
                "remaining": data["remaining"], "schema": data["schema"]}

    @app.post("/api/surveys/{slug}/responses")
    async def response_api(request: Request, slug: str):
        identity = _require_identity(request)
        _csrf(request, identity)
        try:
            payload = await request.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ServiceError("يجب إرسال كائن JSON صالح.", 400, "invalid_json") from exc
        if not isinstance(payload, dict):
            raise ServiceError("صيغة الإجابة غير صالحة.", 422, "invalid_response_payload")
        result = submit_response(request.app.state.session_factory, slug=slug, participant_id=identity.user_id, payload=payload)
        messages = {
            "accepted": "تم استلام إجابتك بنجاح.",
            "accepted_flagged": "تم استلام إجابتك، وستظهر إشارة الجودة في التحليل.",
            "hold": "وصلت إجابتك إلى مراجعة بشرية؛ هذه ليست إدانة تلقائية.",
            "screened_out": "شكراً لوقتك. هذه الدراسة لا تستهدف حالتك وفق إجابة التأهيل.",
            "invalid": "لم تُقبل الإجابة بسبب خطأ في البيانات. راجع الحقول وحاول مجدداً.",
            "quota_full": "اكتملت الحصة الخاصة بهذه الفئة.",
            "excluded_duplicate": "يُسمح بمشاركة واحدة فقط في هذه الدراسة.",
        }
        result["message"] = messages.get(result["status"], "تمت معالجة الإجابة.")
        return result

    @app.get("/api/me")
    def me_api(request: Request):
        identity = _require_identity(request)
        return {"id": identity.user_id, "display_name": identity.display_name, "email": identity.email, "role": identity.role}

    return app


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex


app = create_app()
