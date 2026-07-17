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
  savedRoutes: [],
  savedRoutesOpen: false,
  aiExplanationModalOpen: false,
  sharedRoutePreview: null,
  savedRouteMessage: "",
  pendingSavedRouteDeleteId: null,
  profile: null,
  profileModalDraft: null,
  ragQuery: "",
  conceptFocus: null,
  runtimeScenario: null,
  apiStatus: "추천 준비 완료",
  apiState: {
    status: "idle",
    message: "추천 기준을 준비하고 있습니다.",
    canRetry: false
  },
  aiExplanation: {
    status: "idle",
    message: "공식 근거를 바탕으로 한 AI 설명은 아직 생성하지 않았습니다.",
    contextKey: ""
  }
};

const RECOMMENDATION_MODEL = "gpt-5-mini";
const RECOMMENDATION_LIMIT = 4;
const AI_DISPLAY_NAME = "가치봄 AI";
const AI_HEADLINE_MAX_LENGTH = 90;
const AI_LIST_ITEM_MAX_LENGTH = 86;
const AI_EXPLANATION_TIMEOUT_MS = 40000;
const AI_EXPLANATION_CACHE_LIMIT = 8;
const ROUTE_PROVIDER_TIMEOUT_MS = 7000;
const ROUTE_SPEED_FALLBACK_KMH = 32;
const ROUTE_SUMMARY_CACHE_LIMIT = 24;
const ROUTE_KEY_COLOR = "#126fb5";
const SITE_INTRO_SEEN_KEY = "gachibom:site-intro-seen";
const SAVED_TRIPS = window.GachibomSavedTrips || null;
const shareFeedbackTimers = new WeakMap();
let savedRouteDeleteTimer = null;
let savedRoutesReturnFocus = null;
let aiExplanationReturnFocus = null;
let centerMap = null;
let centerTileLayer = null;
let centerRouteLayerGroup = null;
let centerMarkerLayerGroup = null;
const centerMarkersBySpotId = new Map();
let centerMapLayerMode = "soft";
let centerMapRenderSequence = 0;
let centerMapLastFitKey = null;
let centerMapRenderedRouteKey = null;
let centerMapObserver = null;
let pendingCenterMapScenario = null;
let mapHitBoundsFrame = null;
let centerTileErrorCount = 0;
let routeMap = null;
let routeLayerGroup = null;
let routeTileLayer = null;
let routeTileErrorCount = 0;
let routeProxySupportPromise = null;
const routeSummaryCache = new Map();
const aiExplanationCache = new Map();
let routeModalRenderSequence = 0;
let recommendationRequestSequence = 0;
let recommendationAbortController = null;
let aiExplanationRequestSequence = 0;
let aiExplanationAbortController = null;
let aiExplanationProgressTimers = [];
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

const pointRoleLabels = Object.freeze({
  poi: "장소 대표점",
  facility: "시설 대표점",
  route_start: "코스 시작점",
  route_start_end: "코스 시작·종점",
  route_end_reference: "종점 측 대표점",
  viewpoint: "조망점"
});

const pointRoleShortLabels = Object.freeze({
  facility: "시설",
  route_start: "시작점",
  route_start_end: "시작·종점",
  route_end_reference: "종점 측",
  viewpoint: "조망점"
});

const conditionLabels = {
  traveler_type: "여행자",
  mobility_conditions: "이동 조건",
  preferred_themes: "선호 테마",
  required_accessibility: "필수 확인",
  avoid: "제외 조건"
};

const scoreLabels = {
  source_trust: "정보 신뢰도",
  mobility_fit: "이동 적합성",
  facility_fit: "편의시설",
  theme_fit: "테마 적합성",
  safety_clarity: "안전 안내"
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
    iconClass: "bi-heart-pulse",
    lineArt: "assets/theme-line-recovery.png?v=20260715-1",
    character: "assets/theme-character-recovery.webp?v=20260710-2",
    title: "회복 중",
    body: "무리한 일정을 피하고 휴식이 많은 코스",
    tone: "rose"
  },
  {
    id: "diet_restricted",
    iconClass: "bi-egg-fried",
    lineArt: "assets/theme-line-food.png?v=20260715-1",
    character: "assets/theme-character-food.webp?v=20260710-2",
    title: "음식 제한",
    body: "식당·시장 제외, 휴식 중심",
    tone: "cream"
  },
  {
    id: "stroller_family",
    iconClass: "bi-people",
    lineArt: "assets/theme-line-family.png?v=20260715-1",
    character: "assets/theme-character-family.webp?v=20260710-2",
    title: "아이 동반",
    body: "유모차와 보호자 휴식 동선을 우선",
    tone: "purple"
  },
  {
    id: "wheelchair_access",
    iconClass: "bi-person-wheelchair",
    lineArt: "assets/theme-line-wheelchair.png?v=20260715-1",
    character: "assets/theme-character-wheelchair.webp?v=20260710-2",
    title: "휠체어 접근",
    body: "휠체어 접근 가능한 장소 우선",
    tone: "mint"
  },
  {
    id: "weather_sensitive",
    iconClass: "bi-cloud-rain",
    lineArt: "assets/theme-line-weather.png?v=20260715-1",
    character: "assets/theme-character-weather.webp?v=20260710-2",
    title: "날씨 민감",
    body: "실내/실외 혼합 코스 선호",
    tone: "blue"
  }
];

const conceptRecipeProfiles = {
  recovery_quiet: {
    subtitle: "오늘은 천천히, 쉬어가며 제주를 만나요.",
    companion: { key: "traveler_type", value: "caregiver_group", label: "보호자와" },
    pace: { key: "mobility_conditions", value: "휴식 필요", label: "아주 여유롭게" },
    distance: { key: "mobility_conditions", value: "긴 걷기 어려움", label: "15분 이내" },
    setting: { key: "preferred_themes", value: "실내", label: "실내 위주" },
    essentials: [
      { key: "required_accessibility", value: "주차", label: "주차" },
      { key: "required_accessibility", value: "장애인 화장실", label: "화장실" },
      { key: "required_accessibility", value: "휴식 공간", label: "휴식 공간" }
    ]
  },
  diet_restricted: {
    subtitle: "먹거리 걱정은 덜고, 편안한 관람에 집중해요.",
    companion: { key: "traveler_type", value: "diet_restricted_traveler", label: "식사 기준에 맞춰" },
    pace: { key: "mobility_conditions", value: "체력 저하", label: "여유롭게" },
    distance: { key: "mobility_conditions", value: "짧은 이동", label: "15분 이내" },
    setting: { key: "preferred_themes", value: "실내", label: "실내 위주" },
    essentials: [
      { key: "required_accessibility", value: "주차", label: "주차" },
      { key: "required_accessibility", value: "장애인 화장실", label: "화장실" },
      { key: "avoid", value: "식당 제외", label: "식당 제외" }
    ]
  },
  stroller_family: {
    subtitle: "아이와 보호자 모두 쉬기 좋은 동선으로 둘러봐요.",
    companion: { key: "traveler_type", value: "stroller_family", label: "아이와" },
    pace: { key: "mobility_conditions", value: "휴식 필요", label: "쉬엄쉬엄" },
    distance: { key: "mobility_conditions", value: "짧은 이동", label: "15분 이내" },
    setting: { key: "preferred_themes", value: "공원", label: "공원·실내 위주" },
    essentials: [
      { key: "required_accessibility", value: "주차", label: "주차" },
      { key: "required_accessibility", value: "화장실", label: "화장실" },
      { key: "required_accessibility", value: "휴식 공간", label: "휴식 공간" }
    ]
  },
  wheelchair_access: {
    subtitle: "확인된 접근 정보와 평탄한 동선을 먼저 살펴봐요.",
    companion: { key: "traveler_type", value: "wheelchair_user", label: "휠체어로" },
    pace: { key: "mobility_conditions", value: "긴 걷기 어려움", label: "안전하게" },
    distance: { key: "mobility_conditions", value: "경사와 계단 확인", label: "평탄한 동선" },
    setting: { key: "preferred_themes", value: "실내", label: "실내 위주" },
    essentials: [
      { key: "required_accessibility", value: "주차", label: "주차" },
      { key: "required_accessibility", value: "장애인 화장실", label: "화장실" },
      { key: "required_accessibility", value: "휠체어 접근", label: "휠체어 접근" }
    ]
  },
  weather_sensitive: {
    subtitle: "비와 바람의 영향을 줄인 실내 코스로 여행해요.",
    companion: { key: "traveler_type", value: "senior", label: "동행자와" },
    pace: { key: "mobility_conditions", value: "바람", label: "날씨 걱정 없이" },
    distance: { key: "mobility_conditions", value: "짧은 이동", label: "15분 이내" },
    setting: { key: "preferred_themes", value: "실내", label: "실내 위주" },
    essentials: [
      { key: "required_accessibility", value: "주차", label: "주차" },
      { key: "required_accessibility", value: "장애인 화장실", label: "화장실" },
      { key: "avoid", value: "강풍", label: "강풍 피하기" }
    ]
  }
};

let themeMotionTimer = null;
let ragQueryAssistTimer = null;

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

const ragQueryConditionRules = [
  { label: "지역 · 제주시", aliases: ["제주시", "제주 시내", "제주공항"] },
  { label: "지역 · 서귀포시", aliases: ["서귀포시", "서귀포"] },
  { label: "테마 · 실내", aliases: ["실내", "박물관", "미술관", "전시관", "기념관"] },
  { label: "테마 · 문화", aliases: ["문화", "역사", "유적", "박물관", "미술관"] },
  { label: "테마 · 숲", aliases: ["숲", "수목원", "정원"] },
  { label: "테마 · 바다", aliases: ["바다", "해변", "해안"] },
  { label: "테마 · 공원", aliases: ["공원", "산책로"] },
  { label: "테마 · 휴식", aliases: ["휴식", "조용한", "한적한", "쉼"] },
  { label: "접근 · 휠체어", aliases: ["휠체어", "전동휠체어", "전동 휠체어"] },
  { label: "접근 · 장애인 화장실", aliases: ["장애인 화장실", "휠체어 화장실", "무장애 화장실"] },
  { label: "접근 · 주차", aliases: ["장애인 주차", "주차장", "주차 필요", "주차 가능"] },
  { label: "동행 · 아이", aliases: ["유모차", "유아차", "영유아", "아이 동반"] },
  { label: "동행 · 고령자", aliases: ["어르신", "노인", "고령자", "노약자"] },
  { label: "이동 · 짧은 이동", aliases: ["짧은 이동", "이동 거리가 짧", "가까운 곳", "근처"] },
  { label: "이동 · 휴식 필요", aliases: ["휴식 필요", "자주 쉬", "벤치", "쉼터"] },
  { label: "이동 · 계단 회피", aliases: ["계단 회피", "계단 피", "계단 제외"] },
  { label: "날씨 · 비", aliases: ["비 오는", "우천"] },
  { label: "지원 · 병원", aliases: ["종합병원", "대형병원", "응급실", "병원"] },
  { label: "지원 · 약국", aliases: ["약국"] },
  { label: "지원 · 급속충전기", aliases: ["급속충전기", "급속 충전기", "휠체어 충전", "보장구 충전"] },
  { label: "지원 · 이동지원센터", aliases: ["이동지원센터", "이동 지원 센터", "콜택시", "콜 택시"] },
  { label: "지원 · 관광 복지", aliases: ["관광복지서비스", "관광 복지 서비스", "관광 관련 복지", "복지서비스"] }
];

const ragQueryConflictRules = [
  { label: "음식·식당", avoidAliases: ["식당 제외"], queryAliases: ["음식", "식당", "음식점", "맛집", "먹거리"] },
  { label: "바다", avoidAliases: ["바다"], queryAliases: ["바다", "해변", "해안"] },
  { label: "숲", avoidAliases: ["숲"], queryAliases: ["숲", "수목원", "정원"] },
  { label: "실내", avoidAliases: ["실내"], queryAliases: ["실내", "박물관", "미술관", "전시관", "기념관"] }
];

const ragQueryAvoidAfterMarkers = [
  "회피", "피하", "피해", "피하고", "빼", "제외", "말고", "싫", "없", "어렵", "힘들", "불편", "원하지", "안 가", "가지 않", "못 가"
];

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

const PLACE_IMAGE_VERSION = "20260714-1";
const JEJU_ROADVIEW_IMAGE_SOURCE_URL = "https://www.data.go.kr/data/15110209/fileData.do";

function placeImage(src, caption, {
  source,
  sourceUrl,
  license,
  policy = "실제 장소 대표 이미지 · 16:9 크롭/리사이즈",
  fit = "cover"
}) {
  return {
    src: `${src}?v=${PLACE_IMAGE_VERSION}`,
    caption,
    source,
    sourceUrl,
    license,
    policy,
    fit
  };
}

function roadviewPlaceImage(src, caption) {
  return placeImage(src, caption, {
    source: "제주특별자치도 사회적약자 시설 로드뷰 공공데이터",
    sourceUrl: JEJU_ROADVIEW_IMAGE_SOURCE_URL,
    license: "이용허락범위 제한 없음 · 16:9 크롭/리사이즈"
  });
}

function commonsPlaceImage(src, caption, source, sourceUrl, license, policy) {
  return placeImage(src, caption, {
    source,
    sourceUrl,
    license: `${license} · 16:9 크롭/리사이즈`,
    policy: policy || "실제 장소 대표 이미지 · 16:9 크롭/리사이즈"
  });
}

const PLACE_IMAGE_POLICY = {
  // 제주특별자치도 사회적약자 시설 로드뷰 공공데이터
  jeju_culture_folk_village_007: roadviewPlaceImage(
    "assets/places/jeju_culture_folk_village_007--jeju-roadview--JEJUFOLKVIL-1-032.jpg",
    "제주민속촌 전통 가옥 거리"
  ),
  jeju_culture_hangmong_026: roadviewPlaceImage(
    "assets/places/jeju_culture_hangmong_026--jeju-roadview--ANTIMONG-1-009.jpg",
    "항몽유적지 진입부와 안내 공간"
  ),
  jeju_culture_mokgwana_008: roadviewPlaceImage(
    "assets/places/jeju_culture_mokgwana_008--jeju-roadview--MOKGWANA-1-001.jpg",
    "제주목관아 진입부와 주변 보행로"
  ),
  jeju_forest_cheonjiyeon_014: roadviewPlaceImage(
    "assets/places/jeju_forest_cheonjiyeon_014--jeju-roadview--CHONJIYEON-1-009.jpg",
    "천지연폭포 접근 주차장과 진입부"
  ),
  jeju_forest_halla_005: roadviewPlaceImage(
    "assets/places/jeju_forest_halla_005--jeju-roadview--HALLAARBOR-1-022.jpg",
    "한라수목원 숲 산책로"
  ),
  jeju_forest_healing_001: roadviewPlaceImage(
    "assets/HEALING-1-001.jpg",
    "서귀포 치유의숲 무장애 데크길"
  ),
  jeju_forest_recreation_003: roadviewPlaceImage(
    "assets/places/jeju_forest_recreation_003--jeju-roadview--SEOGWIFOREST-1-024.jpg",
    "서귀포 자연휴양림 무장애 산책로"
  ),
  jeju_forest_red_oreum_004: roadviewPlaceImage(
    "assets/places/jeju_forest_red_oreum_004--jeju-roadview--REDOREUMROAD-1-056.jpg",
    "붉은오름자연휴양림 무장애 데크길"
  ),
  jeju_forest_saryeoni_002: roadviewPlaceImage(
    "assets/SARANI-1-001.jpg",
    "사려니숲길 무장애 데크길"
  ),
  jeju_indoor_art_museum_033: roadviewPlaceImage(
    "assets/places/jeju_indoor_art_museum_033--jeju-roadview--JEJUARTMU-1-008.jpg",
    "제주도립미술관 외관과 진입 광장"
  ),
  jeju_indoor_haenyeo_024: roadviewPlaceImage(
    "assets/places/jeju_indoor_haenyeo_024--jeju-roadview--HAENYEOMU-1-018.jpg",
    "제주해녀박물관 야외 전경"
  ),
  jeju_indoor_hanran_016: roadviewPlaceImage(
    "assets/places/jeju_indoor_hanran_016--jeju-roadview--HALLANEX-1-016.jpg",
    "제주한란전시관 온실 외관과 산책로"
  ),
  jeju_indoor_literature_022: roadviewPlaceImage(
    "assets/places/jeju_indoor_literature_022--jeju-roadview--JEJULITERMU-1-001.jpg",
    "제주문학관 진입로와 외관"
  ),
  jeju_indoor_mandeok_museum_009: roadviewPlaceImage(
    "assets/MANDEOK-1-001.jpg",
    "김만덕기념관과 야외 정원"
  ),
  jeju_indoor_starlight_025: roadviewPlaceImage(
    "assets/places/jeju_indoor_starlight_025--jeju-roadview--STARLIGHT-2-002.jpg",
    "제주별빛누리공원 전시 공간"
  ),
  jeju_indoor_worldheritage_011: roadviewPlaceImage(
    "assets/WNHCENTER-1-001.jpg",
    "제주세계자연유산센터 전경"
  ),
  jeju_rest_sinsan_015: roadviewPlaceImage(
    "assets/SHINSANPA-1-001.jpg",
    "신산공원 산책 광장"
  ),
  jeju_sea_saeyeongyo_039: roadviewPlaceImage(
    "assets/places/jeju_sea_saeyeongyo_039--jeju-roadview--NEWBRIDGE-1-014.jpg",
    "새연교 전망 데크와 교량"
  ),
  jeju_tourism_weak_001: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_001--jeju-roadview--JEJU43PA-1-001.jpg",
    "제주4·3평화공원 기념관 전경"
  ),
  jeju_tourism_weak_005: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_005--jeju-roadview--GIDANG-1-001.jpg",
    "기당미술관 진입부와 외관"
  ),
  jeju_tourism_weak_006: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_006--jeju-roadview--KIMCHANG-1-022.jpg",
    "김창열미술관 출입구 전경"
  ),
  jeju_tourism_weak_011: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_011--jeju-roadview--JEJUSTONE-1-035.jpg",
    "제주돌문화공원 돌담 산책로"
  ),
  jeju_tourism_weak_013: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_013--jeju-roadview--MANJANGCAVE-1-016.jpg",
    "만장굴 관람 진입로"
  ),
  jeju_tourism_weak_019: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_019--jeju-roadview--BIJARIM-1-038.jpg",
    "비자림 숲길"
  ),
  jeju_tourism_weak_023: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_023--jeju-roadview--SEOPJIKOJI-1-009.jpg",
    "섭지코지 해안 진입로"
  ),
  jeju_tourism_weak_037: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_037--jeju-roadview--JEOLMULFOREST-1-008.jpg",
    "절물자연휴양림 산책로"
  ),
  jeju_tourism_weak_038: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_038--jeju-roadview--AEROSPACEMU-2-016.jpg",
    "제주항공우주박물관 실내 전시 공간"
  ),
  jeju_tourism_weak_039: roadviewPlaceImage(
    "assets/places/jeju_tourism_weak_039--jeju-roadview--JEJUCONTEM-1-008.jpg",
    "제주현대미술관 출입구와 외관"
  ),

  // Wikimedia Commons 및 공공누리 재사용 허용 이미지
  jeju_cafe_osulloc_013: commonsPlaceImage(
    "assets/OSULLOC-easyjeju.jpg",
    "오설록 티 뮤지엄 외관",
    "Wikimedia Commons · 골뱅이",
    "https://commons.wikimedia.org/wiki/File:O%27Sulloc_Tea_Museum,_Jeju_(%EC%98%A4%EC%84%A4%EB%A1%9D_%EB%85%B9%EC%B0%A8%EB%B0%95%EB%AC%BC%EA%B4%80,_%EC%A0%9C%EC%A3%BC)_-_panoramio.jpg",
    "CC BY-SA 3.0"
  ),
  jeju_food_market_olle_035: commonsPlaceImage(
    "assets/places/jeju_food_market_olle_035--commons--seogwipo-maeil-olle-market-01--hero-crop.jpg",
    "서귀포매일올레시장 내부 통로",
    "Wikimedia Commons · Seefooddiet",
    "https://commons.wikimedia.org/wiki/File:Seogwipo_Maeil_Olle_Market_01.jpg",
    "CC BY-SA 4.0"
  ),
  jeju_forest_thinking_garden_027: commonsPlaceImage(
    "assets/places/jeju_forest_thinking_garden_027--commons--spirited-garden-06--hero-crop.jpg",
    "생각하는 정원 연못과 정원 풍경",
    "Wikimedia Commons · Bernard Gagnon",
    "https://commons.wikimedia.org/wiki/File:Spirited_Garden_06.jpg",
    "CC0 1.0"
  ),
  jeju_forest_yeomiji_012: commonsPlaceImage(
    "assets/places/jeju_forest_yeomiji_012--commons--yeomiji--hero-crop.jpg",
    "여미지식물원 온실 외관",
    "Wikimedia Commons · WSTAY.com",
    "https://commons.wikimedia.org/wiki/File:Yeomiji.jpg",
    "CC BY 3.0"
  ),
  jeju_indoor_icc_032: placeImage(
    "assets/ICCJEJU-accessible-tourism.jpg",
    "제주국제컨벤션센터와 중문 해안 전경",
    {
      source: "대한민국역사박물관 현대사아카이브",
      sourceUrl: "https://commons.wikimedia.org/wiki/File:%EC%A0%9C%EC%A3%BC_%EC%A4%91%EB%AC%B8%EA%B4%80%EA%B4%91%EB%8B%A8%EC%A7%80_%EA%B5%AD%EC%A0%9C%EC%BB%A8%EB%B2%A4%EC%85%98%EC%84%BC%ED%84%B0.jpg",
      license: "공공누리 제1유형",
      policy: "실제 장소 대표 이미지"
    }
  ),
  jeju_other_dongmun_market_029: commonsPlaceImage(
    "assets/places/jeju_other_dongmun_market_029--commons--dongmun-market-01--hero-crop.jpg",
    "제주 동문재래시장 입구",
    "Wikimedia Commons · Abasaa",
    "https://commons.wikimedia.org/wiki/File:Dongmun_Market_01.JPG",
    "Public domain"
  ),
  jeju_rest_area_geolmae_038: commonsPlaceImage(
    "assets/places/jeju_rest_area_geolmae_038--commons--route-7-1--hero-crop.jpg",
    "천지연 걸매생태공원 산책 데크",
    "Wikimedia Commons · Jeju Olle Foundation",
    "https://commons.wikimedia.org/wiki/File:Jejuolle-route-7-1(5).jpg",
    "CC BY-SA 4.0"
  ),
  jeju_sea_cruise_042: commonsPlaceImage(
    "assets/places/jeju_sea_cruise_042--commons--seogwipo-harbor--hero-crop.jpg",
    "서귀포유람선 출항지인 서귀포항 전경",
    "Wikimedia Commons · SpaceFox",
    "https://commons.wikimedia.org/wiki/File:Le_port_de_Seogwipo,_Cor%C3%A9e_du_Sud.jpg",
    "CC BY 4.0",
    "출항지 대체 이미지 · 16:9 크롭/리사이즈"
  ),
  jeju_sea_olle14_018: commonsPlaceImage(
    "assets/places/jeju_sea_olle14_018--commons--route-14--hero-crop.jpg",
    "올레 14코스 금능해변에서 본 비양도",
    "Wikimedia Commons · Jeju Olle Foundation",
    "https://commons.wikimedia.org/wiki/File:Jeju_Olle_Route_14_(2).jpg",
    "CC BY-SA 4.0"
  ),
  jeju_sea_olle17_019: commonsPlaceImage(
    "assets/places/jeju_sea_olle17_019--commons--route-17--hero-crop.jpg",
    "올레 17코스 용연계곡과 용연다리",
    "Wikimedia Commons · Jeju Olle Foundation",
    "https://commons.wikimedia.org/wiki/File:Jejuolle-route-17(4).jpg",
    "CC BY-SA 4.0"
  ),
  jeju_sea_olle6_017: commonsPlaceImage(
    "assets/places/jeju_sea_olle6_017--commons--route-06--hero-crop.jpg",
    "올레 6코스 시작점 쇠소깍 하구",
    "Wikimedia Commons · Jeju Olle Foundation",
    "https://commons.wikimedia.org/wiki/File:Jejuolle-route-06(1).jpg",
    "CC BY-SA 4.0"
  ),
  jeju_transport_airport_031: commonsPlaceImage(
    "assets/places/jeju_transport_airport_031--commons--jejuairport2024--hero-crop.jpg",
    "제주국제공항 여객터미널 전경",
    "Wikimedia Commons · Kimhs5400",
    "https://commons.wikimedia.org/wiki/File:Jejuairport2024.jpg",
    "CC BY 4.0"
  ),

  jeju_culture_seotal_oreum_030: commonsPlaceImage(
    "assets/places/jeju_culture_seotal_oreum_030--commons--aldreu-hangar--hero-crop.jpg",
    "섯알오름 인근 알뜨르비행장 격납고",
    "Wikimedia Commons · Jjw",
    "https://commons.wikimedia.org/wiki/File:Aldreu_Japanese_underground_hangar_at_WWII.jpg",
    "CC BY-SA 4.0",
    "인접 역사유적 대표 이미지 · 16:9 크롭/리사이즈"
  )
};

