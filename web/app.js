const state = {
  data: null,
  validationReport: null,
  operationsReadiness: null,
  launchActionPlan: null,
  scenarioId: null,
  selectedSpotId: null,
  mapPopupSpotId: null,
  detailCollapsed: false,
  activeNav: "concepts",
  conceptPanelOpen: false,
  routeModalOpen: false,
  promoModalOpen: false,
  siteIntroOpen: true,
  profile: null,
  runtimeScenario: null,
  apiStatus: "추천 준비 완료",
  apiState: {
    status: "idle",
    message: "추천 기준을 준비하고 있습니다.",
    canRetry: false
  }
};

const RECOMMENDATION_MODEL = "gpt-5-mini";
const RECOMMENDATION_LIMIT = 4;
const AI_DISPLAY_NAME = "가치봄 AI";
const AI_HEADLINE_MAX_LENGTH = 90;
const AI_LIST_ITEM_MAX_LENGTH = 86;
const ROUTE_PROVIDER_TIMEOUT_MS = 7000;
const ROUTE_SPEED_FALLBACK_KMH = 32;
const ROUTE_KEY_COLOR = "#126fb5";
const SITE_INTRO_SEEN_KEY = "gachibom:site-intro-seen";
let shareFeedbackTimer = null;
let centerMap = null;
let centerTileLayer = null;
let centerLayerGroup = null;
let centerMapLayerMode = "soft";
let centerMapRenderSequence = 0;
let centerMapLastFitKey = null;
let centerMapObserver = null;
let pendingCenterMapScenario = null;
let routeMap = null;
let routeLayerGroup = null;
let routeProxySupportPromise = null;
const routeSummaryCache = new Map();
let recommendationRequestSequence = 0;
let siteIntroStarted = false;

const centerMapLayerDefinitions = {
  soft: {
    label: "부드러운 지도",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    options: {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO"
    }
  },
  standard: {
    label: "표준 지도",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    options: {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }
  }
};

const valueLabels = {
  recovery_traveler: "회복 중",
  caregiver_group: "보호자 동반",
  wheelchair_user: "휠체어 접근",
  stroller_family: "아이 동반",
  diet_restricted_traveler: "음식 제한",
  senior: "고령자",
  verified: "확인 완료",
  partial: "일부 확인",
  needs_check: "확인 필요",
  unavailable: "정보 부족",
  yes: "가능",
  no: "불가",
  unknown: "정보 부족",
  very_low: "매우 낮음",
  low: "낮음",
  medium: "보통",
  high: "높음"
};

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

const conditionLabels = {
  traveler_type: "여행자",
  mobility_conditions: "이동 조건",
  preferred_themes: "선호 테마",
  required_accessibility: "필수 확인",
  avoid: "제외 조건"
};

const scoreLabels = {
  source_trust: "정보 신뢰",
  mobility_fit: "이동 편의",
  facility_fit: "시설 접근성",
  theme_fit: "편의 시설",
  safety_clarity: "안전·편의"
};

const accessibilityFieldLabels = {
  wheelchair_access: "휠체어",
  accessible_toilet: "화장실",
  accessible_restroom: "화장실",
  restroom: "화장실",
  parking: "주차",
  slope_or_stairs: "경사",
  slope: "경사",
  rest_area: "휴식",
  rental_or_assistance: "대여",
  surface_condition: "바닥",
  crowd_level: "혼잡"
};

const scenarioCards = [
  {
    id: "recovery_quiet",
    icon: "♡",
    image: "assets/theme-character-recovery.webp?v=20260710-2",
    title: "회복 중",
    body: "무리한 일정을 피하고 휴식이 많은 코스",
    tone: "rose"
  },
  {
    id: "diet_restricted",
    icon: "♨",
    image: "assets/theme-character-food.webp?v=20260710-2",
    title: "음식 제한",
    body: "식당·시장 제외, 휴식 중심",
    tone: "cream"
  },
  {
    id: "stroller_family",
    icon: "▣",
    image: "assets/theme-character-family.webp?v=20260710-2",
    title: "아이 동반",
    body: "유모차와 보호자 휴식 동선을 우선",
    tone: "purple"
  },
  {
    id: "wheelchair_access",
    icon: "♿",
    image: "assets/theme-character-wheelchair.webp?v=20260710-2",
    title: "휠체어 접근",
    body: "휠체어 접근 가능한 장소 우선",
    tone: "mint"
  },
  {
    id: "weather_sensitive",
    icon: "☁",
    image: "assets/theme-character-weather.webp?v=20260710-2",
    title: "날씨 민감",
    body: "실내/실외 혼합 코스 선호",
    tone: "blue"
  }
];

let themeMotionTimer = null;

const optionItems = [
  { key: "traveler_type", value: "stroller_family", label: "아이 동반" },
  { key: "mobility_conditions", value: "짧은 이동", label: "짧은 동선" },
  { key: "mobility_conditions", value: "계단 회피", label: "계단 회피" },
  { key: "mobility_conditions", value: "휴식 필요", label: "휴식 필요" },
  { key: "required_accessibility", value: "장애인 화장실", label: "장애인 화장실" },
  { key: "required_accessibility", value: "주차", label: "주차" },
  { key: "preferred_themes", value: "실내", label: "실내" },
  { key: "avoid", value: "식당 제외", label: "식당 제외" }
];

const scenarioMatchWeights = {
  traveler_type: 4,
  mobility_conditions: 3,
  preferred_themes: 2,
  required_accessibility: 3,
  avoid: 4
};

const officialRecommendationWeights = {
  "적극추천": 3,
  "추천": 2,
  "조건부권장": 1
};

const mapCardBounds = [
  { x: 346, y: 108, width: 282, height: 132 },
  { x: 318, y: 292, width: 298, height: 132 },
  { x: 226, y: 438, width: 342, height: 132 },
  { x: 294, y: 617, width: 334, height: 132 }
];

const mapReservedBounds = [
  { x: 38, y: 28, width: 306, height: 170 }
];

const jejuMapProjection = {
  north: 33.57,
  south: 33.1,
  west: 126.15,
  east: 126.98,
  content: {
    left: 10,
    top: 8,
    width: 80,
    height: 80
  }
};

const DEFAULT_PLACE_IMAGE = {
  src: "assets/WELCOME-1-001.jpg",
  caption: "제주 접근성 여행 기본 이미지",
  source: "서비스 기본 이미지",
  policy: "대표 이미지 미수급"
};

