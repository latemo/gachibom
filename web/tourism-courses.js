const TOURISM_DATA_URL = "data/app_recommendation_seed.json";

const tourismState = {
  courses: [],
  filteredCourses: [],
  selectedCourseId: "",
  travelerType: "all",
  query: ""
};

const travelerOptions = [
  { id: "all", label: "전체", icon: "bi-grid" },
  { id: "wheelchair_user", label: "휠체어", icon: "bi-universal-access" },
  { id: "visual_impairment", label: "시각", icon: "bi-eye" },
  { id: "hearing_impairment", label: "청각", icon: "bi-ear" },
  { id: "senior_or_pregnant", label: "고령·임산부", icon: "bi-person-hearts" },
  { id: "stroller_family", label: "영유아 가족", icon: "bi-people" }
];

const categoryLabels = {
  forest: "자연 경관",
  sea: "바다",
  oreum: "오름",
  indoor: "실내",
  culture: "문화",
  cafe: "카페",
  restaurant: "식당",
  food_market: "시장",
  shopping: "쇼핑",
  rest_area: "휴식",
  transport: "교통",
  medical_support: "지원시설",
  other: "기타"
};

const categoryIcons = {
  forest: "bi-tree",
  sea: "bi-water",
  oreum: "bi-triangle",
  indoor: "bi-building",
  culture: "bi-bank",
  cafe: "bi-cup-hot",
  restaurant: "bi-fork-knife",
  food_market: "bi-basket",
  shopping: "bi-bag",
  rest_area: "bi-bench",
  transport: "bi-bus-front",
  medical_support: "bi-hospital",
  other: "bi-geo-alt"
};

const verificationLabels = {
  verified: "확인 완료",
  partial: "일부 확인",
  needs_check: "현장 확인 필요",
  unavailable: "정보 부족"
};

const recommendationWeights = {
  "적극추천": 3,
  "추천": 2,
  "조건부권장": 1
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeSearchValue(value) {
  return String(value ?? "")
    .toLocaleLowerCase("ko-KR")
    .replace(/\s+/g, "");
}

function numberedItems(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return [];
  }
  const markerPattern = /[①②③④⑤⑥⑦⑧⑨⑩]/;
  if (!markerPattern.test(text)) {
    return [text];
  }
  return text
    .split(/(?=[①②③④⑤⑥⑦⑧⑨⑩])/)
    .map((item) => item.replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "").trim())
    .filter(Boolean);
}

function proseMarkup(value) {
  const items = numberedItems(value);
  if (!items.length) {
    return "<p>등록된 설명이 없습니다.</p>";
  }
  if (items.length === 1) {
    return `<p>${escapeHtml(items[0])}</p>`;
  }
  return `<ol>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`;
}

function courseSearchText(course) {
  return normalizeSearchValue([
    course.title,
    course.overview,
    course.recommended_travelers,
    ...(course.stops || []).flatMap((stop) => [stop.name, stop.description])
  ].join(" "));
}

function courseMatchesTraveler(course) {
  if (tourismState.travelerType === "all") {
    return true;
  }
  return Boolean(course.recommendation_by_type?.[tourismState.travelerType]);
}

function recommendationScore(course) {
  if (tourismState.travelerType === "all") {
    return 0;
  }
  return recommendationWeights[course.recommendation_by_type?.[tourismState.travelerType]] || 0;
}

function selectedCourseFromUrl() {
  return new URLSearchParams(window.location.search).get("course") || "";
}

function updateCourseUrl(courseId, { replace = false } = {}) {
  const url = new URL(window.location.href);
  url.searchParams.set("course", courseId);
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({ courseId }, "", url);
}

function renderTravelerFilters() {
  const container = document.getElementById("travelerFilters");
  container.innerHTML = travelerOptions.map((option) => {
    const active = option.id === tourismState.travelerType;
    return `
      <button
        type="button"
        role="tab"
        class="${active ? "active" : ""}"
        data-traveler-type="${escapeHtml(option.id)}"
        aria-selected="${active}"
      >
        <i class="bi ${escapeHtml(option.icon)}" aria-hidden="true"></i>
        <span>${escapeHtml(option.label)}</span>
      </button>
    `;
  }).join("");
}

function renderCourseSelector() {
  const select = document.getElementById("courseSelect");
  select.replaceChildren();
  tourismState.filteredCourses.forEach((course, index) => {
    const option = document.createElement("option");
    option.value = course.id;
    option.textContent = `${String(index + 1).padStart(2, "0")}. ${course.title}`;
    select.append(option);
  });
  select.value = tourismState.selectedCourseId;
  select.disabled = tourismState.filteredCourses.length === 0;
}

function recommendationTone(value) {
  if (value === "적극추천") {
    return "strong";
  }
  if (value === "추천") {
    return "recommended";
  }
  return "conditional";
}

