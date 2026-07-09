(function () {
  const SAFETY_NOTE =
    "이 도움말은 의료 판단이나 여행 가능성을 보장하지 않습니다. 현장 접근성은 날씨, 운영 상황, 공사, 혼잡도에 따라 달라질 수 있으므로 방문 전 공식 정보와 현장 문의를 확인해 주세요.";

  const API_ENDPOINT = "/api/help-chat";
  let activeHelpApi = null;

  const HELP_TOPICS = [
    {
      id: "start",
      title: "처음 사용하는 방법",
      summary: "테마 선택부터 추천 결과 확인까지의 기본 흐름",
      keywords: ["처음", "사용", "시작", "어떻게", "방법", "테마", "추천"],
      answer: [
        "먼저 상단의 테마 선택에서 현재 여행 상황을 고릅니다.",
        "추천 결과에서 점수만 보지 말고 추천 이유, 감점 이유, 방문 전 확인 항목을 함께 확인합니다.",
        "장소 상세에서 주차, 화장실, 경사, 휴식 가능성, 출처와 확인일을 확인합니다.",
        "마지막으로 실제 경로 버튼에서 이동 순서와 거리 부담을 확인합니다."
      ]
    },
    {
      id: "score",
      title: "점수와 등급 읽는 법",
      summary: "높은 점수보다 감점 사유와 정보 상태를 함께 확인",
      keywords: ["점수", "등급", "A", "B", "적합도", "신뢰", "감점", "이유"],
      answer: [
        "점수는 이동 편의, 시설 접근성, 정보 신뢰도, 안전·편의 요소를 합쳐 계산합니다.",
        "높은 점수여도 확인 필요 항목이 있으면 방문 전 전화나 공식 페이지 확인이 필요합니다.",
        "감점 이유는 실제 사용 판단에 중요합니다. 특히 화장실 운영 여부, 경사, 주차장-입구 거리 항목을 확인하세요.",
        "정보 상태가 확인 필요인 장소는 추천보다 확인 보조 대상으로 보는 것이 안전합니다."
      ]
    },
    {
      id: "wheelchair",
      title: "휠체어 접근 확인",
      summary: "단정 대신 경사, 바닥, 화장실, 주차를 분리 확인",
      keywords: ["휠체어", "장애", "무장애", "경사", "계단", "바닥", "화장실", "주차"],
      answer: [
        "휠체어 접근은 하나의 가능/불가능 값으로 보지 않고 경사, 바닥, 입구, 화장실, 주차를 나눠 확인합니다.",
        "추천 카드의 장애인 화장실, 가까운 주차, 경사 또는 계단, 휴식 공간 항목을 먼저 보세요.",
        "로드뷰나 운영자 메모가 있어도 현장 공사나 날씨에 따라 달라질 수 있습니다.",
        "장거리 이동이 부담된다면 실제 경로에서 장소 간 거리와 예상 시간을 함께 확인하세요."
      ]
    },
    {
      id: "diet",
      title: "음식 제한이 있을 때",
      summary: "식당 추천이 아니라 제외 조건과 확인 항목 중심",
      keywords: ["음식", "식당", "알레르기", "제한", "시장", "카페", "먹"],
      answer: [
        "음식 제한은 먹어도 되는 음식을 판단하지 않습니다.",
        "식당 제외나 음식 중심 장소 제외 조건을 켜면 관련 장소는 추천에서 제외하거나 감점합니다.",
        "카페, 시장, 식당이 포함된 코스는 메뉴 안전성보다 체류 부담과 대체 가능성을 기준으로 확인하세요.",
        "알레르기나 치료식 같은 민감한 기준은 반드시 방문처에 직접 문의해야 합니다."
      ]
    },
    {
      id: "route",
      title: "실제 경로 보기",
      summary: "추천 순서, 이동 거리, 예상 시간을 지도에서 확인",
      keywords: ["경로", "지도", "거리", "시간", "이동", "코스", "순서", "길"],
      answer: [
        "실제 경로 버튼을 누르면 추천 장소 순서와 예상 이동거리, 예상 시간이 표시됩니다.",
        "도로형 경로 계산이 실패하면 좌표 기반 요약 경로로 자동 대체됩니다.",
        "코스는 2~4개 장소를 기준으로 보며, 무리한 장소 수를 늘리지 않는 것이 원칙입니다.",
        "이동 시간이 길게 보이면 테마를 바꾸거나 짧은 동선, 휴식 필요 조건을 선택하세요."
      ]
    },
    {
      id: "source",
      title: "출처와 최신성",
      summary: "공식 정보와 운영자 검수 상태를 함께 표시",
      keywords: ["출처", "최신", "확인일", "근거", "공식", "검수", "로드뷰", "데이터"],
      answer: [
        "서비스는 출처가 있는 장소와 운영자 검수 카드를 우선 사용합니다.",
        "정보 확인일이 오래됐거나 출처가 부족한 항목은 확인 필요로 표시합니다.",
        "로드뷰 정보는 접근성 검수의 참고 근거이며, 대표 이미지와 구분해서 다룹니다.",
        "출처가 불명확한 내용은 추천 근거로 강하게 쓰지 않는 것이 원칙입니다."
      ]
    },
    {
      id: "privacy",
      title: "개인정보와 건강정보",
      summary: "이름, 연락처, 진단명 없이 이동 조건 수준으로만 사용",
      keywords: ["개인정보", "건강", "진단", "저장", "로그", "이름", "연락처", "병원"],
      answer: [
        "서비스는 이름, 연락처, 주민등록번호, 병원명, 상세 진단명을 요구하지 않는 것이 원칙입니다.",
        "건강 정보는 진단명이 아니라 짧은 이동, 계단 회피, 휴식 필요 같은 이동 조건으로만 다룹니다.",
        "이 도움말 챗봇은 브라우저에서 직접 API 키를 다루지 않습니다.",
        "민감한 정보는 입력하지 말고, 필요한 경우 보호자나 공식 문의처와 직접 확인하세요."
      ]
    },
    {
      id: "trouble",
      title: "화면이나 API가 실패할 때",
      summary: "정적 추천으로 대체하고 안전한 오류 메시지를 확인",
      keywords: ["오류", "실패", "안됨", "API", "연결", "로딩", "에러", "재시도"],
      answer: [
        "추천 API 연결이 실패하면 화면은 정적 추천 데이터로 자동 전환됩니다.",
        "AI 설명이 없어도 기본 점수와 로컬 근거는 계속 표시될 수 있습니다.",
        "경로 API가 실패하면 좌표 기반 요약 경로로 대체됩니다.",
        "반복해서 실패하면 화면을 새로고침하고, 조건을 단순화한 뒤 다시 시도하세요."
      ]
    },
    {
      id: "operator",
      title: "운영자 확인 항목",
      summary: "장소 카드, 출처, 확인일, 위험 문구를 검수",
      keywords: ["운영자", "관리자", "추가", "수정", "장소", "카드", "검수", "업데이트"],
      answer: [
        "운영자는 장소 카드의 출처, 확인일, 접근성 태그, 확인 필요 항목을 계속 갱신해야 합니다.",
        "새 장소는 검수 완료 또는 제한 공개 가능 상태가 되기 전까지 사용자 추천에 넣지 않는 것이 안전합니다.",
        "의료 효과, 100% 가능, 무조건 추천 같은 표현은 결과에서 차단해야 합니다.",
        "사용자 피드백은 민감정보 없이 부적절한 추천 사례와 데이터 보완 항목 중심으로 기록하세요."
      ]
    }
  ];

  const QUICK_PROMPTS = [
    "처음 어떻게 쓰나요?",
    "휠체어 접근은 뭘 확인하나요?",
    "점수와 감점 이유가 궁금해요",
    "음식 제한이 있으면요?",
    "개인정보는 저장되나요?"
  ];

  function normalize(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function scoreTopic(query, topic) {
    const normalizedQuery = normalize(query);
    const terms = normalizedQuery.split(" ").filter(Boolean);
    let score = 0;

    topic.keywords.forEach((keyword) => {
      if (normalizedQuery.includes(normalize(keyword))) {
        score += 3;
      }
    });

    terms.forEach((term) => {
      if (normalize(topic.title).includes(term)) {
        score += 2;
      }
      if (normalize(topic.summary).includes(term)) {
        score += 1;
      }
    });

    return score;
  }

  function findTopic(query) {
    const ranked = HELP_TOPICS.map((topic) => ({
      topic,
      score: scoreTopic(query, topic)
    })).sort((left, right) => right.score - left.score);

    if (!ranked[0] || ranked[0].score === 0) {
      return {
        topic: null,
        score: 0
      };
    }

    return ranked[0];
  }

  function createElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (text) {
      element.textContent = text;
    }
    return element;
  }

  function splitReadableParagraphs(text) {
    const normalized = String(text || "").replace(/\s+/g, " ").trim();
    if (!normalized) {
      return [];
    }

    const sentences = normalized.match(/[^.!?。！？]+[.!?。！？]?/g) || [normalized];
    const paragraphs = [];
    let current = "";

    sentences.forEach((sentence) => {
      const trimmed = sentence.trim();
      if (!trimmed) {
        return;
      }
      if ((current + " " + trimmed).trim().length > 120 && current) {
        paragraphs.push(current);
        current = trimmed;
        return;
      }
      current = (current ? `${current} ${trimmed}` : trimmed).trim();
    });

    if (current) {
      paragraphs.push(current);
    }
    return paragraphs.slice(0, 5);
  }

  function renderReadableText(text) {
    const answer = createElement("div", "helpbot-answer");
    splitReadableParagraphs(text).forEach((paragraph) => {
      answer.appendChild(createElement("p", "", paragraph));
    });
    if (!answer.childElementCount) {
      answer.appendChild(createElement("p", "", "답변을 가져오지 못했습니다."));
    }
    return answer;
  }

  function setTemporaryButtonText(button, text) {
    const original = button.textContent;
    button.textContent = text;
    window.setTimeout(() => {
      button.textContent = original;
    }, 1300);
  }

  function renderAnswer(topic, confidence) {
    const fragment = document.createDocumentFragment();
    const title = createElement("strong", "", topic.title);
    const list = document.createElement("ul");

    topic.answer.forEach((item) => {
      const listItem = document.createElement("li");
      listItem.textContent = item;
      list.appendChild(listItem);
    });

    const confidenceBadge = createElement(
      "span",
      "helpbot-confidence",
      confidence >= 5 ? "기본 도움말 · 관련도 높음" : "기본 도움말"
    );
    const safeNote = createElement("div", "helpbot-safe-note", SAFETY_NOTE);

    fragment.appendChild(title);
    fragment.appendChild(list);
    fragment.appendChild(confidenceBadge);
    fragment.appendChild(safeNote);
    return fragment;
  }

  function renderLlmAnswer(payload) {
    const fragment = document.createDocumentFragment();
    const title = createElement(
      "strong",
      "",
      payload.status === "success" ? "AI 도움말 답변" : "도움말 상태"
    );
    const answerText = payload.answer || "답변을 가져오지 못했습니다.";
    const answer = renderReadableText(answerText);
    const badge = createElement(
      "span",
      "helpbot-confidence",
      payload.status === "success" ? `LLM 답변 · ${payload.model || "model"}` : payload.status || "fallback"
    );

    fragment.appendChild(title);
    fragment.appendChild(answer);
    fragment.appendChild(badge);

    if (Array.isArray(payload.handoff_checklist) && payload.handoff_checklist.length) {
      const checklist = createElement("div", "helpbot-checklist");
      const checklistTitle = createElement("strong", "", "확인할 항목");
      const list = document.createElement("ul");
      payload.handoff_checklist.forEach((item) => {
        const listItem = document.createElement("li");
        const toggle = createElement("button", "helpbot-check-toggle", item);
        toggle.type = "button";
        toggle.setAttribute("aria-pressed", "false");
        listItem.appendChild(toggle);
        list.appendChild(listItem);
      });
      checklist.appendChild(checklistTitle);
      checklist.appendChild(list);
      fragment.appendChild(checklist);
    }

    const actions = createElement("div", "helpbot-actions");
    const copyAnswer = createElement("button", "helpbot-action-button primary", "답변 복사");
    copyAnswer.type = "button";
    copyAnswer.dataset.helpCopy = answerText;
    actions.appendChild(copyAnswer);

    if (Array.isArray(payload.handoff_checklist) && payload.handoff_checklist.length) {
      const copyChecklist = createElement("button", "helpbot-action-button", "체크리스트 복사");
      copyChecklist.type = "button";
      copyChecklist.dataset.helpCopy = payload.handoff_checklist.join("\n");
      actions.appendChild(copyChecklist);
    }

    const makeCallScript = createElement("button", "helpbot-action-button", "문의 문장 만들기");
    makeCallScript.type = "button";
    makeCallScript.dataset.helpQuestion = "방문 전 전화나 공식 문의에 바로 쓸 수 있는 짧은 확인 문장을 만들어줘.";
    actions.appendChild(makeCallScript);

    const makeSteps = createElement("button", "helpbot-action-button", "실행 순서로 정리");
    makeSteps.type = "button";
    makeSteps.dataset.helpQuestion = "방금 내용을 사용자가 바로 따라할 수 있는 실행 순서 3단계로 다시 정리해줘.";
    actions.appendChild(makeSteps);
    fragment.appendChild(actions);

    if (Array.isArray(payload.followups) && payload.followups.length) {
      const followups = createElement("div", "helpbot-followups");
      payload.followups.forEach((item) => {
        const button = createElement("button", "", item);
        button.type = "button";
        button.dataset.helpQuestion = item;
        followups.appendChild(button);
      });
      fragment.appendChild(followups);
    }

    fragment.appendChild(createElement("div", "helpbot-safe-note", payload.safety_note || SAFETY_NOTE));
    return fragment;
  }

  function renderFallback(query) {
    const fragment = document.createDocumentFragment();
    const title = createElement("strong", "", "가까운 도움말을 찾지 못했습니다");
    const list = document.createElement("ul");
    [
      "질문을 서비스 사용법, 점수, 휠체어 접근, 음식 제한, 출처, 개인정보, 오류 중 하나와 연결해 다시 입력해 주세요.",
      "방문 가능 여부나 의료적 판단은 챗봇이 답할 수 없습니다.",
      "방문 전 확인이 필요하면 장소 상세의 확인 항목과 공식 문의처를 기준으로 확인하세요."
    ].forEach((item) => {
      const listItem = document.createElement("li");
      listItem.textContent = item;
      list.appendChild(listItem);
    });

    fragment.appendChild(title);
    fragment.appendChild(list);
    fragment.appendChild(createElement("div", "helpbot-safe-note", `입력한 질문: ${query.slice(0, 80)}${query.length > 80 ? "..." : ""}`));
    return fragment;
  }

  function createMessage(role, content) {
    const message = createElement("article", "helpbot-message");
    message.dataset.role = role;

    if (typeof content === "string") {
      message.textContent = content;
    } else {
      message.appendChild(content);
    }

    return message;
  }

  function createLoadingMessage() {
    const fragment = document.createDocumentFragment();
    const loading = createElement("div", "helpbot-loading");
    const title = createElement("div", "helpbot-loading-title");
    const dots = createElement("span", "helpbot-loading-dots");

    title.appendChild(createElement("span", "", "AI가 답변을 준비 중입니다"));
    [1, 2, 3].forEach(() => {
      dots.appendChild(createElement("span"));
    });
    title.appendChild(dots);

    loading.appendChild(title);
    loading.appendChild(createElement("div", "helpbot-loading-track"));
    loading.appendChild(createElement("div", "helpbot-loading-copy", "질문 맥락과 안전 안내 기준을 함께 확인하고 있습니다."));
    fragment.appendChild(loading);
    return createMessage("bot", fragment);
  }

  function installInteractionGuards(shell, log) {
    const stopOnly = (event) => {
      event.stopPropagation();
    };

    shell.addEventListener(
      "wheel",
      (event) => {
        event.stopPropagation();
        event.preventDefault();
        const canScroll = log.scrollHeight > log.clientHeight;
        if (!canScroll) {
          return;
        }
        log.scrollTop += event.deltaY;
      },
      { passive: false }
    );

    let touchStartY = 0;
    shell.addEventListener(
      "touchstart",
      (event) => {
        touchStartY = event.touches[0]?.clientY || 0;
        event.stopPropagation();
      },
      { passive: false }
    );
    shell.addEventListener(
      "touchmove",
      (event) => {
        event.stopPropagation();
        event.preventDefault();
        const y = event.touches[0]?.clientY || touchStartY;
        const deltaY = touchStartY - y;
        if (log.scrollHeight > log.clientHeight) {
          log.scrollTop += deltaY;
        }
        touchStartY = y;
      },
      { passive: false }
    );

    let logDragState = null;
    log.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) {
        return;
      }
      if (event.target.closest("button, a, input, textarea, select, label")) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      logDragState = {
        startY: event.clientY,
        scrollTop: log.scrollTop,
      };
      log.classList.add("is-scroll-dragging");
      log.setPointerCapture?.(event.pointerId);
    });

    log.addEventListener("pointermove", (event) => {
      if (!logDragState) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      log.scrollTop = logDragState.scrollTop + (logDragState.startY - event.clientY);
    });

    log.addEventListener("pointerup", () => {
      logDragState = null;
      log.classList.remove("is-scroll-dragging");
    });

    log.addEventListener("pointercancel", () => {
      logDragState = null;
      log.classList.remove("is-scroll-dragging");
    });

    ["pointerdown", "pointermove", "pointerup", "dragstart"].forEach((eventName) => {
      shell.addEventListener(eventName, stopOnly);
    });
  }

  function clamp(value, min, max) {
    if (max < min) {
      return min;
    }
    return Math.min(Math.max(value, min), max);
  }

  function releasePointer(element, pointerId) {
    if (pointerId === undefined || !element?.hasPointerCapture?.(pointerId)) {
      return;
    }
    element.releasePointerCapture(pointerId);
  }

  function readCssPixel(element, propertyName, fallback) {
    const value = Number.parseFloat(window.getComputedStyle(element).getPropertyValue(propertyName));
    return Number.isFinite(value) ? value : fallback;
  }

  function applyInitialWingPosition(positionRoot, wingButton, shell) {
    if (!positionRoot || !wingButton || !shell) {
      return;
    }

    const viewportHeight = window.innerHeight || 720;
    const compact = window.innerWidth <= 900;
    const margin = compact ? 12 : 18;
    const panelBottom = compact ? 12 : 24;
    const tabBottom = compact ? 32 : 44;
    const fallbackPanelHeight = compact
      ? Math.max(360, viewportHeight - 88)
      : Math.min(660, Math.max(360, viewportHeight - 116));
    const panelHeight = shell.getBoundingClientRect().height || fallbackPanelHeight;
    const tabHeight = wingButton.getBoundingClientRect().height || 176;
    const panelTop = clamp(
      viewportHeight - panelHeight - panelBottom,
      margin,
      viewportHeight - panelHeight - margin
    );
    const tabTop = clamp(
      viewportHeight - tabHeight - tabBottom,
      margin,
      viewportHeight - tabHeight - margin
    );

    positionRoot.style.setProperty("--helpbot-panel-top", `${Math.round(panelTop)}px`);
    positionRoot.style.setProperty("--helpbot-tab-top", `${Math.round(tabTop)}px`);
  }

  function installWingBannerDraggable(positionRoot, wingButton, shell) {
    if (!positionRoot || !wingButton || !shell) {
      return;
    }

    const margin = 10;
    const dragThreshold = 5;
    let dragState = null;
    let pendingTabTop = null;
    let dragFrame = 0;

    function getTabOffset() {
      const panelTop = readCssPixel(positionRoot, "--helpbot-panel-top", 92);
      const tabTop = readCssPixel(positionRoot, "--helpbot-tab-top", panelTop + 56);
      return tabTop - panelTop;
    }

    function setTabTop(tabTop) {
      const tabHeight = wingButton.getBoundingClientRect().height || 190;
      const panelHeight = shell.getBoundingClientRect().height || Math.min(660, window.innerHeight - 116);
      const tabOffset = dragState?.tabOffset ?? getTabOffset();
      const nextTabTop = clamp(tabTop, margin, window.innerHeight - tabHeight - margin);
      const nextPanelTop = clamp(nextTabTop - tabOffset, margin, window.innerHeight - panelHeight - margin);

      positionRoot.style.setProperty("--helpbot-panel-top", `${Math.round(nextPanelTop)}px`);
      positionRoot.style.setProperty("--helpbot-tab-top", `${Math.round(nextTabTop)}px`);
    }

    function applyPendingTabTop() {
      dragFrame = 0;
      if (pendingTabTop === null) {
        return;
      }
      setTabTop(pendingTabTop);
    }

    wingButton.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) {
        return;
      }
      if (positionRoot.classList.contains("is-open")) {
        return;
      }

      const rect = wingButton.getBoundingClientRect();
      dragState = {
        pointerId: event.pointerId,
        startY: event.clientY,
        offsetY: event.clientY - rect.top,
        tabOffset: getTabOffset(),
        moved: false,
      };
      wingButton.setPointerCapture?.(event.pointerId);
    });

    document.addEventListener("pointermove", (event) => {
      if (!dragState || event.pointerId !== dragState.pointerId) {
        return;
      }

      const deltaY = event.clientY - dragState.startY;
      if (!dragState.moved && Math.abs(deltaY) < dragThreshold) {
        return;
      }

      dragState.moved = true;
      event.preventDefault();
      event.stopPropagation();
      positionRoot.classList.add("is-wing-dragging");
      pendingTabTop = event.clientY - dragState.offsetY;
      if (!dragFrame) {
        dragFrame = window.requestAnimationFrame(applyPendingTabTop);
      }
    }, true);

    function finishWingDrag(event) {
      if (!dragState) {
        return;
      }
      if (event?.pointerId !== undefined && event.pointerId !== dragState.pointerId) {
        return;
      }
      if (dragFrame) {
        window.cancelAnimationFrame(dragFrame);
        dragFrame = 0;
      }
      if (pendingTabTop !== null) {
        setTabTop(pendingTabTop);
        pendingTabTop = null;
      }
      const moved = dragState.moved;
      if (moved) {
        wingButton.dataset.skipNextClick = "true";
        window.setTimeout(() => {
          if (wingButton.dataset.skipNextClick === "true") {
            delete wingButton.dataset.skipNextClick;
          }
        }, 350);
      }
      releasePointer(wingButton, dragState.pointerId);
      dragState = null;
      positionRoot.classList.remove("is-wing-dragging");
      if (moved) {
        positionRoot.classList.add("is-position-custom");
        positionRoot.dispatchEvent(new CustomEvent("helpbot-wing-moved"));
      }
    }

    document.addEventListener("pointerup", finishWingDrag, true);
    document.addEventListener("pointercancel", finishWingDrag, true);
    window.addEventListener("blur", finishWingDrag);
  }

  function installWingIdleActivity(positionRoot, wingButton) {
    if (!positionRoot || !wingButton) {
      return;
    }
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    const firstDelay = 800;
    const interval = 5600;
    const activeDuration = 5200;
    let idleTimer = 0;
    let clearTimer = 0;

    function isPaused() {
      return (
        document.hidden ||
        positionRoot.classList.contains("is-open") ||
        positionRoot.classList.contains("is-dragging") ||
        positionRoot.classList.contains("is-wing-dragging") ||
        positionRoot.classList.contains("is-resizing")
      );
    }

    function clearIdleActivity() {
      positionRoot.classList.remove("is-idle-active");
      if (clearTimer) {
        window.clearTimeout(clearTimer);
        clearTimer = 0;
      }
    }

    function scheduleIdleActivity(delay = interval) {
      if (idleTimer) {
        window.clearTimeout(idleTimer);
      }
      idleTimer = window.setTimeout(runIdleActivity, delay);
    }

    function runIdleActivity() {
      idleTimer = 0;
      if (isPaused()) {
        clearIdleActivity();
        scheduleIdleActivity(interval);
        return;
      }

      positionRoot.classList.add("is-idle-active");
      clearTimer = window.setTimeout(() => {
        clearIdleActivity();
      }, activeDuration);
      scheduleIdleActivity(interval);
    }

    function resetIdleActivity(delay = interval) {
      clearIdleActivity();
      scheduleIdleActivity(delay);
    }

    wingButton.addEventListener("pointerdown", () => resetIdleActivity());
    wingButton.addEventListener("click", () => resetIdleActivity());
    positionRoot.addEventListener("helpbot-wing-moved", () => resetIdleActivity(450));
    positionRoot.addEventListener("helpbot-wing-closed", () => resetIdleActivity(450));
    positionRoot.addEventListener("helpbot-wing-opened", clearIdleActivity);
    document.addEventListener("visibilitychange", () => resetIdleActivity());
    scheduleIdleActivity(firstDelay);
  }

  function installDraggable(shell, handle, options = {}) {
    const positionRoot = options.positionRoot || shell;
    const wingButton = options.wingButton || null;
    const usesSharedPosition = Boolean(options.positionRoot);
    let dragState = null;
    let pendingTop = null;
    let dragFrame = 0;
    const margin = 10;

    function getTabOffset(panelRect) {
      const tabRect = wingButton?.getBoundingClientRect();
      if (!tabRect || !Number.isFinite(tabRect.top)) {
        return 56;
      }
      return tabRect.top - panelRect.top;
    }

    function setPanelTop(top, panelHeight, tabOffset) {
      const nextTop = clamp(top, margin, window.innerHeight - panelHeight - margin);

      if (!usesSharedPosition) {
        shell.style.top = `${Math.round(nextTop)}px`;
        return;
      }

      const tabHeight = wingButton?.getBoundingClientRect().height || 190;
      const nextTabTop = clamp(nextTop + tabOffset, margin, window.innerHeight - tabHeight - margin);
      positionRoot.style.setProperty("--helpbot-panel-top", `${Math.round(nextTop)}px`);
      positionRoot.style.setProperty("--helpbot-tab-top", `${Math.round(nextTabTop)}px`);
    }

    function applyPendingTop() {
      dragFrame = 0;
      if (pendingTop === null || !dragState) {
        return;
      }
      setPanelTop(pendingTop, dragState.height, dragState.tabOffset);
    }

    function movePanel(clientY) {
      if (!dragState) {
        return;
      }

      pendingTop = clamp(clientY - dragState.offsetY, margin, window.innerHeight - dragState.height - margin);
      if (!dragFrame) {
        dragFrame = window.requestAnimationFrame(applyPendingTop);
      }
    }

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      const rect = shell.getBoundingClientRect();
      dragState = {
        pointerId: event.pointerId,
        offsetY: event.clientY - rect.top,
        width: rect.width,
        height: rect.height,
        left: rect.left,
        tabOffset: getTabOffset(rect),
      };

      shell.classList.add("is-dragged", "is-dragging");
      positionRoot.classList.add("is-dragged", "is-dragging", "is-position-custom");
      setPanelTop(rect.top, rect.height, dragState.tabOffset);

      if (!usesSharedPosition) {
        shell.style.width = `${rect.width}px`;
        shell.style.height = `${rect.height}px`;
        shell.style.right = "auto";
        shell.style.bottom = "auto";
        shell.style.left = `${dragState.left}px`;
        shell.style.transform = "translateX(0)";
      }

      handle.setPointerCapture?.(event.pointerId);
    });

    handle.addEventListener("click", (event) => {
      event.preventDefault();
    });

    document.addEventListener("pointermove", (event) => {
      if (!dragState) {
        return;
      }
      if (event.pointerId !== dragState.pointerId) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      movePanel(event.clientY);
    }, true);

    function finishDrag(event) {
      if (!dragState) {
        return;
      }
      if (event?.pointerId !== undefined && event.pointerId !== dragState.pointerId) {
        return;
      }
      if (dragFrame) {
        window.cancelAnimationFrame(dragFrame);
        dragFrame = 0;
      }
      if (pendingTop !== null) {
        setPanelTop(pendingTop, dragState.height, dragState.tabOffset);
        pendingTop = null;
      }
      releasePointer(handle, dragState.pointerId);
      dragState = null;
      shell.classList.remove("is-dragging");
      positionRoot.classList.remove("is-dragging");
    }

    document.addEventListener("pointerup", finishDrag, true);
    document.addEventListener("pointercancel", finishDrag, true);
    window.addEventListener("blur", finishDrag);

    window.addEventListener("resize", () => {
      if (!shell.classList.contains("is-dragged")) {
        return;
      }
      const rect = shell.getBoundingClientRect();
      setPanelTop(rect.top, rect.height, getTabOffset(rect));
    });
  }

  function installResizable(shell, options = {}) {
    const positionRoot = options.positionRoot || shell;
    const usesSharedPosition = Boolean(options.positionRoot);
    const margin = 10;
    const edgeSize = 14;
    let resizeState = null;
    let pendingSize = null;
    let resizeFrame = 0;

    function getMinWidth() {
      return Math.min(360, Math.max(280, window.innerWidth - 24));
    }

    function getMinHeight() {
      return Math.min(460, Math.max(360, window.innerHeight - 48));
    }

    function applySize(width, height, state) {
      const minWidth = getMinWidth();
      const minHeight = getMinHeight();
      const rightGap = Math.max(margin, state?.rightGap ?? window.innerWidth - shell.getBoundingClientRect().right);
      const top = state?.top ?? shell.getBoundingClientRect().top;
      const maxWidth = Math.max(minWidth, window.innerWidth - rightGap - margin);
      const maxHeight = Math.max(minHeight, window.innerHeight - top - margin);
      const nextWidth = Math.round(clamp(width, minWidth, maxWidth));
      const nextHeight = Math.round(clamp(height, minHeight, maxHeight));

      if (usesSharedPosition) {
        positionRoot.style.setProperty("--helpbot-panel-width", `${nextWidth}px`);
        positionRoot.style.setProperty("--helpbot-panel-height", `${nextHeight}px`);
        return;
      }

      shell.style.width = `${nextWidth}px`;
      shell.style.height = `${nextHeight}px`;
    }

    function getResizeEdge(event) {
      const rect = shell.getBoundingClientRect();
      const nearLeft = event.clientX - rect.left <= edgeSize;
      const nearBottom = rect.bottom - event.clientY <= edgeSize;

      if (nearLeft && nearBottom) {
        return "corner";
      }
      if (nearLeft) {
        return "left";
      }
      if (nearBottom) {
        return "bottom";
      }
      return "";
    }

    function getResizeCursor(edge) {
      if (edge === "corner") {
        return "nesw-resize";
      }
      if (edge === "left") {
        return "ew-resize";
      }
      if (edge === "bottom") {
        return "ns-resize";
      }
      return "";
    }

    function isResizeBlocked(event) {
      return Boolean(event.target.closest("button, a, input, textarea, select, label"));
    }

    function applyPendingSize() {
      resizeFrame = 0;
      if (!pendingSize || !resizeState) {
        return;
      }
      applySize(pendingSize.width, pendingSize.height, resizeState);
    }

    function queueSize(width, height) {
      pendingSize = { width, height };
      if (!resizeFrame) {
        resizeFrame = window.requestAnimationFrame(applyPendingSize);
      }
    }

    shell.addEventListener("pointermove", (event) => {
      if (resizeState || !positionRoot.classList.contains("is-open")) {
        return;
      }
      const edge = isResizeBlocked(event) ? "" : getResizeEdge(event);
      if (edge) {
        shell.dataset.resizeEdge = edge;
        shell.style.cursor = getResizeCursor(edge);
      } else {
        delete shell.dataset.resizeEdge;
        shell.style.cursor = "";
      }
    }, true);

    shell.addEventListener("pointerleave", () => {
      if (resizeState) {
        return;
      }
      delete shell.dataset.resizeEdge;
      shell.style.cursor = "";
    });

    shell.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) {
        return;
      }
      if (isResizeBlocked(event)) {
        return;
      }

      const edge = getResizeEdge(event);
      if (!edge) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      const rect = shell.getBoundingClientRect();
      resizeState = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        startWidth: rect.width,
        startHeight: rect.height,
        rightGap: window.innerWidth - rect.right,
        top: rect.top,
        edge,
        previousBodyCursor: document.body.style.cursor,
        previousBodyUserSelect: document.body.style.userSelect,
      };

      shell.classList.add("is-resizing");
      positionRoot.classList.add("is-resizing");
      shell.dataset.resizeEdge = edge;
      shell.style.cursor = getResizeCursor(edge);
      document.body.style.cursor = getResizeCursor(edge);
      document.body.style.userSelect = "none";
      applySize(rect.width, rect.height, resizeState);
      shell.setPointerCapture?.(event.pointerId);
    }, true);

    document.addEventListener("pointermove", (event) => {
      if (!resizeState) {
        return;
      }
      if (event.pointerId !== resizeState.pointerId) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const nextWidth = resizeState.edge === "left" || resizeState.edge === "corner"
        ? resizeState.startWidth + (resizeState.startX - event.clientX)
        : resizeState.startWidth;
      const nextHeight = resizeState.edge === "bottom" || resizeState.edge === "corner"
        ? resizeState.startHeight + (event.clientY - resizeState.startY)
        : resizeState.startHeight;
      queueSize(nextWidth, nextHeight);
    }, true);

    function finishResize(event) {
      if (!resizeState) {
        return;
      }
      if (event?.pointerId !== undefined && event.pointerId !== resizeState.pointerId) {
        return;
      }
      if (resizeFrame) {
        window.cancelAnimationFrame(resizeFrame);
        resizeFrame = 0;
      }
      if (pendingSize) {
        applySize(pendingSize.width, pendingSize.height, resizeState);
        pendingSize = null;
      }
      const previousBodyCursor = resizeState.previousBodyCursor;
      const previousBodyUserSelect = resizeState.previousBodyUserSelect;
      releasePointer(shell, resizeState.pointerId);
      resizeState = null;
      shell.classList.remove("is-resizing");
      positionRoot.classList.remove("is-resizing");
      delete shell.dataset.resizeEdge;
      shell.style.cursor = "";
      document.body.style.cursor = previousBodyCursor || "";
      document.body.style.userSelect = previousBodyUserSelect || "";
    }

    document.addEventListener("pointerup", finishResize, true);
    document.addEventListener("pointercancel", finishResize, true);
    window.addEventListener("blur", finishResize);

    window.addEventListener("resize", () => {
      const rect = shell.getBoundingClientRect();
      applySize(rect.width, rect.height, {
        rightGap: window.innerWidth - rect.right,
        top: rect.top,
      });
    });
  }

  function collectHistory(log) {
    return Array.from(log.querySelectorAll(".helpbot-message"))
      .slice(-8)
      .map((item) => ({
        role: item.dataset.role === "user" ? "user" : "assistant",
        content: item.textContent.trim().slice(0, 500)
      }))
      .filter((item) => item.content);
  }

  async function requestLlmAnswer(question, history) {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question,
        history
      })
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload.error || `HTTP ${response.status}`);
    }

    return response.json();
  }

  function mountTopicGrid() {
    const grid = document.querySelector("[data-help-topic-grid]");
    if (!grid) {
      return;
    }

    HELP_TOPICS.slice(0, 6).forEach((topic) => {
      const button = createElement("button", "help-topic-button");
      button.type = "button";
      button.dataset.helpQuestion = topic.title;
      button.appendChild(createElement("strong", "", topic.title));
      button.appendChild(createElement("span", "", topic.summary));
      button.addEventListener("click", () => {
        if (activeHelpApi) {
          activeHelpApi.open();
          activeHelpApi.ask(topic.title);
        }
      });
      grid.appendChild(button);
    });
  }

  function mount(root, options) {
    const mode = root.dataset.helpChatbotMode || options?.mode || "wing";
    const wingMode = mode === "wing";
    const wingWrap = wingMode ? createElement("div", "helpbot-wing-wrap") : null;
    const wingButton = wingMode ? createElement("button", "helpbot-wing-banner") : null;
    const shell = createElement("section", "helpbot");
    shell.dataset.mode = mode;
    shell.setAttribute("aria-label", "가치봄 제주 도움말 챗봇");

    const sidebar = createElement("aside", "helpbot-sidebar");
    const intro = createElement("div");
    intro.appendChild(createElement("h3", "helpbot-title", "도움말 주제"));
    intro.appendChild(
      createElement(
        "p",
        "helpbot-note",
        "서비스 사용 중 헷갈리는 점을 빠르게 확인하세요. 브라우저는 API 키를 직접 다루지 않습니다."
      )
    );

    const status = createElement("div", "helpbot-status");
    status.appendChild(createElement("strong", "", "LLM 답변"));
    status.appendChild(
      createElement("span", "", "추천보다 근거, 방문 전 확인, 개인정보 최소 입력 원칙을 기준으로 답합니다.")
    );

    const topicList = createElement("div", "helpbot-topic-list");
    HELP_TOPICS.forEach((topic) => {
      const button = createElement("button", "", topic.title);
      button.type = "button";
      button.dataset.helpQuestion = topic.title;
      topicList.appendChild(button);
    });

    sidebar.appendChild(intro);
    sidebar.appendChild(status);
    sidebar.appendChild(topicList);

    const main = createElement("div", "helpbot-main");
    const head = createElement("header", "helpbot-head");
    const titleBlock = createElement("div");
    titleBlock.appendChild(createElement("strong", "", "가치봄 도움말"));
    titleBlock.appendChild(createElement("span", "", "서버 LLM 기반 답변"));
    const headActions = createElement("div", "helpbot-head-actions");
    const dragHandle = createElement("button", "helpbot-drag-handle", "이동");
    dragHandle.type = "button";
    dragHandle.setAttribute("aria-label", "챗봇 창 이동");
    const resetButton = createElement("button", "helpbot-reset", "대화 초기화");
    resetButton.type = "button";
    headActions.appendChild(dragHandle);
    headActions.appendChild(resetButton);

    let closeButton = null;
    if (wingMode) {
      closeButton = createElement("button", "helpbot-close", "×");
      closeButton.type = "button";
      closeButton.setAttribute("aria-label", "도움말 닫기");
      headActions.appendChild(closeButton);
    }

    head.appendChild(titleBlock);
    head.appendChild(headActions);

    const log = createElement("div", "helpbot-log");
    log.setAttribute("aria-live", "polite");
    log.appendChild(
      createMessage(
        "bot",
        "안녕하세요. 가치봄 제주 사용법, 점수 해석, 접근성 확인, 개인정보 기준을 안내합니다. 질문은 서버의 LLM 도움말 API로 전달됩니다."
      )
    );

    const quick = createElement("div", "helpbot-quick");
    QUICK_PROMPTS.forEach((prompt) => {
      const chip = createElement("button", "helpbot-chip", prompt);
      chip.type = "button";
      chip.dataset.helpQuestion = prompt;
      quick.appendChild(chip);
    });

    const form = createElement("form", "helpbot-form");
    const input = createElement("input", "helpbot-input");
    input.type = "text";
    input.name = "question";
    input.autocomplete = "off";
    input.placeholder = "예: 휠체어 접근은 무엇을 확인하나요?";
    input.setAttribute("aria-label", "도움말 질문 입력");
    const submit = createElement("button", "helpbot-submit", "보내기");
    submit.type = "submit";
    form.appendChild(input);
    form.appendChild(submit);

    main.appendChild(head);
    main.appendChild(log);
    main.appendChild(quick);
    main.appendChild(form);

    shell.appendChild(sidebar);
    shell.appendChild(main);

    if (wingMode && wingWrap && wingButton) {
      wingButton.type = "button";
      wingButton.setAttribute("aria-expanded", "false");
      wingButton.appendChild(createElement("small", "helpbot-wing-badge", "AI"));
      wingButton.appendChild(createElement("span", "helpbot-wing-label", "도움말 챗봇"));
      wingWrap.appendChild(wingButton);
      wingWrap.appendChild(shell);
      document.body.appendChild(wingWrap);
    } else {
      root.appendChild(shell);
    }

    installInteractionGuards(shell, log);
    installDraggable(shell, dragHandle, {
      positionRoot: wingWrap,
      wingButton,
    });
    installResizable(shell, {
      positionRoot: wingWrap,
    });
    applyInitialWingPosition(wingWrap, wingButton, shell);
    window.addEventListener("resize", () => {
      if (!wingWrap || wingWrap.classList.contains("is-position-custom") || wingWrap.classList.contains("is-open")) {
        return;
      }
      applyInitialWingPosition(wingWrap, wingButton, shell);
    });
    installWingBannerDraggable(wingWrap, wingButton, shell);
    installWingIdleActivity(wingWrap, wingButton);

    async function addBotResponse(question) {
      const userText = question.trim();
      if (!userText) {
        return;
      }
      if (submit.disabled) {
        return;
      }

      log.appendChild(createMessage("user", userText));
      const thinking = createLoadingMessage();
      log.appendChild(thinking);
      log.scrollTop = log.scrollHeight;
      input.disabled = true;
      submit.disabled = true;

      try {
        const payload = await requestLlmAnswer(userText, collectHistory(log));
        thinking.replaceWith(createMessage("bot", renderLlmAnswer(payload)));
      } catch (error) {
        const match = findTopic(userText);
        const fallback = match.topic ? renderAnswer(match.topic, match.score) : renderFallback(userText);
        const wrapper = document.createDocumentFragment();
        wrapper.appendChild(
          createElement(
            "div",
            "helpbot-safe-note",
            `LLM 도움말 API에 연결하지 못해 기본 도움말로 답합니다. 사유: ${String(error.message || error).slice(0, 80)}`
          )
        );
        wrapper.appendChild(fallback);
        thinking.replaceWith(createMessage("bot", wrapper));
      } finally {
        input.disabled = false;
        submit.disabled = false;
        input.focus();
      }

      log.scrollTop = log.scrollHeight;
    }

    function openWing() {
      if (!wingWrap || !wingButton) {
        input.focus();
        return;
      }
      wingWrap.classList.add("is-open");
      wingButton.setAttribute("aria-expanded", "true");
      wingWrap.dispatchEvent(new CustomEvent("helpbot-wing-opened"));
      input.focus();
    }

    function closeWing() {
      if (!wingWrap || !wingButton) {
        return;
      }
      wingWrap.classList.remove("is-open");
      wingButton.setAttribute("aria-expanded", "false");
      wingWrap.dispatchEvent(new CustomEvent("helpbot-wing-closed"));
    }

    function isWingOpen() {
      return Boolean(wingWrap?.classList.contains("is-open"));
    }

    function isHelpbotTarget(target, event) {
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      return shell.contains(target) || wingButton?.contains(target) || path.includes(shell) || path.includes(wingButton);
    }

    if (wingWrap && wingButton) {
      document.addEventListener(
        "pointerdown",
        (event) => {
          if (!isWingOpen() || isHelpbotTarget(event.target, event)) {
            return;
          }
          closeWing();
        },
        true
      );
    }

    shell.addEventListener("click", (event) => {
      const copyTarget = event.target.closest("[data-help-copy]");
      if (copyTarget) {
        event.preventDefault();
        const text = copyTarget.dataset.helpCopy || "";
        if (navigator.clipboard && text) {
          navigator.clipboard.writeText(text).then(() => setTemporaryButtonText(copyTarget, "복사됨"));
        } else {
          setTemporaryButtonText(copyTarget, "복사 불가");
        }
        return;
      }

      const checkTarget = event.target.closest(".helpbot-check-toggle");
      if (checkTarget) {
        event.preventDefault();
        const done = !checkTarget.classList.contains("is-done");
        checkTarget.classList.toggle("is-done", done);
        checkTarget.setAttribute("aria-pressed", String(done));
        return;
      }

      const target = event.target.closest("[data-help-question]");
      if (!target) {
        return;
      }
      openWing();
      addBotResponse(target.dataset.helpQuestion);
    });

    if (wingButton) {
      wingButton.addEventListener("click", (event) => {
        if (wingButton.dataset.skipNextClick === "true") {
          event.preventDefault();
          delete wingButton.dataset.skipNextClick;
          return;
        }
        if (wingWrap.classList.contains("is-open")) {
          closeWing();
        } else {
          openWing();
        }
      });
    }

    if (closeButton) {
      closeButton.addEventListener("click", closeWing);
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      addBotResponse(input.value);
      input.value = "";
      input.focus();
    });

    resetButton.addEventListener("click", () => {
      log.replaceChildren(
        createMessage(
          "bot",
          "대화를 초기화했습니다. 서비스 사용법, 점수 해석, 접근성 확인, 개인정보 기준 중 궁금한 내용을 입력하세요."
        )
      );
      input.focus();
    });

    const api = {
      ask: addBotResponse,
      focus: () => input.focus(),
      open: openWing,
      close: closeWing
    };
    activeHelpApi = api;
    return api;
  }

  function mountLaunchers() {
    document.querySelectorAll("[data-help-chatbot]").forEach((root) => {
      if (!root.dataset.helpMounted) {
        root.dataset.helpMounted = "true";
        mount(root);
      }
    });

    if (document.querySelector("[data-help-chatbot]")) {
      return;
    }

    const widgetRoot = createElement("div");
    widgetRoot.dataset.helpChatbot = "";
    widgetRoot.dataset.helpChatbotMode = "wing";
    document.body.appendChild(widgetRoot);
    mount(widgetRoot, { mode: "wing" });
  }

  window.GachibomHelpChatbot = {
    topics: HELP_TOPICS,
    mount
  };

  document.addEventListener("DOMContentLoaded", () => {
    mountTopicGrid();
    mountLaunchers();
  });
})();