const PLACE_IMAGE_POLICY = {
  jeju_indoor_literature_022: {
    src: "assets/JEJULITERMU-1-001.jpg",
    caption: "제주문학관 진입 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  },
  jeju_indoor_hanran_016: {
    src: "assets/HALLANEX-1-001.jpg",
    caption: "제주한란전시관 장애인 주차 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  },
  jeju_indoor_icc_032: {
    src: "assets/ICCJEJU-accessible-tourism.jpg",
    caption: "제주국제컨벤션센터 전경",
    source: "열린관광 모두의 여행",
    policy: "장소별 대표 이미지"
  },
  jeju_indoor_mandeok_museum_009: {
    src: "assets/MANDEOK-1-001.jpg",
    caption: "김만덕기념관 장애인 주차 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  },
  jeju_indoor_worldheritage_011: {
    src: "assets/WNHCENTER-1-001.jpg",
    caption: "제주세계자연유산센터 장애인 주차 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  },
  jeju_forest_saryeoni_002: {
    src: "assets/SARANI-1-001.jpg",
    caption: "사려니숲길 무장애 주차 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  },
  jeju_forest_healing_001: {
    src: "assets/HEALING-1-001.jpg",
    caption: "서귀포 치유의숲 장애인 화장실 진입 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  },
  jeju_cafe_osulloc_013: {
    src: "assets/OSULLOC-easyjeju.jpg",
    caption: "오설록 티 뮤지엄 실내 전경",
    source: "이지제주",
    policy: "장소별 대표 이미지"
  },
  jeju_rest_sinsan_015: {
    src: "assets/SHINSANPA-1-001.jpg",
    caption: "신산공원 장애인 주차 동선",
    source: "제주특별자치도 로드뷰",
    policy: "장소별 접근성 이미지"
  }
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function displayLabel(value) {
  return valueLabels[value] || value;
}

function unique(values) {
  return Array.from(new Set((values || []).filter(Boolean)));
}

function cleanDisplayText(value, maxLength = AI_LIST_ITEM_MAX_LENGTH) {
  const text = String(value || "")
    .replace(/\bvery_low\b/g, "매우 낮음")
    .replace(/\blow\b/g, "낮음")
    .replace(/\bmedium\b/g, "보통")
    .replace(/\bhigh\b/g, "높음")
    .replace(/\byes\b/g, "가능")
    .replace(/\bno\b/g, "불가")
    .replace(/\bunknown\b/g, "정보 부족")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/(.)\1{8,}/g, "$1$1$1");
  if (text.length <= maxLength) {
    return text;
  }
  const separators = ["다.", "요.", ".", "!", "?"];
  const cutoff = separators.reduce((best, separator) => Math.max(best, text.lastIndexOf(separator, maxLength)), -1);
  if (cutoff >= Math.floor(maxLength / 2)) {
    return text.slice(0, cutoff + 1).trim();
  }
  return `${text.slice(0, maxLength).trim()}...`;
}

function cleanDisplayList(values, maxItems = 3) {
  return unique((values || []).map((value) => cleanDisplayText(value)).filter(Boolean)).slice(0, maxItems);
}

function emptyProfile() {
  return Object.keys(conditionLabels).reduce((profile, key) => {
    profile[key] = [];
    return profile;
  }, {});
}

function normalizeProfile(profile) {
  const normalized = emptyProfile();
  Object.keys(normalized).forEach((key) => {
    normalized[key] = unique(profile?.[key] || []);
  });
  return normalized;
}

function profileFromScenario(scenario) {
  return normalizeProfile(scenario?.traveler_summary || {});
}

function hasProfileValue(profile, key, values) {
  const selected = new Set(profile?.[key] || []);
  return values.some((value) => selected.has(value));
}

function overlapCount(leftValues, rightValues) {
  const right = new Set(rightValues || []);
  return (leftValues || []).filter((value) => right.has(value)).length;
}

function scenarioPriorityBoost(scenarioId, profile) {
  let boost = 0;
  if (scenarioId === "diet_restricted" && (
    hasProfileValue(profile, "traveler_type", ["diet_restricted_traveler"])
    || hasProfileValue(profile, "avoid", ["식당 제외", "외부 음식 제한"])
  )) {
    boost += 60;
  }
  if (scenarioId === "wheelchair_access" && (
    hasProfileValue(profile, "traveler_type", ["wheelchair_user"])
    || hasProfileValue(profile, "required_accessibility", ["휠체어 접근"])
  )) {
    boost += 55;
  }
  if (scenarioId === "weather_sensitive" && (
    hasProfileValue(profile, "mobility_conditions", ["비", "바람", "더위"])
    || hasProfileValue(profile, "avoid", ["강풍"])
  )) {
    boost += 50;
  }
  return boost;
}

function scoreScenarioForProfile(scenario, profile) {
  const summary = scenario.traveler_summary || {};
  const baseScore = Object.entries(scenarioMatchWeights).reduce((total, [key, weight]) => (
    total + overlapCount(profile[key], summary[key]) * weight
  ), 0);
  return baseScore + scenarioPriorityBoost(scenario.id, profile);
}

function matchedScenarioFromProfile(profile) {
  return state.data.scenarios.reduce((best, scenario) => {
    const score = scoreScenarioForProfile(scenario, profile);
    if (!best || score > best.score) {
      return { scenario, score };
    }
    return best;
  }, null)?.scenario || state.data.scenarios[0];
}

function toggleProfileValue(key, value) {
  const profile = normalizeProfile(state.profile);
  const selected = new Set(profile[key] || []);
  if (selected.has(value)) {
    selected.delete(value);
  } else {
    selected.add(value);
  }
  profile[key] = Array.from(selected);
  state.profile = profile;
}

async function loadData() {
  const response = await fetch("data/app_recommendation_seed.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("추천 데이터를 불러오지 못했습니다.");
  }
  return response.json();
}

async function loadValidationReport() {
  try {
    const response = await fetch("data/recommendation_case_validation_report.json", { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch (error) {
    return null;
  }
}

async function loadOperationsReadiness() {
  try {
    const response = await fetch("data/operations_readiness_report.json", { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch (error) {
    return null;
  }
}

async function loadServiceLaunchActionPlan() {
  try {
    const response = await fetch("data/service_launch_action_plan.json", { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch (error) {
    return null;
  }
}

function currentStaticScenario() {
  return state.data.scenarios.find((scenario) => scenario.id === state.scenarioId) || state.data.scenarios[0];
}

function currentScenario() {
  return state.runtimeScenario || currentStaticScenario();
}

function runtimeScenarioFromResponse(response) {
  const staticIndex = staticPlacesById();
  const places = enrichRuntimePlaces(response.places || [], response.recommendation?.course?.route || [], staticIndex);
  return {
    id: "runtime_recommendation",
    label: "맞춤",
    title: "맞춤 접근성 추천",
    traveler_summary: response.traveler_summary,
    recommendation: response.recommendation,
    places,
    ai_summary: response.ai_summary,
    engine: response.engine
  };
}

function staticPlacesById() {
  const places = new Map();
  (state.data?.scenarios || []).forEach((scenario) => {
    (scenario.places || []).forEach((place) => {
      if (place?.spot_id && !places.has(place.spot_id)) {
        places.set(place.spot_id, place);
      }
    });
  });
  return places;
}

function enrichRuntimePlaces(runtimePlaces, route, staticIndex) {
  const places = runtimePlaces.map((place) => enrichRuntimePlace(place, staticIndex));
  const existing = new Set(places.map((place) => place.spot_id).filter(Boolean));
  route.forEach((routeItem) => {
    const spotId = routeItem?.spot_id;
    if (!spotId || existing.has(spotId)) {
      return;
    }
    const fallback = staticIndex.get(spotId);
    if (!fallback) {
      return;
    }
    places.push(enrichRuntimePlace({
      ...fallback,
      ...routeItem,
      spot_id: spotId,
      name: routeItem.name || fallback.name
    }, staticIndex));
    existing.add(spotId);
  });
  return places;
}

function enrichRuntimePlace(place, staticIndex) {
  const fallback = staticIndex.get(place?.spot_id) || {};
  return {
    ...fallback,
    ...place,
    accessibility: place?.accessibility || fallback.accessibility || {},
    location: validLocation(place?.location) ? place.location : fallback.location || null
  };
}

function validLocation(location) {
  if (!location) {
    return false;
  }
  const latitude = Number(location.latitude);
  const longitude = Number(location.longitude);
  return Number.isFinite(latitude) && Number.isFinite(longitude);
}

function recommendationStatusText(summary) {
  return "선택한 코스 반영 완료";
}

function recommendationPayload() {
  return {
    traveler_summary: normalizeProfile(state.profile),
    limit: RECOMMENDATION_LIMIT,
    use_ai: true,
    model: RECOMMENDATION_MODEL
  };
}

function setApiState(status, message, { canRetry = false } = {}) {
  state.apiState = { status, message, canRetry };
  state.apiStatus = message;
}

function apiStatusTitle() {
  const status = state.apiState.status;
  if (status === "loading") {
    return "추천 업데이트 중";
  }
  if (status === "success") {
    return "추천 결과 업데이트";
  }
  if (status === "error") {
    return "추천 업데이트 실패";
  }
  if (status === "static") {
    return "기본 추천";
  }
  return "추천 준비 완료";
}

function apiStatusPillText() {
  const status = state.apiState.status;
  if (status === "loading") {
    return "계산 중";
  }
  if (status === "success") {
    return "업데이트";
  }
  if (status === "error") {
    return "기본 추천";
  }
  if (status === "static") {
    return "기본 추천";
  }
  return "준비 완료";
}

function shouldRequestRuntimeApi() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("api") === "1") {
    return true;
  }
  if (params.get("api") === "0") {
    return false;
  }
  return false;
}

function shouldRequestRouteProxy() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("routeProxy") === "1" || params.get("api") === "1") {
    return true;
  }
  if (params.get("routeProxy") === "0" || params.get("api") === "0") {
    return false;
  }
  return false;
}

async function requestRuntimeRecommendation(sequence) {
  const requestSequence = sequence || ++recommendationRequestSequence;
  if (!shouldRequestRuntimeApi()) {
    if (requestSequence === recommendationRequestSequence) {
      state.runtimeScenario = null;
      setApiState("static", "기본 추천 사용");
    }
    return false;
  }

  try {
    const response = await fetch("api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recommendationPayload())
    });
    if (!response.ok) {
      throw new Error("추천 서버 미응답");
    }
    const payload = await response.json();
    if (requestSequence !== recommendationRequestSequence) {
      return false;
    }
    state.runtimeScenario = runtimeScenarioFromResponse(payload);
    setApiState("success", recommendationStatusText(payload.ai_summary));
    return true;
  } catch (error) {
    if (requestSequence !== recommendationRequestSequence) {
      return false;
    }
    state.runtimeScenario = null;
    setApiState("error", "추천 업데이트 실패, 기본 추천 유지", { canRetry: true });
    state.apiState.detail = error?.message || "추천 요청에 실패했습니다.";
    return false;
  }
}

async function refreshScenarioRecommendation({ renderLoading = false } = {}) {
  const sequence = ++recommendationRequestSequence;
  if (shouldRequestRuntimeApi() && renderLoading) {
    state.runtimeScenario = null;
    setApiState("loading", "선택한 코스로 업데이트 중");
    render();
  }
  await requestRuntimeRecommendation(sequence);
}

async function refreshRuntimeRecommendation(options = {}) {
  const matchedScenario = matchedScenarioFromProfile(state.profile);
  state.scenarioId = matchedScenario.id;
  state.selectedSpotId = null;
  state.mapPopupSpotId = null;
  state.detailCollapsed = false;
  await refreshScenarioRecommendation(options);
}

function selectedRoute(scenario) {
  return scenario.recommendation?.course?.route || [];
}

function routeEntriesForScenario(scenario) {
  return selectedRoute(scenario).slice(0, 4).map((routeItem, index) => {
    const place = routePlace(scenario, routeItem);
    return {
      order: Number(routeItem.order || index + 1),
      routeItem,
      place,
      location: validLocation(place.location) ? place.location : null,
      score: scoreForPlace(place, Math.max(88, (scenario.recommendation?.score?.total || 90) - index * 2))
    };
  });
}

function routeCoordinateEntries(scenario) {
  return routeEntriesForScenario(scenario).filter((entry) => entry.location);
}

function placesById(scenario) {
  return new Map((scenario.places || []).map((place) => [place.spot_id, place]));
}

function routePlace(scenario, routeItem) {
  const fallback = staticPlacesById().get(routeItem.spot_id);
  return placesById(scenario).get(routeItem.spot_id) || fallback || {
    spot_id: routeItem.spot_id,
    name: routeItem.name,
    category: "other",
    address: "제주",
    recommendation_score: null,
    accessibility: {},
    verification_status: "needs_check"
  };
}

function selectedPlace(scenario) {
  const route = selectedRoute(scenario);
  if (!route.some((item) => item.spot_id === state.selectedSpotId)) {
    state.selectedSpotId = route[0]?.spot_id || scenario.places?.[0]?.spot_id || null;
  }
  const places = placesById(scenario);
  return places.get(state.selectedSpotId) || null;
}

function placeholderTitleLines(name) {
  const characters = Array.from(name);
  if (characters.length <= 13) {
    return [name];
  }
  const firstLine = characters.slice(0, 13).join("");
  const remainder = characters.slice(13);
  const secondLine = remainder.length > 13
    ? `${remainder.slice(0, 12).join("")}…`
    : remainder.join("");
  return [firstLine, secondLine];
}

function placeholderForPlace(place) {
  const name = String(place?.name || "추천 장소").trim();
  const category = categoryLabels[place?.category] || "제주 여행";
  const palettes = [
    { background: "#17433f", accent: "#f2c84b", text: "#ffffff" },
    { background: "#7a3043", accent: "#9de0c2", text: "#ffffff" },
    { background: "#263238", accent: "#ff8a65", text: "#ffffff" },
    { background: "#126e75", accent: "#f6e7b0", text: "#ffffff" },
    { background: "#53433f", accent: "#9fd7e5", text: "#ffffff" }
  ];
  const hash = Array.from(`${place?.spot_id || ""}:${name}`).reduce(
    (total, character) => ((total * 31) + character.codePointAt(0)) >>> 0,
    0
  );
  const palette = palettes[hash % palettes.length];
  const titleLines = placeholderTitleLines(name);
  const titleStartY = titleLines.length === 1 ? 278 : 246;
  const titleMarkup = titleLines.map((line, index) => (
    `<text x="72" y="${titleStartY + index * 64}" fill="${palette.text}" font-size="52" font-weight="700">${escapeHtml(line)}</text>`
  )).join("");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
      <rect width="960" height="540" fill="${palette.background}"/>
      <rect x="72" y="76" width="88" height="8" fill="${palette.accent}"/>
      <text x="72" y="142" fill="${palette.accent}" font-family="Arial, Malgun Gothic, sans-serif" font-size="26" font-weight="700">${escapeHtml(category)}</text>
      <g font-family="Arial, Malgun Gothic, sans-serif">${titleMarkup}</g>
      <text x="72" y="462" fill="${palette.text}" fill-opacity="0.78" font-family="Arial, Malgun Gothic, sans-serif" font-size="24">대표 이미지 준비 중</text>
    </svg>
  `;
  return {
    src: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    caption: `${name} 대표 이미지 준비 중`,
    source: "서비스 이미지 안내",
    policy: "대표 이미지 준비 중"
  };
}

function visualForPlace(place, usedSources = null) {
  const placeholder = placeholderForPlace(place);
  let policy = PLACE_IMAGE_POLICY[place?.spot_id] || placeholder;
  const sourceKey = String(policy.src || "").split(/[?#]/)[0].toLowerCase();
  if (usedSources && sourceKey) {
    if (usedSources.has(sourceKey)) {
      policy = placeholder;
    } else {
      usedSources.add(sourceKey);
    }
  }
  return {
    src: policy.src,
    alt: `${place?.name || "추천 장소"} 대표 이미지`,
    caption: policy.caption,
    source: policy.source,
    policy: policy.policy,
    fallbackSrc: placeholder.src,
    fallbackCaption: placeholder.caption,
    fallbackSource: placeholder.source
  };
}

function scoreForPlace(place, fallbackScore) {
  const score = Number(place?.recommendation_score ?? place?.score?.total ?? place?.score ?? fallbackScore);
  return Number.isFinite(score) ? Math.round(score) : 90;
}

function scoreGrade(place, score) {
  return place?.score?.grade || (score >= 90 ? "A" : score >= 80 ? "B" : "C");
}

function accessibilityEntries(place) {
  const raw = place?.accessibility;
  if (Array.isArray(raw)) {
    return raw.map((item) => ({
      field: item.field,
      label: item.label || accessibilityFieldLabels[item.field] || item.field,
      state: item.state || "unknown",
      state_label: item.state_label || stateText(item.state || "unknown"),
      note: item.note || ""
    }));
  }
  if (raw && typeof raw === "object") {
    return Object.entries(raw).map(([field, item]) => ({
      field,
      label: accessibilityFieldLabels[field] || field,
      state: item?.state || "unknown",
      state_label: stateText(item?.state || "unknown"),
      note: item?.note || ""
    }));
  }
  return [];
}

function accessibilityItem(place, aliases) {
  const aliasSet = new Set(aliases);
  return accessibilityEntries(place).find((item) => aliasSet.has(item.field)) || {
    field: aliases[0],
    label: accessibilityFieldLabels[aliases[0]] || aliases[0],
    state: "unknown",
    state_label: "정보 부족",
    note: "아직 확인 가능한 세부 정보가 부족합니다."
  };
}

function effortValue(place, key) {
  return place?.effort?.[key] || place?.[key] || "unknown";
}

function verificationLabel(place) {
  const status = place?.verification?.status || place?.verification_status || "needs_check";
  if (status === "verified") {
    return "확인 완료";
  }
  if (status === "partial") {
    return "일부 확인";
  }
  return "확인 필요";
}

function sourceSummaryItems(place) {
  return (place?.source_summary || place?.sources || []).slice(0, 3);
}

function routeNames(scenario) {
  return selectedRoute(scenario).slice(0, 4).map((item) => item.name).filter(Boolean);
}

function scenarioById(scenarioId) {
  return state.data?.scenarios?.find((scenario) => scenario.id === scenarioId) || state.data?.scenarios?.[0] || null;
}

function scenarioCardById(scenarioId) {
  return scenarioCards.find((card) => card.id === scenarioId) || scenarioCards[0];
}

function conceptPreviewPlaces(scenario, maxItems = 3) {
  const usedSources = new Set();
  return selectedRoute(scenario).slice(0, maxItems).map((routeItem, index) => {
    const place = routePlace(scenario, routeItem);
    return {
      order: Number(routeItem.order || index + 1),
      name: place.name || routeItem.name || "추천 장소",
      category: categoryLabels[place.category] || "추천 장소",
      verified: verificationLabel(place),
      located: validLocation(place.location),
      visual: visualForPlace(place, usedSources)
    };
  });
}

function conceptMetaText(scenario) {
  const route = selectedRoute(scenario).slice(0, 4);
  const verifiedCount = route.filter((routeItem) => verificationLabel(routePlace(scenario, routeItem)) !== "확인 필요").length;
  const score = Number(scenario?.recommendation?.score?.total);
  return [
    `${route.length || 0}곳 추천`,
    `검증 ${verifiedCount}/${route.length || 0}`,
    Number.isFinite(score) ? `${Math.round(score)}점` : ""
  ].filter(Boolean).join(" · ");
}

function conceptCardScoreText(scenario) {
  const score = Number(scenario?.recommendation?.score?.total);
  return Number.isFinite(score) ? `접근성 적합도 ${Math.round(score)}%` : "접근성 적합도 계산 중";
}

function conceptCardMetaText(scenario) {
  const route = selectedRoute(scenario).slice(0, 4);
  const verifiedCount = route.filter((routeItem) => verificationLabel(routePlace(scenario, routeItem)) !== "확인 필요").length;
  return `${route.length || 0}곳 추천 · 검증 ${verifiedCount}/${route.length || 0}`;
}

function renderConceptPage(scenario) {
  const grid = document.getElementById("conceptGrid");
  const activeScenario = scenarioById(state.scenarioId) || scenario;
  if (grid) {
    grid.innerHTML = scenarioCards.map((card, index) => {
      const cardScenario = scenarioById(card.id);
      const active = state.conceptPanelOpen && card.id === state.scenarioId;
      return `
        <button class="concept-card ${card.tone} ${active ? "active" : ""}" type="button" data-concept-id="${escapeHtml(card.id)}" aria-label="${escapeHtml(card.title)} 테마 추천 미리보기">
          ${active ? '<span class="concept-selected-badge">선택됨</span>' : ""}
          <span class="concept-card-index">${String(index + 1).padStart(2, "0")}</span>
          <strong>${escapeHtml(card.title)}</strong>
          <small>${escapeHtml(card.body)}</small>
          <span class="concept-card-icon" aria-hidden="true">
            <img src="${escapeHtml(card.image)}" alt="" loading="lazy" decoding="async">
          </span>
          <em>${escapeHtml(conceptCardScoreText(cardScenario))}</em>
          <span class="concept-card-submeta">${escapeHtml(conceptCardMetaText(cardScenario))}</span>
        </button>
      `;
    }).join("");
  }

  const card = scenarioCardById(activeScenario?.id);
  const previewPlaces = conceptPreviewPlaces(activeScenario, 4);
  const summaryBadge = document.getElementById("conceptSummaryBadge");
  const summaryTitle = document.getElementById("conceptSummaryTitle");
  const summaryText = document.getElementById("conceptSummaryText");
  const summaryProof = document.getElementById("conceptSummaryProof");
  const summaryPlaces = document.getElementById("conceptSummaryPlaces");
  const score = Number(activeScenario?.recommendation?.score?.total);
  const scoreText = Number.isFinite(score) ? Math.round(score) : "-";
  const verifiedCount = previewPlaces.filter((place) => place.verified !== "확인 필요").length;

  if (summaryBadge) {
    summaryBadge.textContent = `${card.title} 테마`;
  }
  if (summaryTitle) {
    summaryTitle.textContent = activeScenario?.recommendation?.course?.title || activeScenario?.title || card.title;
  }
  if (summaryText) {
    summaryText.textContent = `${conceptMetaText(activeScenario)} · ${card.body}`;
  }
  if (summaryProof) {
    summaryProof.innerHTML = `
      <span><b>접근성 적합도</b><strong>${escapeHtml(String(scoreText))}%</strong></span>
      <span><b>검증 완료</b><strong>${escapeHtml(String(verifiedCount))}/${escapeHtml(String(previewPlaces.length))}</strong></span>
      <span><b>신뢰도 지수</b><strong>${escapeHtml(String(scoreText))}/100</strong></span>
    `;
  }
  if (summaryPlaces) {
    summaryPlaces.innerHTML = previewPlaces.map((place) => `
      <span class="concept-preview-item ${place.located ? "located" : "needs-check"}">
        <img class="concept-preview-image" src="${escapeHtml(place.visual.src)}" alt="${escapeHtml(place.visual.alt)}" loading="lazy" decoding="async" data-fallback-src="${escapeHtml(place.visual.fallbackSrc)}" data-fallback-caption="${escapeHtml(place.visual.fallbackCaption)}" data-fallback-source="${escapeHtml(place.visual.fallbackSource)}">
        <b>${escapeHtml(place.order)}. ${escapeHtml(place.name)}</b>
        <small>${escapeHtml(place.category)} · ${escapeHtml(place.verified)}</small>
      </span>
    `).join("");
  }
}

function syncStepViewState() {
  const recommendations = document.getElementById("recommendations");
  const recommendationTop = recommendations?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY;
  const journeyInView = recommendationTop <= Math.min(window.innerHeight * 0.4, 260);
  document.body.classList.toggle("concept-result-open", state.conceptPanelOpen && !journeyInView);
  document.body.classList.toggle("journey-in-view", journeyInView);
}

function restartThemeMotion() {
  document.body.classList.remove("theme-preview-motion");
  window.clearTimeout(themeMotionTimer);
  window.requestAnimationFrame(() => {
    document.body.classList.add("theme-preview-motion");
    themeMotionTimer = window.setTimeout(() => {
      document.body.classList.remove("theme-preview-motion");
    }, 720);
  });
}

function openConceptResultPanel() {
  state.conceptPanelOpen = true;
  restartThemeMotion();
  syncStepViewState();
  window.requestAnimationFrame(() => {
    const panel = document.querySelector(".concept-result-panel");
    if (!panel) {
      return;
    }
    if (window.matchMedia("(max-width: 1180px)").matches) {
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
      panel.scrollIntoView({ behavior, block: "start" });
      return;
    }
    panel.focus?.({ preventScroll: true });
  });
}

function closeConceptResultPanel() {
  state.conceptPanelOpen = false;
  syncStepViewState();
}

function officialTravelerTypes(profile) {
  const types = [];
  const text = Object.values(profile || {}).flat().join(" ");
  if (/휠체어|wheelchair/.test(text)) {
    types.push("wheelchair_user");
  }
  if (/유모차|아이|stroller|영유아/.test(text)) {
    types.push("stroller_family");
  }
  if (/고령|노인|임산부|임신|senior|pregnant/.test(text)) {
    types.push("senior_or_pregnant");
  }
  if (/시각/.test(text)) {
    types.push("visual_impairment");
  }
  if (/청각/.test(text)) {
    types.push("hearing_impairment");
  }
  return unique(types);
}

function officialCourseScore(course, scenario) {
  const profile = normalizeProfile(scenario?.traveler_summary || state.profile);
  const activeTypes = officialTravelerTypes(profile);
  const recommendations = course?.recommendation_by_type || {};
  const typeKeys = activeTypes.length ? activeTypes : Object.keys(recommendations);
  const typeScore = Math.max(0, ...typeKeys.map((type) => officialRecommendationWeights[recommendations[type]] || 0));
  const promotedCount = (course?.stops || []).filter((stop) => stop.promoted_candidate).length;
  const locationCount = (course?.stops || []).filter((stop) => stop.location_available).length;
  return typeScore * 100 + promotedCount * 4 + locationCount;
}

function officialCoursesForScenario(scenario) {
  const courses = state.data?.official_courses || [];
  return courses
    .map((course) => ({ course, score: officialCourseScore(course, scenario) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((item) => item.course);
}

function currentValidationCase(scenario) {
  const caseId = scenario?.id === "runtime_recommendation" ? state.scenarioId : scenario?.id;
  return (state.validationReport?.cases || []).find((item) => item.id === caseId) || null;
}

function validationSummaryText() {
  const summary = state.validationReport?.summary;
  if (!summary) {
    return "검증표 미연결";
  }
  return `상황별 검증 ${summary.passed_cases}/${summary.total_cases} 통과`;
}

function validationStatusClass(status) {
  return status === "통과" ? "pass" : "fail";
}

function operationsStatusLabel(status) {
  if (status === "ready_for_full_service") {
    return "전체 공개 가능";
  }
  if (status === "ready_with_warnings") {
    return "제한 공개 가능";
  }
  if (status === "blocked_for_full_service") {
    return "준비 필요";
  }
  return "확인 필요";
}

function operationsStatusClass(status) {
  if (status === "ready_for_full_service") {
    return "pass";
  }
  if (status === "ready_with_warnings") {
    return "warn";
  }
  if (status === "blocked_for_full_service") {
    return "block";
  }
  return "warn";
}

function operationsSectionLabel(name) {
  const labels = {
    base_place_catalog: "기본 장소 카드",
    public_data_dependencies: "공공데이터 의존성",
    roadview_service_seed: "로드뷰 시드",
    operational_documents: "운영 문서"
  };
  return labels[name] || name;
}

function gateStatusText(status) {
  if (status === "pass") {
    return "통과";
  }
  if (status === "warn") {
    return "주의";
  }
  if (status === "block") {
    return "보류";
  }
  return "확인";
}

function readinessValueLabel(value) {
  const labels = {
    awaiting_receipt: "원본 수령 대기",
    ready_to_use: "사용 가능",
    ready_to_submit: "제출 준비",
    not_required_ready: "별도 신청 불필요",
    action_required: "조치 필요",
    blocked: "보류",
    ready_for_service_activation: "서비스 반영 가능",
    ready_for_full_service: "전체 공개 가능",
    ready_with_warnings: "제한 공개 가능",
    blocked_for_full_service: "준비 필요",
    "all service seeds promoted": "모든 시드 승격 완료",
    "primary catalog all active": "기본 카드 모두 활성",
    "downloaded public datasets ready": "다운로드형 공공데이터 준비",
    "not_required_ready or ready_to_use": "별도 신청 불필요 또는 사용 가능"
  };
  const text = String(value ?? "");
  if (labels[text]) {
    return labels[text];
  }
  if (/^\d+\/\d+$/.test(text) || /^\d+(\.\d+)?%$/.test(text) || /^missing \d+$/.test(text)) {
    return text.replace("missing", "누락");
  }
  if (/^\d+ cards$/.test(text)) {
    return text.replace("cards", "개 카드");
  }
  return text
    .replace(/_/g, " ")
    .replace(/\bpass\b/g, "통과")
    .replace(/\bwarn\b/g, "주의")
    .replace(/\bblock\b/g, "보류");
}

function selectedValidationChecks(validationCase) {
  const checks = validationCase?.validation?.checks || [];
  const priority = checks.filter((check) => (
    /총점|도보 부담|상위 추천 제외|필수 장소|필수 편의시설|날씨 민감도|정책 효과/.test(`${check.area} ${check.name}`)
  ));
  return (priority.length ? priority : checks).slice(0, 6);
}

function aiStatusBadge(summary) {
  if (!summary) {
    return "기본 설명";
  }
  if (summary.status === "success") {
    return "AI 반영";
  }
  if (summary.status === "disabled_no_key") {
    return "키 없음";
  }
  if (summary.status === "skipped") {
    return "생략";
  }
  return "점수 근거";
}

function aiDetailText(scenario, place) {
  const summary = scenario.ai_summary || {};
  const parts = unique([
    summary.summary,
    summary.headline,
    ...(summary.rationale || []).slice(0, 4),
    ...(place?.fit_reasons || []).slice(0, 2),
    ...(summary.cautions || []).slice(0, 3).map((item) => `주의: ${item}`),
    ...(summary.next_checks || []).slice(0, 3).map((item) => `확인: ${item}`)
  ]);
  if (parts.length) {
    return cleanDisplayText(parts.join(" "), 220);
  }
  return "선택한 장소는 현재 조건과 접근성 기준을 함께 반영해 추천되었습니다. 현장 상황은 방문 전 다시 확인해 주세요.";
}

function aiDetailSections(scenario, place) {
  const summary = scenario.ai_summary || {};
  const headline = cleanDisplayText(
    summary.headline || summary.summary || "선택한 장소는 현재 조건과 접근성 기준을 함께 반영해 추천되었습니다.",
    AI_HEADLINE_MAX_LENGTH
  );
  const reasons = cleanDisplayList([
    ...(summary.rationale || []),
    ...(place?.fit_reasons || [])
  ]);
  const cautions = cleanDisplayList([
    ...(summary.cautions || []),
    ...(place?.deduction_reasons || []),
    ...(place?.safety_notes || [])
  ], 2);
  const nextChecks = cleanDisplayList([
    ...(summary.next_checks || []),
    ...(place?.check_before_visit || [])
  ]);

  return {
    headline,
    reasons,
    cautions,
    nextChecks,
    fallback: aiDetailText(scenario, place)
  };
}

function visitCheckItems(place, routeItem) {
  const checks = [
    routeItem.stay_tip,
    ...(place?.check_before_visit || []),
    ...(place?.verification?.missing_fields || []).map((field) => `${accessibilityFieldLabels[field] || field} 현장 확인`)
  ];
  return unique(checks).slice(0, 4).map((text) => ({
    text,
    status: /혼잡|운영|현장|확인|대기|성수기/.test(text) ? "확인" : "양호"
  }));
}

function renderServiceStatus() {
  const status = state.apiState.status;
  const statusPill = document.getElementById("serviceStatusPill");
  const serviceStatus = document.getElementById("serviceStatus");
  if (statusPill) {
    statusPill.textContent = apiStatusPillText();
    statusPill.dataset.status = status;
  }
  document.querySelector(".app-shell")?.setAttribute("data-api-status", status);
  if (!serviceStatus) {
    return;
  }

  const canRetry = state.apiState.canRetry && shouldRequestRuntimeApi();
  const description = status === "success"
    ? "선택한 조건에 맞춰 추천 코스와 상세 근거를 갱신했습니다."
    : status === "loading"
      ? "선택한 조건에 맞춰 접근성 점수를 다시 계산하고 있습니다."
      : status === "error"
        ? "현재는 기본 추천을 표시하고 있습니다. 잠시 후 다시 시도할 수 있습니다."
        : "여행 조건을 선택하면 접근성 기준에 맞춰 추천을 다시 계산합니다.";

  serviceStatus.innerHTML = `
    <div class="service-status-card ${escapeHtml(status)}">
      <div>
        <strong>${escapeHtml(apiStatusTitle())}</strong>
        <p>${escapeHtml(description)}</p>
        <small>${escapeHtml([state.apiState.message, validationSummaryText()].filter(Boolean).join(" · "))}</small>
      </div>
      ${canRetry ? '<button class="retry-button" type="button" data-retry-recommendation>재시도</button>' : ""}
    </div>
  `;
}

function renderOperationsGate() {}

function ensureCenterMap() {
  const mapElement = document.getElementById("liveMap");
  if (!mapElement || !window.L) {
    return null;
  }
  if (!centerMap) {
    centerMap = L.map(mapElement, {
      zoomControl: false,
      scrollWheelZoom: true,
      attributionControl: true,
      zoomSnap: 0.25,
      zoomDelta: 0.5
    });
    L.control.zoom({ position: "topleft" }).addTo(centerMap);
    centerLayerGroup = L.layerGroup().addTo(centerMap);
    centerMap.on("zoom move", syncMapHitBounds);
  }
  setCenterMapTileLayer(centerMapLayerMode);
  window.setTimeout(() => centerMap?.invalidateSize(), 80);
  return centerMap;
}

function setCenterMapTileLayer(mode) {
  if (!centerMap || !window.L) {
    return;
  }
  if (centerTileLayer?.__jejuLayerMode === mode) {
    updateCenterMapLayerButton();
    return;
  }
  const definition = centerMapLayerDefinitions[mode] || centerMapLayerDefinitions.soft;
  if (centerTileLayer) {
    centerMap.removeLayer(centerTileLayer);
  }
  centerTileLayer = L.tileLayer(definition.url, definition.options).addTo(centerMap);
  centerTileLayer.__jejuLayerMode = mode;
  centerMapLayerMode = mode;
  updateCenterMapLayerButton();
}

function updateCenterMapLayerButton() {
  const button = document.querySelector("[data-map-layer-toggle]");
  if (!button) {
    return;
  }
  const definition = centerMapLayerDefinitions[centerMapLayerMode] || centerMapLayerDefinitions.soft;
  button.textContent = definition.label;
}

function toggleCenterMapLayer() {
  const nextMode = centerMapLayerMode === "soft" ? "standard" : "soft";
  setCenterMapTileLayer(nextMode);
}

function liveMarkerIcon(index, active) {
  return L.divIcon({
    className: `live-marker-icon rank-${index + 1} ${active ? "active" : ""}`,
    html: `<span>${index + 1}</span>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19]
  });
}

function drawCenterMap(entries, summary, options = {}) {
  const map = ensureCenterMap();
  if (!map || !centerLayerGroup || entries.length === 0) {
    return;
  }
  centerLayerGroup.clearLayers();
  const geometry = summary.geometry?.length >= 2
    ? summary.geometry
    : entries.map((entry) => entry.location).filter(Boolean);
  const lineLatLngs = geometry.map((location) => [Number(location.latitude), Number(location.longitude)]);
  const markerLatLngs = entries.map((entry) => [Number(entry.location.latitude), Number(entry.location.longitude)]);

  if (lineLatLngs.length >= 2) {
    L.polyline(lineLatLngs, {
      color: "#ffffff",
      weight: 13,
      opacity: 0.94,
      lineCap: "round",
      lineJoin: "round"
    }).addTo(centerLayerGroup);
    L.polyline(lineLatLngs, {
      color: ROUTE_KEY_COLOR,
      weight: 6,
      opacity: 0.96,
      lineCap: "round",
      lineJoin: "round"
    }).addTo(centerLayerGroup);
  }

  entries.forEach((entry, index) => {
    const marker = L.marker([Number(entry.location.latitude), Number(entry.location.longitude)], {
      icon: liveMarkerIcon(index, entry.place.spot_id === state.mapPopupSpotId),
      keyboard: true,
      title: entry.place.name,
      bubblingMouseEvents: false
    }).addTo(centerLayerGroup);
    marker.on("click", (event) => {
      if (event.originalEvent) {
        L.DomEvent.stop(event.originalEvent);
      }
      state.selectedSpotId = entry.place.spot_id;
      state.mapPopupSpotId = entry.place.spot_id;
      state.detailCollapsed = false;
      render();
    });
  });

  if (options.fit) {
    const bounds = L.latLngBounds(markerLatLngs);
    map.fitBounds(bounds, {
      paddingTopLeft: [96, 106],
      paddingBottomRight: [96, 116],
      maxZoom: 11.25,
      animate: false
    });
  }
  window.setTimeout(() => {
    map.invalidateSize();
    syncMapHitBounds();
  }, 80);
}

function renderLiveMapStats(entries, summary, statusLabel) {
  const stats = document.getElementById("liveMapStats");
  if (!stats) {
    return;
  }
  const restPoints = entries.filter((entry) => {
    const rest = accessibilityItem(entry.place, ["rest_area"]);
    return rest.state === "yes" || rest.state === "partial";
  }).length;
  stats.innerHTML = `
    <span>
      <b>예상 소요 시간</b>
      <strong>${escapeHtml(formatDurationMinutes(summary.durationMinutes))}</strong>
    </span>
    <span>
      <b>이동 거리</b>
      <strong>${escapeHtml(formatDistanceKm(summary.distanceKm))}</strong>
    </span>
    <span>
      <b>휴식 포인트</b>
      <strong>${escapeHtml(restPoints)}곳</strong>
    </span>
  `;
}

function fitCenterMapToRoute() {
  const scenario = currentScenario();
  const entries = routeCoordinateEntries(scenario);
  if (!centerMap || entries.length < 2) {
    return;
  }
  const bounds = L.latLngBounds(entries.map((entry) => [Number(entry.location.latitude), Number(entry.location.longitude)]));
  centerMap.fitBounds(bounds, {
    paddingTopLeft: [96, 106],
    paddingBottomRight: [96, 116],
    maxZoom: 11.25,
    animate: true
  });
}

function runWhenBrowserIdle(callback, timeout = 900) {
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(callback, { timeout });
    return;
  }
  window.setTimeout(callback, Math.min(timeout, 500));
}

function mapPanelIsNearViewport(panel) {
  if (!panel) {
    return true;
  }
  const rect = panel.getBoundingClientRect();
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  return rect.top < viewportHeight + 160 && rect.bottom > -160;
}

function renderPendingCenterMap() {
  if (!pendingCenterMapScenario) {
    return;
  }
  const scenario = pendingCenterMapScenario;
  pendingCenterMapScenario = null;
  centerMapObserver?.disconnect();
  centerMapObserver = null;
  renderCenterMap(scenario);
}

function scheduleCenterMapRender(scenario) {
  pendingCenterMapScenario = scenario;
  const panel = document.getElementById("mapPanel");
  if (!panel || centerMap || mapPanelIsNearViewport(panel)) {
    renderPendingCenterMap();
    return;
  }

  const status = document.getElementById("mapSyncStatus");
  if (status) {
    status.textContent = `${scenario.title || "추천 코스"}: 지도는 화면에 가까워지면 불러옵니다.`;
  }

  if (!("IntersectionObserver" in window)) {
    window.setTimeout(renderPendingCenterMap, 700);
    return;
  }

  if (!centerMapObserver) {
    centerMapObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        renderPendingCenterMap();
      }
    }, {
      root: null,
      rootMargin: "160px 0px",
      threshold: 0.01
    });
    centerMapObserver.observe(panel);
  }
}

function renderCenterMap(scenario) {
  const entries = routeCoordinateEntries(scenario);
  const map = ensureCenterMap();
  if (!map || entries.length < 2) {
    document.getElementById("mapSyncStatus").textContent = "실제 지도를 표시하려면 두 곳 이상의 좌표가 필요합니다.";
    return;
  }
  const key = routeEntriesCacheKey(entries);
  const fallback = fallbackRouteSummary(entries);
  const shouldFit = centerMapLastFitKey !== key;
  centerMapLastFitKey = key;
  const sequence = ++centerMapRenderSequence;

  drawCenterMap(entries, fallback, { fit: shouldFit });
  renderLiveMapStats(entries, fallback, "경로 계산 중");
  document.getElementById("mapSyncStatus").textContent = `실제 지도: ${entries.length}개 좌표 연결, ${formatDistanceKm(fallback.distanceKm)}, ${formatDurationMinutes(fallback.durationMinutes)}`;

  runWhenBrowserIdle(() => {
    cachedRouteSummaryWithRoadGeometry(entries).then((summary) => {
      if (sequence !== centerMapRenderSequence) {
        return;
      }
      const statusLabel = summary.provider === "coordinate_fallback" ? "좌표 기반" : "도로 경로";
      drawCenterMap(entries, summary, { fit: false });
      renderLiveMapStats(entries, summary, statusLabel);
      document.getElementById("mapSyncStatus").textContent = `실제 지도: ${statusLabel}, ${formatDistanceKm(summary.distanceKm)}, ${formatDurationMinutes(summary.durationMinutes)}`;
    });
  });
}

function syncLiveMapPopup() {
  const frame = document.querySelector(".map-frame");
  const mapElement = document.getElementById("liveMap");
  if (!frame || !mapElement || !centerMap) {
    return;
  }
  const mobileMapList = window.matchMedia("(max-width: 560px)").matches;
  if (mobileMapList) {
    return;
  }
  const frameWidth = frame.clientWidth;
  const frameHeight = frame.clientHeight;
  const frameRect = frame.getBoundingClientRect();
  const placedRects = [".live-map-header", ".live-map-stats", ".leaflet-control-zoom"]
    .map((selector) => frame.querySelector(selector))
    .filter(Boolean)
    .map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        x: rect.left - frameRect.left,
        y: rect.top - frameRect.top,
        width: rect.width,
        height: rect.height
      };
    });

  document.querySelectorAll(".map-popup-card").forEach((button, index) => {
    const location = locationFromDataset(button.dataset);
    if (!location) {
      return;
    }
    const point = centerMap.latLngToContainerPoint([Number(location.latitude), Number(location.longitude)]);
    positionLocatedMapCard(button, { x: point.x, y: point.y }, frameWidth, frameHeight, placedRects, Number(button.dataset.mapBoundIndex || index));
  });
}