function renderRecommendationTypes(course) {
  const container = document.getElementById("courseRecommendationTypes");
  container.innerHTML = travelerOptions
    .filter((option) => option.id !== "all")
    .map((option) => {
      const recommendation = course.recommendation_by_type?.[option.id] || "정보 없음";
      return `
        <span class="${recommendationTone(recommendation)}">
          <i class="bi ${escapeHtml(option.icon)}" aria-hidden="true"></i>
          <b>${escapeHtml(option.label)}</b>
          <em>${escapeHtml(recommendation)}</em>
        </span>
      `;
    })
    .join("");
}

function destinationCardMarkup(stop) {
  const status = stop.verification_status || "needs_check";
  const category = categoryLabels[stop.category] || "장소";
  const icon = categoryIcons[stop.category] || categoryIcons.other;
  const candidateBadge = stop.promoted_candidate
    ? '<span class="destination-candidate">추가 검수 후보</span>'
    : "";
  const locationBadge = stop.location_available
    ? '<span><i class="bi bi-geo-alt-fill" aria-hidden="true"></i> 위치 확인</span>'
    : '<span class="needs-check"><i class="bi bi-geo-alt" aria-hidden="true"></i> 위치 확인 필요</span>';
  const cautions = stop.cautions
    ? `
      <details>
        <summary>
          <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
          방문 전 확인
          <i class="bi bi-chevron-down destination-detail-arrow" aria-hidden="true"></i>
        </summary>
        <div>${proseMarkup(stop.cautions)}</div>
      </details>
    `
    : "";

  return `
    <article class="tourism-destination-card ${escapeHtml(status)}">
      <header>
        <span class="destination-order">${escapeHtml(String(stop.order || "").padStart(2, "0"))}</span>
        <div>
          <span class="destination-category">
            <i class="bi ${escapeHtml(icon)}" aria-hidden="true"></i>
            ${escapeHtml(category)}
          </span>
          <h3>${escapeHtml(stop.name)}</h3>
        </div>
        <span class="destination-status ${escapeHtml(status)}">${escapeHtml(verificationLabels[status] || "확인 필요")}</span>
      </header>
      <p>${escapeHtml(stop.description || "등록된 장소 설명이 없습니다.")}</p>
      ${cautions}
      <footer>
        ${locationBadge}
        ${candidateBadge}
      </footer>
    </article>
  `;
}

function renderDestinations(course) {
  const stops = course.stops || [];
  const candidateCount = stops.filter((stop) => stop.promoted_candidate).length;
  const locatedCount = stops.filter((stop) => stop.location_available).length;
  document.getElementById("destinationGrid").innerHTML = stops.map(destinationCardMarkup).join("");
  document.getElementById("destinationSummary").textContent =
    `위치 확인 ${locatedCount}/${stops.length} · 추가 검수 후보 ${candidateCount}곳`;
}

function renderPager() {
  const courses = tourismState.filteredCourses;
  const index = courses.findIndex((course) => course.id === tourismState.selectedCourseId);
  const previousButton = document.getElementById("previousCourse");
  const nextButton = document.getElementById("nextCourse");
  const hasMultiple = courses.length > 1;
  const previous = hasMultiple ? courses[(index - 1 + courses.length) % courses.length] : null;
  const next = hasMultiple ? courses[(index + 1) % courses.length] : null;

  previousButton.disabled = !previous;
  nextButton.disabled = !next;
  previousButton.dataset.courseId = previous?.id || "";
  nextButton.dataset.courseId = next?.id || "";
  document.getElementById("previousCourseTitle").textContent = previous?.title || "이전 코스 없음";
  document.getElementById("nextCourseTitle").textContent = next?.title || "다음 코스 없음";
}

function renderCourse() {
  const detail = document.getElementById("tourismCourseDetail");
  const empty = document.getElementById("tourismEmpty");
  const loading = document.getElementById("tourismLoading");
  loading.hidden = true;

  if (!tourismState.filteredCourses.length) {
    detail.hidden = true;
    empty.hidden = false;
    return;
  }

  let course = tourismState.filteredCourses.find((item) => item.id === tourismState.selectedCourseId);
  if (!course) {
    course = tourismState.filteredCourses[0];
    tourismState.selectedCourseId = course.id;
  }

  empty.hidden = true;
  detail.hidden = false;
  document.getElementById("courseSelect").value = course.id;

  const index = tourismState.filteredCourses.findIndex((item) => item.id === course.id);
  const stops = course.stops || [];
  document.title = `${course.title} | 제주관광공사 추천 코스`;
  document.getElementById("coursePosition").textContent =
    `코스 ${String(index + 1).padStart(2, "0")} / ${String(tourismState.filteredCourses.length).padStart(2, "0")}`;
  document.getElementById("courseTitle").textContent = course.title;
  document.getElementById("courseRoute").textContent = stops.map((stop) => stop.name).join(" → ");
  document.getElementById("courseStopCount").textContent = `${stops.length}곳`;
  document.getElementById("courseTravelTime").textContent = course.total_travel_minutes
    ? `${course.total_travel_minutes}분`
    : "확인 필요";
  document.getElementById("courseMoveTime").textContent = course.total_move_minutes
    ? `${course.total_move_minutes}분`
    : "확인 필요";
  document.getElementById("courseOverview").innerHTML = proseMarkup(course.overview);
  document.getElementById("courseTravelers").innerHTML = proseMarkup(course.recommended_travelers);

  renderRecommendationTypes(course);
  renderDestinations(course);
  renderPager();
}