const PLACE_IMAGE_PENDING_REASON = {
  jeju_indoor_bunker_lumieres_010: "개별 이미지 이용유형 확인 중",
  jeju_restaurant_nangtteule_036: "재사용 허용 대표 이미지 확인 중",
  jeju_shopping_donghwa_040: "상업 재사용 허용 대표 이미지 확인 중"
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

function profilesHaveSameConditions(leftProfile, rightProfile) {
  const left = normalizeProfile(leftProfile);
  const right = normalizeProfile(rightProfile);
  return Object.keys(left).every((key) => {
    const leftValues = new Set(left[key]);
    const rightValues = new Set(right[key]);
    return leftValues.size === rightValues.size
      && [...leftValues].every((value) => rightValues.has(value));
  });
}

function profileWithToggledValue(sourceProfile, key, value) {
  const profile = normalizeProfile(sourceProfile);
  if (!Object.prototype.hasOwnProperty.call(profile, key) || !value) {
    return profile;
  }
  const selected = new Set(profile[key] || []);
  if (selected.has(value)) {
    selected.delete(value);
  } else {
    selected.add(value);
  }
  profile[key] = Array.from(selected);
  return profile;
}

function toggleProfileValue(key, value) {
  state.profile = profileWithToggledValue(state.profile, key, value);
}

function beginProfileModalEdit() {
  state.profileModalDraft = {
    scenarioId: state.scenarioId,
    profile: normalizeProfile(state.profile),
    ragQuery: normalizeRagQuery(state.ragQuery)
  };
  return state.profileModalDraft;
}

function selectProfileModalScenario(scenarioId) {
  const scenario = state.data?.scenarios?.find((item) => item.id === scenarioId);
  if (!state.profileModalDraft || !scenario) {
    return false;
  }
  state.profileModalDraft.scenarioId = scenarioId;
  state.profileModalDraft.profile = profileFromScenario(scenario);
  return true;
}

function toggleProfileModalValue(key, value) {
  if (!state.profileModalDraft) {
    return false;
  }
  const profile = profileWithToggledValue(state.profileModalDraft.profile, key, value);
  state.profileModalDraft.profile = profile;
  return true;
}

function updateProfileModalQuery(value) {
  if (!state.profileModalDraft) {
    return false;
  }
  state.profileModalDraft.ragQuery = normalizeRagQuery(value);
  return true;
}

function ragQueryAliasIsAvoided(query, alias) {
  let start = 0;
  while (start < query.length) {
    const index = query.indexOf(alias, start);
    if (index < 0) {
      return false;
    }
    const after = query.slice(index + alias.length, index + alias.length + 18);
    const before = query.slice(Math.max(0, index - 16), index);
    if (
      ragQueryAvoidAfterMarkers.some((marker) => after.includes(marker))
      || /(?:피할|피하고 싶은|빼고 싶은|제외할|원하지 않는|싫은|안 갈|가지 않을)\s*$/.test(before)
    ) {
      return true;
    }
    start = index + alias.length;
  }
  return false;
}

function ragQueryHasPositiveAlias(query, aliases) {
  return aliases.some((alias) => query.includes(alias) && !ragQueryAliasIsAvoided(query, alias));
}

function detectRagQueryConditions(value) {
  const query = normalizeRagQuery(value);
  if (!query) {
    return [];
  }
  return ragQueryConditionRules
    .flatMap((rule) => {
      if (!rule.aliases.some((alias) => query.includes(alias))) {
        return [];
      }
      const negationAware = rule.label.startsWith("테마 ·") || rule.label.startsWith("지원 ·");
      if (negationAware && !ragQueryHasPositiveAlias(query, rule.aliases)) {
        return [`제외 · ${rule.label.split(" · ").slice(1).join(" · ")}`];
      }
      return [rule.label];
    })
    .slice(0, 8);
}

function detectRagQueryConflicts(value, profile) {
  const query = normalizeRagQuery(value);
  const avoid = normalizeProfile(profile).avoid;
  if (!query || !avoid.length) {
    return [];
  }
  return ragQueryConflictRules
    .filter((rule) => (
      avoid.some((value) => rule.avoidAliases.some((alias) => value.includes(alias)))
      && ragQueryHasPositiveAlias(query, rule.queryAliases)
    ))
    .map((rule) => rule.label);
}

function renderRagQueryAssist(value) {
  if (ragQueryAssistTimer) {
    clearTimeout(ragQueryAssistTimer);
    ragQueryAssistTimer = null;
  }
  const input = document.getElementById("ragQueryInput");
  const query = normalizeRagQuery(value ?? input?.value ?? state.profileModalDraft?.ragQuery);
  const clearButton = document.getElementById("ragQueryClear");
  const recognized = document.getElementById("ragRecognizedConditions");
  const conflict = document.getElementById("ragQueryConflict");
  if (clearButton) {
    clearButton.hidden = !query;
  }
  if (conflict) {
    const conflicts = detectRagQueryConflicts(query, state.profileModalDraft?.profile);
    conflict.hidden = !conflicts.length;
    conflict.textContent = conflicts.length
      ? `${conflicts.join(", ")} 요청이 아래 제외 조건과 겹쳐요. 검색어나 상세 조건 중 하나를 조정해 주세요.`
      : "";
  }
  if (!recognized) {
    return;
  }
  const conditions = detectRagQueryConditions(query);
  if (!query) {
    recognized.innerHTML = '<span class="rag-recognized-empty">입력하지 않아도 아래 선택 조건만으로 추천할 수 있어요.</span>';
    return;
  }
  if (!conditions.length) {
    recognized.innerHTML = '<span class="rag-recognized-empty">입력한 표현 그대로 검색에 반영해요.</span>';
    return;
  }
  recognized.innerHTML = conditions
    .map((condition) => `<span class="rag-recognized-chip">${escapeHtml(condition)}</span>`)
    .join("");
}

function scheduleRagQueryAssist(value) {
  if (ragQueryAssistTimer) {
    clearTimeout(ragQueryAssistTimer);
  }
  const query = normalizeRagQuery(value);
  ragQueryAssistTimer = setTimeout(() => {
    renderRagQueryAssist(query);
  }, 300);
}

function setRagQueryValue(value, { focus = true } = {}) {
  const input = document.getElementById("ragQueryInput");
  const query = normalizeRagQuery(value);
  if (input) {
    input.value = query;
  }
  updateProfileModalQuery(query);
  renderRagQueryAssist(query);
  if (focus) {
    input?.focus();
  }
  return query;
}

function commitProfileModalEdit(queryValue) {
  if (!state.profileModalDraft) {
    return false;
  }
  updateProfileModalQuery(queryValue);
  const draft = state.profileModalDraft;
  state.scenarioId = draft.scenarioId;
  state.profile = normalizeProfile(draft.profile);
  state.ragQuery = draft.ragQuery;
  state.conceptFocus = null;
  state.profileModalDraft = null;
  return true;
}

function discardProfileModalEdit() {
  state.profileModalDraft = null;
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
    retrieval: response.retrieval,
    engine: response.engine,
    generated_at: response.generated_at
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
  (state.data?.saved_route_places || []).forEach((place) => {
    if (place?.spot_id && place?.name && !places.has(place.spot_id)) {
      places.set(place.spot_id, {
        spot_id: place.spot_id,
        name: place.name,
        region: place.region || "제주",
        category: place.category || "other",
        effort: {
          recommended_duration_minutes: place.duration_minutes || null
        },
        info_url: place.info_url || "",
        visit_info: place.visit_info || null,
        location: validLocation(place.location) ? place.location : null,
        verification_status: "needs_check",
        unavailable: place.available === false
      });
    }
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
    location: mergePlaceLocation(place?.location, fallback.location)
  };
}

function mergePlaceLocation(primary, fallback) {
  const primaryLocation = validLocation(primary) ? primary : null;
  const fallbackLocation = validLocation(fallback) ? fallback : null;
  if (!primaryLocation && !fallbackLocation) {
    return null;
  }
  const merged = { ...(fallbackLocation || {}), ...(primaryLocation || {}) };
  const primaryRole = String(primaryLocation?.point_role || "");
  merged.point_role = Object.prototype.hasOwnProperty.call(pointRoleLabels, primaryRole)
    ? primaryRole
    : locationPointRole(fallbackLocation);
  return merged;
}

function validLocation(location) {
  if (!location) {
    return false;
  }
  const latitude = Number(location.latitude);
  const longitude = Number(location.longitude);
  return Number.isFinite(latitude) && Number.isFinite(longitude);
}

function recommendationStatusText(response) {
  if (response?.retrieval?.status === "resource_data_gap") {
    return "지원서비스 근거 데이터 보강 필요";
  }
  if (response?.retrieval?.status === "no_match") {
    return "검색 근거가 부족해 추천을 보류했습니다";
  }
  if (response?.retrieval?.status === "applied") {
    return "공식 근거 검색과 접근성 재정렬 완료";
  }
  return "실시간 계산 추천 반영 완료";
}

function normalizeRagQuery(value) {
  return String(value || "").replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 500);
}

function recommendationPayload({ useAi = false } = {}) {
  return {
    traveler_summary: normalizeProfile(state.profile),
    query: normalizeRagQuery(state.ragQuery) || normalizeRagQuery(state.conceptFocus?.value),
    limit: RECOMMENDATION_LIMIT,
    use_ai: Boolean(useAi),
    model: RECOMMENDATION_MODEL
  };
}

function recommendationContextKey() {
  const payload = recommendationPayload();
  return JSON.stringify({
    traveler_summary: payload.traveler_summary,
    query: payload.query,
    limit: payload.limit,
    model: payload.model
  });
}

function aiExplanationCacheKey(scenario = currentScenario()) {
  const route = (scenario?.recommendation?.course?.route || [])
    .slice(0, RECOMMENDATION_LIMIT)
    .map((item) => String(item?.spot_id || item?.name || ""));
  const evidence = (scenario?.retrieval?.matches || [])
    .slice(0, RECOMMENDATION_LIMIT)
    .map((match) => {
      const bundle = match?.evidence_bundle || {};
      const factIds = Object.values(bundle.accessibility || {})
        .map((fact) => String(fact?.evidence_id || ""))
        .filter(Boolean);
      const sourceIds = (bundle.sources || [])
        .map((source) => String(source?.evidence_id || ""))
        .filter(Boolean);
      return [String(match?.spot_id || ""), ...factIds, ...sourceIds];
    });
  return JSON.stringify({
    context: recommendationContextKey(),
    generatedAt: String(scenario?.generated_at || ""),
    route,
    evidence
  });
}

function aiExplanationStateFromSummary(summary, contextKey = recommendationContextKey()) {
  const sourceStatus = String(summary?.status || "skipped").toLowerCase();
  if (sourceStatus === "success") {
    return {
      status: "success",
      message: "생성 완료. ‘생성된 AI 설명 보기’를 눌러 공식 근거와 함께 확인하세요.",
      contextKey
    };
  }
  if (["disabled", "disabled_no_key"].includes(sourceStatus)) {
    return {
      status: "disabled",
      message: "AI 설명 연결이 준비되지 않아 검색·점수 근거만 표시합니다.",
      contextKey
    };
  }
  if (sourceStatus === "error") {
    return {
      status: "error",
      message: "AI 설명을 생성하지 못했습니다. 검색 결과와 공식 출처는 그대로 확인할 수 있습니다.",
      contextKey
    };
  }
  if (["ungrounded", "insufficient_evidence", "blocked_retrieval"].includes(sourceStatus)) {
    return {
      status: "ungrounded",
      message: "유효한 공식 근거에 연결되지 않아 AI 설명을 표시하지 않았습니다.",
      contextKey
    };
  }
  return {
    status: "idle",
    message: "공식 근거를 바탕으로 한 AI 설명은 아직 생성하지 않았습니다.",
    contextKey
  };
}

function setAiExplanationFromSummary(summary, contextKey = recommendationContextKey()) {
  state.aiExplanation = aiExplanationStateFromSummary(summary, contextKey);
  return state.aiExplanation;
}

function setAiExplanationState(status, message, contextKey = recommendationContextKey()) {
  state.aiExplanation = { status, message, contextKey };
}

function clearAiExplanationProgressTimers() {
  aiExplanationProgressTimers.forEach((timer) => clearTimeout(timer));
  aiExplanationProgressTimers = [];
}

function cachedAiExplanation(cacheKey) {
  const summary = aiExplanationCache.get(cacheKey);
  if (!summary) {
    return null;
  }
  aiExplanationCache.delete(cacheKey);
  aiExplanationCache.set(cacheKey, summary);
  return summary;
}

function rememberAiExplanation(cacheKey, summary) {
  if (summary?.status !== "success") {
    return;
  }
  aiExplanationCache.delete(cacheKey);
  aiExplanationCache.set(cacheKey, summary);
  while (aiExplanationCache.size > AI_EXPLANATION_CACHE_LIMIT) {
    aiExplanationCache.delete(aiExplanationCache.keys().next().value);
  }
}

function scheduleAiExplanationProgress(requestSequence, contextKey) {
  clearAiExplanationProgressTimers();
  [
    [1200, "공식 근거를 바탕으로 추천 이유를 구성하고 있습니다."],
    [12000, "AI 응답의 문장과 공식 출처 연결을 확인하고 있습니다."],
    [25000, "응답이 평소보다 늦습니다. 최대 40초까지 기다린 뒤 다시 안내할게요."]
  ].forEach(([delay, message]) => {
    aiExplanationProgressTimers.push(setTimeout(() => {
      if (
        requestSequence !== aiExplanationRequestSequence
        || contextKey !== recommendationContextKey()
        || state.aiExplanation?.status !== "loading"
      ) {
        return;
      }
      setAiExplanationState("loading", message, contextKey);
      renderRagProcess(currentScenario());
    }, delay));
  });
}

function cancelGroundedAiExplanation({ reset = true } = {}) {
  aiExplanationRequestSequence += 1;
  aiExplanationAbortController?.abort?.();
  aiExplanationAbortController = null;
  clearAiExplanationProgressTimers();
  closeAiExplanationModal({ restoreFocus: false });
  if (reset) {
    setAiExplanationFromSummary(null);
  }
}

function currentAiExplanationState(scenario = currentScenario()) {
  if (scenario?.retrieval?.status !== "applied") {
    return aiExplanationStateFromSummary(null);
  }
  const contextKey = recommendationContextKey();
  if (state.aiExplanation?.contextKey !== contextKey) {
    return aiExplanationStateFromSummary(scenario?.ai_summary, contextKey);
  }
  return state.aiExplanation;
}

function helpRecommendationContext() {
  if (!state.data) {
    return null;
  }
  const scenario = currentScenario();
  if (!scenario) {
    return null;
  }

  const recommendation = scenario.recommendation || {};
  const course = recommendation.course || {};
  const place = state.detailCollapsed ? null : selectedPlace(scenario);
  return {
    mode: state.runtimeScenario ? "runtime" : "static",
    generated_at: scenario.generated_at || state.data?.generated_at || "",
    engine: scenario.engine || { scoring: "precomputed_recommendation_seed" },
    traveler_summary: normalizeProfile(state.profile),
    recommendation: {
      course: {
        title: course.title || scenario.title || "추천 코스",
        summary: course.summary || "",
        route: (course.route || []).slice(0, 4).map((item) => ({
          order: item.order,
          spot_id: item.spot_id,
          name: item.name,
          purpose: item.purpose,
          stay_tip: item.stay_tip
        }))
      },
      score: recommendation.score || {},
      fit_reasons: (recommendation.fit_reasons || []).slice(0, 8),
      deduction_reasons: (recommendation.deduction_reasons || []).slice(0, 8),
      check_before_visit: (recommendation.check_before_visit || []).slice(0, 8)
    },
    selected_place: place ? {
      spot_id: place.spot_id,
      name: place.name,
      score: place.score || {},
      fit_reasons: (place.fit_reasons || []).slice(0, 8),
      deduction_reasons: (place.deduction_reasons || []).slice(0, 8),
      check_before_visit: (place.check_before_visit || []).slice(0, 8),
      source_summary: (place.source_summary || []).slice(0, 3),
      verification_status: place.verification_status || place.verification?.status || "needs_check",
      blocked: Boolean(place.blocked),
      block_reasons: (place.block_reasons || []).slice(0, 4)
    } : null
  };
}

window.GachibomRecommendationContext = helpRecommendationContext;

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
    return "실시간 추천 결과";
  }
  if (status === "error") {
    return "추천 업데이트 실패";
  }
  if (status === "static") {
    return "사전 계산 추천";
  }
  return "추천 준비 완료";
}