function syncMapHitBounds() {
  if (document.getElementById("liveMap")) {
    syncLiveMapPopup();
    return;
  }

  const frame = document.querySelector(".map-frame");
  const art = document.querySelector(".map-art");
  if (!frame || !art || !art.naturalWidth || !art.naturalHeight) {
    return;
  }

  const frameWidth = frame.clientWidth;
  const frameHeight = frame.clientHeight;
  const mobileMapList = window.matchMedia("(max-width: 560px)").matches;
  const objectFit = window.getComputedStyle(art).objectFit;
  const imageMetrics = mapImageMetrics(art, frameWidth, frameHeight, objectFit);
  const placedRects = mapReservedBounds.map((bound) => imageBoundToFrameRect(bound, imageMetrics));
  const titleLayer = frame.querySelector(".map-title-layer");
  if (titleLayer && window.getComputedStyle(titleLayer).display !== "none") {
    const frameRect = frame.getBoundingClientRect();
    const titleRect = titleLayer.getBoundingClientRect();
    placedRects.push({
      x: titleRect.left - frameRect.left,
      y: titleRect.top - frameRect.top,
      width: titleRect.width,
      height: titleRect.height
    });
  }

  const routePoints = [];
  document.querySelectorAll(".map-location-pin").forEach((pin) => {
    const location = locationFromDataset(pin.dataset);
    const projected = projectMapCoordinate(location, imageMetrics);
    if (!projected) {
      pin.hidden = true;
      return;
    }
    pin.hidden = false;
    pin.style.left = `${projected.x}px`;
    pin.style.top = `${projected.y}px`;
    routePoints.push(projected);
  });
  renderMapRouteLayer(routePoints, frameWidth, frameHeight);

  document.querySelectorAll(".map-place-card").forEach((button, index) => {
    const isListCard = button.classList.contains("map-list-card");
    const isPopupCard = button.classList.contains("map-popup-card");
    if ((!mobileMapList && isListCard) || (mobileMapList && isPopupCard)) {
      return;
    }
    const location = locationFromDataset(button.dataset);
    const projected = projectMapCoordinate(location, imageMetrics);
    if (projected) {
      positionLocatedMapCard(button, projected, frameWidth, frameHeight, placedRects, Number(button.dataset.mapBoundIndex || index));
      return;
    }

    const bound = mapCardBounds[Number(button.dataset.mapBoundIndex)] || mapCardBounds[0];
    button.classList.remove("located");
    button.style.transform = "none";
    button.style.left = `${imageMetrics.offsetX + bound.x * imageMetrics.scaleX}px`;
    button.style.top = `${imageMetrics.offsetY + bound.y * imageMetrics.scaleY}px`;
    button.style.width = `${bound.width * imageMetrics.scaleX}px`;
    button.style.height = `${bound.height * imageMetrics.scaleY}px`;
  });
}

