"""Arabic-first survey validation core.

Pure, standard-library-only engine for survey schema validation, screening,
branching, response-quality signals, batch quotas, project-scoped pseudonyms,
and evidence-labelled reports. Production persistence must enforce quota and
submission idempotency transactionally; this module provides deterministic
batch logic, not a distributed transaction manager.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_DIGIT_TRANSLATION = str.maketrans(
    {chr(0x660 + i): str(i) for i in range(10)}
    | {chr(0x6F0 + i): str(i) for i in range(10)}
)
_ARABIC_MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_SPACE = re.compile(r"\s+")
_LETTER_OR_NUMBER = re.compile(r"[\w\u0600-\u06FF]", re.UNICODE)

SUPPORTED_QUESTION_KINDS = frozenset({"single", "scale", "number", "text"})
ACCEPTED_STATUSES = frozenset({"accepted", "accepted_flagged"})

# Signals are evidence indicators, not fraud verdicts. A category contributes
# at most one review group even if it produces multiple signal codes.
SIGNAL_GROUP = {
    "speeding": "timing",
    "straightlining": "response_pattern",
    "attention_fail": "attention",
    "low_effort_text": "text",
    "duplicate_text": "text",
    "shared_device": "device_context",
}


@dataclass(frozen=True)
class Choice:
    id: str
    label: str


@dataclass(frozen=True)
class Branch:
    question_id: str
    any_of: tuple[str, ...]


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    kind: str  # single | scale | number | text
    options: tuple[Choice, ...] = ()
    required: bool = True
    show_if: Branch | None = None
    disqualify_if: tuple[str, ...] = ()
    attention_expected: str | None = None
    grid: str | None = None
    lo: float | None = None
    hi: float | None = None


@dataclass(frozen=True)
class Survey:
    project_id: str
    version_id: str
    questions: tuple[Question, ...]
    quotas: Mapping[str, Mapping[str, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class Response:
    submission_id: str
    participant_id: str
    device_id: str | None
    seconds: float | int | None
    answers: Mapping[str, Any]
    survey_version_id: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]
    screened_out: bool
    visible_question_ids: tuple[str, ...]
    normalized_answers: Mapping[str, Any]


@dataclass(frozen=True)
class QualityPolicy:
    absolute_speed_seconds: float = 12.0
    speed_ratio_to_batch_median: float = 0.33
    min_relative_speed_batch: int = 20
    min_grid_answers: int = 5
    duplicate_text_min_chars: int = 15
    review_min_groups: int = 2


@dataclass(frozen=True)
class ProcessedResponse:
    response: Response
    status: str
    signals: tuple[str, ...] = ()
    review_groups: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    normalized_answers: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    question_id: str
    positive_values: tuple[Any, ...]
    threshold: float
    minimum_n: int
    evidence_type: str = "declared"  # declared | observed_behavior | transactional
    segment_question_id: str | None = None
    segment_option_id: str | None = None


def norm_digits(value: Any) -> str:
    """Translate Arabic-Indic and Eastern Arabic-Indic digits to ASCII."""
    return str(value).translate(_DIGIT_TRANSLATION).replace("٫", ".").replace("٬", "")


def norm_ar(value: Any) -> str:
    """Conservative Arabic normalization for duplicate-text comparisons.

    Removes diacritics/tatweel and normalizes alef variants/whitespace, but
    preserves taa marbuta (ة) and alif maqsura (ى) to avoid needless collisions.
    It is not a semantic-equivalence or personal-data detector.
    """
    text = unicodedata.normalize("NFKC", str(value))
    text = _ARABIC_MARKS.sub("", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}))
    return _SPACE.sub(" ", text).strip().lower()


def _nonempty(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and value.strip() == "")


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _numeric(value: Any) -> int | float:
    if isinstance(value, bool) or value is None:
        raise ValueError("not numeric")
    try:
        parsed = float(norm_digits(value).strip())
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("not numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError("not finite")
    if parsed.is_integer():
        return int(parsed)
    return parsed


def validate_survey(survey: Survey) -> None:
    """Raise ValueError if a survey definition violates supported contracts."""
    if not isinstance(survey, Survey):
        raise ValueError("survey must be a Survey instance")
    if not isinstance(survey.project_id, str) or not survey.project_id.strip():
        raise ValueError("project_id is required")
    if not isinstance(survey.version_id, str) or not survey.version_id.strip():
        raise ValueError("version_id is required")
    if not isinstance(survey.questions, tuple):
        raise ValueError("survey_questions_must_be_immutable_tuple")
    if not survey.questions:
        raise ValueError("survey must contain at least one question")
    if len(survey.questions) > 500:
        raise ValueError("survey_exceeds_maximum_question_count")

    prior: dict[str, Question] = {}
    for q in survey.questions:
        if not isinstance(q, Question):
            raise ValueError("questions_must_contain_Question_instances")
        if not isinstance(q.options, tuple):
            raise ValueError(f"question_options_must_be_tuple:{q.id}")
        if not isinstance(q.disqualify_if, tuple):
            raise ValueError(f"disqualify_if_must_be_tuple:{q.id}")
        if not _valid_id(q.id):
            raise ValueError(f"invalid_question_id:{q.id}")
        if q.id in prior:
            raise ValueError(f"duplicate_question_id:{q.id}")
        if not isinstance(q.text, str) or not q.text.strip():
            raise ValueError(f"question_text_required:{q.id}")
        if len(q.text) > 4000:
            raise ValueError(f"question_text_too_long:{q.id}")
        if not isinstance(q.kind, str) or q.kind not in SUPPORTED_QUESTION_KINDS:
            raise ValueError(f"unsupported_question_kind:{q.id}")
        if not isinstance(q.required, bool):
            raise ValueError(f"required_must_be_bool:{q.id}")

        if q.kind == "single":
            if not q.options:
                raise ValueError(f"options_required:{q.id}")
            if len(q.options) > 100:
                raise ValueError(f"too_many_options:{q.id}")
            option_ids: set[str] = set()
            for opt in q.options:
                if not isinstance(opt, Choice):
                    raise ValueError(f"options_must_be_Choice_instances:{q.id}")
                if not _valid_id(opt.id):
                    raise ValueError(f"invalid_option_id:{q.id}:{opt.id}")
                if opt.id in option_ids:
                    raise ValueError(f"duplicate_option_id:{q.id}:{opt.id}")
                if not isinstance(opt.label, str) or not opt.label.strip():
                    raise ValueError(f"option_label_required:{q.id}:{opt.id}")
                if len(opt.label) > 500:
                    raise ValueError(f"option_label_too_long:{q.id}:{opt.id}")
                option_ids.add(opt.id)
        elif q.options:
            raise ValueError(f"options_not_supported_for_kind:{q.id}")

        if q.kind in {"number", "scale"}:
            if q.lo is None or q.hi is None:
                raise ValueError(f"numeric_bounds_required:{q.id}")
            if isinstance(q.lo, bool) or isinstance(q.hi, bool) or not isinstance(q.lo, (int, float)) or not isinstance(q.hi, (int, float)):
                raise ValueError(f"invalid_numeric_bounds:{q.id}")
            low_bound, high_bound = float(q.lo), float(q.hi)
            if not math.isfinite(low_bound) or not math.isfinite(high_bound) or low_bound > high_bound:
                raise ValueError(f"invalid_numeric_bounds:{q.id}")
        elif q.lo is not None or q.hi is not None:
            raise ValueError(f"numeric_bounds_not_supported:{q.id}")

        if q.kind != "single" and (q.disqualify_if or q.attention_expected is not None):
            raise ValueError(f"single_choice_rule_on_non_single:{q.id}")
        if any(not _valid_id(value) for value in q.disqualify_if) or len(set(q.disqualify_if)) != len(q.disqualify_if):
            raise ValueError(f"invalid_disqualify_options:{q.id}")
        valid_options = {opt.id for opt in q.options}
        if any(value not in valid_options for value in q.disqualify_if):
            raise ValueError(f"unknown_disqualify_option:{q.id}")
        if q.attention_expected is not None and (not _valid_id(q.attention_expected) or q.attention_expected not in valid_options):
            raise ValueError(f"unknown_attention_option:{q.id}")
        if q.grid is not None:
            if not isinstance(q.grid, str) or not q.grid.strip() or q.kind != "scale":
                raise ValueError(f"grid_requires_named_scale_question:{q.id}")

        if q.show_if is not None:
            if not isinstance(q.show_if, Branch):
                raise ValueError(f"unsupported_branch_contract:{q.id}")
            if not _valid_id(q.show_if.question_id) or not isinstance(q.show_if.any_of, tuple):
                raise ValueError(f"invalid_branch_contract:{q.id}")
            if any(not _valid_id(value) for value in q.show_if.any_of) or len(set(q.show_if.any_of)) != len(q.show_if.any_of):
                raise ValueError(f"branch_options_must_be_unique_tuple:{q.id}")
            controller = prior.get(q.show_if.question_id)
            if controller is None:
                raise ValueError(f"branch_must_reference_prior_question:{q.id}")
            if controller.kind != "single":
                raise ValueError(f"branch_controller_must_be_single:{q.id}")
            controller_options = {opt.id for opt in controller.options}
            if not q.show_if.any_of or not set(q.show_if.any_of).issubset(controller_options):
                raise ValueError(f"invalid_branch_options:{q.id}")

        prior[q.id] = q

    if not isinstance(survey.quotas, Mapping):
        raise ValueError("quotas_must_be_mapping")
    seen_quota_questions: set[str] = set()
    for qid, caps in survey.quotas.items():
        if not _valid_id(qid):
            raise ValueError(f"quota_invalid_question_id:{qid}")
        q = prior.get(qid)
        if q is None:
            raise ValueError(f"quota_unknown_question:{qid}")
        if q.kind != "single":
            raise ValueError(f"quota_requires_single_choice:{qid}")
        if not q.required or q.show_if is not None:
            raise ValueError(f"quota_question_must_be_required_and_always_visible:{qid}")
        if qid in seen_quota_questions:
            raise ValueError(f"duplicate_quota_question:{qid}")
        seen_quota_questions.add(qid)
        if not isinstance(caps, Mapping):
            raise ValueError(f"quota_caps_must_be_mapping:{qid}")
        valid_options = {opt.id for opt in q.options}
        for option_id, cap in caps.items():
            if not _valid_id(option_id):
                raise ValueError(f"quota_invalid_option_id:{qid}:{option_id}")
            if option_id not in valid_options:
                raise ValueError(f"quota_unknown_option:{qid}:{option_id}")
            if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
                raise ValueError(f"quota_cap_must_be_positive_integer:{qid}:{option_id}")


def _reject_unknown_fields(payload: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        names = ",".join(sorted(str(name) for name in unknown))
        raise ValueError(f"unknown_fields:{context}:{names}")


def survey_from_dict(payload: Mapping[str, Any]) -> Survey:
    """Parse an untrusted JSON-like survey contract into validated dataclasses."""
    if not isinstance(payload, Mapping):
        raise ValueError("survey_payload_must_be_mapping")
    _reject_unknown_fields(payload, {"project_id", "version_id", "questions", "quotas"}, "survey")
    for required in ("project_id", "version_id", "questions"):
        if required not in payload:
            raise ValueError(f"missing_survey_field:{required}")
    raw_questions = payload["questions"]
    if not isinstance(raw_questions, (list, tuple)):
        raise ValueError("questions_must_be_array")

    allowed_question_fields = {
        "id", "text", "kind", "options", "required", "show_if", "disqualify_if",
        "attention_expected", "grid", "lo", "hi",
    }
    questions: list[Question] = []
    for index, raw_question in enumerate(raw_questions):
        context = f"question[{index}]"
        if not isinstance(raw_question, Mapping):
            raise ValueError(f"{context}_must_be_object")
        _reject_unknown_fields(raw_question, allowed_question_fields, context)
        for required in ("id", "text", "kind"):
            if required not in raw_question:
                raise ValueError(f"missing_field:{context}:{required}")

        raw_options = raw_question.get("options", [])
        if not isinstance(raw_options, (list, tuple)):
            raise ValueError(f"options_must_be_array:{context}")
        options: list[Choice] = []
        for option_index, raw_option in enumerate(raw_options):
            option_context = f"{context}.options[{option_index}]"
            if not isinstance(raw_option, Mapping):
                raise ValueError(f"{option_context}_must_be_object")
            _reject_unknown_fields(raw_option, {"id", "label"}, option_context)
            if "id" not in raw_option or "label" not in raw_option:
                raise ValueError(f"option_requires_id_and_label:{option_context}")
            options.append(Choice(raw_option["id"], raw_option["label"]))

        raw_branch = raw_question.get("show_if")
        branch: Branch | None = None
        if raw_branch is not None:
            if not isinstance(raw_branch, Mapping):
                raise ValueError(f"show_if_must_be_object:{context}")
            _reject_unknown_fields(raw_branch, {"question_id", "any_of"}, f"{context}.show_if")
            if "question_id" not in raw_branch or "any_of" not in raw_branch:
                raise ValueError(f"show_if_requires_question_id_and_any_of:{context}")
            raw_any_of = raw_branch["any_of"]
            if not isinstance(raw_any_of, (list, tuple)):
                raise ValueError(f"show_if_any_of_must_be_array:{context}")
            branch = Branch(raw_branch["question_id"], tuple(raw_any_of))

        raw_disqualify = raw_question.get("disqualify_if", [])
        if not isinstance(raw_disqualify, (list, tuple)):
            raise ValueError(f"disqualify_if_must_be_array:{context}")

        questions.append(Question(
            id=raw_question["id"],
            text=raw_question["text"],
            kind=raw_question["kind"],
            options=tuple(options),
            required=raw_question.get("required", True),
            show_if=branch,
            disqualify_if=tuple(raw_disqualify),
            attention_expected=raw_question.get("attention_expected"),
            grid=raw_question.get("grid"),
            lo=raw_question.get("lo"),
            hi=raw_question.get("hi"),
        ))

    raw_quotas = payload.get("quotas", {})
    if not isinstance(raw_quotas, Mapping):
        raise ValueError("quotas_must_be_object")
    quotas: dict[str, dict[str, int]] = {}
    for question_id, raw_caps in raw_quotas.items():
        if not isinstance(raw_caps, Mapping):
            raise ValueError(f"quota_caps_must_be_object:{question_id}")
        quotas[question_id] = dict(raw_caps)

    survey = Survey(payload["project_id"], payload["version_id"], tuple(questions), quotas)
    validate_survey(survey)
    return survey


def response_from_dict(payload: Mapping[str, Any]) -> Response:
    """Parse a response transport object; validate it against a survey separately."""
    if not isinstance(payload, Mapping):
        raise ValueError("response_payload_must_be_mapping")
    _reject_unknown_fields(payload, {
        "submission_id", "participant_id", "device_id", "seconds", "answers", "survey_version_id"
    }, "response")
    for required in ("submission_id", "participant_id", "survey_version_id", "answers"):
        if required not in payload:
            raise ValueError(f"missing_response_field:{required}")
    if not isinstance(payload["answers"], Mapping):
        raise ValueError("answers_must_be_object")
    return Response(
        submission_id=payload["submission_id"],
        participant_id=payload["participant_id"],
        device_id=payload.get("device_id"),
        seconds=payload.get("seconds"),
        answers=dict(payload["answers"]),
        survey_version_id=payload["survey_version_id"],
    )


def _is_visible(q: Question, answers: Mapping[str, Any]) -> bool:
    if q.show_if is None:
        return True
    return answers.get(q.show_if.question_id) in q.show_if.any_of


def _validate_response(survey: Survey, response: Response) -> ValidationResult:
    errors: list[str] = []
    normalized: dict[str, Any] = {}
    visible_ids: list[str] = []
    answers = response.answers

    if not isinstance(answers, Mapping):
        return ValidationResult(("answers_must_be_mapping",), False, (), {})
    if not isinstance(response.submission_id, str) or not response.submission_id.strip():
        errors.append("missing_or_invalid_submission_id")
    if not isinstance(response.participant_id, str) or not response.participant_id.strip():
        errors.append("missing_or_invalid_participant_id")
    if response.survey_version_id != survey.version_id:
        errors.append("survey_version_mismatch")
    if response.device_id is not None and not isinstance(response.device_id, str):
        errors.append("invalid_device_id")

    known = {q.id for q in survey.questions}
    for answer_id, value in answers.items():
        if answer_id not in known and _nonempty(value):
            errors.append(f"unknown_question:{answer_id}")

    screened_index: int | None = None
    for index, q in enumerate(survey.questions):
        value = answers.get(q.id)
        has_value = _nonempty(value)
        visible = _is_visible(q, answers)

        if not visible:
            if has_value:
                errors.append(f"branch_violation:{q.id}")
            continue

        if screened_index is not None and index > screened_index:
            if has_value:
                errors.append(f"answer_after_screenout:{q.id}")
            continue
        visible_ids.append(q.id)

        if not has_value:
            if q.required:
                errors.append(f"missing:{q.id}")
            continue

        if q.kind == "single":
            valid_options = {opt.id for opt in q.options}
            if not isinstance(value, str) or value not in valid_options:
                errors.append(f"bad_option:{q.id}")
                continue
            normalized[q.id] = value
        elif q.kind in {"scale", "number"}:
            try:
                numeric = _numeric(value)
            except ValueError:
                errors.append(f"not_number:{q.id}")
                continue
            if numeric < q.lo or numeric > q.hi:
                errors.append(f"out_of_range:{q.id}")
                continue
            normalized[q.id] = numeric
        elif q.kind == "text":
            if not isinstance(value, str):
                errors.append(f"not_text:{q.id}")
                continue
            clean = value.strip()
            if len(clean) > 5000:
                errors.append(f"text_too_long:{q.id}")
                continue
            normalized[q.id] = clean

        if q.disqualify_if and normalized.get(q.id) in q.disqualify_if:
            screened_index = index

    # Unique errors improve API stability and make audit output deterministic.
    unique_errors = tuple(dict.fromkeys(errors))
    screened_out = screened_index is not None and not unique_errors
    return ValidationResult(unique_errors, screened_out, tuple(visible_ids), normalized)


def validate_response(survey: Survey, response: Response) -> ValidationResult:
    validate_survey(survey)
    if not isinstance(response, Response):
        raise ValueError("response_must_be_Response_instance")
    return _validate_response(survey, response)


def _submission_fingerprint(response: Response) -> str:
    payload = {
        "participant_id": response.participant_id,
        "survey_version_id": response.survey_version_id,
        "device_id": response.device_id,
        "seconds": response.seconds,
        "answers": response.answers,
    }
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("response_payload_not_serializable") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _quality_signals(
    survey: Survey,
    response: Response,
    validation: ValidationResult,
    median_seconds: float | None,
    shared_devices: set[str],
    duplicate_texts: set[str],
    policy: QualityPolicy,
) -> tuple[str, ...]:
    signals: set[str] = set()
    seconds: float | None
    try:
        seconds = float(response.seconds) if response.seconds is not None else None
        if seconds is not None and not math.isfinite(seconds):
            seconds = None
    except (TypeError, ValueError, OverflowError):
        seconds = None

    if seconds is not None and seconds >= 0:
        if seconds < policy.absolute_speed_seconds:
            signals.add("speeding")
        elif median_seconds is not None and seconds < policy.speed_ratio_to_batch_median * median_seconds:
            signals.add("speeding")

    if response.device_id and response.device_id in shared_devices:
        signals.add("shared_device")

    grids: dict[str, list[int | float]] = defaultdict(list)
    for q in survey.questions:
        if q.id not in validation.visible_question_ids:
            continue
        value = validation.normalized_answers.get(q.id)
        if value is None:
            continue
        if q.attention_expected is not None and value != q.attention_expected:
            signals.add("attention_fail")
        if q.grid is not None and q.kind == "scale" and isinstance(value, (int, float)):
            grids[q.grid].append(value)
        if q.kind == "text" and isinstance(value, str) and value:
            text_norm = norm_ar(value)
            letters = [c for c in text_norm if _LETTER_OR_NUMBER.fullmatch(c)]
            # Do not flag a short legitimate answer (e.g. «لا») just for length.
            # Flag empty-noise strings and long repeated single-character text.
            if not letters or (len(letters) >= 4 and len(set(letters)) == 1):
                signals.add("low_effort_text")
            if len(text_norm) >= policy.duplicate_text_min_chars and text_norm in duplicate_texts:
                signals.add("duplicate_text")

    if any(len(values) >= policy.min_grid_answers and len(set(values)) == 1 for values in grids.values()):
        signals.add("straightlining")

    # Stable order makes outcomes reproducible in tests, logs, and exports.
    return tuple(sorted(signals))


def process_responses(
    survey: Survey,
    responses: Sequence[Response],
    pseudonym_secret: bytes,
    policy: QualityPolicy = QualityPolicy(),
) -> tuple[list[ProcessedResponse], dict[str, Counter]]:
    """Validate/process a batch and return per-cell accepted quota counts.

    Batch processing is deterministic for a fixed input order. A production
    service still needs database uniqueness constraints and transactions for
    concurrent quota reservations and accepted-completion uniqueness.
    """
    validate_survey(survey)
    if not isinstance(pseudonym_secret, bytes) or len(pseudonym_secret) < 32:
        raise ValueError("pseudonym_secret_must_be_at_least_32_bytes")
    if not isinstance(policy, QualityPolicy):
        raise ValueError("policy_must_be_QualityPolicy")
    integer_policy_values = (policy.review_min_groups, policy.min_grid_answers, policy.min_relative_speed_batch, policy.duplicate_text_min_chars)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integer_policy_values):
        raise ValueError("invalid_quality_policy_count")
    if isinstance(policy.absolute_speed_seconds, bool) or not isinstance(policy.absolute_speed_seconds, (int, float)) or not math.isfinite(policy.absolute_speed_seconds) or policy.absolute_speed_seconds < 0:
        raise ValueError("invalid_absolute_speed_seconds")
    if isinstance(policy.speed_ratio_to_batch_median, bool) or not isinstance(policy.speed_ratio_to_batch_median, (int, float)) or not math.isfinite(policy.speed_ratio_to_batch_median) or not 0 < policy.speed_ratio_to_batch_median <= 1:
        raise ValueError("invalid_speed_ratio_to_batch_median")

    unique_responses: list[Response] = []
    seen_submission_ids: dict[str, str] = {}
    for response in responses:
        if not isinstance(response, Response):
            raise ValueError("responses_must_contain_Response_instances")
        if not isinstance(response.submission_id, str) or not response.submission_id.strip():
            raise ValueError("missing_or_invalid_submission_id")
        fingerprint = _submission_fingerprint(response)
        prior = seen_submission_ids.get(response.submission_id)
        if prior is not None:
            if prior != fingerprint:
                raise ValueError(f"conflicting_duplicate_submission_id:{response.submission_id}")
            # Exact retry: same submission identity and payload; one result only.
            continue
        seen_submission_ids[response.submission_id] = fingerprint
        unique_responses.append(response)

    validations = [_validate_response(survey, r) for r in unique_responses]
    preliminary: list[ProcessedResponse | None] = [None] * len(unique_responses)
    participant_seen: set[str] = set()
    candidate_indices: list[int] = []
    for i, (response, result) in enumerate(zip(unique_responses, validations)):
        if result.errors:
            preliminary[i] = ProcessedResponse(response, "invalid", errors=result.errors, normalized_answers=result.normalized_answers)
            continue
        participant_key = str(response.participant_id)
        if participant_key in participant_seen:
            preliminary[i] = ProcessedResponse(response, "excluded_duplicate", signals=("duplicate_submission",), normalized_answers=result.normalized_answers)
            continue
        # A valid screen-out consumes this survey attempt, preventing answer
        # shopping by changing a screener after seeing the result.
        participant_seen.add(participant_key)
        if result.screened_out:
            preliminary[i] = ProcessedResponse(response, "screened_out", normalized_answers=result.normalized_answers)
        else:
            candidate_indices.append(i)

    timing_values: list[float] = []
    for i in candidate_indices:
        value = unique_responses[i].seconds
        try:
            sec = float(value) if value is not None else math.nan
        except (TypeError, ValueError, OverflowError):
            sec = math.nan
        if math.isfinite(sec) and sec >= 0:
            timing_values.append(sec)
    median_seconds = (
        statistics.median(timing_values)
        if len(timing_values) >= policy.min_relative_speed_batch
        else None
    )

    device_participants: dict[str, set[str]] = defaultdict(set)
    text_participants: dict[str, set[str]] = defaultdict(set)
    for i in candidate_indices:
        response, result = unique_responses[i], validations[i]
        if response.device_id and str(response.device_id).strip():
            device_participants[str(response.device_id)].add(str(response.participant_id))
        for q in survey.questions:
            if q.kind != "text":
                continue
            value = result.normalized_answers.get(q.id)
            if isinstance(value, str) and value:
                normalized_text = norm_ar(value)
                if len(normalized_text) >= policy.duplicate_text_min_chars:
                    text_participants[normalized_text].add(str(response.participant_id))
    shared_devices = {device for device, users in device_participants.items() if len(users) > 1}
    duplicate_texts = {text for text, users in text_participants.items() if len(users) > 1}

    quota_counts: dict[str, Counter] = defaultdict(Counter)
    for i in candidate_indices:
        response, validation = unique_responses[i], validations[i]
        signals = _quality_signals(
            survey,
            response,
            validation,
            median_seconds,
            shared_devices,
            duplicate_texts,
            policy,
        )
        groups = tuple(sorted({SIGNAL_GROUP[s] for s in signals}))
        if len(groups) >= policy.review_min_groups:
            preliminary[i] = ProcessedResponse(
                response, "hold", signals, groups, (), validation.normalized_answers
            )
            continue

        is_quota_full = False
        for question_id, caps in survey.quotas.items():
            value = validation.normalized_answers.get(question_id)
            cap = caps.get(value)
            if cap is not None and quota_counts[question_id][value] >= cap:
                is_quota_full = True
                break
        if is_quota_full:
            preliminary[i] = ProcessedResponse(
                response, "quota_full", signals, groups, (), validation.normalized_answers
            )
            continue

        # Only accepted rows update quota cells; held, invalid, screen-out,
        # duplicate and quota-full responses do not consume accepted capacity.
        for question_id in survey.quotas:
            value = validation.normalized_answers.get(question_id)
            if value is not None:
                quota_counts[question_id][value] += 1
        status = "accepted_flagged" if signals else "accepted"
        preliminary[i] = ProcessedResponse(response, status, signals, groups, (), validation.normalized_answers)

    rows = [row for row in preliminary if row is not None]
    return rows, {question_id: counts for question_id, counts in quota_counts.items()}


def pseudo_id(participant_id: str, secret: bytes, project_id: str) -> str:
    """Return a deterministic pseudonym isolated to a project namespace."""
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("pseudonym_secret_must_be_at_least_32_bytes")
    if not isinstance(participant_id, str) or not participant_id.strip():
        raise ValueError("participant_id_required")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id_required")
    message = f"survey-pseudonym:v1:{project_id}:{participant_id}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]


def analysis_records(
    rows: Sequence[ProcessedResponse],
    survey: Survey,
    secret: bytes,
    *,
    include_free_text: bool = False,
    statuses: frozenset[str] = ACCEPTED_STATUSES,
) -> list[dict[str, Any]]:
    """Build a business-facing pseudonymous response export.

    Free text is omitted by default because it may contain names, phone
    numbers, addresses, or other identifiers. This function does not perform
    semantic PII detection; enabling free text requires an explicit review.
    """
    validate_survey(survey)
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("pseudonym_secret_must_be_at_least_32_bytes")
    exportable_text = {q.id for q in survey.questions if q.kind == "text"}
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, ProcessedResponse):
            raise ValueError("export_rows_must_be_ProcessedResponse_instances")
        if row.response.survey_version_id != survey.version_id:
            raise ValueError("processed_response_survey_version_mismatch")
        if row.status not in statuses:
            continue
        answers = {
            qid: value
            for qid, value in row.normalized_answers.items()
            if include_free_text or qid not in exportable_text
        }
        output.append({
            "pid": pseudo_id(row.response.participant_id, secret, survey.project_id),
            "status": row.status,
            "answers": answers,
        })
    return output


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; it excludes selection bias."""
    if isinstance(n, bool) or isinstance(k, bool) or not isinstance(n, int) or not isinstance(k, int):
        raise ValueError("k_and_n_must_be_integers")
    if n < 0 or k < 0 or k > n:
        raise ValueError("require 0 <= k <= n")
    if isinstance(z, bool) or not isinstance(z, (int, float)) or not math.isfinite(z) or z <= 0:
        raise ValueError("z_must_be_positive_and_finite")
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = p + z2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n * n)))
    return ((center - margin) / denom, (center + margin) / denom)