function apiStatusPillText() {
  const status = state.apiState.status;
  if (status === "loading") {
    return "계산 중";
  }
  if (status === "success") {
    return "실시간 계산";
  }
  if (status === "error") {
    return "사전 계산";
  }
  if (status === "static") {
    return "사전 계산";
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
  const selectedScenario = state.data?.scenarios?.find((scenario) => scenario.id === state.scenarioId);
  const hasCustomProfile = Boolean(
    selectedScenario
    && !profilesHaveSameConditions(state.profile, profileFromScenario(selectedScenario))
  );
  return Boolean(normalizeRagQuery(state.ragQuery)) || hasCustomProfile;
}

function conceptFocusKey(focus = state.conceptFocus) {
  const key = String(focus?.key || "").trim();
  const value = String(focus?.value || "").trim();
  return key && value ? `${key}:${value}` : "";
}

function staticConditionVariant() {
  const variant = currentStaticScenario()?.condition_variants?.[conceptFocusKey()];
  return variant ? { ...variant, engine: { scoring: "precomputed_condition_focus" } } : null;
}

function shouldRequestRouteProxy() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("routeProxy") === "1" || params.get("api") === "1") {
    return true;
  }
  if (params.get("routeProxy") === "0" || params.get("api") === "0") {
    return false;
  }
  return window.location.protocol !== "file:";
}

async function requestRuntimeRecommendation(sequence) {
  const requestSequence = sequence || ++recommendationRequestSequence;
  if (!shouldRequestRuntimeApi()) {
    recommendationAbortController?.abort?.();
    recommendationAbortController = null;
    if (requestSequence === recommendationRequestSequence) {
      state.runtimeScenario = staticConditionVariant();
      setAiExplanationFromSummary(state.runtimeScenario?.ai_summary);
      setApiState(
        "static",
        state.runtimeScenario ? "선택 조건 우선 추천 반영" : "사전 계산 추천 사용"
      );
    }
    return false;
  }

  recommendationAbortController?.abort?.();
  const AbortControllerClass = window.AbortController || globalThis.AbortController;
  const controller = AbortControllerClass ? new AbortControllerClass() : null;
  recommendationAbortController = controller;

  try {
    const response = await fetch("api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recommendationPayload()),
      ...(controller ? { signal: controller.signal } : {})
    });
    if (!response.ok) {
      throw new Error("추천 서버 미응답");
    }
    const payload = await response.json();
    if (requestSequence !== recommendationRequestSequence) {
      return false;
    }
    state.runtimeScenario = runtimeScenarioFromResponse(payload);
    setAiExplanationFromSummary(payload.ai_summary);
    setApiState("success", recommendationStatusText(payload));
    return true;
  } catch (error) {
    if (controller?.signal?.aborted || error?.name === "AbortError") {
      return false;
    }
    if (requestSequence !== recommendationRequestSequence) {
      return false;
    }
    state.runtimeScenario = staticConditionVariant();
    setAiExplanationFromSummary(state.runtimeScenario?.ai_summary);
    setApiState(
      state.runtimeScenario ? "static" : "error",
      state.runtimeScenario ? "선택 조건 우선 추천 반영" : "실시간 계산 실패, 사전 계산 추천 유지",
      { canRetry: !state.runtimeScenario }
    );
    state.apiState.detail = error?.message || "추천 요청에 실패했습니다.";
    return false;
  } finally {
    if (recommendationAbortController === controller) {
      recommendationAbortController = null;
    }
  }
}

async function requestGroundedAiExplanation({ forceRefresh = false } = {}) {
  const scenario = currentScenario();
  if (scenario?.retrieval?.status !== "applied") {
    return false;
  }

  const requestContextKey = recommendationContextKey();
  const requestCacheKey = aiExplanationCacheKey(scenario);
  if (forceRefresh) {
    aiExplanationCache.delete(requestCacheKey);
  } else {
    const cachedSummary = cachedAiExplanation(requestCacheKey);
    if (cachedSummary) {
      state.runtimeScenario = { ...state.runtimeScenario, ai_summary: cachedSummary };
      setAiExplanationFromSummary(cachedSummary, requestContextKey);
      render();
      return true;
    }
  }

  aiExplanationAbortController?.abort?.();
  clearAiExplanationProgressTimers();
  const requestSequence = ++aiExplanationRequestSequence;
  const AbortControllerClass = window.AbortController || globalThis.AbortController;
  const controller = AbortControllerClass ? new AbortControllerClass() : null;
  aiExplanationAbortController = controller;
  setAiExplanationState(
    "loading",
    "공식 근거를 준비하고 있습니다.",
    requestContextKey
  );
  render();
  scheduleAiExplanationProgress(requestSequence, requestContextKey);

  let timeoutId = null;
  let timedOut = false;
  try {
    const payload = await Promise.race([
      (async () => {
        const response = await fetch("api/recommendations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(recommendationPayload({ useAi: true })),
          ...(controller ? { signal: controller.signal } : {})
        });
        if (!response.ok) {
          throw new Error("AI 설명 서버 미응답");
        }
        return response.json();
      })(),
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          timedOut = true;
          controller?.abort?.();
          const error = new Error("AI 설명 요청 시간 초과");
          error.name = "TimeoutError";
          reject(error);
        }, AI_EXPLANATION_TIMEOUT_MS);
      })
    ]);
    if (
      requestSequence !== aiExplanationRequestSequence
      || requestContextKey !== recommendationContextKey()
    ) {
      return false;
    }
    if (!payload?.ai_summary || typeof payload.ai_summary !== "object") {
      throw new Error("AI 설명 응답 형식 오류");
    }

    state.runtimeScenario = {
      ...state.runtimeScenario,
      ai_summary: payload.ai_summary
    };
    rememberAiExplanation(requestCacheKey, payload.ai_summary);
    setAiExplanationFromSummary(payload.ai_summary, requestContextKey);
    render();
    return state.aiExplanation.status === "success";
  } catch (error) {
    if (
      requestSequence !== aiExplanationRequestSequence
      || requestContextKey !== recommendationContextKey()
    ) {
      return false;
    }
    if (timedOut || error?.name === "TimeoutError") {
      setAiExplanationState(
        "error",
        "40초 안에 응답이 완료되지 않았습니다. 검색 결과는 유지되며 다시 시도할 수 있습니다.",
        requestContextKey
      );
      render();
      return false;
    }
    if (controller?.signal?.aborted || error?.name === "AbortError") {
      return false;
    }
    setAiExplanationState(
      "error",
      "AI 설명을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      requestContextKey
    );
    render();
    return false;
  } finally {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
    clearAiExplanationProgressTimers();
    if (aiExplanationAbortController === controller) {
      aiExplanationAbortController = null;
    }
  }
}

async function refreshScenarioRecommendation({ renderLoading = false } = {}) {
  cancelGroundedAiExplanation();
  const sequence = ++recommendationRequestSequence;
  if (shouldRequestRuntimeApi() && renderLoading) {
    state.runtimeScenario = staticConditionVariant();
    setApiState("loading", "선택한 코스로 업데이트 중");
    render();
  }
  await requestRuntimeRecommendation(sequence);
}

async function refreshRuntimeRecommendation(options = {}) {
  state.selectedSpotId = null;
  state.mapPopupSpotId = null;
  state.detailCollapsed = false;
  await refreshScenarioRecommendation(options);
}

function hasGroundedRecommendationEvidence(place) {
  const status = String(place?.verification?.status || place?.verification_status || "").toLowerCase();
  if (!["verified", "partial"].includes(status)) {
    return false;
  }
  return (place?.source_summary || place?.sources || []).some((source) => (
    Boolean(safeExternalUrl(source?.url))
  ));
}

function selectedRoute(scenario) {
  if (["resource_data_gap", "no_match"].includes(scenario?.retrieval?.status)) {
    return [];
  }
  return (scenario?.recommendation?.course?.route || []).filter((routeItem) => (
    hasGroundedRecommendationEvidence(routePlace(scenario, routeItem))
  ));
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
  const routeItem = route.find((item) => item.spot_id === state.selectedSpotId);
  return places.get(state.selectedSpotId) || (routeItem ? routePlace(scenario, routeItem) : null);
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
  const pendingReason = PLACE_IMAGE_PENDING_REASON[place?.spot_id] || "대표 이미지 준비 중";
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
      <text x="72" y="462" fill="${palette.text}" fill-opacity="0.78" font-family="Arial, Malgun Gothic, sans-serif" font-size="24">${escapeHtml(pendingReason)}</text>
    </svg>
  `;
  return {
    src: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    caption: `${name} · ${pendingReason}`,
    source: "서비스 이미지 안내",
    policy: pendingReason,
    fit: "cover"
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
    sourceUrl: policy.sourceUrl || "",
    license: policy.license || "",
    policy: policy.policy,
    fit: policy.fit || "cover",
    fallbackSrc: placeholder.src,
    fallbackCaption: placeholder.caption,
    fallbackSource: placeholder.source
  };
}

function imageSourceMarkup(source, sourceUrl, license) {
  const sourceLabel = escapeHtml(source || "이미지 출처 확인 중");
  const sourceMarkup = sourceUrl
    ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${sourceLabel}</a>`
    : sourceLabel;
  return `${sourceMarkup}${license ? ` · ${escapeHtml(license)}` : ""}`;
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

function normalizedPointRole(value) {
  const pointRole = String(value || "poi");
  return Object.prototype.hasOwnProperty.call(pointRoleLabels, pointRole) ? pointRole : "poi";
}

function locationPointRole(location) {
  return normalizedPointRole(location?.point_role);
}

function locationPointLabel(location) {
  return pointRoleLabels[locationPointRole(location)];
}

function locationPointShortLabel(location) {
  return pointRoleShortLabels[locationPointRole(location)] || "";
}

function hasSpecialPointRole(location) {
  return validLocation(location) && locationPointRole(location) !== "poi";
}

function locationPointStatusLabel(location) {
  if (!validLocation(location)) {
    return "위치 확인 필요";
  }
  return hasSpecialPointRole(location)
    ? `실제 위치 · ${locationPointLabel(location)}`
    : "실제 위치 기반";
}

function pointRoleBadgeMarkup(location, className = "point-role-badge") {
  if (!hasSpecialPointRole(location)) {
    return "";
  }
  return `<b class="${escapeHtml(className)}">${escapeHtml(locationPointLabel(location))}</b>`;
}

function mapPointDisplayName(place) {
  const name = String(place?.name || "제주 여행지");
  return hasSpecialPointRole(place?.location)
    ? `${name} (${locationPointLabel(place.location)})`
    : name;
}

function sourceSummaryItems(place) {
  return (place?.source_summary || place?.sources || []).slice(0, 3);
}

function routeNames(scenario) {
  return selectedRoute(scenario).slice(0, 4).map((item) => item.name).filter(Boolean);
}

function savedRouteStorage() {
  try {
    return window.localStorage;
  } catch (error) {
    return null;
  }
}

function allowedSavedSpotIds() {
  return new Set(staticPlacesById().keys());
}

function shareableSavedSpotIds() {
  const spotIds = new Set();
  staticPlacesById().forEach((place, spotId) => {
    if (!place.unavailable) {
      spotIds.add(spotId);
    }
  });
  return spotIds;
}

function currentRouteSpotIds(scenario = currentScenario()) {
  if (!scenario) {
    return [];
  }
  const allowed = allowedSavedSpotIds();
  return unique(selectedRoute(scenario)
    .slice(0, 4)
    .map((item) => String(item?.spot_id || ""))
    .filter((spotId) => allowed.has(spotId)));
}

function loadSavedRouteState() {
  if (!SAVED_TRIPS || !state.data) {
    state.savedRoutes = [];
    state.sharedRoutePreview = null;
    return;
  }
  const allowed = allowedSavedSpotIds();
  state.savedRoutes = SAVED_TRIPS.load(savedRouteStorage(), allowed);
  const sharedSpotIds = SAVED_TRIPS.parseSharedSpotIds(window.location, shareableSavedSpotIds());
  const sharedRouteId = sharedSpotIds ? SAVED_TRIPS.routeId(sharedSpotIds) : "";
  state.sharedRoutePreview = sharedSpotIds
    && !state.savedRoutes.some((item) => item.id === sharedRouteId) ? {
    id: sharedRouteId,
    spotIds: sharedSpotIds,
    checkedIds: [],
    savedAt: ""
  } : null;
}

function persistSavedRoutes(successMessage = "저장 상태를 업데이트했습니다.") {
  if (!SAVED_TRIPS) {
    announceSavedRoute("이 브라우저에서는 저장 기능을 사용할 수 없습니다.");
    return false;
  }
  const result = SAVED_TRIPS.persist(
    savedRouteStorage(),
    state.savedRoutes,
    allowedSavedSpotIds(),
    state.data?.generated_at || ""
  );
  state.savedRoutes = result.items;
  announceSavedRoute(result.ok ? successMessage : "브라우저 저장소를 사용할 수 없어 현재 화면에서만 유지됩니다.");
  return result.ok;
}

function announceSavedRoute(message) {
  state.savedRouteMessage = String(message || "");
  const globalStatus = document.getElementById("savedRouteGlobalStatus");
  const modalStatus = document.getElementById("savedRoutesStatus");
  if (globalStatus) {
    globalStatus.textContent = state.savedRouteMessage;
  }
  if (modalStatus) {
    modalStatus.textContent = state.savedRouteMessage;
  }
}

function savedRouteForSpotIds(spotIds) {
  if (!SAVED_TRIPS || !spotIds?.length) {
    return null;
  }
  const id = SAVED_TRIPS.routeId(spotIds);
  return state.savedRoutes.find((item) => item.id === id) || null;
}

function currentSavedRoute() {
  return savedRouteForSpotIds(currentRouteSpotIds());
}

function saveRouteSpotIds(spotIds, message = "추천 코스를 저장했습니다.") {
  if (!SAVED_TRIPS || !spotIds?.length) {
    announceSavedRoute("저장할 추천 코스를 찾지 못했습니다.");
    return false;
  }
  state.savedRoutes = SAVED_TRIPS.upsert(
    state.savedRoutes,
    spotIds,
    allowedSavedSpotIds()
  );
  persistSavedRoutes(message);
  refreshSavedRouteViews();
  return true;
}

function saveCurrentRoute() {
  return saveRouteSpotIds(currentRouteSpotIds());
}

function saveSharedRoute() {
  if (!state.sharedRoutePreview) {
    return false;
  }
  const spotIds = state.sharedRoutePreview.spotIds;
  state.sharedRoutePreview = null;
  const saved = saveRouteSpotIds(spotIds, "공유받은 코스를 내 저장함에 추가했습니다.");
  if (!saved) {
    state.sharedRoutePreview = {
      id: SAVED_TRIPS.routeId(spotIds),
      spotIds,
      checkedIds: [],
      savedAt: ""
    };
    renderSavedRoutesModal();
  }
  return saved;
}

function savedRoutePlaces(item) {
  const index = staticPlacesById();
  const orderedSpotIds = SAVED_TRIPS?.orderedSpotIds(item) || item?.spotIds || [];
  return orderedSpotIds
    .map((spotId) => index.get(spotId) || {
      spot_id: spotId,
      name: "현재 제공하지 않는 장소",
      region: "장소 정보 업데이트 필요",
      unavailable: true,
      effort: { recommended_duration_minutes: null },
      info_url: "",
      location: null
    });
}

function savedRouteTitle(item) {
  const places = savedRoutePlaces(item);
  const availablePlaces = places.filter((place) => !place.unavailable);
  if (!availablePlaces.length) {
    return "저장한 제주 추천 코스";
  }
  return places.length > 1
    ? `${availablePlaces[0].name} 외 ${places.length - 1}곳`
    : availablePlaces[0].name;
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : "";
  } catch (error) {
    return "";
  }
}

function placeInfoUrl(place) {
  const official = safeExternalUrl(place?.visit_info?.official_url);
  if (official) {
    return official;
  }
  const direct = safeExternalUrl(place?.info_url);
  if (direct) {
    return direct;
  }
  const source = (place?.source_summary || place?.sources || []).find((item) => (
    safeExternalUrl(item?.url)
  ));
  return safeExternalUrl(source?.url);
}

function placeReservationUrl(place) {
  return safeExternalUrl(place?.visit_info?.reservation_url);
}

function safePhoneHref(value) {
  const raw = String(value || "").trim();
  if (!raw || !/^[+0-9().\s-]{7,30}$/.test(raw)) {
    return "";
  }
  const digits = raw.replace(/\D/g, "");
  if (digits.length < 7 || digits.length > 15) {
    return "";
  }
  return `tel:${raw.startsWith("+") ? "+" : ""}${digits}`;
}

function formatVisitInfoDate(value) {
  const text = String(value || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return "확인일 없음";
  }
  const parsed = new Date(`${text}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return "확인일 없음";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC"
  }).format(parsed);
}

function visitInfoDateLabel(info) {
  const verifiedAt = formatVisitInfoDate(info?.last_verified_at);
  if (verifiedAt !== "확인일 없음") {
    return `정보 확인 ${verifiedAt}`;
  }
  const sourceUpdatedAt = formatVisitInfoDate(info?.source_updated_at);
  if (sourceUpdatedAt !== "확인일 없음") {
    return `원본 갱신 ${sourceUpdatedAt}`;
  }
  return "정보 확인일 없음";
}

function visitInfoStatusLabel(value) {
  if (value === "verified") {
    return "확인 완료";
  }
  if (value === "partial") {
    return "일부 확인";
  }
  return "재확인 필요";
}

function visitServiceStatusLabel(value) {
  if (value === "temporarily_closed") {
    return "임시휴관 확인";
  }
  if (value === "permanently_closed") {
    return "운영 종료 확인";
  }
  return "";
}

function visitInfoMarkup(place) {
  const info = place?.visit_info && typeof place.visit_info === "object" ? place.visit_info : {};
  const address = String(info.address || "").trim();
  const phone = String(info.phone || "").trim();
  const phoneHref = safePhoneHref(phone);
  const operatingHours = String(info.operating_hours || "").trim();
  const officialUrl = safeExternalUrl(info.official_url);
  const reservationUrl = safeExternalUrl(info.reservation_url);
  const evidence = Array.isArray(info.evidence)
    ? info.evidence.find((item) => safeExternalUrl(item?.source_url))
    : null;
  const evidenceUrl = safeExternalUrl(evidence?.source_url);
  const serviceLabel = visitServiceStatusLabel(info.service_status);
  const hasDetails = Boolean(address || phoneHref || operatingHours || officialUrl || reservationUrl);
  return `
    ${serviceLabel ? `
      <p class="visit-service-alert" role="status">
        <i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>
        <span><strong>${escapeHtml(serviceLabel)}</strong> · 방문 전 공식 운영 여부를 다시 확인해 주세요.</span>
      </p>
    ` : ""}
    <details class="visit-info-card detail-disclosure ${hasDetails ? "" : "empty"}">
      <summary>
        <span class="detail-disclosure-heading">
          <i class="bi bi-info-circle" aria-hidden="true"></i>
          <span><b>방문 정보</b><small>주소·운영시간·예약</small></span>
        </span>
        <span class="detail-disclosure-status">
          <strong>${escapeHtml(serviceLabel || visitInfoStatusLabel(info.verification_status))}</strong>
          <small>${escapeHtml(visitInfoDateLabel(info))}</small>
          <i class="bi bi-chevron-down" aria-hidden="true"></i>
        </span>
      </summary>
      <div class="detail-disclosure-content">
        <p class="visit-info-expanded-meta"><i class="bi bi-calendar-check" aria-hidden="true"></i>${escapeHtml(visitInfoDateLabel(info))}</p>
        ${hasDetails ? `
          <dl>
            ${address ? `<div><dt>주소</dt><dd>${escapeHtml(address)}</dd></div>` : ""}
            ${operatingHours ? `<div><dt>운영시간</dt><dd>${escapeHtml(operatingHours)}</dd></div>` : ""}
            ${phoneHref ? `<div><dt>전화</dt><dd><a href="${escapeHtml(phoneHref)}">${escapeHtml(phone)}</a></dd></div>` : ""}
          </dl>
          <div class="visit-info-actions">
            ${officialUrl ? `<a href="${escapeHtml(officialUrl)}" target="_blank" rel="noopener noreferrer">공식 홈페이지</a>` : ""}
            ${reservationUrl ? `<a href="${escapeHtml(reservationUrl)}" target="_blank" rel="noopener noreferrer">예약하기</a>` : ""}
            ${evidenceUrl ? `<a href="${escapeHtml(evidenceUrl)}" target="_blank" rel="noopener noreferrer">정보 근거</a>` : ""}
          </div>
        ` : `<p>주소·전화·운영시간을 공식 또는 공공 출처로 확인 중입니다.</p>`}
        <p class="visit-info-notice">${escapeHtml(info.notice || "운영시간과 연락처는 변경될 수 있으니 방문 전에 공식 정보로 다시 확인해 주세요.")}</p>
      </div>
    </details>
  `;
}

function kakaoPlaceUrl(place) {
  if (validLocation(place?.location)) {
    return `https://map.kakao.com/link/map/${encodeURIComponent(mapPointDisplayName(place))},${Number(place.location.latitude)},${Number(place.location.longitude)}`;
  }
  return `https://map.kakao.com/link/search/${encodeURIComponent(`${place?.name || "제주 여행지"} 제주`)}`;
}