function mapImageMetrics(art, frameWidth, frameHeight, objectFit) {
  if (objectFit === "fill") {
    return {
      offsetX: 0,
      offsetY: 0,
      renderedWidth: frameWidth,
      renderedHeight: frameHeight,
      scaleX: frameWidth / art.naturalWidth,
      scaleY: frameHeight / art.naturalHeight
    };
  }

  const scale = objectFit === "contain"
    ? Math.min(frameWidth / art.naturalWidth, frameHeight / art.naturalHeight)
    : Math.max(frameWidth / art.naturalWidth, frameHeight / art.naturalHeight);
  const renderedWidth = art.naturalWidth * scale;
  const renderedHeight = art.naturalHeight * scale;
  return {
    offsetX: (frameWidth - renderedWidth) / 2,
    offsetY: (frameHeight - renderedHeight) / 2,
    renderedWidth,
    renderedHeight,
    scaleX: scale,
    scaleY: scale
  };
}

function renderMapRouteLayer(points, frameWidth, frameHeight) {
  const layer = document.getElementById("mapRouteLayer");
  if (!layer) {
    return;
  }
  layer.setAttribute("viewBox", `0 0 ${frameWidth} ${frameHeight}`);
  layer.setAttribute("width", String(frameWidth));
  layer.setAttribute("height", String(frameHeight));
  if (points.length < 2) {
    layer.innerHTML = "";
    return;
  }

  const path = routePathData(points);
  const nodes = points.map((point, index) =>
    `<circle class="map-route-node rank-${index + 1}" cx="${roundSvg(point.x)}" cy="${roundSvg(point.y)}" r="5"></circle>`
  ).join("");
  layer.innerHTML = `
    <defs>
      <marker id="mapRouteArrow" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M2 2 L10 6 L2 10 Z" fill="${ROUTE_KEY_COLOR}"></path>
      </marker>
    </defs>
    <path class="map-route-path-shadow" d="${path}"></path>
    <path class="map-route-path" d="${path}" marker-end="url(#mapRouteArrow)"></path>
    <circle class="map-route-traveler" r="5">
      <animateMotion path="${path}" dur="7.5s" repeatCount="indefinite" rotate="auto"></animateMotion>
    </circle>
    ${nodes}
  `;
}

function routePathData(points) {
  const [first, ...rest] = points;
  return `M ${roundSvg(first.x)} ${roundSvg(first.y)} ${rest.map((point) => `L ${roundSvg(point.x)} ${roundSvg(point.y)}`).join(" ")}`;
}

function roundSvg(value) {
  return Number(value).toFixed(1);
}

function routeDistanceKm(entries) {
  return entries.slice(1).reduce((total, entry, index) => {
    const previous = entries[index];
    return total + haversineKm(previous.location, entry.location);
  }, 0);
}

function haversineKm(from, to) {
  if (!from || !to) {
    return 0;
  }
  const earthRadiusKm = 6371;
  const deltaLat = toRadians(Number(to.latitude) - Number(from.latitude));
  const deltaLng = toRadians(Number(to.longitude) - Number(from.longitude));
  const fromLat = toRadians(Number(from.latitude));
  const toLat = toRadians(Number(to.latitude));
  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(fromLat) * Math.cos(toLat) * Math.sin(deltaLng / 2) ** 2;
  return earthRadiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function toRadians(value) {
  return value * Math.PI / 180;
}

function formatDistanceKm(km) {
  if (!Number.isFinite(km) || km <= 0) {
    return "거리 계산 중";
  }
  return `${km.toFixed(km >= 10 ? 1 : 2)}km`;
}

function formatDurationMinutes(minutes) {
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return "시간 계산 중";
  }
  const rounded = Math.max(1, Math.round(minutes));
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  if (hours <= 0) {
    return `약 ${rest}분`;
  }
  if (rest === 0) {
    return `약 ${hours}시간`;
  }
  return `약 ${hours}시간 ${rest}분`;
}

