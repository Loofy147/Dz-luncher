(() => {
  "use strict";

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const parseList = (value) => value.split(/[،,]/).map((part) => part.trim()).filter(Boolean);

  const builder = qs("#survey-builder");
  if (builder) {
    const list = qs("#questions-list");
    const template = qs("#question-template");
    let nextQuestionNumber = 1;

    const optionText = (options) => (options || []).map((item) => `${item.id} | ${item.label}`).join("\n");
    const updateKindFields = (card) => {
      const kind = qs(".q-kind", card).value;
      qs(".q-options-wrap", card).hidden = kind !== "single";
      qsa(".q-bounds-wrap", card).forEach((node) => { node.hidden = !["scale", "number"].includes(kind); });
      qs(".q-grid", card).closest("div").hidden = kind !== "scale";
      qsa(".q-single-rules", card).forEach((node) => { node.hidden = kind !== "single"; });
    };

    const updateBranchOptions = () => {
      const cards = qsa(".question-builder-card", list);
      cards.forEach((card, index) => {
        const select = qs(".q-branch-controller", card);
        const previous = select.dataset.desiredValue || select.value;
        select.replaceChildren(new Option("عرض دائم", ""));
        cards.slice(0, index).forEach((controller) => {
          if (qs(".q-kind", controller).value !== "single") return;
          const id = controller.dataset.questionId;
          const text = qs(".q-text", controller).value.trim() || id;
          select.add(new Option(`بعد إجابة: ${text.slice(0, 42)}`, id));
        });
        select.value = previous;
        select.dataset.desiredValue = select.value;
        qs(".question-index", card).textContent = `السؤال ${index + 1}`;
        qs(".question-id-badge", card).textContent = card.dataset.questionId;
      });
    };

    const addQuestion = (data = {}) => {
      const fragment = template.content.cloneNode(true);
      const card = qs(".question-builder-card", fragment);
      const requestedNumber = Number(String(data.id || "").match(/^q(\d+)$/)?.[1] || 0);
      const id = data.id || `q${nextQuestionNumber}`;
      nextQuestionNumber = Math.max(nextQuestionNumber + 1, requestedNumber + 1);
      card.dataset.questionId = id;
      qs(".q-text", card).value = data.text || "";
      qs(".q-kind", card).value = data.kind || "single";
      qs(".q-options", card).value = optionText(data.options || []);
      qs(".q-required", card).checked = data.required !== false;
      qs(".q-lo", card).value = data.lo ?? 1;
      qs(".q-hi", card).value = data.hi ?? 5;
      qs(".q-grid", card).value = data.grid || "";
      qs(".q-branch-controller", card).dataset.desiredValue = data.show_if?.question_id || "";
      qs(".q-branch-values", card).value = data.show_if?.any_of?.join(", ") || "";
      qs(".q-disqualify", card).value = (data.disqualify_if || []).join(", ");
      qs(".q-attention", card).value = data.attention_expected || "";
      qs(".remove-question", card).addEventListener("click", () => {
        card.remove();
        updateBranchOptions();
      });
      qs(".q-kind", card).addEventListener("change", () => {
        updateKindFields(card);
        updateBranchOptions();
      });
      qs(".q-text", card).addEventListener("input", updateBranchOptions);
      list.appendChild(fragment);
      updateKindFields(card);
      updateBranchOptions();
    };

    const parseOptions = (raw, questionId) => raw.split("\n").map((line) => line.trim()).filter(Boolean).map((line, index) => {
      const divider = line.indexOf("|");
      if (divider >= 0) return { id: line.slice(0, divider).trim(), label: line.slice(divider + 1).trim() };
      return { id: `option_${index + 1}`, label: line.trim() };
    });

    const buildPayload = () => {
      const questions = qsa(".question-builder-card", list).map((card) => {
        const id = card.dataset.questionId;
        const kind = qs(".q-kind", card).value;
        const controller = qs(".q-branch-controller", card).value;
        const branchValues = parseList(qs(".q-branch-values", card).value);
        const q = {
          id,
          text: qs(".q-text", card).value.trim(),
          kind,
          required: qs(".q-required", card).checked,
        };
        if (kind === "single") {
          q.options = parseOptions(qs(".q-options", card).value, id);
          const disqualify = parseList(qs(".q-disqualify", card).value);
          const expected = qs(".q-attention", card).value.trim();
          if (disqualify.length) q.disqualify_if = disqualify;
          if (expected) q.attention_expected = expected;
        }
        if (["number", "scale"].includes(kind)) {
          q.lo = Number(qs(".q-lo", card).value);
          q.hi = Number(qs(".q-hi", card).value);
          if (kind === "scale" && qs(".q-grid", card).value.trim()) q.grid = qs(".q-grid", card).value.trim();
        }
        if (controller && branchValues.length) q.show_if = { question_id: controller, any_of: branchValues };
        return q;
      });
      let quotas;
      let hypotheses;
      try { quotas = JSON.parse(qs("#quotas-json").value || "{}"); }
      catch { throw new Error("صيغة JSON للحصص غير صالحة."); }
      try { hypotheses = JSON.parse(qs("#hypotheses-json").value || "[]"); }
      catch { throw new Error("صيغة JSON للفرضيات غير صالحة."); }
      if (!Array.isArray(questions) || questions.length === 0) throw new Error("أضف سؤالاً واحداً على الأقل.");
      return {
        title: qs("#survey-title").value.trim(),
        objective: qs("#survey-objective").value.trim(),
        description: qs("#survey-description").value.trim(),
        reward_per_response_dzd: Number(qs("#reward-amount").value || 0),
        response_limit: Number(qs("#response-limit").value || 100),
        questions,
        quotas,
        hypotheses,
      };
    };

    qs("#add-question", builder).addEventListener("click", () => addQuestion());
    builder.addEventListener("submit", (event) => {
      const message = qs("#builder-message");
      try {
        qs("#payload-json").value = JSON.stringify(buildPayload());
        if (message) message.hidden = true;
      } catch (error) {
        event.preventDefault();
        if (message) {
          message.hidden = false;
          message.textContent = error.message || "راجع إعدادات الاستبيان.";
        }
      }
    });

    let initial = null;
    try { initial = JSON.parse(qs("#initial-payload")?.value || "null"); } catch { initial = null; }
    if (initial) {
      qs("#survey-title").value = initial.title || "";
      qs("#survey-objective").value = initial.objective || "";
      qs("#survey-description").value = initial.description || "";
      qs("#reward-amount").value = initial.reward_per_response_dzd ?? 0;
      qs("#response-limit").value = initial.response_limit ?? 100;
      qs("#quotas-json").value = JSON.stringify(initial.quotas || {}, null, 2);
      qs("#hypotheses-json").value = JSON.stringify(initial.hypotheses || [], null, 2);
      (initial.questions || []).forEach(addQuestion);
    } else {
      addQuestion({ id: "q1", text: "في أي ولاية تقيم؟", kind: "single", options: [
        { id: "option_1", label: "الجزائر" }, { id: "option_2", label: "وهران" }, { id: "option_3", label: "ولاية أخرى" },
      ] });
      addQuestion({ id: "q2", text: "هل استخدمت هذه الخدمة خلال آخر 3 أشهر؟", kind: "single", options: [
        { id: "option_1", label: "نعم" }, { id: "option_2", label: "لا" },
      ], disqualify_if: ["option_2"] });
      addQuestion({ id: "q3", text: "ما أهم عامل في قرارك؟", kind: "text", required: false, show_if: { question_id: "q2", any_of: ["option_1"] } });
    }
    updateBranchOptions();
  }

  const surveyForm = qs("#participant-survey-form");
  if (surveyForm) {
    const startedAt = performance.now();
    const result = qs("#submission-result");
    const submitButton = qs("#submit-response");
    const progressBar = qs("#progress-bar");
    const progressLabel = qs("#progress-label");

    const answerValue = (question) => {
      const controls = qsa("input, textarea, select", question).filter((control) => !control.disabled);
      if (controls.some((control) => control.type === "radio")) {
        return controls.find((control) => control.type === "radio" && control.checked)?.value;
      }
      return controls[0]?.value?.trim() || undefined;
    };

    const updateSurvey = () => {
      const questions = qsa(".participant-question", surveyForm);
      const visibility = new Map();
      let screenedOutAt = -1;
      questions.forEach((question, index) => {
        let visible = screenedOutAt === -1;
        const controllerId = question.dataset.showIfQuestionId;
        if (visible && controllerId) {
          const controller = qs(`[data-question-id="${CSS.escape(controllerId)}"]`, surveyForm);
          const current = controller ? answerValue(controller) : undefined;
          const allowed = (question.dataset.showIfAnyOf || "").split(",").filter(Boolean);
          visible = visibility.get(controllerId) === true && allowed.includes(String(current));
        }
        question.hidden = !visible;
        visibility.set(question.dataset.questionId, visible);
        qsa("input, textarea, select", question).forEach((control) => {
          control.disabled = !visible;
          control.required = visible && control.dataset.required === "true";
        });
        if (visible) {
          const disqualifiers = (question.dataset.disqualifyIf || "").split(",").filter(Boolean);
          if (disqualifiers.includes(String(answerValue(question)))) screenedOutAt = index;
        }
      });
      const visible = questions.filter((question) => !question.hidden);
      const complete = visible.filter((question) => answerValue(question) !== undefined).length;
      progressLabel.textContent = `${complete} من ${visible.length}`;
      progressBar.value = visible.length ? Math.round((complete / visible.length) * 100) : 0;
    };

    qsa(".participant-question input, .participant-question textarea, .participant-question select", surveyForm).forEach((control) => {
      control.dataset.required = control.required ? "true" : "false";
      control.addEventListener("change", updateSurvey);
      control.addEventListener("input", updateSurvey);
    });
    updateSurvey();

    surveyForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!surveyForm.reportValidity()) return;
      submitButton.disabled = true;
      submitButton.textContent = "جارٍ إرسال الإجابة…";
      const answers = {};
      qsa(".participant-question", surveyForm).forEach((question) => {
        if (question.hidden) return;
        const value = answerValue(question);
        if (value !== undefined) answers[question.dataset.questionId] = value;
      });
      const payload = {
        submission_id: qs("#submission-id").value,
        survey_version_id: qs("#survey-version-id").value,
        seconds: Math.max(0, Math.round((performance.now() - startedAt) / 1000)),
        answers,
      };
      try {
        const response = await fetch(`/api/surveys/${encodeURIComponent(surveyForm.dataset.surveySlug)}/responses`, {
          method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": qs('meta[name="csrf-token"]').content },
          body: JSON.stringify(payload), credentials: "same-origin",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error?.message || "تعذر إرسال الإجابة.");
        result.hidden = false;
        result.className = `submission-result ${["accepted", "accepted_flagged"].includes(data.status) ? "result-success" : data.status === "hold" ? "result-review" : "result-neutral"}`;
        result.textContent = data.message;
        if (data.reward_status === "pending") result.textContent += ` استحقاق المكافأة: ${data.reward_amount_dzd} دج، قيد التسوية.`;
        submitButton.hidden = true;
        qsa("input, textarea, select", surveyForm).forEach((control) => { control.disabled = true; });
      } catch (error) {
        result.hidden = false;
        result.className = "submission-result result-error";
        result.textContent = error.message || "تعذر إرسال الإجابة. تحقق من الاتصال وحاول مجدداً.";
        submitButton.disabled = false;
        submitButton.textContent = "إعادة المحاولة";
      }
    });
  }

  qsa("[data-copy-text]").forEach((button) => button.addEventListener("click", async () => {
    const value = button.dataset.copyText || "";
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = "تم النسخ";
    } catch {
      button.textContent = value;
    }
  }));
})();