function kakaoRouteUrl(places) {
  if (places.length < 2 || !places.every((place) => validLocation(place?.location))) {
    return "";
  }
  const points = places.map((place) => (
    `${encodeURIComponent(mapPointDisplayName(place))},${Number(place.location.latitude)},${Number(place.location.longitude)}`
  ));
  return `https://map.kakao.com/link/by/car/${points.join("/")}`;
}

function formatTravelMinutes(value) {
  const minutes = Math.max(0, Math.round(Number(value) || 0));
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (!hours) {
    return `${remainder}분`;
  }
  return remainder ? `${hours}시간 ${remainder}분` : `${hours}시간`;
}

function savedRouteStayMinutes(item) {
  return savedRoutePlaces(item).reduce((total, place) => (
    total + Math.max(0, Number(place?.effort?.recommended_duration_minutes) || 0)
  ), 0);
}

function savedRouteMiniMapPoint(location) {
  if (!validLocation(location)) {
    return null;
  }
  const xRatio = (Number(location.longitude) - jejuMapProjection.west)
    / (jejuMapProjection.east - jejuMapProjection.west);
  const yRatio = (jejuMapProjection.north - Number(location.latitude))
    / (jejuMapProjection.north - jejuMapProjection.south);
  if (!Number.isFinite(xRatio) || !Number.isFinite(yRatio)) {
    return null;
  }
  return {
    x: jejuMapProjection.content.left + clamp(xRatio, 0, 1) * jejuMapProjection.content.width,
    y: jejuMapProjection.content.top + clamp(yRatio, 0, 1) * jejuMapProjection.content.height
  };
}

function savedRouteMiniMapMarkup(item, places) {
  const entries = places.map((place, index) => ({
    place,
    order: index + 1,
    point: savedRouteMiniMapPoint(place.location)
  }));
  const located = entries.filter((entry) => entry.point);
  const pathSegments = [];
  let currentSegment = [];
  entries.forEach((entry) => {
    if (entry.point) {
      currentSegment.push(entry.point);
      return;
    }
    if (currentSegment.length >= 2) {
      pathSegments.push(currentSegment);
    }
    currentSegment = [];
  });
  if (currentSegment.length >= 2) {
    pathSegments.push(currentSegment);
  }
  return `
    <figure class="saved-route-mini-map" aria-label="저장 코스 위치 미리보기">
      <div class="saved-route-mini-map-canvas">
        <img src="assets/jeju-map-fallback.svg?v=20260713-1" alt="" aria-hidden="true" loading="lazy" decoding="async">
        <svg viewBox="0 0 100 100" role="img" aria-label="${escapeHtml(`${located.length}개 장소의 방문 순서 지도`)}">
          ${pathSegments.map((segment) => {
            const path = routePathData(segment);
            return `<path class="saved-route-mini-path-shadow" d="${path}"></path><path class="saved-route-mini-path" d="${path}"></path>`;
          }).join("")}
          ${located.map((entry) => `
            <g class="saved-route-mini-marker" transform="translate(${roundSvg(entry.point.x)} ${roundSvg(entry.point.y)})">
              <title>${escapeHtml(`${entry.order}번 ${mapPointDisplayName(entry.place)}`)}</title>
              <circle r="5.2"></circle>
              <text x="0" y="0.6">${entry.order}</text>
            </g>
          `).join("")}
        </svg>
      </div>
      <figcaption>
        <span>코스 위치 미리보기</span>
        <b>${located.length}/${places.length}곳 좌표 표시</b>
        ${located.length < places.length ? "<small>좌표가 없는 장소 앞뒤 동선은 연결하지 않습니다.</small>" : ""}
        <a class="saved-route-map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">지도 데이터 © OpenStreetMap contributors</a>
      </figcaption>
    </figure>
  `;
}

function localTodayValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 10);
}

function sameRouteSpotIds(left, right) {
  return left.length === right.length && left.every((spotId, index) => spotId === right[index]);
}

function scenarioForRouteSpotIds(spotIds) {
  return (state.data?.scenarios || []).find((scenario) => (
    sameRouteSpotIds(currentRouteSpotIds(scenario), spotIds)
  )) || null;
}

function canOpenSavedRoute(item) {
  if (!item?.spotIds?.length) {
    return false;
  }
  return sameRouteSpotIds(currentRouteSpotIds(), item.spotIds)
    || Boolean(scenarioForRouteSpotIds(item.spotIds));
}

function openSavedRoute(routeId) {
  const item = state.savedRoutes.find((saved) => saved.id === routeId)
    || (state.sharedRoutePreview?.id === routeId ? state.sharedRoutePreview : null);
  if (!item) {
    announceSavedRoute("다시 볼 코스를 찾지 못했습니다.");
    return false;
  }

  const isCurrentRoute = sameRouteSpotIds(currentRouteSpotIds(), item.spotIds);
  if (!isCurrentRoute) {
    const scenario = scenarioForRouteSpotIds(item.spotIds);
    if (!scenario) {
      announceSavedRoute("이 코스는 저장함의 장소 목록과 방문 체크에서 다시 볼 수 있습니다.");
      return false;
    }
    state.scenarioId = scenario.id;
    state.runtimeScenario = null;
    state.conceptFocus = null;
    state.profile = profileFromScenario(scenario);
    setApiState("static", "저장한 추천 코스를 다시 열었습니다.");
  }

  state.selectedSpotId = (SAVED_TRIPS?.orderedSpotIds(item) || item.spotIds)
    .find((spotId) => allowedSavedSpotIds().has(spotId)) || null;
  state.mapPopupSpotId = null;
  state.detailCollapsed = false;
  cancelGroundedAiExplanation();
  render();

  closeSavedRoutesModal({ restoreFocus: false });
  navigateToSection("recommend", "#recommendations", { updateLocation: true });
  return true;
}

function savedRouteChecklist(item) {
  if (!SAVED_TRIPS) {
    return [];
  }
  const result = [];
  savedRoutePlaces(item).forEach((place) => {
    if (place.unavailable) {
      return;
    }
    const labels = [
      "운영시간과 임시휴관 여부",
      "주차·출입 동선 이용 가능 여부",
      "화장실·휴식 공간 이용 가능 여부"
    ];
    labels.forEach((label) => {
      const id = SAVED_TRIPS.checkId(place.spot_id, label);
      if (!result.some((check) => check.id === id)) {
        result.push({ id, spotId: place.spot_id, placeName: place.name, label });
      }
    });
  });
  return result.slice(0, 12);
}

function updateSavedRouteCheck(routeId, checkId, checked, focusContainerId = "") {
  if (!SAVED_TRIPS) {
    return;
  }
  state.savedRoutes = SAVED_TRIPS.updateCheck(
    state.savedRoutes,
    routeId,
    checkId,
    checked,
    allowedSavedSpotIds()
  );
  persistSavedRoutes("방문 전 체크 상태를 저장했습니다.");
  refreshSavedRouteViews();
  window.requestAnimationFrame(() => {
    const scope = document.getElementById(focusContainerId) || document;
    const checkbox = Array.from(scope.querySelectorAll("[data-saved-route-id][data-saved-check-id]")).find((item) => (
      item.dataset.savedRouteId === routeId && item.dataset.savedCheckId === checkId
    ));
    checkbox?.focus();
  });
}

function updateSavedRouteItinerary(routeId, date, startTime) {
  if (!SAVED_TRIPS) {
    return;
  }
  state.savedRoutes = SAVED_TRIPS.updateItinerary(
    state.savedRoutes,
    routeId,
    { date, startTime },
    allowedSavedSpotIds()
  );
  persistSavedRoutes("여행 일정을 이 기기에 저장했습니다.");
}

function moveSavedRouteSpot(routeId, spotId, direction) {
  if (!SAVED_TRIPS) {
    return;
  }
  if (![-1, 1].includes(direction)) {
    return;
  }
  const item = state.savedRoutes.find((saved) => saved.id === routeId);
  if (!item) {
    announceSavedRoute("순서를 변경할 코스를 찾지 못했습니다.");
    return;
  }
  const orderedSpotIds = SAVED_TRIPS.orderedSpotIds(item);
  const index = orderedSpotIds.indexOf(spotId);
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || nextIndex >= orderedSpotIds.length) {
    return;
  }
  [orderedSpotIds[index], orderedSpotIds[nextIndex]] = [orderedSpotIds[nextIndex], orderedSpotIds[index]];
  state.savedRoutes = SAVED_TRIPS.updateSpotOrder(
    state.savedRoutes,
    routeId,
    orderedSpotIds,
    allowedSavedSpotIds()
  );
  persistSavedRoutes("방문 순서를 변경했습니다.");
  renderSavedRoutesModal();
  window.requestAnimationFrame(() => {
    const buttons = Array.from(document.querySelectorAll("[data-move-saved-route]")).filter((itemButton) => (
      itemButton.dataset.moveSavedRoute === routeId
      && itemButton.dataset.moveSavedSpot === spotId
    ));
    const button = buttons.find((itemButton) => (
      !itemButton.disabled && Number(itemButton.dataset.moveDirection) === direction
    )) || buttons.find((itemButton) => !itemButton.disabled);
    button?.focus();
  });
}

function focusSavedRouteDeleteButton(routeId) {
  window.requestAnimationFrame(() => {
    const button = Array.from(document.querySelectorAll("[data-delete-saved-route]")).find((item) => (
      item.dataset.deleteSavedRoute === routeId
    ));
    button?.focus();
  });
}

function clearSavedRouteDeleteConfirmation({ clearMessage = false } = {}) {
  const hadPendingDelete = Boolean(state.pendingSavedRouteDeleteId);
  window.clearTimeout(savedRouteDeleteTimer);
  savedRouteDeleteTimer = null;
  state.pendingSavedRouteDeleteId = null;
  if (clearMessage && hadPendingDelete) {
    state.savedRouteMessage = "";
  }
}

function requestDeleteSavedRoute(routeId) {
  if (!SAVED_TRIPS) {
    return;
  }
  if (state.pendingSavedRouteDeleteId !== routeId) {
    clearSavedRouteDeleteConfirmation();
    state.pendingSavedRouteDeleteId = routeId;
    announceSavedRoute("삭제 버튼을 한 번 더 누르면 이 코스가 삭제됩니다.");
    savedRouteDeleteTimer = window.setTimeout(() => {
      savedRouteDeleteTimer = null;
      const keepFocus = document.activeElement?.dataset?.deleteSavedRoute === routeId;
      state.pendingSavedRouteDeleteId = null;
      announceSavedRoute("삭제 확인이 취소되었습니다.");
      renderSavedRoutesModal();
      if (keepFocus) {
        focusSavedRouteDeleteButton(routeId);
      }
    }, 3500);
    renderSavedRoutesModal();
    focusSavedRouteDeleteButton(routeId);
    return;
  }
  clearSavedRouteDeleteConfirmation();
  state.savedRoutes = SAVED_TRIPS.remove(state.savedRoutes, routeId, allowedSavedSpotIds());
  persistSavedRoutes("저장한 코스를 삭제했습니다.");
  refreshSavedRouteViews();
}

function formatSavedRouteDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "저장일 확인 필요";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(date);
}

function savedRouteCardMarkup(item, { shared = false } = {}) {
  const places = savedRoutePlaces(item);
  const checks = savedRouteChecklist(item);
  const checkedIds = new Set(item.checkedIds || []);
  const completed = checks.filter((check) => checkedIds.has(check.id)).length;
  const confirmingDelete = state.pendingSavedRouteDeleteId === item.id;
  const canOpen = canOpenSavedRoute(item);
  const itinerary = item.itinerary || {};
  const routeUrl = kakaoRouteUrl(places);
  const stayMinutes = savedRouteStayMinutes(item);
  const unavailableCount = places.filter((place) => place.unavailable).length;
  const shareable = shareableSavedSpotIds();
  const canShare = unavailableCount === 0
    && item.spotIds?.every((spotId) => shareable.has(spotId));
  return `
    <article class="saved-route-card ${shared ? "shared" : ""}" data-saved-route-card="${escapeHtml(item.id)}">
      <header>
        <div>
          <span>${shared ? "공유받은 코스" : escapeHtml(formatSavedRouteDate(item.savedAt))}</span>
          <h3>${escapeHtml(shared ? "공유받은 제주 추천 코스" : savedRouteTitle(item))}</h3>
        </div>
        <b>${places.length}곳</b>
      </header>
      <ol class="saved-route-places" aria-label="${shared ? "공유받은 코스 방문 순서" : "저장한 코스 방문 순서"}">
        ${places.map((place, index) => {
          const duration = Number(place?.effort?.recommended_duration_minutes);
          const infoUrl = placeInfoUrl(place);
          const reservationUrl = placeReservationUrl(place);
          const phoneHref = safePhoneHref(place?.visit_info?.phone);
          const pointLabel = hasSpecialPointRole(place.location) ? locationPointLabel(place.location) : "";
          return `
            <li class="${place.unavailable ? "unavailable" : ""}">
              <i>${index + 1}</i>
              <div class="saved-route-place-main">
                <span class="saved-route-place-copy">
                  <b>${escapeHtml(place.name)}</b>
                  <small>${escapeHtml([
                    place.visit_info?.address || place.region || "제주",
                    pointLabel,
                    place.unavailable
                      ? "저장 기록은 유지됩니다"
                      : (Number.isFinite(duration) && duration > 0 ? `체류 ${formatTravelMinutes(duration)}` : "체류시간 확인")
                   ].filter(Boolean).join(" · "))}</small>
                </span>
                <div class="saved-route-place-actions">
                  ${!shared ? `
                    <div class="saved-route-order-actions" role="group" aria-label="${escapeHtml(place.name)} 방문 순서 변경">
                      <span class="saved-route-action-label">순서 변경</span>
                      <button type="button" data-move-saved-route="${escapeHtml(item.id)}" data-move-saved-spot="${escapeHtml(place.spot_id)}" data-move-direction="-1" aria-label="${escapeHtml(place.name)} 순서를 위로 이동" ${index === 0 ? "disabled" : ""}><i class="bi bi-chevron-up" aria-hidden="true"></i><span>위로</span></button>
                      <button type="button" data-move-saved-route="${escapeHtml(item.id)}" data-move-saved-spot="${escapeHtml(place.spot_id)}" data-move-direction="1" aria-label="${escapeHtml(place.name)} 순서를 아래로 이동" ${index === places.length - 1 ? "disabled" : ""}><i class="bi bi-chevron-down" aria-hidden="true"></i><span>아래로</span></button>
                    </div>
                  ` : ""}
                  <div class="saved-route-place-links" role="group" aria-label="${escapeHtml(place.name)} 장소 바로가기">
                    ${place.unavailable
                      ? `<span class="saved-route-place-unavailable">현재 정보 없음</span>`
                      : `<a class="saved-route-map-link" href="${escapeHtml(kakaoPlaceUrl(place))}" target="_blank" rel="noopener noreferrer" aria-label="카카오맵에서 ${escapeHtml(place.name)} 보기"><i class="bi bi-map" aria-hidden="true"></i><span>지도</span></a>`}
                    ${!place.unavailable && infoUrl ? `<a href="${escapeHtml(infoUrl)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHtml(place.name)} 정보 확인"><i class="bi bi-info-circle" aria-hidden="true"></i><span>정보</span></a>` : ""}
                    ${!place.unavailable && phoneHref ? `<a href="${escapeHtml(phoneHref)}" aria-label="${escapeHtml(place.name)} 전화 연결"><i class="bi bi-telephone" aria-hidden="true"></i><span>전화</span></a>` : ""}
                    ${!place.unavailable && reservationUrl ? `<a href="${escapeHtml(reservationUrl)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHtml(place.name)} 예약하기"><i class="bi bi-calendar-check" aria-hidden="true"></i><span>예약</span></a>` : ""}
                  </div>
                </div>
              </div>
            </li>
          `;
        }).join("")}
      </ol>
      ${savedRouteMiniMapMarkup(item, places)}
      ${shared ? `
        <p class="saved-route-share-note">공유 링크에는 공개 장소 ID만 포함되며 개인 조건·일정·체크 상태는 포함되지 않습니다.</p>
      ` : `
        <section class="saved-route-itinerary" aria-label="여행 일정 설정">
          <header>
            <span><i class="bi bi-calendar2-check" aria-hidden="true"></i> 여행 준비</span>
            <b>예상 체류 ${escapeHtml(formatTravelMinutes(stayMinutes))}</b>
          </header>
          <div class="saved-route-schedule-fields">
            <label>
              <span>여행 날짜</span>
              <input type="date" value="${escapeHtml(itinerary.date || "")}" min="${escapeHtml(localTodayValue())}" data-saved-trip-date="${escapeHtml(item.id)}">
            </label>
            <label>
              <span>시작 시간</span>
              <input type="time" value="${escapeHtml(itinerary.startTime || "")}" data-saved-start-time="${escapeHtml(item.id)}">
            </label>
          </div>
          <div class="saved-route-plan-actions">
            ${routeUrl
              ? `<a href="${escapeHtml(routeUrl)}" target="_blank" rel="noopener noreferrer"><i class="bi bi-sign-turn-right" aria-hidden="true"></i> 카카오맵 자동차 경로</a>`
              : `<span><i class="bi bi-geo-alt" aria-hidden="true"></i> 좌표가 부족한 장소는 위의 ‘지도’에서 검색하세요.</span>`}
          </div>
          <p>예상 체류에는 이동시간이 포함되지 않습니다. 날짜·시간·변경한 순서는 이 기기에만 저장되며 공유되지 않습니다.</p>
          ${unavailableCount ? `<p class="saved-route-availability-note">현재 정보를 찾을 수 없는 장소 ${unavailableCount}곳은 기록만 보존되며, 정보가 복구될 때까지 이 코스는 공유할 수 없습니다.</p>` : ""}
        </section>
        <fieldset class="saved-route-checklist">
          <legend>방문 전 체크 <span>${completed}/${checks.length}</span></legend>
          ${checks.map((check) => `
            <label>
              <input type="checkbox" data-saved-route-id="${escapeHtml(item.id)}" data-saved-check-id="${escapeHtml(check.id)}" ${checkedIds.has(check.id) ? "checked" : ""}>
              <span><small>${escapeHtml(check.placeName)}</small>${escapeHtml(check.label)}</span>
            </label>
          `).join("")}
        </fieldset>
      `}
      <footer>
        ${shared ? `
          ${canOpen ? `<button class="outline-button" type="button" data-open-saved-route="${escapeHtml(item.id)}">코스 보기</button>` : ""}
          <button class="primary-button" type="button" data-save-shared-route>내 저장함에 추가</button>
        ` : `
          ${canOpen ? `<button class="primary-button" type="button" data-open-saved-route="${escapeHtml(item.id)}">원본 추천 상세</button>` : ""}
          ${canShare ? `<button class="outline-button" type="button" data-share-saved-route="${escapeHtml(item.id)}">공유 링크</button>` : ""}
          <button class="saved-route-delete-button ${confirmingDelete ? "confirm" : ""}" type="button" data-delete-saved-route="${escapeHtml(item.id)}">${confirmingDelete ? "한 번 더 삭제" : "삭제"}</button>
        `}
      </footer>
    </article>
  `;
}