function fallbackRouteSummary(entries) {
  const baseKm = routeDistanceKm(entries);
  const estimatedRoadKm = baseKm * 1.28;
  return {
    provider: "coordinate_fallback",
    providerLabel: "좌표 기반 경로",
    distanceKm: estimatedRoadKm,
    durationMinutes: estimatedRoadKm / ROUTE_SPEED_FALLBACK_KMH * 60,
    geometry: entries.map((entry) => entry.location).filter(Boolean)
  };
}

async function routeSummaryWithRoadGeometry(entries) {
  const fallback = fallbackRouteSummary(entries);
  if (entries.length < 2) {
    return fallback;
  }
  const proxied = await fetchProxiedRoute(entries).catch(() => null);
  if (proxied) {
    return proxied;
  }
  const direct = await fetchOsrmRoute(entries).catch(() => null);
  return direct || fallback;
}

function routeEntriesCacheKey(entries) {
  return entries
    .map((entry) => `${entry.place.spot_id}:${Number(entry.location.latitude).toFixed(6)},${Number(entry.location.longitude).toFixed(6)}`)
    .join("|");
}

async function cachedRouteSummaryWithRoadGeometry(entries) {
  const key = routeEntriesCacheKey(entries);
  if (!routeSummaryCache.has(key)) {
    routeSummaryCache.set(key, routeSummaryWithRoadGeometry(entries));
  }
  return routeSummaryCache.get(key);
}

async function fetchProxiedRoute(entries) {
  if (window.location.protocol === "file:") {
    return null;
  }
  const proxyEnabled = await routeProxyEnabled();
  if (!proxyEnabled) {
    return null;
  }
  const response = await fetch("api/routes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ points: routeRequestPoints(entries), mode: "driving" })
  });
  if (!response.ok) {
    return null;
  }
  const payload = await response.json();
  return routeSummaryFromProviderPayload(payload, "경로 계산");
}

async function routeProxyEnabled() {
  if (!shouldRequestRouteProxy()) {
    return false;
  }
  if (!routeProxySupportPromise) {
    routeProxySupportPromise = fetch("api/health", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => payload?.features?.route_proxy === true)
      .catch(() => false);
  }
  return routeProxySupportPromise;
}

async function fetchOsrmRoute(entries) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ROUTE_PROVIDER_TIMEOUT_MS);
  try {
    const coordinates = entries
      .map((entry) => `${Number(entry.location.longitude).toFixed(7)},${Number(entry.location.latitude).toFixed(7)}`)
      .join(";");
    const url = `https://router.project-osrm.org/route/v1/driving/${coordinates}?overview=full&geometries=geojson&steps=false`;
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return routeSummaryFromProviderPayload(payload, "도로 경로 반영");
  } finally {
    window.clearTimeout(timer);
  }
}

function routeRequestPoints(entries) {
  return entries.map((entry) => ({
    name: entry.place.name,
    spot_id: entry.place.spot_id,
    latitude: Number(entry.location.latitude),
    longitude: Number(entry.location.longitude)
  }));
}

function routeSummaryFromProviderPayload(payload, providerLabel) {
  const route = payload.routes?.[0] || payload.route || payload;
  const coordinates = route.geometry?.coordinates || payload.geometry?.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2) {
    return null;
  }
  const distanceMeters = Number(route.distance ?? payload.distance_meters);
  const durationSeconds = Number(route.duration ?? payload.duration_seconds);
  return {
    provider: payload.provider || "road_route",
    providerLabel,
    distanceKm: Number.isFinite(distanceMeters) ? distanceMeters / 1000 : null,
    durationMinutes: Number.isFinite(durationSeconds) ? durationSeconds / 60 : null,
    geometry: coordinates.map((coordinate) => ({
      latitude: Number(coordinate[1]),
      longitude: Number(coordinate[0])
    })).filter(validLocation)
  };
}

function imageBoundToFrameRect(bound, imageMetrics) {
  return {
    x: imageMetrics.offsetX + bound.x * imageMetrics.scaleX,
    y: imageMetrics.offsetY + bound.y * imageMetrics.scaleY,
    width: bound.width * imageMetrics.scaleX,
    height: bound.height * imageMetrics.scaleY
  };
}

function locationFromDataset(dataset) {
  const latitude = Number(dataset.latitude);
  const longitude = Number(dataset.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }
  return { latitude, longitude };
}

function projectMapCoordinate(location, imageMetrics) {
  if (!location) {
    return null;
  }
  const xRatio = (location.longitude - jejuMapProjection.west) / (jejuMapProjection.east - jejuMapProjection.west);
  const yRatio = (jejuMapProjection.north - location.latitude) / (jejuMapProjection.north - jejuMapProjection.south);
  if (!Number.isFinite(xRatio) || !Number.isFinite(yRatio)) {
    return null;
  }
  const content = jejuMapProjection.content;
  const xPercent = content.left + clamp(xRatio, 0, 1) * content.width;
  const yPercent = content.top + clamp(yRatio, 0, 1) * content.height;
  return {
    x: imageMetrics.offsetX + imageMetrics.renderedWidth * (xPercent / 100),
    y: imageMetrics.offsetY + imageMetrics.renderedHeight * (yPercent / 100)
  };
}

function positionLocatedMapCard(button, anchor, frameWidth, frameHeight, placedRects, index) {
  button.classList.add("located");
  const targetWidth = button.classList.contains("map-popup-card")
    ? Math.min(500, Math.max(420, frameWidth - 24))
    : Math.min(272, Math.max(220, frameWidth - 24));
  button.style.width = `${targetWidth}px`;
  button.style.height = "auto";
  button.style.transform = "none";

  const width = button.offsetWidth || targetWidth;
  const height = button.offsetHeight || (button.classList.contains("map-popup-card") ? 208 : 128);
  const xLanes = uniqueNumbers([
    anchor.x - width / 2,
    anchor.x + 18,
    anchor.x - width - 18,
    frameWidth - width - 12,
    12,
    anchor.x - width / 2 + (index % 2 ? 42 : -42)
  ]);
  const yPreferences = uniqueNumbers([
    anchor.y - height - 18,
    anchor.y + 18,
    anchor.y - height / 2,
    12,
    frameHeight - height - 12,
    anchor.y + 36 + index * 18
  ]);
  const candidates = yPreferences.flatMap((y) =>
    xLanes.map((x) => clampRect({ x, y }, width, height, frameWidth, frameHeight))
  );
  const rect = candidates.find((candidate) => !placedRects.some((placed) => rectsOverlap(candidate, placed))) ||
    findOpenMapCardRect(xLanes, width, height, frameWidth, frameHeight, placedRects, anchor) ||
    candidates[candidates.length - 1];
  placedRects.push({ x: rect.x, y: rect.y, width, height });
  button.style.left = `${rect.x}px`;
  button.style.top = `${rect.y}px`;
}

function findOpenMapCardRect(xLanes, width, height, frameWidth, frameHeight, placedRects, anchor) {
  const margin = 12;
  const maxY = Math.max(margin, frameHeight - height - margin);
  let best = null;
  for (const x of xLanes) {
    for (let y = margin; y <= maxY; y += 8) {
      const rect = clampRect({ x, y }, width, height, frameWidth, frameHeight);
      if (placedRects.some((placed) => rectsOverlap(rect, placed))) {
        continue;
      }
      const distance = Math.abs(rect.x + width / 2 - anchor.x) + Math.abs(rect.y + height / 2 - anchor.y);
      if (!best || distance < best.distance) {
        best = { ...rect, distance };
      }
    }
  }
  return best;
}

function uniqueNumbers(values) {
  const result = [];
  values.forEach((value) => {
    const rounded = Math.round(value);
    if (Number.isFinite(rounded) && !result.includes(rounded)) {
      result.push(rounded);
    }
  });
  return result;
}

function clampRect(candidate, width, height, frameWidth, frameHeight) {
  const margin = 12;
  return {
    x: clamp(candidate.x, margin, Math.max(margin, frameWidth - width - margin)),
    y: clamp(candidate.y, margin, Math.max(margin, frameHeight - height - margin)),
    width,
    height
  };
}