def label_hypothesis(
    *, k: int, n: int, threshold: float, minimum_n: int, evidence_type: str = "declared"
) -> dict[str, Any]:
    """Label a threshold hypothesis while retaining evidence-scope limits."""
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold_must_be_between_0_and_1")
    if isinstance(minimum_n, bool) or not isinstance(minimum_n, int) or minimum_n < 1:
        raise ValueError("minimum_n_must_be_positive_integer")
    if not isinstance(evidence_type, str) or evidence_type not in {"declared", "observed_behavior", "transactional"}:
        raise ValueError("unsupported_evidence_type")
    low, high = wilson_interval(k, n)
    if n < minimum_n:
        label = "inconclusive"
    elif low >= threshold:
        label = "supported"
    elif high < threshold:
        label = "contradicted"
    else:
        label = "weak"

    scope = {
        "declared": "declared_only",
        "observed_behavior": "observed_behavior_only",
        "transactional": "transactional_sample",
    }[evidence_type]
    qualification = {
        "declared": "Declared preferences only; not demand validation.",
        "observed_behavior": "Observed behavior in this study; not proof of repeat purchasing or market-wide demand.",
        "transactional": "Transactional evidence in this sample; assess data quality and population coverage before a broader demand claim.",
    }[evidence_type]
    return {
        "label": label,
        "k": k,
        "n": n,
        "proportion": k / n if n else None,
        "interval": (low, high),
        "threshold": float(threshold),
        "minimum_n": minimum_n,
        "evidence_type": evidence_type,
        "evidence_scope": scope,
        "demand_validation_eligible": evidence_type == "transactional" and label == "supported",
        "qualification": qualification,
    }