function renderSavedRouteControls() {
  const count = state.savedRoutes.length;
  const countNode = document.getElementById("savedRoutesCount");
  if (countNode) {
    countNode.textContent = String(count);
  }
  document.querySelectorAll("[data-open-saved-routes]").forEach((button) => {
    button.setAttribute("aria-label", `저장한 추천 코스 ${count}개 보기`);
  });
  const saved = Boolean(currentSavedRoute());
  document.querySelectorAll("[data-save-current-route]").forEach((button) => {
    button.classList.toggle("saved", saved);
    button.setAttribute("aria-pressed", String(saved));
    button.setAttribute("aria-label", saved ? "저장한 코스 열기" : "현재 추천 코스 저장");
    const label = button.querySelector("[data-save-current-route-label]");
    if (label) {
      label.textContent = saved ? "저장됨" : "코스 저장";
    }
    const icon = button.querySelector("i");
    if (icon) {
      icon.className = `bi ${saved ? "bi-bookmark-check-fill" : "bi-bookmark-plus"}`;
    }
    const note = button.querySelector("small");
    if (note) {
      note.textContent = saved
        ? "저장함에서 방문 전 체크를 이어갈 수 있습니다."
        : "개인 조건 없이 장소 목록만 이 기기에 저장합니다.";
    }
  });
}

function refreshSavedRouteViews() {
  renderSavedRouteControls();
  renderSavedRoutesModal();
  if (state.data) {
    renderDetail(currentScenario());
  }
}

function renderSavedRoutesModal() {
  const list = document.getElementById("savedRoutesList");
  if (!list) {
    return;
  }
  const sharedMarkup = state.sharedRoutePreview
    ? savedRouteCardMarkup(state.sharedRoutePreview, { shared: true })
    : "";
  const savedMarkup = state.savedRoutes.map((item) => savedRouteCardMarkup(item)).join("");
  list.innerHTML = sharedMarkup + savedMarkup || `
    <section class="saved-routes-empty">
      <i class="bi bi-bookmark-heart" aria-hidden="true"></i>
      <h3>저장한 코스가 없습니다</h3>
      <p>추천 결과에서 ‘코스 저장’을 누르면 이 기기에서 다시 볼 수 있습니다.</p>
    </section>
  `;
  const status = document.getElementById("savedRoutesStatus");
  if (status) {
    status.textContent = state.savedRouteMessage;
  }
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
    const category = categoryLabels[place.category] || "추천 장소";
    const stayTip = cleanDisplayText(routeItem.stay_tip || "");
    return {
      order: Number(routeItem.order || index + 1),
      spotId: place.spot_id || routeItem.spot_id || "",
      name: place.name || routeItem.name || "추천 장소",
      category,
      detail: [category, stayTip].filter(Boolean).join(" · "),
      durationMinutes: Math.max(0, Number(place?.effort?.recommended_duration_minutes || place?.duration_minutes) || 0),
      verified: verificationLabel(place),
      located: validLocation(place.location),
      visual: visualForPlace(place, usedSources)
    };
  });
}

function conceptRecipeProfile(scenarioId = state.scenarioId) {
  return conceptRecipeProfiles[scenarioId] || conceptRecipeProfiles.recovery_quiet;
}

function conceptPreferenceChipMarkup(profile, option) {
  const selected = hasProfileValue(profile, option.key, [option.value]);
  const prioritized = conceptFocusKey() === conceptFocusKey(option);
  return `
    <button class="concept-preference-chip ${selected ? "active" : ""} ${prioritized ? "is-priority" : ""}" type="button" data-concept-focus-key="${escapeHtml(option.key)}" data-concept-focus-value="${escapeHtml(option.value)}" data-concept-focus-label="${escapeHtml(option.label)}" aria-pressed="${prioritized ? "true" : "false"}" aria-label="${escapeHtml(option.label)} 기준을 추천에 우선 반영">
      ${escapeHtml(option.label)}
    </button>
  `;
}