function rectsOverlap(a, b) {
  const gap = 6;
  return !(
    a.x + a.width + gap <= b.x ||
    b.x + b.width + gap <= a.x ||
    a.y + a.height + gap <= b.y ||
    b.y + b.height + gap <= a.y
  );
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function stateText(value) {
  if (value === "yes") {
    return "좋음";
  }
  if (value === "no") {
    return "낮음";
  }
  if (value === "partial" || value === "needs_check") {
    return "보통";
  }
  return displayLabel(value);
}

function mapStateText(value) {
  if (value === "yes") {
    return "좋음";
  }
  if (value === "no") {
    return "낮음";
  }
  if (value === "partial" || value === "needs_check" || value === "unknown" || !value) {
    return "확인";
  }
  if (value === "very_low" || value === "low") {
    return "낮음";
  }
  if (value === "medium") {
    return "보통";
  }
  if (value === "high") {
    return "높음";
  }
  return displayLabel(value);
}

function mapMetricTone(value) {
  if (value === "yes" || value === "very_low" || value === "low") {
    return "good";
  }
  if (value === "no" || value === "high") {
    return "risk";
  }
  return "check";
}

function mapPopupMetric(label, value) {
  return `
    <span class="map-popup-metric ${mapMetricTone(value)}">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(mapStateText(value))}</b>
    </span>
  `;
}

function scoreBreakdown(place) {
  const raw = place?.score_breakdown || place?.score?.breakdown || {};
  return Object.entries(scoreLabels).map(([key, label]) => {
    const item = raw[key] || {};
    const score = Number(item.score);
    const max = Number(item.max);
    const fallbackMax = key === "facility_fit" ? 20 : key === "theme_fit" || key === "safety_clarity" ? 15 : 25;
    return {
      label,
      score: Number.isFinite(score) ? score : Math.max(1, fallbackMax - 2),
      max: Number.isFinite(max) ? max : fallbackMax
    };
  });
}

function scenarioCardsMarkup() {
  return scenarioCards.map((card) => `
    <button class="scenario-tile ${card.tone} ${card.id === state.scenarioId ? "active" : ""}" type="button" data-scenario-id="${escapeHtml(card.id)}">
      <span>${escapeHtml(card.icon)}</span>
      <strong>${escapeHtml(card.title)}</strong>
      <small>${escapeHtml(card.body)}</small>
    </button>
  `).join("");
}

function renderScenarioCards() {
  ["scenarioList", "modalScenarioList"].forEach((id) => {
    const container = document.getElementById(id);
    if (container) {
      container.innerHTML = scenarioCardsMarkup();
    }
  });
}

function profileOptionsMarkup() {
  const profile = normalizeProfile(state.profile);
  return optionItems.map((option) => {
    const selected = hasProfileValue(profile, option.key, [option.value]);
    return `
      <button class="option-chip ${selected ? "active" : ""}" type="button" data-profile-key="${escapeHtml(option.key)}" data-profile-value="${escapeHtml(option.value)}">
        ${escapeHtml(option.label)}
      </button>
    `;
  }).join("");
}

function renderProfileOptions() {
  ["modalProfileForm"].forEach((id) => {
    const container = document.getElementById(id);
    if (container) {
      container.innerHTML = profileOptionsMarkup();
    }
  });
}

function renderOfficialCourses(scenario) {
  const container = document.getElementById("officialCourseList");
  const meta = document.getElementById("officialCourseMeta");
  if (!container) {
    return;
  }

  const courses = officialCoursesForScenario(scenario).slice(0, 2);
  const allCourses = state.data?.official_courses || [];
  const promotedVisible = courses.reduce(
    (total, course) => total + (course.stops || []).filter((stop) => stop.promoted_candidate).length,
    0
  );
  if (meta) {
    meta.textContent = `${allCourses.length}개 코스 · 후보 ${promotedVisible}개`;
  }
  if (!courses.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = courses.map((course) => {
    const duration = course.total_travel_minutes ? `${course.total_travel_minutes}분` : "시간 확인";
    const stops = (course.stops || []).slice(0, 4);
    return `
      <a class="official-course-item" href="tourism-courses.html?course=${encodeURIComponent(course.id)}" aria-label="${escapeHtml(course.title)} 관광공사 추천 코스 보기">
        <div class="official-course-head">
          <strong title="${escapeHtml(course.title)}">${escapeHtml(course.title)}</strong>
          <span>${escapeHtml(duration)}</span>
          <i class="bi bi-chevron-right official-course-arrow" aria-hidden="true"></i>
        </div>
        <div class="official-stop-list">
          ${stops.map((stop) => {
            const category = categoryLabels[stop.category] || "장소";
            const status = displayLabel(stop.verification_status || "needs_check");
            const candidate = stop.promoted_candidate ? " · 후보" : "";
            return `
              <div class="official-stop ${stop.promoted_candidate ? "candidate" : ""} ${escapeHtml(stop.verification_status || "needs_check")}">
                <i>${escapeHtml(stop.order || "")}</i>
                <b title="${escapeHtml(stop.name)}">${escapeHtml(stop.name)}</b>
                <small>${escapeHtml(category)} · ${escapeHtml(status)}${escapeHtml(candidate)}</small>
              </div>
            `;
          }).join("")}
        </div>
      </a>
    `;
  }).join("");
}

function renderNavTabs() {
  document.querySelectorAll("[data-nav-target]").forEach((link) => {
    link.classList.toggle("active", link.dataset.navTarget === state.activeNav);
  });
}

function renderAiNote(scenario) {
  const title = scenario.recommendation?.course?.title || scenario.title || "추천 코스";
  const rawScore = Number(scenario.recommendation?.score?.total);
  const score = Number.isFinite(rawScore) ? Math.round(rawScore) : "-";
  const matchNote = document.getElementById("matchNote");
  if (matchNote) {
    matchNote.innerHTML = `
      <span class="match-score">
        <small>추천 일치도</small>
        <strong>${escapeHtml(score)}<em>/100</em></strong>
      </span>
      <span class="match-course">
        <b title="${escapeHtml(title)}">${escapeHtml(title)}</b>
        <small>${escapeHtml(state.apiStatus)}</small>
      </span>
    `;
  }
  document.getElementById("safetyNotice").textContent = state.data.safety_notice || "";
}

function renderMapHits(scenario) {
  const route = selectedRoute(scenario).slice(0, 4);
  const scoreTotal = scenario.recommendation?.score?.total || 90;
  const mapHits = document.getElementById("mapHits");
  const names = routeNames(scenario);
  const locatedCount = route.filter((routeItem) => routePlace(scenario, routeItem).location).length;
  mapHits.dataset.currentScenario = scenario.id;
  mapHits.dataset.routeSpots = route.map((item) => item.spot_id).join(",");
  mapHits.dataset.routeNames = names.join(" | ");
  document.getElementById("mapSyncStatus").textContent = `${scenario.title || "추천 코스"}: ${names.join(", ")} · 실제 좌표 ${locatedCount}/${route.length} · 실제 지도 ${locatedCount >= 2 ? "표시" : "대기"}`;
  scheduleCenterMapRender(scenario);
  const cardMarkup = route.map((routeItem, index) => {
    const place = routePlace(scenario, routeItem);
    const bound = mapCardBounds[index] || mapCardBounds[0];
    const location = place.location || null;
    const score = scoreForPlace(place, Math.max(88, scoreTotal - index * 2));
    const active = place.spot_id === state.selectedSpotId;
    const restroom = accessibilityItem(place, ["accessible_toilet", "accessible_restroom", "restroom"]);
    const parking = accessibilityItem(place, ["parking"]);
    const restArea = accessibilityItem(place, ["rest_area"]);
    const locationAttrs = location
      ? `data-latitude="${escapeHtml(location.latitude)}" data-longitude="${escapeHtml(location.longitude)}"`
      : "";
    const locationLabel = location ? "실제 위치 기반" : "위치 확인 필요";
    return `
      <button class="map-place-card map-list-card rank-${index + 1} ${location ? "located" : ""} ${active ? "active" : ""}" type="button" data-spot-id="${escapeHtml(place.spot_id)}" data-map-bound-index="${index}" ${locationAttrs} title="${escapeHtml(place.name)} 상세 보기" aria-label="${index + 1}번 추천 장소 ${escapeHtml(place.name)} 상세 보기" style="left:${(bound.x / 816) * 100}%; top:${(bound.y / 931) * 100}%; width:${(bound.width / 816) * 100}%; height:${(bound.height / 931) * 100}%;">
        <span class="map-rank">${index + 1}</span>
        <strong>${escapeHtml(place.name)}</strong>
        <em>${score}점</em>
        <i>${escapeHtml(locationLabel)}</i>
        <small>
          <b>도보 부담<br>${mapStateText(effortValue(place, "walking_level"))}</b>
          <b>화장실<br>${mapStateText(restroom.state)}</b>
          <b>주차<br>${mapStateText(parking.state)}</b>
          <b>휴식<br>${mapStateText(restArea.state)}</b>
        </small>
      </button>
    `;
  }).join("");
  const popup = renderMapPopupCard(scenario, route, scoreTotal);
  mapHits.innerHTML = popup + cardMarkup;
  window.requestAnimationFrame(syncMapHitBounds);
}

function renderMapPopupCard(scenario, route, scoreTotal) {
  const index = route.findIndex((routeItem) => routeItem.spot_id === state.mapPopupSpotId);
  if (index < 0) {
    return "";
  }
  const routeItem = route[index];
  const place = routePlace(scenario, routeItem);
  const location = place.location || null;
  const visual = visualForPlace(place);
  const score = scoreForPlace(place, Math.max(88, scoreTotal - index * 2));
  const category = categoryLabels[place.category] || "추천 장소";
  const restroom = accessibilityItem(place, ["accessible_toilet", "accessible_restroom", "restroom"]);
  const parking = accessibilityItem(place, ["parking"]);
  const slope = accessibilityItem(place, ["slope_or_stairs", "slope"]);
  const restArea = accessibilityItem(place, ["rest_area"]);
  const verificationStatus = place?.verification?.status || place?.verification_status || "needs_check";
  const bound = mapCardBounds[index] || mapCardBounds[0];
  const locationAttrs = location
    ? `data-latitude="${escapeHtml(location.latitude)}" data-longitude="${escapeHtml(location.longitude)}"`
    : "";
  return `
    <button class="map-place-card map-popup-card rank-${index + 1} ${location ? "located" : ""} active" type="button" data-spot-id="${escapeHtml(place.spot_id)}" data-map-bound-index="${index}" ${locationAttrs} title="${escapeHtml(place.name)} 상세 보기" aria-label="${index + 1}번 추천 장소 ${escapeHtml(place.name)} 상세 보기" style="left:${(bound.x / 816) * 100}%; top:${(bound.y / 931) * 100}%; width:${(bound.width / 816) * 100}%; height:${(bound.height / 931) * 100}%;">
      <span class="map-popup-media">
        <img class="map-popup-image" src="${escapeHtml(visual.src)}" alt="${escapeHtml(visual.alt)}" loading="lazy" decoding="async">
        <span class="map-rank">${index + 1}</span>
        <span class="map-popup-status ${escapeHtml(verificationStatus)}">${escapeHtml(verificationLabel(place))}</span>
      </span>
      <span class="map-popup-body">
        <span class="map-popup-head">
          <span class="map-popup-title-group">
            <strong>${escapeHtml(place.name)}</strong>
            <span class="map-popup-subtitle">${escapeHtml(category)} · ${escapeHtml(location ? "실제 위치 기반" : "위치 확인 필요")}</span>
          </span>
          <em class="map-popup-score"><b>${score}</b>점</em>
        </span>
        <span class="map-popup-metrics">
          ${mapPopupMetric("도보 부담", effortValue(place, "walking_level"))}
          ${mapPopupMetric("화장실", restroom.state)}
          ${mapPopupMetric("주차", parking.state)}
          ${mapPopupMetric("휴식", restArea.state)}
          ${mapPopupMetric("경사", slope.state)}
        </span>
        <span class="map-popup-note">현재 조건에 맞춰 이동 부담과 휴식 가능성을 우선 반영했습니다.</span>
      </span>
    </button>
  `;
}

function renderDetail(scenario) {
  const detail = document.getElementById("placeDetail");
  if (state.detailCollapsed) {
    detail.innerHTML = `
      <section class="detail-empty">
        <h2>장소를 선택해 주세요</h2>
        <p>중앙 지도 또는 추천 목록에서 장소를 선택하면 접근성 점수와 추천 근거를 다시 볼 수 있습니다.</p>
        <button class="outline-button" type="button" data-focus-map>추천 목록 보기</button>
      </section>
    `;
    return;
  }

  const place = selectedPlace(scenario);
  if (!place) {
    detail.innerHTML = `
      <section class="detail-empty">
        <h2>장소를 선택해 주세요</h2>
        <p>추천 결과가 준비되면 장소별 접근성 근거를 확인할 수 있습니다.</p>
      </section>
    `;
    return;
  }

  const route = selectedRoute(scenario);
  const index = Math.max(0, route.findIndex((item) => item.spot_id === place.spot_id));
  const routeItem = route[index] || {};
  const score = scoreForPlace(place, scenario.recommendation?.score?.total || 90);
  const grade = scoreGrade(place, score);
  const visual = visualForPlace(place);
  const checks = visitCheckItems(place, routeItem);
  const breakdown = scoreBreakdown(place);
  const restroom = accessibilityItem(place, ["accessible_toilet", "accessible_restroom", "restroom"]);
  const parking = accessibilityItem(place, ["parking"]);
  const slope = accessibilityItem(place, ["slope_or_stairs", "slope"]);
  const restArea = accessibilityItem(place, ["rest_area"]);
  const facilityCards = [
    { title: "화장실", item: restroom },
    { title: "주차", item: parking },
    { title: "경사", item: slope },
    { title: "휴식", item: restArea }
  ];
  const sources = sourceSummaryItems(place);
  const category = categoryLabels[place.category] || "접근성 장소";
  const duration = place.effort?.recommended_duration_minutes;
  const aiSections = aiDetailSections(scenario, place);
  const locationEvidence = locationEvidenceItem(place);
  const validationMarkup = renderValidationEvidence(scenario);

  detail.innerHTML = `
    <div class="detail-head">
      <div>
        <span class="detail-rank">${index + 1}</span>
        <h2>${escapeHtml(place.name)}</h2>
        <p>${escapeHtml(place.address || place.region || "제주 접근성 추천 장소")} · ${escapeHtml(category)}</p>
      </div>
      <button class="close-button" type="button" data-close-detail aria-label="선택 장소 상세 닫기">×</button>
    </div>
    <button class="detail-photo" type="button" data-open-image-modal data-image-src="${escapeHtml(visual.src)}" data-image-alt="${escapeHtml(visual.alt)}" data-image-caption="${escapeHtml(visual.caption)}" data-image-source="${escapeHtml(visual.source)}" data-image-policy="${escapeHtml(visual.policy)}">
      <img class="detail-photo-image" src="${escapeHtml(visual.src)}" alt="${escapeHtml(visual.alt)}" loading="lazy" decoding="async" data-fallback-src="${escapeHtml(visual.fallbackSrc)}" data-fallback-caption="${escapeHtml(visual.fallbackCaption)}" data-fallback-source="${escapeHtml(visual.fallbackSource)}">
      <span>${escapeHtml(visual.policy)}</span>
    </button>
    <div class="image-credit">
      <strong>${escapeHtml(visual.caption)}</strong>
      <small>${escapeHtml(visual.source)} · 접근성 확인 자료와 대표 이미지를 함께 참고합니다.</small>
    </div>
    <button class="route-cta-button" type="button" data-open-route-modal>
      <span>실제 경로 보기</span>
      <b>${escapeHtml(routeNames(scenario).join(" → "))}</b>
    </button>
    <section class="detail-score">
      <span>접근성 점수</span>
      <strong>${score}<small>/100</small></strong>
      <em>${grade} · ${escapeHtml(verificationLabel(place))}</em>
    </section>
    <section class="detail-meta">
      <span>도보 부담 <b>${escapeHtml(mapStateText(effortValue(place, "walking_level")))}</b></span>
      <span>예상 체류 <b>${duration ? `${duration}분` : "확인"}</b></span>
      <span>날씨 영향 <b>${escapeHtml(mapStateText(effortValue(place, "weather_sensitivity")))}</b></span>
    </section>
    <section class="score-basis">
      <div class="detail-section-row neutral">
        <h3>점수 근거</h3>
        <span>추천 엔진</span>
      </div>
      ${breakdown.slice(1, 5).map((item) => {
        const percent = item.max > 0 ? Math.round((item.score / item.max) * 100) : 0;
        return `
          <div class="bar-row">
            <span>${escapeHtml(item.label)}</span>
            <i><b style="width:${percent}%"></b></i>
            <strong>${item.score}/${item.max}</strong>
          </div>
        `;
      }).join("")}
    </section>
    <section class="evidence-grid">
      ${facilityCards.map(({ title, item }) => `
        <div title="${escapeHtml(item.note || "세부 메모 없음")}">
          <b>${escapeHtml(title)}</b>
          <span>${escapeHtml(stateText(item.state))}</span>
          <small>${escapeHtml(item.state_label || stateText(item.state))}</small>
        </div>
      `).join("")}
    </section>
    <section class="visit-check">
      <div class="detail-section-row">
        <h3>방문 전 확인</h3>
        <span>${escapeHtml(verificationLabel(place))}</span>
      </div>
      <ul>
        ${checks.map((check) => `<li>${escapeHtml(check.text)}<span>${escapeHtml(check.status)}</span></li>`).join("")}
      </ul>
    </section>
    <section class="gpt-box">
      <div class="detail-section-row ai">
        <h3>${escapeHtml(AI_DISPLAY_NAME)} 설명</h3>
        <span>${escapeHtml(aiStatusBadge(scenario.ai_summary))}</span>
      </div>
      <p>${escapeHtml(aiSections.headline)}</p>
      <div class="ai-reason-list">
        ${aiSections.reasons.length ? `
          <div>
            <strong>추천 근거</strong>
            <ul>${aiSections.reasons.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </div>
        ` : ""}
        ${aiSections.cautions.length ? `
          <div>
            <strong>주의할 점</strong>
            <ul>${aiSections.cautions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </div>
        ` : ""}
        ${aiSections.nextChecks.length ? `
          <div>
            <strong>방문 전 확인</strong>
            <ul>${aiSections.nextChecks.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </div>
        ` : `<p>${escapeHtml(aiSections.fallback)}</p>`}
      </div>
    </section>
    <section class="source-box">
      <div class="detail-section-row neutral">
        <h3>정보 출처</h3>
        <span>확인 기준</span>
      </div>
      <ul>
        ${(sources.length ? sources : [{ title: "가치봄 추천 기준", status: "partial" }]).map((source) => `
          <li>
            <span>${escapeHtml(source.title || "출처명 확인 필요")}</span>
            <b>${escapeHtml(displayLabel(source.status || "partial"))}</b>
          </li>
        `).join("")}
        ${locationEvidence ? `
          <li>
            <span>${escapeHtml(locationEvidence.title)}</span>
            <b>${escapeHtml(locationEvidence.status)}</b>
          </li>
        ` : ""}
      </ul>
    </section>
    ${validationMarkup}
  `;
}

function locationEvidenceItem(place) {
  const location = place?.location;
  if (!location) {
    return null;
  }
  const coordinate = `${Number(location.latitude).toFixed(5)}, ${Number(location.longitude).toFixed(5)}`;
  const sourceTitle = location.source_title || "위치 좌표";
  return {
    title: `지도 위치 ${coordinate} · ${sourceTitle}`,
    status: location.match_method === "manual_override" ? "직접 확인" : "좌표 확인"
  };
}

function renderValidationEvidence() {
  return "";
}

function render() {
  const scenario = currentScenario();
  if (!state.detailCollapsed) {
    selectedPlace(scenario);
  }
  renderNavTabs();
  renderConceptPage(scenario);
  renderScenarioCards();
  renderProfileOptions();
  renderOfficialCourses(scenario);
  renderServiceStatus();
  renderOperationsGate();
  renderAiNote(scenario);
  renderMapHits(scenario);
  renderDetail(scenario);
}

function closeDetailPanel() {
  state.selectedSpotId = null;
  state.mapPopupSpotId = null;
  state.detailCollapsed = true;
  render();
  window.requestAnimationFrame(() => {
    document.querySelector("[data-focus-map]")?.focus();
  });
}

function closeMapPopup(options = {}) {
  if (!state.mapPopupSpotId) {
    return false;
  }
  state.mapPopupSpotId = null;
  if (options.render !== false) {
    render();
  }
  return true;
}

function isMapPopupInteractionTarget(target) {
  return Boolean(
    target?.closest?.(".map-popup-card")
    || target?.closest?.("[data-map-pin-spot-id]")
    || target?.closest?.(".live-marker-icon")
  );
}

function focusRecommendationList() {
  state.detailCollapsed = false;
  selectedPlace(currentScenario());
  render();
  window.requestAnimationFrame(() => {
    const target = document.querySelector(".map-place-card.active") || document.querySelector(".map-place-card");
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
}

function openProfileModal() {
  const modal = document.getElementById("profileModal");
  if (!modal) {
    return;
  }
  modal.hidden = false;
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => {
    modal.querySelector(".modal-close-button")?.focus();
  });
}

function closeProfileModal() {
  const modal = document.getElementById("profileModal");
  if (!modal) {
    return;
  }
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function openImageModal(trigger) {
  const modal = document.getElementById("imageModal");
  const image = document.getElementById("imageModalImage");
  if (!modal || !image) {
    return;
  }
  document.getElementById("imageModalTitle").textContent = trigger.dataset.imageAlt || "장소 이미지";
  document.getElementById("imageModalPolicy").textContent = trigger.dataset.imagePolicy || "대표 이미지";
  document.getElementById("imageModalCaption").textContent = trigger.dataset.imageCaption || "";
  document.getElementById("imageModalSource").textContent = trigger.dataset.imageSource || "";
  image.src = trigger.dataset.imageSrc || DEFAULT_PLACE_IMAGE.src;
  image.alt = trigger.dataset.imageAlt || "장소 이미지";
  modal.hidden = false;
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => {
    modal.querySelector(".modal-close-button")?.focus();
  });
}

function closeImageModal() {
  const modal = document.getElementById("imageModal");
  if (!modal) {
    return;
  }
  modal.hidden = true;
  document.getElementById("imageModalImage")?.removeAttribute("src");
  document.body.classList.remove("modal-open");
}

function openRouteModal() {
  const modal = document.getElementById("routeModal");
  if (!modal) {
    return;
  }
  state.routeModalOpen = true;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderRouteModal();
  window.requestAnimationFrame(() => {
    modal.querySelector(".modal-close-button")?.focus();
  });
}

function closeRouteModal() {
  const modal = document.getElementById("routeModal");
  if (!modal) {
    return;
  }
  state.routeModalOpen = false;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function openPromoModal() {
  const modal = document.getElementById("promoVideoModal");
  if (!modal) {
    return;
  }
  state.promoModalOpen = true;
  state.activeNav = "promo";
  modal.hidden = false;
  document.body.classList.add("modal-open");
  const video = document.getElementById("promoVideo");
  if (video) {
    video.preload = "metadata";
    video.load?.();
  }
  renderNavTabs();
  window.requestAnimationFrame(() => {
    modal.querySelector(".modal-close-button")?.focus();
  });
}

function openSiteIntro() {
  const intro = document.getElementById("siteIntro");
  const video = document.getElementById("siteIntroVideo");
  if (!intro || !video || siteIntroStarted) {
    return;
  }
  siteIntroStarted = true;
  state.siteIntroOpen = true;
  intro.hidden = false;
  document.body.classList.add("modal-open");
  document.body.classList.add("site-intro-open");
  video.currentTime = 0;
  video.muted = true;
  video.preload = "auto";
  video.play?.().catch(() => {
    intro.querySelector("[data-close-site-intro]")?.focus();
  });
}

function markSiteIntroSeen() {
  try {
    window.sessionStorage.setItem(SITE_INTRO_SEEN_KEY, "true");
  } catch (error) {
    // The intro still works when browser storage is unavailable.
  }
}

function shouldSkipSiteIntro() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("intro") === "1") {
    return false;
  }
  if (params.get("intro") === "0") {
    return true;
  }
  try {
    return window.sessionStorage.getItem(SITE_INTRO_SEEN_KEY) === "true";
  } catch (error) {
    return false;
  }
}

function bypassSiteIntro() {
  const intro = document.getElementById("siteIntro");
  const video = document.getElementById("siteIntroVideo");
  siteIntroStarted = true;
  state.siteIntroOpen = false;
  if (intro) {
    intro.hidden = true;
  }
  video?.pause();
  document.body.classList.remove("site-intro-open");
  document.body.classList.remove("modal-open");
  document.documentElement.classList.remove("skip-site-intro");
  markSiteIntroSeen();

  const url = new URL(window.location.href);
  if (url.searchParams.get("intro") === "0") {
    url.searchParams.delete("intro");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }
}

function closeSiteIntro() {
  const intro = document.getElementById("siteIntro");
  const video = document.getElementById("siteIntroVideo");
  if (!intro) {
    return false;
  }
  const wasOpen = state.siteIntroOpen || !intro.hidden;
  if (!wasOpen) {
    return false;
  }
  state.siteIntroOpen = false;
  markSiteIntroSeen();
  intro.hidden = true;
  if (video) {
    video.pause();
  }
  document.body.classList.remove("site-intro-open");
  document.body.classList.remove("modal-open");
  showThemeSelectionAfterIntro();
  return true;
}

function showThemeSelectionAfterIntro() {
  const promoModal = document.getElementById("promoVideoModal");
  const promoVideo = document.getElementById("promoVideo");
  state.promoModalOpen = false;
  if (promoModal) {
    promoModal.hidden = true;
  }
  if (promoVideo) {
    promoVideo.pause();
  }
  state.activeNav = "concepts";
  state.conceptPanelOpen = false;
  renderNavTabs();
  if (window.location.hash !== "#conceptPage") {
    window.history.replaceState(null, "", "#conceptPage");
  }
  window.requestAnimationFrame(() => {
    scrollToSelector("#conceptPage", "auto");
    syncStepViewState();
  });
}

function toggleSiteIntroSound(button) {
  const video = document.getElementById("siteIntroVideo");
  if (!video) {
    return;
  }
  video.muted = !video.muted;
  if (button) {
    button.textContent = video.muted ? "소리 켜기" : "소리 끄기";
  }
  video.play?.().catch(() => {});
}

function closePromoModal() {
  const modal = document.getElementById("promoVideoModal");
  if (!modal) {
    return;
  }
  state.promoModalOpen = false;
  modal.hidden = true;
  const video = document.getElementById("promoVideo");
  if (video) {
    video.pause();
  }
  if (state.activeNav === "promo") {
    state.activeNav = "map";
    renderNavTabs();
  }
  document.body.classList.remove("modal-open");
}

function renderRouteModal() {
  const scenario = currentScenario();
  const routeTitle = scenario.recommendation?.course?.title || scenario.title || "오늘의 동행 경로";
  const entries = routeCoordinateEntries(scenario);
  const allEntries = routeEntriesForScenario(scenario);
  document.getElementById("routeModalTitle").textContent = routeTitle;
  document.getElementById("routeModalSubtitle").textContent = `${routeNames(scenario).join(" → ")} 순서로 실제 위치를 연결합니다.`;

  if (entries.length < 2) {
    setRouteMapStatus("좌표 확인 필요", "두 곳 이상의 실제 좌표가 있어야 경로를 계산할 수 있습니다.");
    renderRouteItinerary(allEntries, fallbackRouteSummary(entries), "좌표 확인 필요");
    clearRouteMap();
    return;
  }

  const fallback = fallbackRouteSummary(entries);
  setRouteMapStatus("경로 계산 중", "실제 도로형 경로를 가져오는 중입니다.");
  renderRouteItinerary(allEntries, fallback, "계산 중");
  window.requestAnimationFrame(async () => {
    const summary = await routeSummaryWithRoadGeometry(entries);
    if (!state.routeModalOpen) {
      return;
    }
    drawRouteMap(entries, summary);
    renderRouteItinerary(allEntries, summary, summary.provider === "coordinate_fallback" ? "좌표 기반" : "도로 경로");
    setRouteMapStatus(
      summary.provider === "coordinate_fallback" ? "좌표 기반 경로" : "도로 경로 반영",
      `${formatDistanceKm(summary.distanceKm)} · ${formatDurationMinutes(summary.durationMinutes)}`
    );
  });
}

function setRouteMapStatus(badge, text) {
  const badgeElement = document.getElementById("routeMapBadge");
  const statusElement = document.getElementById("routeMapStatus");
  if (badgeElement) {
    badgeElement.textContent = badge;
  }
  if (statusElement) {
    statusElement.textContent = text;
  }
}

function renderRouteItinerary(entries, summary, statusLabel) {
  const container = document.getElementById("routeItinerary");
  if (!container) {
    return;
  }
  const locatedCount = entries.filter((entry) => entry.location).length;
  container.innerHTML = `
    <div class="route-summary-card">
      <span>${escapeHtml(statusLabel)}</span>
      <h3>추천 코스가 실제 지도 위에 연결됐습니다</h3>
      <p>장소 점수와 접근성 확인 항목을 유지한 채, 이동 순서와 좌표 근거를 한 화면에서 검토합니다.</p>
      <div class="route-stat-grid">
        <b><small>총 이동</small>${escapeHtml(formatDistanceKm(summary.distanceKm))}</b>
        <b><small>예상 시간</small>${escapeHtml(formatDurationMinutes(summary.durationMinutes))}</b>
        <b><small>좌표</small>${locatedCount}/${entries.length}곳</b>
      </div>
    </div>
    <ol class="route-step-list">
      ${entries.map((entry, index) => routeStepMarkup(entry, index)).join("")}
    </ol>
    <div class="route-service-note">
      <strong>이동 전 확인</strong>
      <p>현장 운영 시간, 날씨, 혼잡도는 방문 전에 한 번 더 확인하는 것이 좋습니다.</p>
    </div>
  `;
}

function routeStepMarkup(entry, index) {
  const place = entry.place;
  const restroom = accessibilityItem(place, ["accessible_toilet", "accessible_restroom", "restroom"]);
  const parking = accessibilityItem(place, ["parking"]);
  const slope = accessibilityItem(place, ["slope_or_stairs", "slope"]);
  const restArea = accessibilityItem(place, ["rest_area"]);
  const coordinate = entry.location
    ? `${Number(entry.location.latitude).toFixed(5)}, ${Number(entry.location.longitude).toFixed(5)}`
    : "좌표 확인 필요";
  return `
    <li class="${entry.location ? "" : "missing"}">
      <div class="route-step-rank">${index + 1}</div>
      <div class="route-step-main">
        <div class="route-step-head">
          <strong>${escapeHtml(place.name)}</strong>
          <span>${escapeHtml(entry.score)}점</span>
        </div>
        <p>${escapeHtml(place.region || place.address || "제주 접근성 추천 장소")}</p>
        <div class="route-step-tags">
          <b>화장실 ${escapeHtml(mapStateText(restroom.state))}</b>
          <b>주차 ${escapeHtml(mapStateText(parking.state))}</b>
          <b>경사 ${escapeHtml(mapStateText(slope.state))}</b>
          <b>휴식 ${escapeHtml(mapStateText(restArea.state))}</b>
        </div>
        <small>${escapeHtml(coordinate)} · ${escapeHtml(place.location?.source_title || "위치 근거 확인 중")}</small>
      </div>
    </li>
  `;
}

function clearRouteMap() {
  if (routeLayerGroup) {
    routeLayerGroup.clearLayers();
  }
}

function ensureRouteMap() {
  const mapElement = document.getElementById("routeMap");
  if (!mapElement || !window.L) {
    return null;
  }
  if (!routeMap) {
    routeMap = L.map(mapElement, {
      zoomControl: true,
      scrollWheelZoom: false,
      attributionControl: true
    });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(routeMap);
    routeLayerGroup = L.layerGroup().addTo(routeMap);
  }
  window.setTimeout(() => routeMap.invalidateSize(), 80);
  return routeMap;
}

function drawRouteMap(entries, summary) {
  const map = ensureRouteMap();
  if (!map) {
    setRouteMapStatus("지도 로딩 대기", "지도 라이브러리를 불러오지 못해 경로 목록으로 표시합니다.");
    return;
  }
  clearRouteMap();
  const geometry = summary.geometry?.length >= 2
    ? summary.geometry
    : entries.map((entry) => entry.location).filter(Boolean);
  const lineLatLngs = geometry.map((location) => [Number(location.latitude), Number(location.longitude)]);
  const markerLatLngs = entries.map((entry) => [Number(entry.location.latitude), Number(entry.location.longitude)]);

  L.polyline(lineLatLngs, {
    color: "#ffffff",
    weight: 12,
    opacity: 0.96,
    lineCap: "round",
    lineJoin: "round"
  }).addTo(routeLayerGroup);
  L.polyline(lineLatLngs, {
    color: ROUTE_KEY_COLOR,
    weight: 6,
    opacity: 0.95,
    lineCap: "round",
    lineJoin: "round"
  }).addTo(routeLayerGroup);

  entries.forEach((entry, index) => {
    const marker = L.marker([Number(entry.location.latitude), Number(entry.location.longitude)], {
      icon: L.divIcon({
        className: `route-marker-icon rank-${index + 1}`,
        html: `<span>${index + 1}</span>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
        popupAnchor: [0, -18]
      })
    }).addTo(routeLayerGroup);
    marker.bindPopup(`<strong>${escapeHtml(entry.place.name)}</strong><br>${escapeHtml(entry.score)}점 · ${escapeHtml(verificationLabel(entry.place))}`);
  });

  const bounds = L.latLngBounds(markerLatLngs);
  map.fitBounds(bounds, { padding: [44, 44], maxZoom: 12 });
  window.setTimeout(() => map.invalidateSize(), 120);
}

function applyImageFallback(image) {
  const fallbackSrc = image.dataset.fallbackSrc || DEFAULT_PLACE_IMAGE.src;
  if (image.dataset.fallbackApplied === "true" || image.src.endsWith(fallbackSrc.replace("assets/", ""))) {
    return;
  }
  image.dataset.fallbackApplied = "true";
  image.src = fallbackSrc;
  image.alt = DEFAULT_PLACE_IMAGE.caption;
  const photo = image.closest("[data-open-image-modal]");
  if (photo) {
    photo.dataset.imageSrc = fallbackSrc;
    photo.dataset.imageCaption = image.dataset.fallbackCaption || DEFAULT_PLACE_IMAGE.caption;
    photo.dataset.imageSource = image.dataset.fallbackSource || DEFAULT_PLACE_IMAGE.source;
    photo.dataset.imagePolicy = "이미지 로딩 실패";
    photo.querySelector("span").textContent = "이미지 로딩 실패";
    photo.nextElementSibling?.querySelector("strong")?.replaceChildren(document.createTextNode(photo.dataset.imageCaption));
    photo.nextElementSibling?.querySelector("small")?.replaceChildren(document.createTextNode(`${photo.dataset.imageSource} · 원본 이미지 확인 필요`));
  }
}

async function shareCurrentView(button) {
  const url = new URL(window.location.href);
  url.searchParams.delete("qa");
  const scenario = currentScenario();
  const place = state.detailCollapsed ? null : selectedPlace(scenario);
  const title = "가치봄 제주 접근성 여행 추천";
  const text = place
    ? `${place.name} 접근성 근거와 추천 코스를 확인해 보세요.`
    : "가치봄 제주 맞춤 접근성 여행 추천 화면을 확인해 보세요.";

  try {
    const preferNativeShare = window.matchMedia("(pointer: coarse)").matches && navigator.share;
    if (preferNativeShare) {
      await navigator.share({ title, text, url: url.toString() });
      setShareButtonFeedback(button, "공유 완료");
      return;
    }
    await copyTextToClipboard(url.toString());
    setShareButtonFeedback(button, "링크 복사됨");
  } catch (error) {
    setShareButtonFeedback(button, "복사 실패");
  }
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) {
    throw new Error("copy failed");
  }
}

function setShareButtonFeedback(button, text) {
  if (!button) {
    return;
  }
  const original = button.dataset.originalText || button.textContent;
  button.dataset.originalText = original;
  button.textContent = text;
  window.clearTimeout(shareFeedbackTimer);
  shareFeedbackTimer = window.setTimeout(() => {
    button.textContent = button.dataset.originalText || "공유";
  }, 1800);
}

function navTargetFromHash(hash = window.location.hash) {
  if (hash === "#recommendations" || hash === "#mapPanel") {
    return "recommend";
  }
  if (hash === "#officialCourseList") {
    return "official";
  }
  if (hash === "#promoVideoModal") {
    return "promo";
  }
  return "concepts";
}

function scrollToSelector(selector, behavior = "smooth") {
  if (!selector || !selector.startsWith("#")) {
    return;
  }
  if (selector === "#conceptPage") {
    window.scrollTo({ top: 0, behavior });
    return;
  }
  const target = targetElementFromSelector(selector);
  if (target) {
    const top = Math.max(0, window.scrollY + target.getBoundingClientRect().top - stickyTopbarOffset());
    window.scrollTo({ top, behavior });
    return;
  }
}

function targetElementFromSelector(selector) {
  try {
    return document.querySelector(selector);
  } catch (error) {
    return document.getElementById(selector.slice(1));
  }
}

function stickyTopbarOffset() {
  const topbar = document.querySelector(".topbar");
  if (!topbar) {
    return 0;
  }
  const style = window.getComputedStyle(topbar);
  if (style.position !== "sticky" && style.position !== "fixed") {
    return 0;
  }
  const rect = topbar.getBoundingClientRect();
  return Math.max(0, Math.ceil(rect.bottom + 8));
}

function updateHash(href) {
  if (!href || !href.startsWith("#") || window.location.hash === href) {
    return;
  }
  window.history.pushState(null, "", href);
}

function navigateToSection(target, href, { updateLocation = false, behavior = "smooth" } = {}) {
  state.activeNav = target || navTargetFromHash(href);
  if (state.activeNav !== "concepts") {
    state.conceptPanelOpen = false;
  }
  renderNavTabs();
  if (updateLocation) {
    updateHash(href);
  }
  window.requestAnimationFrame(() => {
    scrollToSelector(href || "#conceptPage", behavior);
    centerMap?.invalidateSize();
    syncMapHitBounds();
    syncStepViewState();
  });
}

async function selectScenarioForResult(scenarioId, { navigateToResults = false, fromModal = false } = {}) {
  if (!scenarioById(scenarioId)) {
    return;
  }
  state.scenarioId = scenarioId;
  state.runtimeScenario = null;
  state.profile = profileFromScenario(currentStaticScenario());
  state.selectedSpotId = null;
  state.mapPopupSpotId = null;
  state.detailCollapsed = false;

  if (navigateToResults) {
    navigateToSection("recommend", "#recommendations", { updateLocation: true });
  }

  if (fromModal) {
    setApiState(shouldRequestRuntimeApi() ? "idle" : "static", shouldRequestRuntimeApi() ? "적용 전 조건 편집 중" : "기본 추천 사용");
    render();
    return;
  }

  if (!navigateToResults) {
    openConceptResultPanel();
    render();
  }

  await refreshScenarioRecommendation({ renderLoading: true });
  render();
  if (!navigateToResults) {
    syncStepViewState();
  }
}

function bindEvents() {
  document.addEventListener("click", async (event) => {
    if (state.mapPopupSpotId && !isMapPopupInteractionTarget(event.target)) {
      closeMapPopup();
    }

    const navLink = event.target.closest("[data-nav-target]");
    if (navLink) {
      event.preventDefault();
      handleNavTarget(navLink.dataset.navTarget, navLink.getAttribute("href"));
      return;
    }

    const goConceptsButton = event.target.closest("[data-go-concepts]");
    if (goConceptsButton) {
      closeConceptResultPanel();
      navigateToSection("concepts", "#conceptPage", { updateLocation: true });
      return;
    }

    const shareButton = event.target.closest("[data-share-app]");
    if (shareButton) {
      await shareCurrentView(shareButton);
      return;
    }

    const openRouteButton = event.target.closest("[data-open-route-modal]");
    if (openRouteButton) {
      openRouteModal();
      return;
    }

    const mapLayerButton = event.target.closest("[data-map-layer-toggle]");
    if (mapLayerButton) {
      toggleCenterMapLayer();
      return;
    }

    const mapFitButton = event.target.closest("[data-map-fit-route]");
    if (mapFitButton) {
      fitCenterMapToRoute();
      return;
    }

    const closeRouteButton = event.target.closest("[data-close-route-modal]");
    if (closeRouteButton) {
      closeRouteModal();
      return;
    }

    const closePromoButton = event.target.closest("[data-close-promo-modal]");
    if (closePromoButton) {
      closePromoModal();
      return;
    }

    const closeIntroButton = event.target.closest("[data-close-site-intro]");
    if (closeIntroButton) {
      closeSiteIntro();
      return;
    }

    const toggleIntroSoundButton = event.target.closest("[data-toggle-intro-sound]");
    if (toggleIntroSoundButton) {
      toggleSiteIntroSound(toggleIntroSoundButton);
      return;
    }

    const openImageButton = event.target.closest("[data-open-image-modal]");
    if (openImageButton) {
      openImageModal(openImageButton);
      return;
    }

    const closeImageButton = event.target.closest("[data-close-image-modal]");
    if (closeImageButton) {
      closeImageModal();
      return;
    }

    const openModalButton = event.target.closest("[data-open-profile-modal]");
    if (openModalButton) {
      openProfileModal();
      return;
    }

    const closeModalButton = event.target.closest("[data-close-profile-modal]");
    if (closeModalButton) {
      closeProfileModal();
      return;
    }

    const applyModalButton = event.target.closest("[data-apply-profile-modal]");
    if (applyModalButton) {
      closeProfileModal();
      await refreshRuntimeRecommendation({ renderLoading: true });
      render();
      return;
    }

    const retryButton = event.target.closest("[data-retry-recommendation]");
    if (retryButton) {
      await refreshRuntimeRecommendation({ renderLoading: true });
      render();
      return;
    }

    const mapPinButton = event.target.closest("[data-map-pin-spot-id]");
    if (mapPinButton) {
      state.selectedSpotId = mapPinButton.dataset.mapPinSpotId;
      state.mapPopupSpotId = mapPinButton.dataset.mapPinSpotId;
      state.detailCollapsed = false;
      render();
      return;
    }

    const conceptButton = event.target.closest("[data-concept-id]");
    if (conceptButton) {
      await selectScenarioForResult(conceptButton.dataset.conceptId, { navigateToResults: false });
      return;
    }

    const viewSelectedConceptButton = event.target.closest("[data-view-selected-concept]");
    if (viewSelectedConceptButton) {
      closeConceptResultPanel();
      navigateToSection("recommend", "#recommendations", { updateLocation: true });
      return;
    }

    const scenarioButton = event.target.closest("[data-scenario-id]");
    if (scenarioButton) {
      if (scenarioButton.closest("#profileModal")) {
        await selectScenarioForResult(scenarioButton.dataset.scenarioId, { fromModal: true });
        return;
      }
      await selectScenarioForResult(scenarioButton.dataset.scenarioId);
      return;
    }

    const profileButton = event.target.closest("[data-profile-key]");
    if (profileButton) {
      toggleProfileValue(profileButton.dataset.profileKey, profileButton.dataset.profileValue);
      if (profileButton.closest("#profileModal")) {
        const matchedScenario = matchedScenarioFromProfile(state.profile);
        state.scenarioId = matchedScenario.id;
        state.runtimeScenario = null;
        state.selectedSpotId = null;
        state.mapPopupSpotId = null;
        state.detailCollapsed = false;
        setApiState(shouldRequestRuntimeApi() ? "idle" : "static", shouldRequestRuntimeApi() ? "적용 전 조건 편집 중" : "기본 추천 사용");
        render();
        return;
      }
      await refreshRuntimeRecommendation({ renderLoading: true });
      render();
      return;
    }

    const placeButton = event.target.closest("[data-spot-id]");
    if (placeButton) {
      state.selectedSpotId = placeButton.dataset.spotId;
      if (placeButton.classList.contains("map-popup-card")) {
        state.mapPopupSpotId = placeButton.dataset.spotId;
      }
      state.detailCollapsed = false;
      render();
      return;
    }

    const closeDetailButton = event.target.closest("[data-close-detail]");
    if (closeDetailButton) {
      closeDetailPanel();
      return;
    }

    const focusMapButton = event.target.closest("[data-focus-map]");
    if (focusMapButton) {
      focusRecommendationList();
      return;
    }

    if (
      state.mapPopupSpotId
      && !event.target.closest(".map-popup-card")
      && !event.target.closest("[data-map-pin-spot-id]")
    ) {
      closeMapPopup();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSiteIntro();
      closeImageModal();
      closeProfileModal();
      closeRouteModal();
      closePromoModal();
      closeMapPopup();
    }
  });

  document.addEventListener("error", (event) => {
    const target = event.target;
    if (target instanceof HTMLImageElement && target.dataset.fallbackSrc) {
      applyImageFallback(target);
    }
  }, true);

  window.addEventListener("resize", () => {
    centerMap?.invalidateSize();
    syncMapHitBounds();
    syncStepViewState();
  });

  window.addEventListener("scroll", () => {
    syncStepViewState();
  }, { passive: true });

  window.addEventListener("wheel", (event) => {
    if (state.conceptPanelOpen && window.scrollY < 24 && event.deltaY > 8) {
      closeConceptResultPanel();
      navigateToSection("recommend", "#recommendations", { updateLocation: true });
    }
  }, { passive: true });

  window.addEventListener("touchmove", () => {
    syncStepViewState();
  }, { passive: true });

  window.addEventListener("hashchange", () => {
    const target = navTargetFromHash();
    if (target === "promo") {
      openPromoModal();
      return;
    }
    state.activeNav = target;
    if (target !== "concepts") {
      state.conceptPanelOpen = false;
    }
    renderNavTabs();
    scrollToSelector(window.location.hash || "#conceptPage");
    window.requestAnimationFrame(syncStepViewState);
  });

  document.getElementById("siteIntroVideo")?.addEventListener("ended", closeSiteIntro);
}

function handleNavTarget(target, href) {
  state.activeNav = target || "concepts";
  if (target === "promo") {
    updateHash(href);
    openPromoModal();
    return;
  }

  if (target === "evidence") {
    state.detailCollapsed = false;
    selectedPlace(currentScenario());
    render();
    window.requestAnimationFrame(() => {
      const evidence = document.getElementById("validationEvidence");
      evidence?.scrollIntoView({ block: "start", behavior: "smooth" });
      evidence?.focus({ preventScroll: true });
    });
    return;
  }

  const selector = href && href.startsWith("#") ? href : "#conceptPage";
  navigateToSection(target, selector, { updateLocation: true });
}

async function init() {
  try {
    const seed = await loadData();
    state.data = seed;
    state.validationReport = null;
    state.operationsReadiness = null;
    state.launchActionPlan = null;
    state.scenarioId = state.data.scenarios[0]?.id || null;
    state.activeNav = navTargetFromHash();
    state.profile = profileFromScenario(currentStaticScenario());
    setApiState("idle", "추천 준비 완료");
    render();
    bindEvents();
    syncStepViewState();
    const skipIntro = shouldSkipSiteIntro();
    if (skipIntro) {
      bypassSiteIntro();
    } else {
      window.requestAnimationFrame(openSiteIntro);
    }
    window.requestAnimationFrame(() => {
      if (skipIntro && state.activeNav === "promo") {
        openPromoModal();
        return;
      }
      if (window.location.hash) {
        scrollToSelector(window.location.hash, "auto");
      }
    });
  } catch (error) {
    document.querySelector(".journey-layout").innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
  }
}

init();