def build_report(
    rows: Sequence[ProcessedResponse], survey: Survey, hypotheses: Sequence[Hypothesis]
) -> dict[str, Any]:
    """Create an evidence-labelled summary with sample-flow and limitations."""
    validate_survey(survey)
    for row in rows:
        if not isinstance(row, ProcessedResponse):
            raise ValueError("report_rows_must_be_ProcessedResponse_instances")
        if row.response.survey_version_id != survey.version_id:
            raise ValueError("processed_response_survey_version_mismatch")
    accepted = [r for r in rows if r.status in ACCEPTED_STATUSES]
    status_values = ("accepted", "accepted_flagged", "hold", "quota_full", "screened_out", "invalid", "excluded_duplicate")
    counted_statuses = Counter(row.status for row in rows)
    status_counts = {status: counted_statuses.get(status, 0) for status in status_values}
    hypothesis_results: list[dict[str, Any]] = []
    question_by_id = {q.id: q for q in survey.questions}

    for hypothesis in hypotheses:
        if not isinstance(hypothesis, Hypothesis):
            raise ValueError("hypotheses_must_contain_Hypothesis_instances")
        if not isinstance(hypothesis.id, str) or not hypothesis.id.strip() or not isinstance(hypothesis.question_id, str):
            raise ValueError("invalid_hypothesis_identity")
        question = question_by_id.get(hypothesis.question_id)
        if question is None:
            raise ValueError(f"hypothesis_unknown_question:{hypothesis.question_id}")
        if hypothesis.segment_question_id is not None and (not isinstance(hypothesis.segment_question_id, str) or hypothesis.segment_question_id not in question_by_id):
            raise ValueError(f"hypothesis_unknown_segment_question:{hypothesis.segment_question_id}")
        if not hypothesis.id or not hypothesis.id.strip() or not hypothesis.positive_values:
            raise ValueError(f"invalid_hypothesis_contract:{hypothesis.id}")
        # Values entering this function came from a survey answer payload.
        # The current engine therefore cannot certify observed or transaction
        # evidence; those need separate evidence records and provenance.
        if hypothesis.evidence_type != "declared":
            raise ValueError(f"non_declared_evidence_requires_external_provenance:{hypothesis.id}")
        if isinstance(hypothesis.threshold, bool) or not isinstance(hypothesis.threshold, (int, float)) or not math.isfinite(hypothesis.threshold) or not 0 <= hypothesis.threshold <= 1 or isinstance(hypothesis.minimum_n, bool) or not isinstance(hypothesis.minimum_n, int) or hypothesis.minimum_n < 1:
            raise ValueError(f"invalid_hypothesis_contract:{hypothesis.id}")
        if not isinstance(hypothesis.positive_values, tuple) or not hypothesis.positive_values or any(not isinstance(value, (str, int, float)) or isinstance(value, bool) for value in hypothesis.positive_values):
            raise ValueError(f"invalid_hypothesis_positive_values:{hypothesis.id}")
        if hypothesis.segment_question_id is not None:
            segment_question = question_by_id[hypothesis.segment_question_id]
            if segment_question.kind != "single" or not isinstance(hypothesis.segment_option_id, str) or hypothesis.segment_option_id not in {o.id for o in segment_question.options}:
                raise ValueError(f"invalid_hypothesis_segment:{hypothesis.id}")
        pool = accepted
        if hypothesis.segment_question_id is not None:
            pool = [r for r in pool if r.normalized_answers.get(hypothesis.segment_question_id) == hypothesis.segment_option_id]
        observed = [r.normalized_answers[hypothesis.question_id] for r in pool if hypothesis.question_id in r.normalized_answers]
        positive = set(hypothesis.positive_values)
        k = sum(value in positive for value in observed)
        item = label_hypothesis(
            k=k,
            n=len(observed),
            threshold=hypothesis.threshold,
            minimum_n=hypothesis.minimum_n,
            evidence_type=hypothesis.evidence_type,
        )
        item.update({"id": hypothesis.id, "question_id": hypothesis.question_id, "segment_question_id": hypothesis.segment_question_id, "segment_option_id": hypothesis.segment_option_id})
        hypothesis_results.append(item)

    return {
        "project_id": survey.project_id,
        "survey_version_id": survey.version_id,
        "sample_flow": dict(status_counts),
        "accepted_n": len(accepted),
        "hypotheses": hypothesis_results,
        "limitations": [
            "A voluntary/convenience sample describes participating respondents; it is not automatically representative of Algeria.",
            "Wilson intervals describe binomial sampling variability, not self-selection, coverage, or non-response bias.",
            "Survey answers are treated as declared/reported evidence; the engine cannot promote them to observed behavior or transaction evidence without separately sourced, linked evidence.",
            "Declared preferences are not observed purchases and cannot alone establish demand validation.",
            "This report is bound to the supplied survey version and processing run; production must persist an immutable analysis snapshot.",
        ],
    }