function conceptPreferenceSentencesMarkup(profile, recipe) {
  return `
    <p>
      <span>나는</span>
      ${conceptPreferenceChipMarkup(profile, recipe.companion)}
      ${conceptPreferenceChipMarkup(profile, recipe.pace)}
      <span>여행해요</span>
    </p>
    <p>
      <span>한 번에</span>
      ${conceptPreferenceChipMarkup(profile, recipe.distance)}
      <span>이동하고</span>
      ${conceptPreferenceChipMarkup(profile, recipe.setting)}
      <span>로 둘러봐요</span>
    </p>
    <p>
      ${recipe.essentials.map((option) => conceptPreferenceChipMarkup(profile, option)).join("")}
      <span>은 꼭 필요해요</span>
    </p>
  `;
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

function conceptTravelTimeSnapshot(scenario) {
  const entries = routeCoordinateEntries(scenario);
  if (entries.length < 2) {
    return { entries, routeKey: "", label: "시간 확인 필요" };
  }
  return {
    entries,
    routeKey: routeEntriesCacheKey(entries),
    label: formatDurationMinutes(fallbackRouteSummary(entries).durationMinutes)
  };
}

function updateConceptTravelTime(snapshot) {
  if (!snapshot.routeKey || !shouldRequestRouteProxy()) {
    return;
  }
  cachedRouteSummaryWithRoadGeometry(snapshot.entries).then((summary) => {
    const currentEntries = routeCoordinateEntries(currentScenario());
    const currentRouteKey = currentEntries.length >= 2 ? routeEntriesCacheKey(currentEntries) : "";
    const target = document.querySelector("[data-concept-travel-time]");
    if (
      currentRouteKey !== snapshot.routeKey
      || target?.dataset.conceptTravelRouteKey !== snapshot.routeKey
    ) {
      return;
    }
    const value = target.querySelector("strong");
    if (value) {
      value.textContent = formatDurationMinutes(summary.durationMinutes);
    }
  }).catch(() => {});
}

function renderConceptPage(scenario) {
  const grid = document.getElementById("conceptGrid");
  const activeScenario = scenario || scenarioById(state.scenarioId);
  if (grid) {
    const visibleCards = state.conceptPanelOpen
      ? scenarioCards.filter((card) => card.id === state.scenarioId)
      : scenarioCards;
    grid.innerHTML = visibleCards.map((card) => {
      const index = scenarioCards.findIndex((item) => item.id === card.id);
      const cardScenario = scenarioById(card.id);
      const active = state.conceptPanelOpen && card.id === state.scenarioId;
      return `
        <button class="concept-card ${card.tone} ${active ? "active" : ""}" type="button" data-concept-id="${escapeHtml(card.id)}" aria-label="${escapeHtml(card.title)} 테마 추천 미리보기" aria-pressed="${active ? "true" : "false"}">
          ${active ? '<span class="concept-selected-badge">선택됨</span>' : ""}
          <span class="concept-card-index">${String(index + 1).padStart(2, "0")}</span>
          <strong>${escapeHtml(card.title)}</strong>
          <small>${escapeHtml(card.body)}</small>
          <span class="concept-card-visual" aria-hidden="true">
            <img class="concept-card-line-art" src="${escapeHtml(card.lineArt)}" alt="" loading="eager" decoding="async">
            <img class="concept-card-character" src="${escapeHtml(card.character)}" alt="" loading="eager" decoding="async">
          </span>
          <span class="concept-card-divider" aria-hidden="true"></span>
          <span class="concept-card-score-row">
            <span class="concept-card-shield" aria-hidden="true">
              <i class="bi bi-shield"></i>
              <i class="bi bi-heart-fill"></i>
            </span>
            <em>${escapeHtml(conceptCardScoreText(cardScenario))}</em>
          </span>
          <span class="concept-card-submeta">${escapeHtml(conceptCardMetaText(cardScenario))}</span>
        </button>
      `;
    }).join("");
  }

  const card = scenarioCardById(state.scenarioId);
  const recipe = conceptRecipeProfile(state.scenarioId);
  const profile = normalizeProfile(state.profile || activeScenario?.traveler_summary);
  const previewPlaces = conceptPreviewPlaces(activeScenario, 4);
  const summaryBadge = document.getElementById("conceptSummaryBadge");
  const summaryTitle = document.getElementById("conceptSummaryTitle");
  const summaryText = document.getElementById("conceptSummaryText");
  const summaryProof = document.getElementById("conceptSummaryProof");
  const preferenceSentences = document.getElementById("conceptPreferenceSentences");
  const summaryPlaces = document.getElementById("conceptSummaryPlaces");
  const fitNote = document.getElementById("conceptFitNote");
  const primaryCharacter = document.getElementById("conceptRecipeCharacterPrimary");
  const score = Number(activeScenario?.recommendation?.score?.total);
  const scoreText = Number.isFinite(score) ? Math.round(score) : "-";
  const verifiedCount = previewPlaces.filter((place) => place.verified !== "확인 필요").length;
  const travelTime = conceptTravelTimeSnapshot(activeScenario);

  if (summaryBadge) {
    summaryBadge.textContent = `${card.title} 테마`;
  }
  if (summaryTitle) {
    summaryTitle.textContent = activeScenario?.recommendation?.course?.title || activeScenario?.title || card.title;
  }
  if (summaryText) {
    summaryText.textContent = recipe.subtitle;
  }
  if (summaryProof) {
    summaryProof.innerHTML = `
      <span><strong>${escapeHtml(String(previewPlaces.length))}</strong><b>곳 추천</b></span>
      <span><b>검증</b><strong>${escapeHtml(String(verifiedCount))}/${escapeHtml(String(previewPlaces.length))}</strong></span>
      <span data-concept-travel-time data-concept-travel-route-key="${escapeHtml(travelTime.routeKey)}"><b>예상 이동</b><strong>${escapeHtml(travelTime.label)}</strong></span>
    `;
    updateConceptTravelTime(travelTime);
  }
  if (preferenceSentences) {
    preferenceSentences.innerHTML = conceptPreferenceSentencesMarkup(profile, recipe);
  }
  if (summaryPlaces) {
    summaryPlaces.innerHTML = previewPlaces.length ? previewPlaces.map((place) => `
      <button class="concept-preview-item ${place.located ? "located" : "needs-check"}" type="button" data-concept-place-id="${escapeHtml(place.spotId)}" aria-label="${escapeHtml(place.order)}번째 장소 ${escapeHtml(place.name)} 자세히 보기">
        <span class="concept-preview-order">${escapeHtml(place.order)}</span>
        <img class="concept-preview-image${place.visual.fit === "contain" ? " is-contain" : ""}" src="${escapeHtml(place.visual.src)}" alt="${escapeHtml(place.visual.alt)}" loading="lazy" decoding="async" data-fallback-src="${escapeHtml(place.visual.fallbackSrc)}" data-fallback-caption="${escapeHtml(place.visual.fallbackCaption)}" data-fallback-source="${escapeHtml(place.visual.fallbackSource)}">
        <span class="concept-preview-copy">
          <b>${escapeHtml(place.name)}</b>
          <small>${escapeHtml(place.detail || place.category)}${place.durationMinutes ? ` · ${escapeHtml(String(place.durationMinutes))}분` : ""}</small>
        </span>
        <i class="bi bi-chevron-right" aria-hidden="true"></i>
      </button>
    `).join("") : `
      <div class="concept-preview-empty" role="status">
        <i class="bi bi-shield-exclamation" aria-hidden="true"></i>
        <strong>공식 근거가 확인된 장소가 없습니다.</strong>
        <span>근거가 부족한 장소를 대신 보여드리지 않아요. 다른 조건을 선택해 주세요.</span>
      </div>
    `;
  }
  if (fitNote) {
    const focusText = state.conceptFocus?.label
      ? `<b>${escapeHtml(state.conceptFocus.label)}</b> 기준 우선 · `
      : "";
    fitNote.innerHTML = `<i class="bi bi-info-circle" aria-hidden="true"></i> ${focusText}현재 조건으로 접근성 적합도 <strong>${escapeHtml(String(scoreText))}%</strong>`;
  }
  if (primaryCharacter) {
    primaryCharacter.src = card.character;
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
  const wasOpen = state.conceptPanelOpen;
  state.conceptPanelOpen = false;
  syncStepViewState();
  if (wasOpen && state.data) {
    renderConceptPage(currentScenario());
  }
}

function restoreSelectedConceptFocus() {
  window.requestAnimationFrame(() => {
    const selectedCard = Array.from(document.querySelectorAll("[data-concept-id]"))
      .find((card) => card.dataset.conceptId === state.scenarioId);
    selectedCard?.focus();
  });
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

function aiStatusBadge(status) {
  return {
    idle: "생성 전",
    loading: "생성 중",
    success: "근거 연결 완료",
    disabled: "AI 연결 준비 필요",
    error: "생성 실패",
    ungrounded: "근거 부족",
    local: "검색·점수 기반"
  }[status] || "검색·점수 기반";
}

function aiStatusIcon(status) {
  return {
    idle: "bi-stars",
    loading: "bi-arrow-repeat",
    success: "bi-patch-check-fill",
    disabled: "bi-plug",
    error: "bi-exclamation-triangle",
    ungrounded: "bi-shield-exclamation"
  }[status] || "bi-info-circle";
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

function aiCitationItems(scenario, spotId) {
  const citations = Array.isArray(scenario?.ai_summary?.citations)
    ? scenario.ai_summary.citations
    : [];
  return citations.reduce((items, citation) => {
    if (!citation || (spotId && citation.spot_id !== spotId)) {
      return items;
    }
    const sourceUrl = safeExternalUrl(citation.source_url);
    if (!sourceUrl) {
      return items;
    }
    items.push({
      evidenceId: String(citation.evidence_id || ""),
      title: String(citation.source_title || "공식 근거"),
      url: sourceUrl,
      checkedAt: /^\d{4}-\d{2}-\d{2}$/.test(String(citation.checked_at || ""))
        ? String(citation.checked_at)
        : "확인일 재검토 필요",
      status: String(citation.verification_status || "needs_check")
    });
    return items;
  }, []).slice(0, 4);
}

function aiClaimCitationGroups(scenario) {
  const claims = Array.isArray(scenario?.ai_summary?.claim_citations)
    ? scenario.ai_summary.claim_citations
    : [];
  if (!claims.length) {
    return null;
  }

  const allowedSections = new Set(["rationale", "cautions", "next_checks"]);
  const evidenceNumbers = new Map();
  const groups = {};
  let nextEvidenceNumber = 1;

  claims.forEach((claim) => {
    const section = String(claim?.section || "");
    const index = Number(claim?.index);
    if (!allowedSections.has(section) || !Number.isInteger(index) || index < 0) {
      return;
    }

    const key = `${section}:${index}`;
    const seen = new Set();
    const citations = Array.isArray(claim?.citations) ? claim.citations : [];
    const safeCitations = citations.reduce((items, citation) => {
      const sourceUrl = safeExternalUrl(citation?.source_url);
      if (!sourceUrl) {
        return items;
      }
      const evidenceId = String(citation?.evidence_id || "");
      const identity = evidenceId || sourceUrl;
      if (seen.has(identity)) {
        return items;
      }
      seen.add(identity);

      if (!evidenceNumbers.has(identity)) {
        evidenceNumbers.set(identity, nextEvidenceNumber);
        nextEvidenceNumber += 1;
      }
      items.push({
        evidenceId,
        number: evidenceNumbers.get(identity),
        title: String(citation?.source_title || "공식 근거"),
        url: sourceUrl,
        checkedAt: /^\d{4}-\d{2}-\d{2}$/.test(String(citation?.checked_at || ""))
          ? String(citation.checked_at)
          : "확인일 재검토 필요"
      });
      return items;
    }, []).slice(0, 3);

    if (safeCitations.length) {
      groups[key] = safeCitations;
    }
  });
  return Object.keys(groups).length ? groups : null;
}

function retrievalEvidenceItems(scenario, spotId) {
  const matches = Array.isArray(scenario?.retrieval?.matches)
    ? scenario.retrieval.matches
    : [];
  const match = matches.find((item) => item?.spot_id === spotId);
  const sources = Array.isArray(match?.evidence_bundle?.sources)
    ? match.evidence_bundle.sources
    : [];
  return sources.reduce((items, source) => {
    const sourceUrl = safeExternalUrl(source?.url);
    if (!sourceUrl) {
      return items;
    }
    items.push({
      title: String(source.title || "공식 근거"),
      url: sourceUrl,
      checkedAt: /^\d{4}-\d{2}-\d{2}$/.test(String(source.checked_at || ""))
        ? String(source.checked_at)
        : "확인일 재검토 필요",
      status: String(source.status || "needs_check")
    });
    return items;
  }, []).slice(0, 4);
}

function aiCitationMarkup(citations) {
  if (!citations.length) {
    return "";
  }
  return `
    <div class="ai-citation-list">
      <strong>답변에 사용한 공식 근거</strong>
      <ul>${citations.map((citation) => `
        <li>
          <a href="${escapeHtml(citation.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(citation.title)}</a>
          <small>${escapeHtml(citation.checkedAt)} · ${escapeHtml(displayLabel(citation.status))}</small>
        </li>
      `).join("")}</ul>
    </div>
  `;
}

function aiClaimCitationMarkup(citations) {
  if (!citations.length) {
    return "";
  }
  return `
    <span class="ai-claim-citations" aria-label="이 문장의 공식 근거">
      ${citations.map((citation) => `
        <a href="${escapeHtml(citation.url)}" target="_blank" rel="noopener noreferrer" aria-label="근거 ${escapeHtml(citation.number)}: ${escapeHtml(citation.title)}, 확인일 ${escapeHtml(citation.checkedAt)}">
          <b>[${escapeHtml(citation.number)}]</b>
          <span>${escapeHtml(citation.title)}</span>
          <small>확인 ${escapeHtml(citation.checkedAt)}</small>
        </a>
      `).join("")}
    </span>
  `;
}

function aiReasonItemMarkup(item, section, index, claimCitationGroups) {
  const citations = claimCitationGroups?.[`${section}:${index}`] || [];
  return `
    <li class="${citations.length ? "has-claim-citations" : ""}" data-ai-claim-section="${escapeHtml(section)}" data-ai-claim-index="${escapeHtml(index)}">
      <span class="ai-claim-text">${escapeHtml(item)}</span>
      ${aiClaimCitationMarkup(citations)}
    </li>
  `;
}

function aiReasonSectionsMarkup(sections, citations = [], claimCitationGroups = null) {
  return `
    <div class="ai-reason-list">
      ${sections.reasons.length ? `
        <div>
          <strong>추천 근거</strong>
          <ul>${sections.reasons.map((item, index) => aiReasonItemMarkup(item, "rationale", index, claimCitationGroups)).join("")}</ul>
        </div>
      ` : ""}
      ${sections.cautions.length ? `
        <div>
          <strong>주의할 점</strong>
          <ul>${sections.cautions.map((item, index) => aiReasonItemMarkup(item, "cautions", index, claimCitationGroups)).join("")}</ul>
        </div>
      ` : ""}
      ${sections.nextChecks.length ? `
        <div>
          <strong>방문 전 확인</strong>
          <ul>${sections.nextChecks.map((item, index) => aiReasonItemMarkup(item, "next_checks", index, claimCitationGroups)).join("")}</ul>
        </div>
      ` : `<p>${escapeHtml(sections.fallback)}</p>`}
      ${claimCitationGroups ? "" : aiCitationMarkup(citations)}
    </div>
  `;
}

function aiExplanationPanelMarkup(scenario, generatedSections, localSections, citations) {
  if (scenario?.retrieval?.status !== "applied") {
    return `
      <section class="gpt-box" data-ai-explanation-status="local">
        <div class="detail-section-row ai">
          <h3>추천 근거</h3>
          <span>${escapeHtml(aiStatusBadge("local"))}</span>
        </div>
        <p>${escapeHtml(localSections.headline)}</p>
        ${aiReasonSectionsMarkup(localSections)}
      </section>
    `;
  }

  const explanationState = currentAiExplanationState(scenario);
  if (explanationState.status === "success") {
    const claimCitationGroups = aiClaimCitationGroups(scenario);
    const retrieval = scenario?.retrieval || {};
    const routeCount = selectedRoute(scenario).slice(0, RECOMMENDATION_LIMIT).length;
    return `
      <section class="gpt-box" id="generatedAiExplanation" data-ai-explanation-status="success" tabindex="-1">
        <div class="detail-section-row ai">
          <h3>${escapeHtml(AI_DISPLAY_NAME)} 코스 근거 설명</h3>
          <span>${escapeHtml(aiStatusBadge("success"))}</span>
        </div>
        <p>${escapeHtml(generatedSections.headline)}</p>
        <div class="ai-explanation-trace" aria-label="RAG 처리 요약">
          <span><small>검수 데이터</small><strong>${escapeHtml(ragCountLabel(retrieval.corpus_count))}</strong></span>
          <i class="bi bi-arrow-right" aria-hidden="true"></i>
          <span><small>검색 근거</small><strong>${escapeHtml(ragCountLabel(retrieval.retrieved_count))}</strong></span>
          <i class="bi bi-arrow-right" aria-hidden="true"></i>
          <span><small>추천 코스</small><strong>${escapeHtml(ragCountLabel(routeCount))}</strong></span>
        </div>
        ${aiReasonSectionsMarkup(generatedSections, citations, claimCitationGroups)}
      </section>
    `;
  }

  return `
    <section class="gpt-box" data-ai-explanation-status="${escapeHtml(explanationState.status)}">
      <div class="detail-section-row ai">
        <h3>공식 근거 AI 설명</h3>
        <span>${escapeHtml(aiStatusBadge(explanationState.status))}</span>
      </div>
      <div class="ai-state-message">
        <i class="bi ${escapeHtml(aiStatusIcon(explanationState.status))}" aria-hidden="true"></i>
        <p>${escapeHtml(explanationState.message)}</p>
      </div>
      <div class="ai-local-preview">
        <strong>현재 검색·점수 기반 추천 근거</strong>
        ${aiReasonSectionsMarkup(localSections)}
      </div>
    </section>
  `;
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
  const retrievalStatus = currentScenario()?.retrieval?.status;
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
    ? retrievalStatus === "resource_data_gap"
      ? "요청한 지원서비스는 아직 공식 근거 데이터가 부족해 관련 없는 장소를 대신 추천하지 않았습니다."
      : retrievalStatus === "no_match"
        ? "현재 검증된 장소에서 충분한 검색 근거를 찾지 못해 추천을 보류했습니다."
        : "선택한 조건에 맞춰 추천 코스와 상세 근거를 갱신했습니다."
    : status === "loading"
      ? "선택한 조건에 맞춰 접근성 점수를 다시 계산하고 있습니다."
      : status === "error"
        ? "실시간 계산에 실패해 사전 계산된 추천을 표시하고 있습니다. 잠시 후 다시 시도할 수 있습니다."
        : status === "static"
          ? "현재는 선택 조건과 가장 가까운 사전 계산 시나리오를 표시합니다."
          : "여행 조건을 선택하면 접근성 기준에 맞는 추천을 준비합니다.";

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

function activateCenterMapFallback(message = "외부 지도 연결 없이 로컬 지도로 표시합니다.") {
  const frame = document.querySelector("#mapPanel .map-frame");
  const art = document.getElementById("mapFallbackArt");
  const notice = document.getElementById("mapFallbackNotice");
  const noticeMessage = notice?.querySelector?.("[data-map-fallback-message]");
  const liveMap = document.getElementById("liveMap");
  if (!frame || !art) {
    return;
  }
  frame.classList.add("map-fallback-active");
  liveMap?.setAttribute("aria-hidden", "true");
  if (notice) {
    notice.hidden = false;
    if (noticeMessage) {
      noticeMessage.textContent = message;
    } else {
      notice.textContent = message;
    }
  }
  const sync = () => scheduleMapHitBoundsSync();
  if (art.complete && art.naturalWidth > 0) {
    sync();
  } else {
    art.addEventListener("load", sync, { once: true });
  }
}

function deactivateCenterMapFallback() {
  const frame = document.querySelector("#mapPanel .map-frame");
  const notice = document.getElementById("mapFallbackNotice");
  const liveMap = document.getElementById("liveMap");
  frame?.classList.remove("map-fallback-active");
  liveMap?.removeAttribute("aria-hidden");
  if (notice) {
    notice.hidden = true;
  }
}

function scheduleMapHitBoundsSync() {
  if (mapHitBoundsFrame) {
    return;
  }
  mapHitBoundsFrame = true;
  window.requestAnimationFrame(() => {
    mapHitBoundsFrame = false;
    syncMapHitBounds();
  });
}

function ensureCenterMap() {
  const mapElement = document.getElementById("liveMap");
  if (!mapElement) {
    return null;
  }
  if (!window.L) {
    activateCenterMapFallback("지도 라이브러리를 불러오지 못해 로컬 지도로 표시합니다.");
    return null;
  }
  if (!centerMap) {
    centerMap = L.map(mapElement, {
      zoomControl: false,
      scrollWheelZoom: false,
      dragging: true,
      touchZoom: true,
      attributionControl: true,
      zoomSnap: 0.25,
      zoomDelta: 0.5
    });
    L.control.zoom({ position: "topleft" }).addTo(centerMap);
    centerRouteLayerGroup = L.layerGroup().addTo(centerMap);
    centerMarkerLayerGroup = L.layerGroup().addTo(centerMap);
    centerMap.on("zoom move", scheduleMapHitBoundsSync);
    setCenterMapTileLayer(centerMapLayerMode);
    window.setTimeout(() => {
      centerMap?.invalidateSize();
      scheduleMapHitBoundsSync();
    }, 80);
  }
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
  centerTileErrorCount = 0;
  centerTileLayer = L.tileLayer(definition.url, definition.options)
    .on("loading", () => {
      centerTileErrorCount = 0;
    })
    .on("tileerror", () => {
      centerTileErrorCount += 1;
      if (centerTileErrorCount >= 3) {
        activateCenterMapFallback("지도 타일 연결이 원활하지 않아 로컬 지도로 표시합니다.");
      }
    })
    .on("load", () => {
      if (centerTileErrorCount < 3) {
        deactivateCenterMapFallback();
      }
    })
    .addTo(centerMap);
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

function liveMarkerIcon(index, active, location) {
  return L.divIcon({
    className: `live-marker-icon rank-${index + 1} ${active ? "active" : ""}`,
    html: `<span>${index + 1}</span>${pointRoleBadgeMarkup(location, "live-marker-role")}`,
    iconSize: [38, 38],
    iconAnchor: [19, 19]
  });
}

function routeGeometryWithStopAnchors(entries, geometry) {
  const routeGeometry = (Array.isArray(geometry) ? geometry : [])
    .filter((location) => Number.isFinite(Number(location?.latitude)) && Number.isFinite(Number(location?.longitude)));
  const stopLocations = (Array.isArray(entries) ? entries : [])
    .map((entry) => entry?.location)
    .filter((location) => Number.isFinite(Number(location?.latitude)) && Number.isFinite(Number(location?.longitude)));

  if (routeGeometry.length < 2) {
    return stopLocations;
  }
  if (stopLocations.length < 2) {
    return routeGeometry;
  }

  // Road providers snap waypoints to nearby roads. Keep the reviewed place
  // coordinates as markers and add short access legs so the route meets them.
  const anchorsByGeometryIndex = new Map();
  let searchStartIndex = 0;
  stopLocations.slice(1, -1).forEach((stop) => {
    let nearestIndex = searchStartIndex;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (let index = searchStartIndex; index < routeGeometry.length; index += 1) {
      const distance = haversineKm(stop, routeGeometry[index]);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    }
    if (!anchorsByGeometryIndex.has(nearestIndex)) {
      anchorsByGeometryIndex.set(nearestIndex, []);
    }
    anchorsByGeometryIndex.get(nearestIndex).push(stop);
    searchStartIndex = nearestIndex;
  });

  const alignedGeometry = [];
  const appendDistinct = (location) => {
    const previous = alignedGeometry[alignedGeometry.length - 1];
    if (
      previous
      && Number(previous.latitude) === Number(location.latitude)
      && Number(previous.longitude) === Number(location.longitude)
    ) {
      return;
    }
    alignedGeometry.push(location);
  };

  appendDistinct(stopLocations[0]);
  routeGeometry.forEach((location, index) => {
    appendDistinct(location);
    (anchorsByGeometryIndex.get(index) || []).forEach((stop) => {
      appendDistinct(stop);
    });
  });
  appendDistinct(stopLocations[stopLocations.length - 1]);
  return alignedGeometry;
}

function clearCenterMapLayers() {
  centerRouteLayerGroup?.clearLayers();
  centerMarkerLayerGroup?.clearLayers();
  centerMarkersBySpotId.clear();
  centerMapRenderedRouteKey = null;
  centerMapLastFitKey = null;
}

function syncCenterMapMarkerSelection(entries) {
  entries.forEach((entry, index) => {
    const marker = centerMarkersBySpotId.get(entry.place.spot_id);
    marker?.setIcon?.(liveMarkerIcon(
      index,
      entry.place.spot_id === state.mapPopupSpotId,
      entry.location
    ));
  });
}

function drawCenterMap(entries, summary, options = {}) {
  const map = centerMap;
  if (!map || !centerRouteLayerGroup || !centerMarkerLayerGroup || entries.length === 0) {
    return;
  }
  const routeKey = options.routeKey || routeEntriesCacheKey(entries);
  centerRouteLayerGroup.clearLayers();
  const geometry = routeGeometryWithStopAnchors(entries, summary.geometry);
  const lineLatLngs = geometry.map((location) => [Number(location.latitude), Number(location.longitude)]);
  const markerLatLngs = entries.map((entry) => [Number(entry.location.latitude), Number(entry.location.longitude)]);

  if (lineLatLngs.length >= 2) {
    L.polyline(lineLatLngs, {
      color: "#ffffff",
      weight: 13,
      opacity: 0.94,
      smoothFactor: 0,
      lineCap: "round",
      lineJoin: "round"
    }).addTo(centerRouteLayerGroup);
    L.polyline(lineLatLngs, {
      color: ROUTE_KEY_COLOR,
      weight: 6,
      opacity: 0.96,
      smoothFactor: 0,
      lineCap: "round",
      lineJoin: "round"
    }).addTo(centerRouteLayerGroup);
  }

  if (centerMapRenderedRouteKey !== routeKey) {
    centerMarkerLayerGroup.clearLayers();
    centerMarkersBySpotId.clear();
    entries.forEach((entry, index) => {
      const marker = L.marker([Number(entry.location.latitude), Number(entry.location.longitude)], {
        icon: liveMarkerIcon(index, entry.place.spot_id === state.mapPopupSpotId, entry.location),
        keyboard: true,
        title: mapPointDisplayName(entry.place),
        bubblingMouseEvents: false
      }).addTo(centerMarkerLayerGroup);
      centerMarkersBySpotId.set(entry.place.spot_id, marker);
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
    centerMapRenderedRouteKey = routeKey;
  } else {
    syncCenterMapMarkerSelection(entries);
  }

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
    scheduleMapHitBoundsSync();
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
  const key = routeEntriesCacheKey(entries);

  if (entries.length < 2) {
    centerMapRenderSequence += 1;
    clearCenterMapLayers();
    renderLiveMapStats(entries, fallbackRouteSummary(entries), "좌표 확인 필요");
    const status = document.getElementById("mapSyncStatus");
    if (status) {
      status.textContent = "실제 지도를 표시하려면 두 곳 이상의 좌표가 필요합니다.";
    }
    scheduleMapHitBoundsSync();
    return;
  }

  const map = ensureCenterMap();
  const fallback = fallbackRouteSummary(entries);
  if (!map) {
    centerMapRenderSequence += 1;
    renderLiveMapStats(entries, fallback, "로컬 지도");
    document.getElementById("mapSyncStatus").textContent = `로컬 지도: ${entries.length}개 좌표 연결, ${formatDistanceKm(fallback.distanceKm)}, ${formatDurationMinutes(fallback.durationMinutes)}`;
    scheduleMapHitBoundsSync();
    return;
  }

  if (centerMapRenderedRouteKey === key) {
    syncCenterMapMarkerSelection(entries);
    scheduleMapHitBoundsSync();
    return;
  }

  const shouldFit = centerMapLastFitKey !== key;
  centerMapLastFitKey = key;
  const sequence = ++centerMapRenderSequence;

  drawCenterMap(entries, fallback, { fit: shouldFit, routeKey: key });
  renderLiveMapStats(entries, fallback, shouldRequestRouteProxy() ? "경로 계산 중" : "좌표 기반");
  document.getElementById("mapSyncStatus").textContent = `실제 지도: ${entries.length}개 좌표 연결, ${formatDistanceKm(fallback.distanceKm)}, ${formatDurationMinutes(fallback.durationMinutes)}`;

  if (!shouldRequestRouteProxy()) {
    return;
  }

  runWhenBrowserIdle(() => {
    const activeKey = routeEntriesCacheKey(routeCoordinateEntries(currentScenario()));
    if (sequence !== centerMapRenderSequence || activeKey !== key) {
      return;
    }
    cachedRouteSummaryWithRoadGeometry(entries).then((summary) => {
      const latestKey = routeEntriesCacheKey(routeCoordinateEntries(currentScenario()));
      if (
        sequence !== centerMapRenderSequence
        || latestKey !== key
        || centerMapRenderedRouteKey !== key
      ) {
        return;
      }
      const statusLabel = summary.provider === "coordinate_fallback" ? "좌표 기반" : "도로 경로";
      drawCenterMap(entries, summary, { fit: false, routeKey: key });
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
  const frame = document.querySelector(".map-frame");
  const fallbackActive = frame?.classList.contains("map-fallback-active");
  if (document.getElementById("liveMap") && centerMap && !fallbackActive) {
    syncLiveMapPopup();
    return;
  }

  const art = document.querySelector(".map-art");
  if (!frame || !art || !art.naturalWidth || !art.naturalHeight) {
    return;
  }

  const frameWidth = art.clientWidth || frame.clientWidth;
  const frameHeight = art.clientHeight || frame.clientHeight;
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
  if (entries.length < 2 || !shouldRequestRouteProxy()) {
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
  if (routeSummaryCache.has(key)) {
    const cached = routeSummaryCache.get(key);
    routeSummaryCache.delete(key);
    routeSummaryCache.set(key, cached);
    return cached;
  }
  if (routeSummaryCache.size >= ROUTE_SUMMARY_CACHE_LIMIT) {
    const oldestKey = routeSummaryCache.keys().next().value;
    routeSummaryCache.delete(oldestKey);
  }
  const pending = routeSummaryWithRoadGeometry(entries);
  routeSummaryCache.set(key, pending);
  return pending;
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
      max: Number.isFinite(max) ? max : fallbackMax,
      reason: cleanDisplayText(item.reason || "세부 근거 확인 필요", 120)
    };
  });
}

function scoreCalculationTrace(place) {
  const raw = place?.score?.calculation_trace;
  if (!raw || typeof raw !== "object") {
    return null;
  }

  const baseTotal = Number(raw.base_total);
  const finalTotal = Number(raw.final_total);
  if (!Number.isFinite(baseTotal) || !Number.isFinite(finalTotal)) {
    return null;
  }

  const adjustments = [
    ...(Array.isArray(raw.bonuses) ? raw.bonuses : []),
    ...(Array.isArray(raw.deductions) ? raw.deductions : [])
  ].map((item) => ({
    label: cleanDisplayText(item?.label || "점수 조정", 120),
    delta: Number(item?.delta)
  })).filter((item) => Number.isFinite(item.delta) && item.delta !== 0);
  const caps = (Array.isArray(raw.caps) ? raw.caps : []).map((item) => ({
    label: cleanDisplayText(item?.label || "점수 상한 적용", 120),
    before: Number(item?.before),
    after: Number(item?.after)
  })).filter((item) => Number.isFinite(item.before) && Number.isFinite(item.after) && item.before !== item.after);

  return { baseTotal, adjustments, caps, finalTotal };
}

function signedScore(value) {
  return value > 0 ? `+${value}` : String(value);
}

function scenarioCardsMarkup(selectedScenarioId = state.scenarioId) {
  return scenarioCards.map((card) => `
    <button class="scenario-tile ${card.tone} ${card.id === selectedScenarioId ? "active" : ""}" type="button" data-scenario-id="${escapeHtml(card.id)}">
      <span class="scenario-tile-icon" aria-hidden="true"><i class="bi ${escapeHtml(card.iconClass)}"></i></span>
      <strong>${escapeHtml(card.title)}</strong>
      <small>${escapeHtml(card.body)}</small>
    </button>
  `).join("");
}

function renderScenarioCards() {
  [
    ["scenarioList", state.scenarioId],
    ["modalScenarioList", state.profileModalDraft?.scenarioId || state.scenarioId]
  ].forEach(([id, selectedScenarioId]) => {
    const container = document.getElementById(id);
    if (container) {
      container.innerHTML = scenarioCardsMarkup(selectedScenarioId);
    }
  });
}

function profileOptionsMarkup(sourceProfile = state.profile) {
  const profile = normalizeProfile(sourceProfile);
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
      container.innerHTML = profileOptionsMarkup(state.profileModalDraft?.profile || state.profile);
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

function ragIntentLabels(queryIntent) {
  if (!queryIntent || typeof queryIntent !== "object") {
    return ["입력 조건 기반 탐색"];
  }
  const intentLabels = {
    place_search: "장소 탐색",
    general_search: "일반 탐색",
    support_resource_search: "지원서비스 탐색",
    emergency_support: "긴급 지원 탐색"
  };
  const labels = [
    intentLabels[queryIntent.intent],
    ...(queryIntent.regions || []),
    ...(queryIntent.categories || []).map((category) => categoryLabels[category] || category),
    ...(queryIntent.signals?.emergency ? ["긴급 지원"] : []),
    ...(queryIntent.signals?.charging ? ["충전시설"] : [])
  ];
  return unique(labels.filter(Boolean)).slice(0, 8);
}

function ragCountLabel(value, suffix = "곳") {
  const count = Number(value);
  return Number.isFinite(count) ? `${Math.max(0, Math.round(count))}${suffix}` : "확인 중";
}

function ragEngineLabel(engine) {
  return String(engine || "").toLowerCase().includes("bm25")
    ? "BM25 + 구조화 조건 + 접근성 재정렬"
    : "근거 검색 + 접근성 재정렬";
}

function renderRagProcess(scenario) {
  const panel = document.getElementById("ragProcessPanel");
  if (!panel) {
    return;
  }
  const retrieval = scenario?.retrieval || {};
  const retrievalStatus = String(retrieval.status || "not_requested");
  const hasRetrievalTrace = ["applied", "no_match", "resource_data_gap"].includes(retrievalStatus);
  panel.hidden = false;
  if (!hasRetrievalTrace) {
    panel.innerHTML = `
      <header class="rag-process-header">
        <div>
          <span><i class="bi bi-diagram-3" aria-hidden="true"></i> 검증 가능한 추천</span>
          <h3 id="ragProcessTitle">RAG 검색 과정</h3>
          <p>원하는 지역·장소·접근성 조건을 입력하면 검수 데이터에서 근거를 찾아 추천합니다.</p>
        </div>
        <b class="rag-engine-badge">RAG 조건 입력 대기</b>
      </header>
      <div class="rag-process-onboarding">
        <i class="bi bi-chat-square-text" aria-hidden="true"></i>
        <div>
          <strong>아직 RAG 검색 전입니다.</strong>
          <p>‘제주시 실내 휠체어 화장실’처럼 입력하면 검색 후보와 출처를 이 영역에서 바로 보여드려요.</p>
        </div>
        <button class="grounded-ai-button rag-query-cta" type="button" data-open-profile-modal>
          <i class="bi bi-pencil-square" aria-hidden="true"></i>
          <span>RAG 조건 입력하기</span>
        </button>
      </div>
    `;
    return;
  }

  const routeLength = selectedRoute(scenario).slice(0, RECOMMENDATION_LIMIT).length;
  const intentLabels = ragIntentLabels(retrieval.query_intent);
  const applied = retrievalStatus === "applied";
  const explanationState = applied
    ? currentAiExplanationState(scenario)
    : {
        status: "ungrounded",
        message: retrievalStatus === "resource_data_gap"
          ? "요청한 지원서비스의 공식 근거가 부족해 AI 설명도 생성하지 않습니다."
          : "충분한 검색 근거가 없어 추천과 AI 설명을 함께 보류했습니다."
      };
  const isLoading = explanationState.status === "loading";

  panel.innerHTML = `
    <header class="rag-process-header">
      <div>
        <span><i class="bi bi-diagram-3" aria-hidden="true"></i> 검증 가능한 추천</span>
        <h3 id="ragProcessTitle">RAG 검색 과정</h3>
        <p>검수 데이터 검색부터 접근성 재정렬, 근거 제한 설명까지 한 흐름으로 확인합니다.</p>
      </div>
      <b class="rag-engine-badge">${escapeHtml(ragEngineLabel(retrieval.engine))}</b>
    </header>
    <ol class="rag-process-steps" aria-label="RAG 검색 처리 단계">
      <li>
        <span>1</span>
        <small>검수 코퍼스</small>
        <strong>${escapeHtml(ragCountLabel(retrieval.corpus_count))}</strong>
      </li>
      <li>
        <span>2</span>
        <small>검색 후보</small>
        <strong>${escapeHtml(ragCountLabel(retrieval.retrieved_count))}</strong>
      </li>
      <li>
        <span>3</span>
        <small>최종 추천</small>
        <strong>${escapeHtml(ragCountLabel(routeLength))}</strong>
      </li>
    </ol>
    <div class="rag-intent-row">
      <strong>인식한 검색 의도</strong>
      <div>${intentLabels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</div>
    </div>
    <footer class="rag-process-footer">
      <div class="rag-ai-state" id="ragAiState" data-status="${escapeHtml(explanationState.status)}" role="status" aria-live="polite" aria-atomic="true" aria-busy="${isLoading ? "true" : "false"}">
        <i class="bi ${escapeHtml(aiStatusIcon(explanationState.status))}" aria-hidden="true"></i>
        <span>
          <strong>${escapeHtml(aiStatusBadge(explanationState.status))}</strong>
          <small>${escapeHtml(explanationState.message)}</small>
        </span>
      </div>
      ${applied ? `
        <div class="rag-process-actions">
          ${explanationState.status === "success" ? `
            <button class="rag-regenerate-button" type="button" data-generate-grounded-ai data-ai-refresh="true" aria-describedby="ragAiState">
              <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
              <span>설명 다시 생성</span>
            </button>
            <button class="grounded-ai-button rag-view-explanation-button" type="button" data-focus-ai-explanation>
              <i class="bi bi-arrow-right-circle" aria-hidden="true"></i>
              <span>생성된 AI 설명 보기</span>
            </button>
          ` : `
            <button class="grounded-ai-button" type="button" data-generate-grounded-ai aria-describedby="ragAiState" aria-busy="${isLoading ? "true" : "false"}" ${isLoading ? "disabled" : ""}>
              <i class="bi ${isLoading ? "bi-arrow-repeat" : "bi-stars"}" aria-hidden="true"></i>
              <span>${isLoading ? "AI 설명 생성 중" : explanationState.status === "error" ? "AI 설명 다시 시도" : "공식 근거로 AI 설명 생성"}</span>
            </button>
          `}
        </div>
      ` : ""}
    </footer>
  `;
}

function renderAiNote(scenario) {
  const title = scenario.recommendation?.course?.title || scenario.title || "추천 코스";
  const rawScore = Number(scenario.recommendation?.score?.total);
  const score = Number.isFinite(rawScore) ? Math.round(rawScore) : "-";
  const retrievalStatus = scenario.retrieval?.status;
  const retrievalDescription = retrievalStatus === "resource_data_gap"
    ? "요청한 지원서비스는 공식 근거 데이터가 부족해 관련 없는 장소를 대신 추천하지 않았습니다."
    : retrievalStatus === "no_match"
      ? "현재 검증된 장소에서 충분한 검색 근거를 찾지 못해 추천을 보류했습니다."
      : "";
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
      ${retrievalDescription ? `<span class="rag-status-detail" role="status">${escapeHtml(retrievalDescription)}</span>` : ""}
    `;
  }
  const safetyNotice = document.getElementById("safetyNotice");
  if (safetyNotice) {
    safetyNotice.textContent = state.data.safety_notice || "";
  }
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
    const locationLabel = locationPointStatusLabel(location);
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
  const pinMarkup = route.map((routeItem, index) => {
    const place = routePlace(scenario, routeItem);
    const location = validLocation(place.location) ? place.location : null;
    if (!location) {
      return "";
    }
    const active = place.spot_id === state.selectedSpotId;
    const pointLabel = locationPointLabel(location);
    return `
      <button class="map-location-pin rank-${index + 1} ${active ? "active" : ""}" type="button" data-spot-id="${escapeHtml(place.spot_id)}" data-latitude="${escapeHtml(location.latitude)}" data-longitude="${escapeHtml(location.longitude)}" aria-label="${index + 1}번 ${escapeHtml(place.name)} ${escapeHtml(pointLabel)}" title="${escapeHtml(mapPointDisplayName(place))}">${index + 1}${pointRoleBadgeMarkup(location, "map-pin-role")}</button>
    `;
  }).join("");
  const popup = renderMapPopupCard(scenario, route, scoreTotal);
  mapHits.innerHTML = popup + pinMarkup + cardMarkup;
  scheduleCenterMapRender(scenario);
  scheduleMapHitBoundsSync();
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
  const pointNote = hasSpecialPointRole(location)
    ? `지도 핀은 ${locationPointLabel(location)} 기준입니다. 실제 출입·탐방 시작 위치를 다시 확인해 주세요.`
    : "현재 조건에 맞춰 이동 부담과 휴식 가능성을 우선 반영했습니다.";
  const bound = mapCardBounds[index] || mapCardBounds[0];
  const locationAttrs = location
    ? `data-latitude="${escapeHtml(location.latitude)}" data-longitude="${escapeHtml(location.longitude)}"`
    : "";
  return `
    <button class="map-place-card map-popup-card rank-${index + 1} ${location ? "located" : ""} active" type="button" data-spot-id="${escapeHtml(place.spot_id)}" data-map-bound-index="${index}" ${locationAttrs} title="${escapeHtml(place.name)} 상세 보기" aria-label="${index + 1}번 추천 장소 ${escapeHtml(place.name)} 상세 보기" style="left:${(bound.x / 816) * 100}%; top:${(bound.y / 931) * 100}%; width:${(bound.width / 816) * 100}%; height:${(bound.height / 931) * 100}%;">
      <span class="map-popup-media">
        <img class="map-popup-image${visual.fit === "contain" ? " is-contain" : ""}" src="${escapeHtml(visual.src)}" alt="${escapeHtml(visual.alt)}" loading="lazy" decoding="async">
        <span class="map-rank">${index + 1}</span>
        <span class="map-popup-status ${escapeHtml(verificationStatus)}">${escapeHtml(verificationLabel(place))}</span>
      </span>
      <span class="map-popup-body">
        <span class="map-popup-head">
          <span class="map-popup-title-group">
            <strong>${escapeHtml(place.name)}</strong>
            <span class="map-popup-subtitle">${escapeHtml(category)} · ${escapeHtml(location ? "실제 위치 기반" : "위치 확인 필요")}</span>
            ${pointRoleBadgeMarkup(location, "map-popup-point-role")}
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
        <span class="map-popup-note">${escapeHtml(pointNote)}</span>
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
  const savedRoute = currentSavedRoute();
  const persistentChecks = savedRoute
    ? savedRouteChecklist(savedRoute).filter((check) => check.spotId === place.spot_id)
    : [];
  const savedCheckedIds = new Set(savedRoute?.checkedIds || []);
  const completedPersistentChecks = persistentChecks.filter((check) => savedCheckedIds.has(check.id)).length;
  const breakdown = scoreBreakdown(place);
  const calculationTrace = scoreCalculationTrace(place);
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
  const retrievalSources = retrievalEvidenceItems(scenario, place.spot_id);
  const locationEvidence = locationEvidenceItem(place);
  const sourceCount = retrievalSources.length + sources.length + (locationEvidence ? 1 : 0);
  const validationMarkup = renderValidationEvidence(scenario);

  detail.innerHTML = `
    <div class="detail-head">
      <div>
        <span class="detail-rank">${index + 1}</span>
        <h2>${escapeHtml(place.name)}</h2>
        ${pointRoleBadgeMarkup(place.location, "detail-point-role")}
        <p>${escapeHtml(place.visit_info?.address || place.address || place.region || "제주 접근성 추천 장소")} · ${escapeHtml(category)}</p>
      </div>
      <button class="close-button" type="button" data-close-detail aria-label="선택 장소 상세 닫기">×</button>
    </div>
    <button class="detail-photo" type="button" data-open-image-modal data-image-src="${escapeHtml(visual.src)}" data-image-alt="${escapeHtml(visual.alt)}" data-image-caption="${escapeHtml(visual.caption)}" data-image-source="${escapeHtml(visual.source)}" data-image-source-url="${escapeHtml(visual.sourceUrl)}" data-image-license="${escapeHtml(visual.license)}" data-image-policy="${escapeHtml(visual.policy)}">
      <img class="detail-photo-image${visual.fit === "contain" ? " is-contain" : ""}" src="${escapeHtml(visual.src)}" alt="${escapeHtml(visual.alt)}" loading="lazy" decoding="async" data-fallback-src="${escapeHtml(visual.fallbackSrc)}" data-fallback-caption="${escapeHtml(visual.fallbackCaption)}" data-fallback-source="${escapeHtml(visual.fallbackSource)}">
      <span>${escapeHtml(visual.policy)}</span>
    </button>
    <div class="image-credit">
      <strong>${escapeHtml(visual.caption)}</strong>
      <small>${imageSourceMarkup(visual.source, visual.sourceUrl, visual.license)}</small>
    </div>
    <button class="route-cta-button" type="button" data-open-route-modal>
      <span>실제 경로 보기</span>
      <b>${escapeHtml(routeNames(scenario).join(" → "))}</b>
    </button>
    <button class="saved-route-cta ${savedRoute ? "saved" : ""}" type="button" data-save-current-route aria-pressed="${savedRoute ? "true" : "false"}">
      <i class="bi ${savedRoute ? "bi-bookmark-check-fill" : "bi-bookmark-plus"}" aria-hidden="true"></i>
      <span data-save-current-route-label>${savedRoute ? "저장됨" : "코스 저장"}</span>
      <small>${savedRoute ? "저장함에서 방문 전 체크를 이어갈 수 있습니다." : "개인 조건 없이 장소 목록만 이 기기에 저장합니다."}</small>
    </button>
    ${visitInfoMarkup(place)}
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
    <details class="score-basis detail-disclosure">
      <summary>
        <span class="detail-disclosure-heading">
          <i class="bi bi-bar-chart-line" aria-hidden="true"></i>
          <span><b>점수 계산 상세</b><small>${breakdown.length}개 항목·보정 내역</small></span>
        </span>
        <span class="detail-disclosure-status">
          <strong>${score}점</strong>
          <i class="bi bi-chevron-down" aria-hidden="true"></i>
        </span>
      </summary>
      <div class="detail-disclosure-content">
        ${breakdown.map((item) => {
          const percent = item.max > 0 ? Math.round((item.score / item.max) * 100) : 0;
          return `
            <div class="score-factor">
              <div class="bar-row">
                <span>${escapeHtml(item.label)}</span>
                <i><b style="width:${percent}%"></b></i>
                <strong>${item.score}/${item.max}</strong>
              </div>
              <small>${escapeHtml(item.reason)}</small>
            </div>
          `;
        }).join("")}
        ${calculationTrace ? `
          <div class="score-trace" aria-label="점수 계산 과정">
            <div class="score-trace-row base">
              <span>5개 항목 기본 합계</span>
              <b>${calculationTrace.baseTotal}점</b>
            </div>
            ${calculationTrace.adjustments.map((item) => `
              <div class="score-trace-row ${item.delta > 0 ? "bonus" : "deduction"}">
                <span>${escapeHtml(item.label)}</span>
                <b>${escapeHtml(signedScore(item.delta))}점</b>
              </div>
            `).join("")}
            ${calculationTrace.caps.map((item) => `
              <div class="score-trace-row cap">
                <span>${escapeHtml(item.label)}</span>
                <b>${item.before}→${item.after}점</b>
              </div>
            `).join("")}
            <div class="score-trace-row final">
              <span>최종 점수</span>
              <b>${calculationTrace.finalTotal}점</b>
            </div>
          </div>
        ` : ""}
      </div>
    </details>
    <section class="evidence-grid">
      ${facilityCards.map(({ title, item }) => `
        <div role="group" aria-label="${escapeHtml(`${title}: ${stateText(item.state)}. ${item.note || "세부 메모 없음"}`)}" title="${escapeHtml(item.note || "세부 메모 없음")}">
          <b>${escapeHtml(title)}</b>
          <span>${escapeHtml(stateText(item.state))}</span>
          <small>${escapeHtml(item.state_label || stateText(item.state))}</small>
        </div>
      `).join("")}
    </section>
    <section class="visit-check">
      <div class="detail-section-row">
        <h3>방문 전 확인</h3>
        <span>${savedRoute ? `${completedPersistentChecks}/${persistentChecks.length} 완료` : "저장 후 체크 가능"}</span>
      </div>
      <ul>
        ${savedRoute && persistentChecks.length ? persistentChecks.map((check) => `
          <li class="interactive">
            <label>
              <input type="checkbox" data-saved-route-id="${escapeHtml(savedRoute.id)}" data-saved-check-id="${escapeHtml(check.id)}" ${savedCheckedIds.has(check.id) ? "checked" : ""}>
              <b>${escapeHtml(check.label)}</b>
            </label>
            <span>${savedCheckedIds.has(check.id) ? "완료" : "확인"}</span>
          </li>
        `).join("") : checks.map((check) => `<li>${escapeHtml(check.text)}<span>저장 후 체크</span></li>`).join("")}
      </ul>
    </section>
    <details class="source-box detail-disclosure">
      <summary>
        <span class="detail-disclosure-heading">
          <i class="bi bi-link-45deg" aria-hidden="true"></i>
          <span><b>정보 출처</b><small>공식 링크와 확인일</small></span>
        </span>
        <span class="detail-disclosure-status">
          <strong>${sourceCount || 1}개</strong>
          <i class="bi bi-chevron-down" aria-hidden="true"></i>
        </span>
      </summary>
      <div class="detail-disclosure-content">
        <ul>
        ${retrievalSources.map((source) => `
          <li class="grounded-source">
            <span>
              <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>
              <small>정보 확인일 ${escapeHtml(source.checkedAt)}</small>
            </span>
            <b>${escapeHtml(displayLabel(source.status))}</b>
          </li>
        `).join("")}
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
      </div>
    </details>
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
    title: `${locationPointLabel(location)} · 지도 위치 ${coordinate} · ${sourceTitle}`,
    status: location.match_method === "manual_override" ? "직접 확인" : "좌표 확인"
  };
}

function renderValidationEvidence() {
  return "";
}

function renderAiExplanationModal(scenario = currentScenario()) {
  const modal = document.getElementById("aiExplanationModal");
  const body = document.getElementById("aiExplanationModalBody");
  if (!modal || !body) {
    return;
  }
  const generatedSections = aiDetailSections(scenario, null);
  const localSections = aiDetailSections({ ...scenario, ai_summary: null }, null);
  body.innerHTML = aiExplanationPanelMarkup(
    scenario,
    generatedSections,
    localSections,
    aiCitationItems(scenario)
  );
  const courseTitle = scenario?.recommendation?.course?.title || scenario?.title || "추천 코스";
  const title = document.getElementById("aiExplanationModalTitle");
  if (title) {
    title.textContent = `${courseTitle} · AI 근거 설명`;
  }
  if (state.aiExplanationModalOpen && currentAiExplanationState(scenario).status !== "success") {
    closeAiExplanationModal({ restoreFocus: false });
  }
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
  renderRagProcess(scenario);
  renderAiExplanationModal(scenario);
  renderMapHits(scenario);
  renderDetail(scenario);
  renderSavedRouteControls();
  renderSavedRoutesModal();
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
  const draft = beginProfileModalEdit();
  renderScenarioCards();
  renderProfileOptions();
  modal.hidden = false;
  document.body.classList.add("modal-open");
  const queryInput = document.getElementById("ragQueryInput");
  if (queryInput) {
    queryInput.value = draft.ragQuery;
  }
  const panel = modal.querySelector(".profile-modal-panel");
  if (panel) {
    panel.scrollTop = 0;
  }
  renderRagQueryAssist(draft.ragQuery);
  window.requestAnimationFrame(() => {
    (modal.querySelector("[data-rag-example]") || queryInput)?.focus({ preventScroll: true });
  });
}

function setAiExplanationModalIsolation(active) {
  document.querySelectorAll(".app-shell, .helpbot-wing-wrap").forEach((node) => {
    if (active) {
      node.setAttribute("inert", "");
    } else {
      node.removeAttribute("inert");
    }
  });
  document.body.classList.toggle("ai-explanation-modal-open", active);
}

function openAiExplanationModal(trigger = document.activeElement) {
  const modal = document.getElementById("aiExplanationModal");
  const scenario = currentScenario();
  if (!modal || currentAiExplanationState(scenario).status !== "success") {
    return;
  }
  if (modal.hidden && trigger?.focus && !modal.contains(trigger)) {
    aiExplanationReturnFocus = trigger;
  }
  renderAiExplanationModal(scenario);
  state.aiExplanationModalOpen = true;
  modal.hidden = false;
  setAiExplanationModalIsolation(true);
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => {
    modal.querySelector(".modal-close-button")?.focus({ preventScroll: true });
  });
}

function closeAiExplanationModal({ restoreFocus = true } = {}) {
  const modal = document.getElementById("aiExplanationModal");
  if (!modal) {
    state.aiExplanationModalOpen = false;
    return;
  }
  const wasOpen = state.aiExplanationModalOpen || !modal.hidden;
  const returnFocus = aiExplanationReturnFocus;
  state.aiExplanationModalOpen = false;
  modal.hidden = true;
  if (wasOpen) {
    setAiExplanationModalIsolation(false);
    document.body.classList.remove("modal-open");
  }
  aiExplanationReturnFocus = null;
  if (wasOpen && restoreFocus && returnFocus?.isConnected) {
    window.requestAnimationFrame(() => returnFocus.focus({ preventScroll: true }));
  }
}

function trapAiExplanationFocus(event) {
  const modal = document.getElementById("aiExplanationModal");
  if (!state.aiExplanationModalOpen || !modal || modal.hidden || event.key !== "Tab") {
    return false;
  }
  const controls = Array.from(modal.querySelectorAll(
    "a[href], button:not([disabled]):not(.ai-explanation-modal-backdrop), [tabindex]:not([tabindex=\"-1\"])"
  ));
  if (!controls.length) {
    return false;
  }
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && (document.activeElement === first || !modal.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
    return true;
  }
  if (!event.shiftKey && (document.activeElement === last || !modal.contains(document.activeElement))) {
    event.preventDefault();
    first.focus();
    return true;
  }
  return false;
}

function closeProfileModal() {
  const modal = document.getElementById("profileModal");
  if (!modal) {
    return;
  }
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  discardProfileModalEdit();
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
  document.getElementById("imageModalSource").innerHTML = imageSourceMarkup(
    trigger.dataset.imageSource,
    trigger.dataset.imageSourceUrl,
    trigger.dataset.imageLicense
  );
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
  routeModalRenderSequence += 1;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function setSavedRoutesModalIsolation(active) {
  const isolatedNodes = [
    document.querySelector(".app-shell"),
    document.querySelector(".helpbot-wing-wrap")
  ].filter(Boolean);
  isolatedNodes.forEach((node) => {
    if (active) {
      node.setAttribute("inert", "");
    } else {
      node.removeAttribute("inert");
    }
  });
  if (active) {
    document.body.classList.add("saved-routes-modal-open");
  } else {
    document.body.classList.remove("saved-routes-modal-open");
  }
}

function openSavedRoutesModal() {
  const modal = document.getElementById("savedRoutesModal");
  if (!modal) {
    return;
  }
  if (modal.hidden && document.activeElement?.focus && !modal.contains(document.activeElement)) {
    savedRoutesReturnFocus = document.activeElement;
  }
  state.savedRoutesOpen = true;
  clearSavedRouteDeleteConfirmation({ clearMessage: true });
  renderSavedRoutesModal();
  modal.hidden = false;
  setSavedRoutesModalIsolation(true);
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => {
    modal.querySelector(".modal-close-button")?.focus();
  });
}

function closeSavedRoutesModal({ restoreFocus = true } = {}) {
  const modal = document.getElementById("savedRoutesModal");
  if (!modal) {
    return;
  }
  const wasOpen = !modal.hidden;
  const returnFocus = savedRoutesReturnFocus;
  state.savedRoutesOpen = false;
  clearSavedRouteDeleteConfirmation({ clearMessage: true });
  modal.hidden = true;
  setSavedRoutesModalIsolation(false);
  document.body.classList.remove("modal-open");
  savedRoutesReturnFocus = null;
  if (wasOpen && restoreFocus && returnFocus?.isConnected) {
    window.requestAnimationFrame(() => returnFocus.focus());
  }
}

function trapSavedRoutesFocus(event) {
  const modal = document.getElementById("savedRoutesModal");
  if (!state.savedRoutesOpen || !modal || modal.hidden || event.key !== "Tab") {
    return false;
  }
  const controls = Array.from(modal.querySelectorAll(
    "button:not([disabled]):not(.saved-routes-modal-backdrop), input:not([disabled])"
  ));
  if (!controls.length) {
    return false;
  }
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && (document.activeElement === first || !modal.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
    return true;
  }
  if (!event.shiftKey && (document.activeElement === last || !modal.contains(document.activeElement))) {
    event.preventDefault();
    first.focus();
    return true;
  }
  return false;
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
  const routeKey = routeEntriesCacheKey(entries);
  const sequence = ++routeModalRenderSequence;
  document.getElementById("routeModalTitle").textContent = routeTitle;
  document.getElementById("routeModalSubtitle").textContent = `${routeNames(scenario).join(" → ")} 순서로 실제 위치를 연결합니다.`;

  if (entries.length < 2) {
    setRouteMapStatus("좌표 확인 필요", "두 곳 이상의 실제 좌표가 있어야 경로를 계산할 수 있습니다.");
    renderRouteItinerary(allEntries, fallbackRouteSummary(entries), "좌표 확인 필요");
    clearRouteMap();
    return;
  }

  const fallback = fallbackRouteSummary(entries);
  drawRouteMap(entries, fallback);
  renderRouteItinerary(allEntries, fallback, shouldRequestRouteProxy() ? "계산 중" : "좌표 기반");
  if (!shouldRequestRouteProxy()) {
    setRouteMapStatus(
      "좌표 기반 경로",
      `${formatDistanceKm(fallback.distanceKm)} · ${formatDurationMinutes(fallback.durationMinutes)}`
    );
    return;
  }

  setRouteMapStatus("경로 계산 중", "실제 도로형 경로를 가져오는 중입니다.");
  window.requestAnimationFrame(async () => {
    const summary = await cachedRouteSummaryWithRoadGeometry(entries);
    const currentKey = routeEntriesCacheKey(routeCoordinateEntries(currentScenario()));
    if (!state.routeModalOpen || sequence !== routeModalRenderSequence || currentKey !== routeKey) {
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
          ${pointRoleBadgeMarkup(entry.location, "route-point-role")}
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
  const fallbackLayer = document.getElementById("routeMapFallbackLayer");
  if (fallbackLayer) {
    fallbackLayer.innerHTML = "";
  }
  deactivateRouteMapFallback();
}

function prepareRouteMapFallback(entries) {
  const layer = document.getElementById("routeMapFallbackLayer");
  if (!layer) {
    return;
  }
  const located = entries.map((entry, index) => ({
    entry,
    order: Number(entry.order || index + 1),
    point: savedRouteMiniMapPoint(entry.location)
  })).filter((item) => item.point);
  const path = located.length >= 2 ? routePathData(located.map((item) => item.point)) : "";
  layer.innerHTML = `
    ${path ? `<path class="route-map-fallback-path-shadow" d="${path}"></path><path class="route-map-fallback-path" d="${path}"></path>` : ""}
    ${located.map((item) => {
      const roleLabel = locationPointShortLabel(item.entry.location);
      const roleWidth = Math.max(10, Math.min(20, 4 + roleLabel.length * 3));
      const roleX = clamp(-roleWidth / 2, 1 - item.point.x, 99 - item.point.x - roleWidth);
      return `
        <g class="route-map-fallback-marker" transform="translate(${roundSvg(item.point.x)} ${roundSvg(item.point.y)})">
          <title>${escapeHtml(`${item.order}번 ${mapPointDisplayName(item.entry.place)}`)}</title>
          <circle r="4.8"></circle>
          <text x="0" y="0.5">${item.order}</text>
          ${roleLabel ? `
            <rect class="route-map-fallback-role-bg" x="${roundSvg(roleX)}" y="6.2" width="${roundSvg(roleWidth)}" height="6.2" rx="3.1"></rect>
            <text class="route-map-fallback-role" x="${roundSvg(roleX + roleWidth / 2)}" y="9.5">${escapeHtml(roleLabel)}</text>
          ` : ""}
        </g>
      `;
    }).join("")}
  `;
}

function activateRouteMapFallback(badge, message) {
  const shell = document.querySelector(".route-map-shell");
  const mapElement = document.getElementById("routeMap");
  shell?.classList.add("route-map-fallback-active");
  mapElement?.setAttribute("aria-hidden", "true");
  setRouteMapStatus(badge, message);
}

function deactivateRouteMapFallback() {
  const shell = document.querySelector(".route-map-shell");
  const mapElement = document.getElementById("routeMap");
  shell?.classList.remove("route-map-fallback-active");
  mapElement?.removeAttribute("aria-hidden");
}

function ensureRouteMap() {
  const mapElement = document.getElementById("routeMap");
  if (!mapElement) {
    return null;
  }
  if (!window.L) {
    activateRouteMapFallback("로컬 경로 지도", "지도 라이브러리 없이 실제 좌표 순서를 표시합니다.");
    return null;
  }
  if (!routeMap) {
    routeMap = L.map(mapElement, {
      zoomControl: true,
      scrollWheelZoom: false,
      attributionControl: true
    });
    routeTileErrorCount = 0;
    routeTileLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    })
      .on("loading", () => {
        routeTileErrorCount = 0;
      })
      .on("tileerror", () => {
        routeTileErrorCount += 1;
        if (routeTileErrorCount >= 3) {
          activateRouteMapFallback("로컬 경로 지도", "지도 타일 연결 없이 실제 좌표 순서를 표시합니다.");
        }
      })
      .on("load", () => {
        if (routeTileErrorCount < 3) {
          deactivateRouteMapFallback();
        }
      })
      .addTo(routeMap);
    routeLayerGroup = L.layerGroup().addTo(routeMap);
  }
  if (routeTileErrorCount >= 3) {
    activateRouteMapFallback("로컬 경로 지도", "지도 타일 연결 없이 실제 좌표 순서를 표시합니다.");
  }
  window.setTimeout(() => routeMap.invalidateSize(), 80);
  return routeMap;
}

function drawRouteMap(entries, summary) {
  clearRouteMap();
  prepareRouteMapFallback(entries);
  const map = ensureRouteMap();
  if (!map) {
    activateRouteMapFallback("로컬 경로 지도", "외부 지도 연결 없이 실제 좌표 순서를 표시합니다.");
    return;
  }
  const geometry = routeGeometryWithStopAnchors(entries, summary.geometry);
  const lineLatLngs = geometry.map((location) => [Number(location.latitude), Number(location.longitude)]);
  const markerLatLngs = entries.map((entry) => [Number(entry.location.latitude), Number(entry.location.longitude)]);

  L.polyline(lineLatLngs, {
    color: "#ffffff",
    weight: 12,
    opacity: 0.96,
    smoothFactor: 0,
    lineCap: "round",
    lineJoin: "round"
  }).addTo(routeLayerGroup);
  L.polyline(lineLatLngs, {
    color: ROUTE_KEY_COLOR,
    weight: 6,
    opacity: 0.95,
    smoothFactor: 0,
    lineCap: "round",
    lineJoin: "round"
  }).addTo(routeLayerGroup);

  entries.forEach((entry, index) => {
    const marker = L.marker([Number(entry.location.latitude), Number(entry.location.longitude)], {
      icon: L.divIcon({
        className: `route-marker-icon rank-${index + 1}`,
        html: `<span>${index + 1}</span>${pointRoleBadgeMarkup(entry.location, "route-marker-role")}`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
        popupAnchor: [0, -18]
      }),
      keyboard: true,
      title: mapPointDisplayName(entry.place)
    }).addTo(routeLayerGroup);
    marker.bindPopup(`<strong>${escapeHtml(entry.place.name)}</strong><br>${escapeHtml(locationPointLabel(entry.location))} · ${escapeHtml(entry.score)}점 · ${escapeHtml(verificationLabel(entry.place))}`);
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
    photo.dataset.imageSourceUrl = "";
    photo.dataset.imageLicense = "";
    photo.dataset.imagePolicy = "이미지 로딩 실패";
    photo.querySelector("span").textContent = "이미지 로딩 실패";
    photo.nextElementSibling?.querySelector("strong")?.replaceChildren(document.createTextNode(photo.dataset.imageCaption));
    photo.nextElementSibling?.querySelector("small")?.replaceChildren(document.createTextNode(`${photo.dataset.imageSource} · 원본 이미지 확인 필요`));
  }
}

async function shareCurrentView(button) {
  const scenario = currentScenario();
  const place = state.detailCollapsed ? null : selectedPlace(scenario);
  const text = place
    ? `${place.name} 접근성 근거와 추천 코스를 확인해 보세요.`
    : "가치봄 제주 맞춤 접근성 여행 추천 화면을 확인해 보세요.";
  await shareRouteSpotIds(button, currentRouteSpotIds(scenario), text);
}

async function shareSavedRoute(button, routeId) {
  const item = state.savedRoutes.find((saved) => saved.id === routeId);
  if (!item) {
    setShareButtonFeedback(button, "코스 없음");
    return;
  }
  await shareRouteSpotIds(button, item.spotIds, `${savedRouteTitle(item)} 코스를 확인해 보세요.`);
}

async function shareRouteSpotIds(button, spotIds, text) {
  const url = SAVED_TRIPS?.buildShareUrl(window.location, spotIds, shareableSavedSpotIds());
  if (!url) {
    setShareButtonFeedback(button, "공유 실패");
    return;
  }
  const title = "가치봄 제주 접근성 여행 추천";

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
    setShareButtonFeedback(button, error?.name === "AbortError" ? "공유 취소" : "복사 실패");
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
  window.clearTimeout(shareFeedbackTimers.get(button));
  const timer = window.setTimeout(() => {
    button.textContent = button.dataset.originalText || "공유";
    shareFeedbackTimers.delete(button);
  }, 1800);
  shareFeedbackTimers.set(button, timer);
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
    const wasOpen = state.conceptPanelOpen;
    state.conceptPanelOpen = false;
    if (wasOpen && state.data) {
      renderConceptPage(currentScenario());
    }
  }
  renderNavTabs();
  if (updateLocation) {
    updateHash(href);
  }
  window.requestAnimationFrame(() => {
    scrollToSelector(href || "#conceptPage", behavior);
    centerMap?.invalidateSize();
    scheduleMapHitBoundsSync();
    syncStepViewState();
  });
}

async function selectScenarioForResult(scenarioId, { navigateToResults = false } = {}) {
  if (!scenarioById(scenarioId)) {
    return;
  }
  state.scenarioId = scenarioId;
  state.runtimeScenario = null;
  state.conceptFocus = null;
  state.profile = profileFromScenario(currentStaticScenario());
  state.selectedSpotId = null;
  state.mapPopupSpotId = null;
  state.detailCollapsed = false;

  if (navigateToResults) {
    navigateToSection("recommend", "#recommendations", { updateLocation: true });
  } else {
    openConceptResultPanel();
  }
  render();

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
      const shouldRestoreConceptFocus = goConceptsButton.hasAttribute("data-return-to-concept-list");
      closeConceptResultPanel();
      navigateToSection("concepts", "#conceptPage", { updateLocation: true });
      if (shouldRestoreConceptFocus) {
        restoreSelectedConceptFocus();
      }
      return;
    }

    const shareButton = event.target.closest("[data-share-app]");
    if (shareButton) {
      await shareCurrentView(shareButton);
      return;
    }

    const saveCurrentRouteButton = event.target.closest("[data-save-current-route]");
    if (saveCurrentRouteButton) {
      if (currentSavedRoute()) {
        openSavedRoutesModal();
      } else {
        saveCurrentRoute();
      }
      return;
    }

    const openSavedRoutesButton = event.target.closest("[data-open-saved-routes]");
    if (openSavedRoutesButton) {
      openSavedRoutesModal();
      return;
    }

    const closeSavedRoutesButton = event.target.closest("[data-close-saved-routes]");
    if (closeSavedRoutesButton) {
      closeSavedRoutesModal();
      return;
    }

    const openSavedRouteButton = event.target.closest("[data-open-saved-route]");
    if (openSavedRouteButton) {
      openSavedRoute(openSavedRouteButton.dataset.openSavedRoute);
      return;
    }

    const saveSharedRouteButton = event.target.closest("[data-save-shared-route]");
    if (saveSharedRouteButton) {
      saveSharedRoute();
      return;
    }

    const shareSavedRouteButton = event.target.closest("[data-share-saved-route]");
    if (shareSavedRouteButton) {
      await shareSavedRoute(shareSavedRouteButton, shareSavedRouteButton.dataset.shareSavedRoute);
      return;
    }

    const moveSavedSpotButton = event.target.closest("[data-move-saved-route][data-move-saved-spot]");
    if (moveSavedSpotButton) {
      moveSavedRouteSpot(
        moveSavedSpotButton.dataset.moveSavedRoute,
        moveSavedSpotButton.dataset.moveSavedSpot,
        Number(moveSavedSpotButton.dataset.moveDirection)
      );
      return;
    }

    const deleteSavedRouteButton = event.target.closest("[data-delete-saved-route]");
    if (deleteSavedRouteButton) {
      requestDeleteSavedRoute(deleteSavedRouteButton.dataset.deleteSavedRoute);
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

    const ragExampleButton = event.target.closest("[data-rag-example]");
    if (ragExampleButton) {
      setRagQueryValue(ragExampleButton.dataset.ragExample);
      return;
    }

    const clearRagQueryButton = event.target.closest("[data-clear-rag-query]");
    if (clearRagQueryButton) {
      setRagQueryValue("");
      return;
    }

    const applyModalButton = event.target.closest("[data-apply-profile-modal]");
    if (applyModalButton) {
      commitProfileModalEdit(document.getElementById("ragQueryInput")?.value);
      closeProfileModal();
      await refreshRuntimeRecommendation({ renderLoading: true });
      render();
      return;
    }

    const groundedAiButton = event.target.closest("[data-generate-grounded-ai]");
    if (groundedAiButton) {
      await requestGroundedAiExplanation({
        forceRefresh: groundedAiButton.dataset.aiRefresh === "true"
      });
      return;
    }

    const focusAiExplanationButton = event.target.closest("[data-focus-ai-explanation]");
    if (focusAiExplanationButton) {
      openAiExplanationModal(focusAiExplanationButton);
      return;
    }

    const closeAiExplanationButton = event.target.closest("[data-close-ai-explanation]");
    if (closeAiExplanationButton) {
      closeAiExplanationModal();
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

    const conceptPlaceButton = event.target.closest("[data-concept-place-id]");
    if (conceptPlaceButton) {
      state.selectedSpotId = conceptPlaceButton.dataset.conceptPlaceId || null;
      state.mapPopupSpotId = null;
      state.detailCollapsed = false;
      closeConceptResultPanel();
      render();
      navigateToSection("recommend", "#recommendations", { updateLocation: true });
      return;
    }

    const conceptFocusButton = event.target.closest("[data-concept-focus-key]");
    if (conceptFocusButton) {
      const nextFocus = {
        key: conceptFocusButton.dataset.conceptFocusKey,
        value: conceptFocusButton.dataset.conceptFocusValue,
        label: conceptFocusButton.dataset.conceptFocusLabel
      };
      state.conceptFocus = conceptFocusKey() === conceptFocusKey(nextFocus) ? null : nextFocus;
      state.runtimeScenario = staticConditionVariant();
      await refreshRuntimeRecommendation({ renderLoading: true });
      render();
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
        if (selectProfileModalScenario(scenarioButton.dataset.scenarioId)) {
          renderScenarioCards();
          renderProfileOptions();
          renderRagQueryAssist();
        }
        return;
      }
      await selectScenarioForResult(scenarioButton.dataset.scenarioId);
      return;
    }

    const profileButton = event.target.closest("[data-profile-key]");
    if (profileButton) {
      if (profileButton.closest("#profileModal")) {
        if (toggleProfileModalValue(profileButton.dataset.profileKey, profileButton.dataset.profileValue)) {
          renderScenarioCards();
          renderProfileOptions();
          renderRagQueryAssist();
        }
        return;
      }
      state.conceptFocus = null;
      toggleProfileValue(profileButton.dataset.profileKey, profileButton.dataset.profileValue);
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

  document.getElementById("ragQueryInput")?.addEventListener("input", (event) => {
    updateProfileModalQuery(event.target.value);
    scheduleRagQueryAssist(event.target.value);
  });

  document.addEventListener("change", (event) => {
    const scheduleInput = event.target.closest?.("[data-saved-trip-date], [data-saved-start-time]");
    if (scheduleInput) {
      const card = scheduleInput.closest("[data-saved-route-card]");
      const routeId = card?.dataset.savedRouteCard;
      const date = card?.querySelector("[data-saved-trip-date]")?.value || "";
      const startTime = card?.querySelector("[data-saved-start-time]")?.value || "";
      if (routeId) {
        updateSavedRouteItinerary(routeId, date, startTime);
      }
      return;
    }
    const checkbox = event.target.closest?.("[data-saved-route-id][data-saved-check-id]");
    if (!checkbox || checkbox.type !== "checkbox") {
      return;
    }
    updateSavedRouteCheck(
      checkbox.dataset.savedRouteId,
      checkbox.dataset.savedCheckId,
      checkbox.checked,
      checkbox.closest("#savedRoutesModal") ? "savedRoutesModal" : "placeDetail"
    );
  });

  document.addEventListener("keydown", (event) => {
    if (trapAiExplanationFocus(event)) {
      return;
    }
    if (trapSavedRoutesFocus(event)) {
      return;
    }
    if (event.key === "Escape" && state.aiExplanationModalOpen) {
      closeAiExplanationModal();
      return;
    }
    if (event.key === "Escape") {
      closeSiteIntro();
      closeImageModal();
      closeProfileModal();
      closeRouteModal();
      closeSavedRoutesModal();
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
    scheduleMapHitBoundsSync();
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
      const wasOpen = state.conceptPanelOpen;
      state.conceptPanelOpen = false;
      if (wasOpen && state.data) {
        renderConceptPage(currentScenario());
      }
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
    loadSavedRouteState();
    setApiState(
      shouldRequestRuntimeApi() ? "idle" : "static",
      shouldRequestRuntimeApi() ? "실시간 추천 준비 완료" : "사전 계산 추천 사용"
    );
    render();
    bindEvents();
    syncStepViewState();
    const skipIntro = Boolean(state.sharedRoutePreview) || shouldSkipSiteIntro();
    if (skipIntro) {
      bypassSiteIntro();
    } else {
      window.requestAnimationFrame(openSiteIntro);
    }
    window.requestAnimationFrame(() => {
      if (state.sharedRoutePreview) {
        openSavedRoutesModal();
        return;
      }
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