function refreshFilteredCourses({ syncUrl = true, replaceUrl = true } = {}) {
  const query = normalizeSearchValue(tourismState.query);
  tourismState.filteredCourses = tourismState.courses
    .filter(courseMatchesTraveler)
    .filter((course) => !query || courseSearchText(course).includes(query))
    .map((course, index) => ({ course, index, score: recommendationScore(course) }))
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .map((item) => item.course);

  if (!tourismState.filteredCourses.some((course) => course.id === tourismState.selectedCourseId)) {
    tourismState.selectedCourseId = tourismState.filteredCourses[0]?.id || "";
  }

  renderCourseSelector();
  renderCourse();
  if (syncUrl && tourismState.selectedCourseId) {
    updateCourseUrl(tourismState.selectedCourseId, { replace: replaceUrl });
  }
}

function renderHeroStats() {
  const stopCount = tourismState.courses.reduce((total, course) => total + (course.stops || []).length, 0);
  const candidateCount = tourismState.courses.reduce(
    (total, course) => total + (course.stops || []).filter((stop) => stop.promoted_candidate).length,
    0
  );
  document.getElementById("tourismHeroStats").innerHTML = `
    <span><b>${tourismState.courses.length}</b>개 공식 코스</span>
    <span><b>${stopCount}</b>개 추천 여행지</span>
    <span><b>${candidateCount}</b>개 추가 검수 후보</span>
  `;
}

function selectCourse(courseId, { replaceUrl = false } = {}) {
  if (!tourismState.filteredCourses.some((course) => course.id === courseId)) {
    return;
  }
  tourismState.selectedCourseId = courseId;
  updateCourseUrl(courseId, { replace: replaceUrl });
  renderCourse();
  window.scrollTo({ top: document.querySelector(".tourism-toolbar").offsetTop, behavior: "smooth" });
}

function bindTourismEvents() {
  document.getElementById("courseSelect").addEventListener("change", (event) => {
    selectCourse(event.target.value);
  });

  document.getElementById("courseSearch").addEventListener("input", (event) => {
    tourismState.query = event.target.value;
    refreshFilteredCourses();
  });

  document.getElementById("travelerFilters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-traveler-type]");
    if (!button) {
      return;
    }
    tourismState.travelerType = button.dataset.travelerType;
    renderTravelerFilters();
    refreshFilteredCourses();
  });

  document.getElementById("previousCourse").addEventListener("click", (event) => {
    selectCourse(event.currentTarget.dataset.courseId);
  });

  document.getElementById("nextCourse").addEventListener("click", (event) => {
    selectCourse(event.currentTarget.dataset.courseId);
  });

  document.getElementById("resetCourseFilters").addEventListener("click", () => {
    tourismState.query = "";
    tourismState.travelerType = "all";
    document.getElementById("courseSearch").value = "";
    renderTravelerFilters();
    refreshFilteredCourses();
  });

  window.addEventListener("popstate", () => {
    const courseId = selectedCourseFromUrl();
    if (tourismState.courses.some((course) => course.id === courseId)) {
      tourismState.selectedCourseId = courseId;
      if (!tourismState.filteredCourses.some((course) => course.id === courseId)) {
        tourismState.query = "";
        tourismState.travelerType = "all";
        document.getElementById("courseSearch").value = "";
        renderTravelerFilters();
        refreshFilteredCourses({ syncUrl: false });
        return;
      }
      renderCourseSelector();
      renderCourse();
    }
  });
}

async function initTourismCourses() {
  renderTravelerFilters();
  bindTourismEvents();

  try {
    const response = await fetch(TOURISM_DATA_URL, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("추천 코스 데이터를 불러오지 못했습니다.");
    }
    const data = await response.json();
    tourismState.courses = Array.isArray(data.official_courses) ? data.official_courses : [];
    tourismState.selectedCourseId = selectedCourseFromUrl() || tourismState.courses[0]?.id || "";
    renderHeroStats();
    refreshFilteredCourses();
  } catch (error) {
    document.getElementById("tourismLoading").hidden = true;
    const empty = document.getElementById("tourismEmpty");
    empty.hidden = false;
    empty.querySelector("h2").textContent = "추천 코스를 불러오지 못했습니다.";
    empty.querySelector("p").textContent = error?.message || "잠시 후 다시 확인해 주세요.";
    document.getElementById("resetCourseFilters").hidden = true;
  }
}

initTourismCourses();
