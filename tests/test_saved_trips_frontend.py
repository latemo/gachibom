import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAVED_TRIPS_SCRIPT = ROOT / "web" / "saved-trips.js"
APP_SCRIPT = ROOT / "web" / "app.js"
INDEX_FILE = ROOT / "web" / "index.html"
STYLES_FILE = ROOT / "web" / "styles.css"
SEED_FILE = ROOT / "web" / "data" / "app_recommendation_seed.json"
MAP_FALLBACK_FILE = ROOT / "web" / "assets" / "jeju-map-fallback.svg"
LEAFLET_JS_FILE = ROOT / "web" / "vendor" / "leaflet" / "leaflet.js"
LEAFLET_CSS_FILE = ROOT / "web" / "vendor" / "leaflet" / "leaflet.css"
LEAFLET_LICENSE_FILE = ROOT / "web" / "vendor" / "leaflet" / "LICENSE"


HARNESS_PREFIX = r"""
const fs = require("fs");
const vm = require("vm");
const path = process.argv[1];
const source = fs.readFileSync(path, "utf8");
const context = { window: {}, URL, TextEncoder, Set };
vm.runInNewContext(source, context);
const api = context.window.GachibomSavedTrips;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`${message}: expected ${expectedJson}, got ${actualJson}`);
  }
}

function memoryStorage(initialValue) {
  const values = new Map();
  if (initialValue !== undefined) values.set(api.STORAGE_KEY, initialValue);
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, value); },
    raw() { return values.get(api.STORAGE_KEY); }
  };
}
"""


class SavedTripsFrontendTests(unittest.TestCase):
    def run_node(self, body):
        result = subprocess.run(
            ["node", "-e", HARNESS_PREFIX + body, str(SAVED_TRIPS_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_save_restore_check_update_and_remove(self):
        self.run_node(
            r"""
const allowed = new Set(["spot_a", "spot_b", "spot_c"]);
const storage = memoryStorage();
let items = api.upsert([], ["spot_a", "spot_b"], allowed, {
  now: "2026-07-12T01:02:03.000Z"
});
const routeId = items[0].id;
const checkId = api.checkId("spot_a", "경사로 운영 여부 확인");
items = api.updateCheck(items, routeId, checkId, true, allowed);

// 정규화 과정에서 저장 대상이 아닌 프로필·점수·문구가 제거되는지도 함께 검증한다.
items[0].traveler_summary = { disability: "private" };
items[0].score = 99;
items[0].checkText = "경사로 운영 여부 확인";
const saved = api.persist(storage, items, allowed, "2026-07-12");
assert(saved.ok, "persist should succeed");

const document = JSON.parse(storage.raw());
equal(Object.keys(document).sort(), ["dataVersion", "items", "schemaVersion"], "root fields");
equal(
  Object.keys(document.items[0]).sort(),
  ["checkedIds", "id", "itinerary", "savedAt", "spotIds"],
  "saved route fields"
);
equal(
  Object.keys(document.items[0].itinerary).sort(),
  ["date", "orderedSpotIds", "startTime"],
  "itinerary fields"
);
assert(!storage.raw().includes("traveler_summary"), "profile must not be stored");
assert(!storage.raw().includes("checkText"), "check text must not be stored");
assert(!storage.raw().includes("score"), "score must not be stored");

const restored = api.load(storage, allowed);
assert(restored.length === 1, "one route should be restored");
equal(restored[0].spotIds, ["spot_a", "spot_b"], "restored spots");
equal(restored[0].checkedIds, [checkId], "restored checks");
equal(restored[0].itinerary, {
  date: null,
  startTime: null,
  orderedSpotIds: ["spot_a", "spot_b"]
}, "default itinerary");
assert(restored[0].savedAt === "2026-07-12T01:02:03.000Z", "saved time should be stable");

const unchecked = api.updateCheck(restored, routeId, checkId, false, allowed);
equal(unchecked[0].checkedIds, [], "unchecked state");
const removed = api.remove(unchecked, routeId, allowed);
equal(removed, [], "route removal");
"""
        )

    def test_v1_migration_and_itinerary_validation(self):
        self.run_node(
            r"""
const allowed = new Set(["spot_a", "spot_b", "spot_c"]);
const checkId = api.checkId("spot_a", "운영 시간 확인");
const legacyStorage = memoryStorage(JSON.stringify({
  schemaVersion: 1,
  dataVersion: "legacy",
  items: [{
    id: "ignored-legacy-id",
    spotIds: ["spot_a", "spot_b", "spot_c"],
    checkedIds: [checkId],
    savedAt: "2026-07-12T00:00:00.000Z"
  }]
}));
let items = api.load(legacyStorage, allowed);
assert(items.length === 1, "v1 route should migrate");
equal(items[0].itinerary, {
  date: null,
  startTime: null,
  orderedSpotIds: ["spot_a", "spot_b", "spot_c"]
}, "v1 itinerary defaults");

const routeId = items[0].id;
items = api.updateItinerary(items, routeId, {
  date: "2028-02-29",
  startTime: "23:59"
}, allowed);
items = api.updateSpotOrder(items, routeId, ["spot_c", "spot_a", "spot_b"], allowed);
assert(items[0].id === routeId, "planning must not change route id");
equal(items[0].checkedIds, [checkId], "planning must preserve checks");
equal(items[0].spotIds, ["spot_a", "spot_b", "spot_c"], "original route order must remain stable");
equal(items[0].itinerary, {
  date: "2028-02-29",
  startTime: "23:59",
  orderedSpotIds: ["spot_c", "spot_a", "spot_b"]
}, "valid itinerary update");

const validSnapshot = JSON.stringify(items);
equal(
  api.updateItinerary(items, routeId, { date: "2027-02-29", startTime: "23:59" }, allowed),
  items,
  "invalid calendar date should be rejected"
);
equal(
  api.updateItinerary(items, routeId, { date: "2028-02-29", startTime: "24:00" }, allowed),
  items,
  "invalid time should be rejected"
);
for (const invalidOrder of [
  ["spot_a", "spot_a", "spot_b"],
  ["spot_a", "spot_b"],
  ["spot_a", "spot_b", "unknown"]
]) {
  equal(api.updateSpotOrder(items, routeId, invalidOrder, allowed), items, "invalid order should be rejected");
}
assert(JSON.stringify(items) === validSnapshot, "invalid updates must not mutate the source array");

items = api.upsert(items, ["spot_a", "spot_b", "spot_c"], allowed, {
  now: "2026-07-13T00:00:00.000Z"
});
equal(items[0].itinerary.orderedSpotIds, ["spot_c", "spot_a", "spot_b"], "duplicate save keeps order");
assert(items[0].itinerary.date === "2028-02-29", "duplicate save keeps date");

const storage = memoryStorage();
const persisted = api.persist(storage, items, allowed, "v2");
assert(persisted.ok, "migrated itinerary should persist");
assert(JSON.parse(storage.raw()).schemaVersion === 2, "next persist should write schema v2");
equal(api.load(storage, allowed)[0].itinerary, items[0].itinerary, "v2 itinerary round trip");
"""
        )

    def test_route_ids_do_not_collide_and_retired_places_are_preserved(self):
        self.run_node(
            r"""
const first = [
  "jeju_forest_healing_001",
  "jeju_restaurant_donsadon_037",
  "jeju_tourism_weak_031"
];
const second = [
  "jeju_indoor_haenyeo_024",
  "jeju_sea_olle14_018",
  "jeju_restaurant_donsadon_037"
];
const allowed = new Set([...first, ...second]);
assert(api.routeId(first) !== api.routeId(second), "distinct routes must have distinct canonical ids");

const legacyV2 = memoryStorage(JSON.stringify({
  schemaVersion: 2,
  dataVersion: "legacy-v2",
  items: [{
    id: "route-c955fd4e",
    spotIds: first,
    checkedIds: [],
    itinerary: { date: null, startTime: null, orderedSpotIds: first },
    savedAt: "2026-07-11T00:00:00.000Z"
  }]
}));
const migratedV2 = api.load(legacyV2, allowed);
assert(migratedV2[0].id === api.routeId(first), "legacy v2 hash id should migrate to the canonical id");
equal(migratedV2[0].spotIds, first, "v2 migration should preserve route contents");

let items = api.upsert([], first, allowed, { now: "2026-07-12T00:00:00.000Z" });
items = api.upsert(items, second, allowed, { now: "2026-07-13T00:00:00.000Z" });
assert(items.length === 2, "previously colliding routes must both be saved");

const storage = memoryStorage();
assert(api.persist(storage, items, allowed, "before-retirement").ok, "fixture should persist");
const currentCatalog = new Set([...first, ...second].filter((spotId) => spotId !== first[1]));
const restored = api.load(storage, currentCatalog);
assert(restored.length === 2, "a retired place must not delete its whole saved route");
const retiredRoute = restored.find((item) => item.id === api.routeId(first));
equal(retiredRoute.spotIds, first, "retired place id should be retained as a tombstone");
assert(api.buildShareUrl("https://example.com/", first, currentCatalog) === null, "retired places must not enter new share links");
"""
        )

    def test_duplicate_upsert_preserves_checks_and_moves_route_to_front(self):
        self.run_node(
            r"""
const allowed = new Set(["spot_a", "spot_b", "spot_c"]);
let items = api.upsert([], ["spot_a", "spot_b"], allowed, {
  now: "2026-07-10T00:00:00.000Z"
});
const duplicateId = items[0].id;
const checkId = api.checkId("spot_a", "운영 시간 확인");
items = api.updateCheck(items, duplicateId, checkId, true, allowed);
items = api.upsert(items, ["spot_c"], allowed, {
  now: "2026-07-11T00:00:00.000Z"
});
items = api.upsert(items, ["spot_a", "spot_b"], allowed, {
  now: "2026-07-12T00:00:00.000Z"
});

assert(items.length === 2, "duplicate route must not increase item count");
assert(items[0].id === duplicateId, "updated duplicate should move to front");
equal(items[0].checkedIds, [checkId], "duplicate should preserve checked state");
assert(items[0].savedAt === "2026-07-12T00:00:00.000Z", "duplicate should refresh saved time");
"""
        )

    def test_saved_routes_are_limited_to_twenty(self):
        self.run_node(
            r"""
const spotIds = Array.from({ length: 25 }, (_, index) => `spot_${index}`);
const allowed = new Set(spotIds);
let items = [];
for (let index = 0; index < spotIds.length; index += 1) {
  items = api.upsert(items, [spotIds[index]], allowed, {
    now: `2026-07-${String(index + 1).padStart(2, "0")}T00:00:00.000Z`
  });
}

assert(api.MAX_ITEMS === 20, "public maximum should remain 20");
assert(items.length === 20, "in-memory routes should be capped at 20");
equal(items[0].spotIds, ["spot_24"], "newest route should be first");
equal(items[19].spotIds, ["spot_5"], "oldest retained route should be the twentieth newest");

const storage = memoryStorage();
const saved = api.persist(storage, items, allowed, "v1");
assert(saved.ok, "capped routes should persist");
assert(api.load(storage, allowed).length === 20, "restored routes should remain capped at 20");
"""
        )

    def test_broken_storage_fails_closed_and_retired_ids_are_sanitized(self):
        self.run_node(
            r"""
const allowed = new Set(["spot_a"]);
equal(api.load(memoryStorage("{broken"), allowed), [], "malformed JSON");
equal(
  api.load(memoryStorage(JSON.stringify({ schemaVersion: 999, items: [] })), allowed),
  [],
  "unknown schema"
);
equal(api.load(memoryStorage("x".repeat(64 * 1024 + 1)), allowed), [], "oversized storage");
equal(api.load({ getItem() { throw new Error("denied"); } }, allowed), [], "read failure");

const invalidItems = JSON.stringify({
  schemaVersion: api.SCHEMA_VERSION,
   items: [
     { spotIds: ["unknown_spot"], checkedIds: [], savedAt: "2026-07-12T00:00:00.000Z" },
     { spotIds: ["<img_onerror>"], checkedIds: [], savedAt: "2026-07-12T00:00:00.000Z" },
     { spotIds: ["spot_a"], checkedIds: [], savedAt: "not-a-date" }
   ]
 });
const sanitized = api.load(memoryStorage(invalidItems), allowed);
assert(sanitized.length === 1, "only a syntactically safe retired-place record should survive");
equal(sanitized[0].spotIds, ["unknown_spot"], "safe retired id should be preserved as a tombstone");

const valid = api.upsert([], ["spot_a"], allowed, { now: "2026-07-12T00:00:00.000Z" });
const failed = api.persist({
  getItem() { return null; },
  setItem() { throw new Error("quota exceeded"); }
}, valid, allowed, "v1");
assert(!failed.ok, "write failure should be reported without throwing");
assert(failed.items.length === 1, "normalized in-memory data should be retained after write failure");
"""
        )

    def test_share_url_is_fresh_minimal_and_round_trips(self):
        self.run_node(
            r"""
const allowed = new Set(["spot_a", "spot_b", "spot_c"]);
const shared = api.buildShareUrl(
  { href: "https://example.test/app/index.html?token=secret&api_key=hidden&intro=0&date=2026-08-01&startTime=09%3A00&checked=1#private" },
  ["spot_a", "spot_b"],
  allowed
);
assert(shared instanceof URL, "valid route should produce a URL");
assert(shared.origin === "https://example.test", "origin should be preserved");
assert(shared.pathname === "/app/index.html", "pathname should be preserved");
assert(shared.hash === "#recommendations", "share target hash");
equal(Array.from(shared.searchParams.keys()), ["share", "spot", "spot"], "share query keys");
assert(shared.searchParams.get("share") === "1", "share flag");
equal(shared.searchParams.getAll("spot"), ["spot_a", "spot_b"], "shared spot ids");
assert(!shared.href.includes("token"), "current token must be discarded");
assert(!shared.href.includes("api_key"), "current api key must be discarded");
assert(!shared.href.includes("intro"), "current intro flag must be discarded");
assert(!shared.href.includes("checked"), "check state must not be shared");
assert(!shared.href.includes("date"), "trip date must not be shared");
assert(!shared.href.includes("startTime"), "start time must not be shared");
assert(!shared.href.includes("order"), "custom order must not be shared");
equal(api.parseSharedSpotIds(shared, allowed), ["spot_a", "spot_b"], "share round trip");
assert(api.buildShareUrl("https://example.test/app", ["unknown"], allowed) === null, "unknown spot");
"""
        )

    def test_invalid_share_urls_are_rejected(self):
        self.run_node(
            r"""
const allowed = new Set(["spot_a", "spot_b", "spot_c", "spot_d", "spot_e"]);
const invalidUrls = [
  "not a url",
  "https://example.test/app?spot=spot_a",
  "https://example.test/app?share=0&spot=spot_a",
  "https://example.test/app?share=1",
  "https://example.test/app?share=1&spot=spot_a&spot=spot_a",
  "https://example.test/app?share=1&spot=spot_a&spot=spot_b&spot=spot_c&spot=spot_d&spot=spot_e",
  "https://example.test/app?share=1&spot=unknown",
  "https://example.test/app?share=1&spot=spot%2Fa",
  `https://example.test/app?share=1&spot=spot_a&padding=${"x".repeat(1100)}`
];
for (const url of invalidUrls) {
  assert(api.parseSharedSpotIds(url, allowed) === null, `invalid URL accepted: ${url}`);
}
"""
        )

    def test_app_save_restore_check_reopen_and_delete_flow(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`${message}: expected ${expectedJson}, got ${actualJson}`);
  }
}

const storageValues = new Map();
const storage = {
  getItem(key) { return storageValues.has(key) ? storageValues.get(key) : null; },
  setItem(key, value) { storageValues.set(key, value); },
  raw(key) { return storageValues.get(key); }
};
function attributeNode() {
  const attributes = new Set();
  return {
    attributes,
    setAttribute(name) { attributes.add(name); },
    removeAttribute(name) { attributes.delete(name); }
  };
}
const appShell = attributeNode();
const helpbotWing = attributeNode();
const modalCloseButton = { focus() {} };
const savedRoutesModal = {
  hidden: true,
  contains() { return false; },
  querySelector(selector) { return selector === ".modal-close-button" ? modalCloseButton : null; }
};
const bodyClasses = new Set();
const document = {
  activeElement: null,
  body: {
    classList: {
      add(name) { bodyClasses.add(name); },
      remove(name) { bodyClasses.delete(name); },
      contains(name) { return bodyClasses.has(name); }
    }
  },
  getElementById(id) { return id === "savedRoutesModal" ? savedRoutesModal : null; },
  querySelector(selector) {
    if (selector === ".app-shell") return appShell;
    if (selector === ".helpbot-wing-wrap") return helpbotWing;
    return null;
  },
  querySelectorAll() { return []; }
};
let nextTimerId = 0;
const clearedTimerIds = [];
const window = {
  GachibomSavedTrips: null,
  localStorage: storage,
  location: {
    href: "https://example.test/?intro=0#recommendations",
    search: "?intro=0",
    hash: "#recommendations"
  },
  history: {},
  requestAnimationFrame(callback) { callback(); },
  setTimeout() { nextTimerId += 1; return nextTimerId; },
  clearTimeout(timerId) { if (timerId) clearedTimerIds.push(timerId); }
};
const context = vm.createContext({
  window,
  document,
  navigator: {},
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
});

vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
let appSource = fs.readFileSync(process.argv[2], "utf8");
appSource = appSource.replace(/\ninit\(\);\s*$/, `
const __actualOpenSavedRoutesModal = openSavedRoutesModal;
const __actualCloseSavedRoutesModal = closeSavedRoutesModal;
const __savedFlowEffects = {
  refreshCount: 0,
  renderCount: 0,
  modalRenderCount: 0,
  closeOptions: null,
  navigation: null
};
refreshSavedRouteViews = () => { __savedFlowEffects.refreshCount += 1; };
renderSavedRoutesModal = () => { __savedFlowEffects.modalRenderCount += 1; };
focusSavedRouteDeleteButton = () => {};
render = () => { __savedFlowEffects.renderCount += 1; };
closeSavedRoutesModal = (options = {}) => { __savedFlowEffects.closeOptions = options; };
navigateToSection = (target, href, options = {}) => {
  __savedFlowEffects.navigation = { target, href, options };
};
globalThis.__savedFlowApp = {
  state,
  effects: __savedFlowEffects,
  currentRouteSpotIds,
  loadSavedRouteState,
  saveCurrentRoute,
  savedRouteChecklist,
  updateSavedRouteCheck,
  updateSavedRouteItinerary,
  moveSavedRouteSpot,
  savedRouteCardMarkup,
  shareableSavedSpotIds,
  safePhoneHref,
  visitInfoMarkup,
  mergePlaceLocation,
  locationPointLabel,
  locationPointShortLabel,
  locationPointStatusLabel,
  pointRoleBadgeMarkup,
  mapPointDisplayName,
  kakaoPlaceUrl,
  routeStepMarkup,
  openSavedRoute,
  requestDeleteSavedRoute,
  openSavedRoutesModal: __actualOpenSavedRoutesModal,
  closeSavedRoutesModal: __actualCloseSavedRoutesModal
};
`);
vm.runInContext(appSource, context);

const api = context.window.GachibomSavedTrips;
const app = context.__savedFlowApp;
const seed = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
app.state.data = seed;
const routeStartPlace = seed.saved_route_places.find((place) => place.location?.point_role === "route_start");
assert(routeStartPlace, "fixture should contain a route start point");
assert(app.locationPointLabel(routeStartPlace.location) === "코스 시작점", "route start label should be explicit");
assert(app.locationPointShortLabel(routeStartPlace.location) === "시작점", "fallback map label should stay compact");
assert(app.locationPointStatusLabel(routeStartPlace.location).includes("코스 시작점"), "map status should expose the point role");
assert(app.mapPointDisplayName(routeStartPlace).includes("(코스 시작점)"), "external map label should include the point role");
assert(decodeURIComponent(app.kakaoPlaceUrl(routeStartPlace)).includes("코스 시작점"), "Kakao map URL should retain the point role");
const pointBadge = app.pointRoleBadgeMarkup(routeStartPlace.location, "route-point-role");
assert(pointBadge.includes("route-point-role") && pointBadge.includes("코스 시작점"), "point role badge should render");
const pointStep = app.routeStepMarkup({ place: routeStartPlace, location: routeStartPlace.location, score: 88 }, 0);
assert(pointStep.includes("route-point-role") && pointStep.includes("코스 시작점"), "route itinerary should render the point role");
const mergedPoint = app.mergePlaceLocation(
  { latitude: routeStartPlace.location.latitude, longitude: routeStartPlace.location.longitude },
  routeStartPlace.location
);
assert(mergedPoint.point_role === "route_start", "coordinate-only runtime data should preserve the static point role");
const invalidMergedPoint = app.mergePlaceLocation(
  { latitude: routeStartPlace.location.latitude, longitude: routeStartPlace.location.longitude, point_role: "unsupported" },
  routeStartPlace.location
);
assert(invalidMergedPoint.point_role === "route_start", "invalid runtime point roles should not erase the static role");
assert(app.locationPointLabel({ point_role: "unsupported" }) === "장소 대표점", "unknown point roles should fail closed");
const savedScenario = seed.scenarios[0];
app.state.scenarioId = savedScenario.id;
app.state.runtimeScenario = null;
const savedSpotIds = app.currentRouteSpotIds();
assert(savedSpotIds.length > 0, "fixture scenario must have a public route");

assert(app.saveCurrentRoute(), "app should save the current route");
assert(app.state.savedRoutes.length === 1, "saved route should enter app state");
equal(app.state.savedRoutes[0].spotIds, savedSpotIds, "saved route spots");
assert(app.effects.refreshCount === 1, "saving should refresh saved-route UI");
const routeId = app.state.savedRoutes[0].id;
let storedDocument = JSON.parse(storage.raw(api.STORAGE_KEY));
assert(storedDocument.items.length === 1, "saving should write localStorage");
equal(storedDocument.items[0].spotIds, savedSpotIds, "persisted route spots");

// 새 페이지가 같은 localStorage를 읽는 상황을 앱 상태 초기화로 재현한다.
app.state.savedRoutes = [];
app.state.sharedRoutePreview = null;
app.loadSavedRouteState();
assert(app.state.savedRoutes.length === 1, "loadSavedRouteState should restore the route");
assert(app.state.savedRoutes[0].id === routeId, "restored route id should remain stable");
const alreadySavedShareUrl = api.buildShareUrl(
  window.location,
  savedSpotIds,
  app.shareableSavedSpotIds()
);
window.location.href = alreadySavedShareUrl.href;
window.location.search = alreadySavedShareUrl.search;
window.location.hash = alreadySavedShareUrl.hash;
app.loadSavedRouteState();
assert(
  app.state.sharedRoutePreview === null,
  "a shared route already in local storage must not render a duplicate preview"
);

const checklist = app.savedRouteChecklist(app.state.savedRoutes[0]);
assert(checklist.length > 0, "restored route should expose visit checks");
const checkId = checklist[0].id;
app.updateSavedRouteCheck(routeId, checkId, true);
equal(app.state.savedRoutes[0].checkedIds, [checkId], "check should update app state");
storedDocument = JSON.parse(storage.raw(api.STORAGE_KEY));
equal(storedDocument.items[0].checkedIds, [checkId], "check should persist to localStorage");

app.updateSavedRouteItinerary(routeId, "2026-08-01", "09:30");
assert(app.state.savedRoutes[0].itinerary.date === "2026-08-01", "trip date should update app state");
assert(app.state.savedRoutes[0].itinerary.startTime === "09:30", "start time should update app state");
storedDocument = JSON.parse(storage.raw(api.STORAGE_KEY));
assert(storedDocument.items[0].itinerary.date === "2026-08-01", "trip date should persist");

const originalRouteId = app.state.savedRoutes[0].id;
const originalSpotIds = [...app.state.savedRoutes[0].spotIds];
const movedSpotId = originalSpotIds[1];
app.moveSavedRouteSpot(routeId, movedSpotId, -1);
assert(app.state.savedRoutes[0].id === originalRouteId, "reordering must keep route id");
equal(app.state.savedRoutes[0].spotIds, originalSpotIds, "reordering must keep original route order");
assert(app.state.savedRoutes[0].itinerary.orderedSpotIds[0] === movedSpotId, "planned order should move");
storedDocument = JSON.parse(storage.raw(api.STORAGE_KEY));
assert(storedDocument.items[0].itinerary.orderedSpotIds[0] === movedSpotId, "planned order should persist");
const itineraryMarkup = app.savedRouteCardMarkup(app.state.savedRoutes[0]);
assert(itineraryMarkup.includes('value="2026-08-01"'), "saved date should render");
assert(itineraryMarkup.includes('value="09:30"'), "saved start time should render");
assert(itineraryMarkup.includes("예상 체류"), "stay duration should render");
assert(itineraryMarkup.includes("data-move-saved-route"), "order controls should render");
assert(itineraryMarkup.includes('aria-label="저장한 코스 방문 순서"'), "saved stops should expose their visit order");
assert(itineraryMarkup.includes('class="saved-route-order-actions" role="group"'), "order controls should be grouped separately");
assert(itineraryMarkup.includes('class="saved-route-place-links" role="group"'), "place links should be grouped separately");
assert(itineraryMarkup.includes('class="saved-route-map-link"'), "map should be the primary place action");
assert(itineraryMarkup.includes("<span>위로</span>"), "move controls should have a visible label");
assert(itineraryMarkup.includes("<span>아래로</span>"), "move controls should have a visible label");
assert(itineraryMarkup.includes("https://map.kakao.com/link/by/car/"), "full Kakao route should render when coordinates exist");
assert(itineraryMarkup.includes("<span>정보</span></a>"), "public information link should render");
assert(itineraryMarkup.includes("<span>전화</span></a>"), "verified-format phone action should render when available");
assert(itineraryMarkup.includes("제주특별자치도"), "saved route should render the public address when available");
assert(itineraryMarkup.includes("saved-route-mini-map"), "saved route should render an embedded mini map");
assert(itineraryMarkup.includes("assets/jeju-map-fallback.svg"), "mini map should use the local map asset");
assert((itineraryMarkup.match(/class="saved-route-mini-marker"/g) || []).length === savedSpotIds.length, "mini map should render every located stop");
const movedPlace = seed.saved_route_places.find((place) => place.spot_id === movedSpotId);
assert(itineraryMarkup.includes(`<title>1번 ${movedPlace.name}</title>`), "mini map markers should follow the planned order");
assert(app.safePhoneHref("064-710-3490") === "tel:0647103490", "phone href should be normalized");
assert(app.safePhoneHref("javascript:alert(1)") === "", "unsafe phone input should be rejected");
const reviewedVisitPlace = seed.saved_route_places.find((place) => place.visit_info?.last_verified_at);
assert(reviewedVisitPlace, "fixture should contain manually reviewed visit info");
const reviewedVisitMarkup = app.visitInfoMarkup(reviewedVisitPlace);
assert(reviewedVisitMarkup.includes("방문 정보"), "detail should render the visit information section");
assert(reviewedVisitMarkup.includes(reviewedVisitPlace.visit_info.address), "detail should render the reviewed address");
assert(reviewedVisitMarkup.includes("정보 확인"), "manual source review date should be visible");
assert(!reviewedVisitMarkup.includes("현장 확인"), "source review must not be mislabeled as an on-site inspection");
assert(reviewedVisitMarkup.includes("정보 근거"), "detail should expose the reviewed evidence link");

const catalogVisitPlace = seed.saved_route_places.find(
  (place) => place.visit_info?.source_updated_at && !place.visit_info?.last_verified_at
);
assert(catalogVisitPlace, "fixture should retain catalog-only visit info");
const catalogVisitMarkup = app.visitInfoMarkup(catalogVisitPlace);
assert(catalogVisitMarkup.includes("재확인 필요"), "stale public data must not look currently verified");
assert(catalogVisitMarkup.includes("원본 갱신"), "dataset update date must be labeled separately from field verification");
assert(!catalogVisitMarkup.includes("정보 확인 2025"), "dataset update date must not look like a field verification date");

const unavailableSeedPlace = seed.saved_route_places.find((place) => place.available === false);
assert(unavailableSeedPlace, "fixture should retain an unavailable place for old saved routes");
assert(!app.shareableSavedSpotIds().has(unavailableSeedPlace.spot_id), "hidden places must be rejected by share URL validation");
const unavailableSpotIds = [savedSpotIds[0], unavailableSeedPlace.spot_id];
const unavailableItem = {
  id: api.routeId(unavailableSpotIds),
  spotIds: unavailableSpotIds,
  checkedIds: [],
  itinerary: { date: null, startTime: null, orderedSpotIds: unavailableSpotIds },
  savedAt: "2026-07-12T00:00:00.000Z"
};
const unavailableMarkup = app.savedRouteCardMarkup(unavailableItem);
assert(unavailableMarkup.includes("현재 정보 없음"), "hidden seed places should be unavailable in old saved routes");
assert(!unavailableMarkup.includes("data-share-saved-route"), "routes containing hidden places must not be shareable");
const sharedMarkup = app.savedRouteCardMarkup(app.state.savedRoutes[0], { shared: true });
assert(!sharedMarkup.includes("data-saved-trip-date"), "shared preview must not expose the trip date");
assert(!sharedMarkup.includes("data-move-saved-route"), "shared preview must not expose custom order controls");

const retiredSpotIds = [savedSpotIds[0], "retired_spot_999"];
const retiredItem = {
  id: api.routeId(retiredSpotIds),
  spotIds: retiredSpotIds,
  checkedIds: [],
  itinerary: { date: null, startTime: null, orderedSpotIds: retiredSpotIds },
  savedAt: "2026-07-12T00:00:00.000Z"
};
const retiredMarkup = app.savedRouteCardMarkup(retiredItem);
assert(retiredMarkup.includes("현재 정보 없음"), "retired place should render a neutral tombstone");
assert(retiredMarkup.includes("이 코스는 공유할 수 없습니다"), "share restriction should be explained");
assert(!retiredMarkup.includes("data-share-saved-route"), "a route with a retired place must not expose sharing");
assert((retiredMarkup.match(/<span>지도<\/span><\/a>/g) || []).length === 1, "retired place must not expose a map link");

const interruptedSpotIds = [savedSpotIds[0], "retired_spot_999", savedSpotIds[1]];
const interruptedItem = {
  id: api.routeId(interruptedSpotIds),
  spotIds: interruptedSpotIds,
  checkedIds: [],
  itinerary: { date: null, startTime: null, orderedSpotIds: interruptedSpotIds },
  savedAt: "2026-07-12T00:00:00.000Z"
};
const interruptedMarkup = app.savedRouteCardMarkup(interruptedItem);
assert(!interruptedMarkup.includes('class="saved-route-mini-path"'), "missing middle coordinates must break the mini-map route line");
assert(interruptedMarkup.includes("앞뒤 동선은 연결하지 않습니다"), "broken route segment should be explained");

const otherScenario = seed.scenarios.find((scenario) => (
  JSON.stringify(app.currentRouteSpotIds(scenario)) !== JSON.stringify(savedSpotIds)
));
assert(otherScenario, "fixture needs a different scenario for reopen navigation");
app.state.scenarioId = otherScenario.id;
app.state.runtimeScenario = { id: "runtime-route-that-must-be-cleared" };
assert(app.openSavedRoute(routeId), "saved route should reopen");
assert(app.state.scenarioId === savedScenario.id, "reopen should restore the saved scenario");
assert(app.state.runtimeScenario === null, "reopen should leave runtime recommendation state");
assert(app.state.selectedSpotId === movedSpotId, "reopen should select the first place in the planned order");
assert(app.state.apiState.status === "static", "reopen should mark the static recommendation state");
assert(app.effects.renderCount === 1, "reopen should render the restored route");
equal(app.effects.closeOptions, { restoreFocus: false }, "reopen should close the saved modal");
equal(
  app.effects.navigation,
  { target: "recommend", href: "#recommendations", options: { updateLocation: true } },
  "reopen should navigate to recommendations"
);

app.openSavedRoutesModal();
assert(appShell.attributes.has("inert"), "opening saved routes should isolate the app shell");
assert(helpbotWing.attributes.has("inert"), "opening saved routes should isolate the chatbot wing");
assert(bodyClasses.has("saved-routes-modal-open"), "opening saved routes should hide chatbot layers");
app.requestDeleteSavedRoute(routeId);
assert(app.state.pendingSavedRouteDeleteId === routeId, "first delete click should request confirmation");
assert(app.state.savedRoutes.length === 1, "first delete click must keep the route");
const pendingDeleteTimer = nextTimerId;
app.closeSavedRoutesModal({ restoreFocus: false });
assert(app.state.pendingSavedRouteDeleteId === null, "closing the modal should cancel delete confirmation");
assert(clearedTimerIds.includes(pendingDeleteTimer), "closing the modal should clear the delete timer");
assert(!appShell.attributes.has("inert"), "closing saved routes should restore the app shell");
assert(!helpbotWing.attributes.has("inert"), "closing saved routes should restore the chatbot wing");
assert(!bodyClasses.has("saved-routes-modal-open"), "closing saved routes should restore chatbot visibility");

app.requestDeleteSavedRoute(routeId);
assert(app.state.pendingSavedRouteDeleteId === routeId, "delete confirmation should be reusable after closing");
app.requestDeleteSavedRoute(routeId);
assert(app.state.pendingSavedRouteDeleteId === null, "confirmed delete should clear confirmation state");
equal(app.state.savedRoutes, [], "confirmed delete should remove app state");
storedDocument = JSON.parse(storage.raw(api.STORAGE_KEY));
equal(storedDocument.items, [], "confirmed delete should update localStorage");
"""
        result = subprocess.run(
            [
                "node",
                "-e",
                harness,
                str(SAVED_TRIPS_SCRIPT),
                str(APP_SCRIPT),
                str(SEED_FILE),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_route_geometry_anchors_every_stop_and_both_maps_use_it(self):
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")
        center_map_source = app[
            app.index("function drawCenterMap") : app.index("function renderLiveMapStats")
        ]
        route_map_source = app[
            app.index("function drawRouteMap") : app.index("function applyImageFallback")
        ]
        self.assertIn("routeGeometryWithStopAnchors(", center_map_source)
        self.assertIn("routeGeometryWithStopAnchors(", route_map_source)
        self.assertGreaterEqual(center_map_source.count("smoothFactor: 0"), 2)
        self.assertGreaterEqual(route_map_source.count("smoothFactor: 0"), 2)
        live_marker_source = styles[
            styles.index(".live-marker-icon {") : styles.index(".live-marker-icon span")
        ]
        route_marker_source = styles[
            styles.index(".route-marker-icon {") : styles.index(".route-marker-icon span")
        ]
        self.assertIn("position: absolute", live_marker_source)
        self.assertIn("position: absolute", route_marker_source)
        active_marker_source = styles[
            styles.index(".live-marker-icon.active span") : styles.index(".live-marker-role")
        ]
        self.assertNotIn("translateY(", active_marker_source)

        harness = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
globalThis.__routeAnchorTest = { routeGeometryWithStopAnchors };
`);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function samePoint(left, right) {
  return Number(left?.latitude) === Number(right?.latitude)
    && Number(left?.longitude) === Number(right?.longitude);
}

const context = {
  window: {
    GachibomSavedTrips: null,
    location: { search: "", hash: "", href: "https://example.test/" },
    history: {}
  },
  document: {},
  navigator: {},
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);

const api = context.__routeAnchorTest;
assert(api && typeof api.routeGeometryWithStopAnchors === "function", "anchor helper must be exposed");

const entries = [
  { place: { spot_id: "stop_a" }, location: { latitude: 33.5, longitude: 126.5 } },
  { place: { spot_id: "stop_b" }, location: { latitude: 33.4, longitude: 126.6 } },
  { place: { spot_id: "stop_c" }, location: { latitude: 33.3, longitude: 126.7 } }
];
const roadGeometry = [
  { latitude: 33.499, longitude: 126.501 },
  { latitude: 33.45, longitude: 126.55 },
  { latitude: 33.401, longitude: 126.599 },
  { latitude: 33.35, longitude: 126.65 },
  { latitude: 33.301, longitude: 126.699 }
];
const entriesBefore = JSON.stringify(entries);
const geometryBefore = JSON.stringify(roadGeometry);
const anchored = api.routeGeometryWithStopAnchors(entries, roadGeometry);

assert(Array.isArray(anchored), "anchored geometry must be an array");
assert(JSON.stringify(entries) === entriesBefore, "entries must not be mutated");
assert(JSON.stringify(roadGeometry) === geometryBefore, "road geometry must not be mutated");

let stopCursor = -1;
for (const entry of entries) {
  const nextIndex = anchored.findIndex((point, index) => index > stopCursor && samePoint(point, entry.location));
  assert(nextIndex > stopCursor, `stop ${entry.place.spot_id} must appear in route order`);
  const occurrences = anchored.filter((point) => samePoint(point, entry.location)).length;
  assert(occurrences === 1, `stop ${entry.place.spot_id} must be inserted exactly once`);
  stopCursor = nextIndex;
}

let roadCursor = -1;
for (const roadPoint of roadGeometry) {
  const nextIndex = anchored.findIndex((point, index) => index > roadCursor && samePoint(point, roadPoint));
  assert(nextIndex > roadCursor, "road geometry order must be preserved");
  roadCursor = nextIndex;
}

const alreadyAnchoredGeometry = [
  entries[0].location,
  { latitude: 33.45, longitude: 126.55 },
  entries[1].location,
  { latitude: 33.35, longitude: 126.65 },
  entries[2].location
];
const withoutDuplicates = api.routeGeometryWithStopAnchors(entries, alreadyAnchoredGeometry);
for (const entry of entries) {
  const occurrences = withoutDuplicates.filter((point) => samePoint(point, entry.location)).length;
  assert(occurrences === 1, `existing stop ${entry.place.spot_id} must not be duplicated`);
}
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_route_proxy_auto_detects_http_server_and_respects_overrides(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const app = fs.readFileSync(process.argv[1], "utf8");
const start = app.indexOf("function shouldRequestRouteProxy()");
const end = app.indexOf("async function requestRuntimeRecommendation", start);
assert(start >= 0 && end > start, "route proxy gate source must exist");
const gateSource = app.slice(start, end);

function routeProxyEnabled(search, protocol) {
  const context = {
    window: { location: { search, protocol } },
    URLSearchParams
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(`${gateSource}\nglobalThis.__result = shouldRequestRouteProxy();`, context);
  return context.__result;
}

assert(routeProxyEnabled("", "http:") === true, "HTTP servers should auto-detect the route proxy");
assert(routeProxyEnabled("", "https:") === true, "HTTPS servers should auto-detect the route proxy");
assert(routeProxyEnabled("", "file:") === false, "file previews should skip the route proxy");
assert(routeProxyEnabled("?routeProxy=0", "http:") === false, "routeProxy=0 should disable the proxy");
assert(routeProxyEnabled("?api=0", "http:") === false, "api=0 should keep the legacy disable override");
assert(routeProxyEnabled("?routeProxy=1", "file:") === true, "routeProxy=1 should explicitly enable the proxy");
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_site_wires_saved_routes_before_the_main_app(self):
        index = INDEX_FILE.read_text(encoding="utf-8")
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        self.assertLess(index.index("saved-trips.js"), index.index("app.js"))
        self.assertIn('id="savedRoutesModal"', index)
        self.assertIn("data-open-saved-routes", index)
        self.assertGreaterEqual(index.count("data-save-current-route"), 2)
        self.assertIn("styles.css?v=20260716-1", index)
        self.assertIn("app.js?v=20260716-2", index)
        self.assertIn("top-save-route-button", index)
        self.assertIn("live-map-save-button", index)
        self.assertIn("loadSavedRouteState();", app)
        self.assertIn("SAVED_TRIPS.parseSharedSpotIds", app)
        self.assertIn("buildShareUrl(window.location", app)
        self.assertIn("state.data?.saved_route_places", app)
        self.assertIn("data-open-saved-route", app)
        self.assertIn("[data-saved-route-id][data-saved-check-id]", app)
        self.assertIn("data-saved-trip-date", app)
        self.assertIn("data-saved-start-time", app)
        self.assertIn("data-move-saved-route", app)
        self.assertIn("https://map.kakao.com/link/by/car/", app)
        self.assertIn('id="mapFallbackArt"', index)
        self.assertIn('id="mapRouteLayer"', index)
        self.assertIn("vendor/leaflet/leaflet.js?v=1.9.4", index)
        self.assertIn("vendor/leaflet/leaflet.css?v=1.9.4", index)
        self.assertNotIn("unpkg.com/leaflet", index)
        self.assertIn("activateCenterMapFallback", app)
        self.assertIn("map-fallback-active", app)
        self.assertIn("saved-route-mini-map", app)
        self.assertIn("visitInfoMarkup", app)
        self.assertIn("locationPointLabel", app)
        self.assertIn("pointRoleBadgeMarkup", app)
        self.assertIn("safePhoneHref", app)
        self.assertIn("© OpenStreetMap contributors", index)
        self.assertIn("© OpenStreetMap contributors", app)
        checklist_source = app[
            app.index("function savedRouteChecklist") : app.index("function updateSavedRouteCheck")
        ]
        self.assertNotIn("check_before_visit", checklist_source)
        self.assertIn(".saved-routes-modal-panel", styles)
        self.assertIn(".saved-routes-modal .modal-close-button", styles)
        self.assertIn("flex: 0 0 44px", styles)
        self.assertIn("body.saved-routes-modal-open .helpbot-wing-wrap", styles)
        self.assertIn(
            "body.saved-routes-modal-open .helpbot-wing-wrap {\n  display: none !important;",
            styles,
        )
        self.assertIn(".saved-route-itinerary", styles)
        self.assertIn(".saved-route-place-actions", styles)
        saved_route_place_styles = styles[
            styles.index(".saved-route-places {") : styles.index(".saved-route-mini-map {")
        ]
        self.assertNotIn("repeat(2, minmax(0, 1fr))", saved_route_place_styles)
        self.assertIn(".saved-route-place-main", saved_route_place_styles)
        self.assertIn(".saved-route-order-actions", saved_route_place_styles)
        self.assertIn(".saved-route-place-links .saved-route-map-link", saved_route_place_styles)
        self.assertIn("white-space: normal", saved_route_place_styles)
        self.assertIn("button:focus-visible", saved_route_place_styles)
        self.assertIn(".saved-route-mini-map", styles)
        self.assertIn(".visit-info-card", styles)
        self.assertIn(".live-marker-role", styles)
        self.assertIn(".map-popup-point-role", styles)
        self.assertIn(".route-point-role", styles)
        self.assertIn(".route-map-fallback-role", styles)
        self.assertIn(".map-frame.map-fallback-active", styles)
        self.assertIn("body.journey-in-view .top-save-route-button", styles)
        self.assertIn(".live-map-save-button.saved", styles)
        self.assertIn(".saved-route-card.shared > footer", styles)

    def test_desktop_header_reserves_space_for_journey_actions(self):
        styles = STYLES_FILE.read_text(encoding="utf-8")

        topbar_start = styles.index(".topbar {")
        topbar_end = styles.index("}", topbar_start)
        topbar_rule = styles[topbar_start:topbar_end]
        nav_start = styles.index(".nav-tabs {")
        nav_end = styles.index("}", nav_start)
        nav_rule = styles[nav_start:nav_end]

        self.assertIn(
            "grid-template-columns: max-content minmax(0, 1fr) max-content",
            topbar_rule,
        )
        self.assertIn("border-bottom: 1px solid #d6dbe5", topbar_rule)
        self.assertIn("background: rgba(243, 245, 249, 0.96)", topbar_rule)
        self.assertIn("box-shadow: 0 4px 18px rgba(18, 28, 42, 0.06)", topbar_rule)
        self.assertIn("min-width: 0", nav_rule)
        self.assertIn("overflow-x: auto", nav_rule)

        nav_link_start = styles.index(".nav-tabs a {")
        nav_link_end = styles.index("}", nav_link_start)
        nav_link_rule = styles[nav_link_start:nav_link_end]
        self.assertIn("color: #4f5968", nav_link_rule)

        brand_mark_start = styles.index(".brand-mark {")
        brand_mark_end = styles.index("}", brand_mark_start)
        brand_mark_rule = styles[brand_mark_start:brand_mark_end]
        brand_video_start = styles.index(".brand-logo-video {")
        brand_video_end = styles.index("}", brand_video_start)
        brand_video_rule = styles[brand_video_start:brand_video_end]
        self.assertIn("background: transparent", brand_mark_rule)
        self.assertIn("mix-blend-mode: multiply", brand_video_rule)

    def test_profile_scenario_cards_are_compact_and_use_semantic_icons(self):
        index = INDEX_FILE.read_text(encoding="utf-8")
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        for icon_class in (
            "bi-heart-pulse",
            "bi-egg-fried",
            "bi-people",
            "bi-person-wheelchair",
            "bi-cloud-rain",
        ):
            self.assertIn(f'iconClass: "{icon_class}"', app)

        self.assertIn('class="scenario-tile-icon"', app)
        self.assertIn('class="profile-scenario-section"', index)
        self.assertIn('class="profile-options-section"', index)
        self.assertLess(
            index.index('class="profile-scenario-section"'),
            index.index('class="profile-options-section"'),
        )
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", styles)
        self.assertIn("flex-wrap: nowrap", styles)
        self.assertIn(".scenario-tile-icon {", styles)
        self.assertIn("min-height: 64px", styles)

    def test_selected_theme_expands_into_personalized_recipe_result(self):
        index = INDEX_FILE.read_text(encoding="utf-8")
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        self.assertIn('id="conceptPreferenceSentences"', index)
        self.assertIn('id="conceptFitNote"', index)
        self.assertIn("이 코스로 여행하기", index)
        self.assertIn("RAG 조건 입력", index)
        self.assertIn("전체 테마 보기", index)
        self.assertIn("conceptRecipeProfiles", app)
        self.assertIn("conceptPreferenceSentencesMarkup", app)
        self.assertIn("data-concept-focus-key", app)
        self.assertIn("staticConditionVariant", app)
        self.assertIn("data-concept-place-id", app)
        self.assertIn("aria-pressed", app)
        self.assertNotIn('id="conceptRecipeCharacterSecondary"', index)
        self.assertIn("조건을 누르면 그 기준을 먼저 반영해요.", index)
        self.assertIn(
            "scenarioCards.filter((card) => card.id === state.scenarioId)",
            app,
        )
        self.assertIn(
            "grid-template-columns: clamp(300px, 19vw, 370px) minmax(0, 1fr)",
            styles,
        )
        self.assertIn(
            "body.concept-result-open .concept-main > h1",
            styles,
        )
        self.assertIn("height: var(--concept-stage-height)", styles)
        self.assertIn(".concept-preference-chip:focus-visible", styles)
        self.assertIn(".concept-preference-chip.is-priority", styles)

    def test_theme_cards_use_clean_line_art_instead_of_photo_backgrounds(self):
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        self.assertEqual(app.count("theme-line-"), 5)
        self.assertIn('class="concept-card-line-art"', app)
        self.assertIn('class="concept-card-character"', app)
        self.assertIn('class="concept-card-score-row"', app)
        self.assertIn('class="concept-card-shield"', app)
        self.assertIn("bi-heart-fill", app)
        self.assertIn('aria-pressed="${active ? "true" : "false"}"', app)
        self.assertIn("solid var(--theme-rail)", styles)
        self.assertIn(".concept-card.rose .concept-card-line-art", styles)
        self.assertIn("background: #fff", styles)
        self.assertNotIn("--theme-image:", styles)
        self.assertNotIn("theme-recovery-editorial.webp", styles)

    def test_concept_travel_time_uses_the_shared_route_summary(self):
        app = APP_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("travelMinutes:", app)
        self.assertIn("conceptTravelTimeSnapshot(activeScenario)", app)
        self.assertIn("cachedRouteSummaryWithRoadGeometry(snapshot.entries)", app)
        self.assertIn('data-concept-travel-route-key="${escapeHtml(travelTime.routeKey)}"', app)
        self.assertIn("currentRouteKey !== snapshot.routeKey", app)

    def test_recommendation_layout_uses_condition_bar_and_responsive_map_detail_columns(self):
        index = INDEX_FILE.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        recommendations_start = index.index(
            '<main class="journey-layout" id="recommendations">'
        )
        recommendations_end = index.index("</main>", recommendations_start)
        recommendations = index[recommendations_start:recommendations_end]

        self.assertNotIn("companion-card", recommendations)
        condition_bar_start = recommendations.index("journey-condition-bar")
        map_panel_start = recommendations.index('id="mapPanel"')
        place_detail_start = recommendations.index('id="placeDetail"')
        condition_bar = recommendations[condition_bar_start:map_panel_start]
        self.assertIn('id="matchNote"', condition_bar)
        self.assertIn('id="safetyNotice"', condition_bar)
        self.assertIn("data-open-profile-modal", condition_bar)
        self.assertLess(map_panel_start, place_detail_start)

        def css_block(source, marker):
            marker_start = source.index(marker)
            opening_brace = source.index("{", marker_start)
            depth = 1
            cursor = opening_brace + 1
            while depth and cursor < len(source):
                if source[cursor] == "{":
                    depth += 1
                elif source[cursor] == "}":
                    depth -= 1
                cursor += 1
            self.assertEqual(depth, 0, f"unclosed CSS block: {marker}")
            return source[opening_brace + 1 : cursor - 1]

        def grid_tracks(rule):
            declaration = "grid-template-columns:"
            value_start = rule.index(declaration) + len(declaration)
            value_end = rule.index(";", value_start)
            value = rule[value_start:value_end].strip()
            tracks = []
            current = []
            depth = 0
            for character in value:
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                if character.isspace() and depth == 0:
                    if current:
                        tracks.append("".join(current))
                        current = []
                else:
                    current.append(character)
            if current:
                tracks.append("".join(current))
            return tracks

        concept_main_rule = css_block(styles, ".concept-main {")
        base_journey_rule = css_block(styles, ".journey-layout {")
        compact_media = css_block(styles, "@media (max-width: 1480px) {")
        compact_journey_rule = css_block(compact_media, ".journey-layout {")
        mobile_media = css_block(styles, "@media (max-width: 1180px) {")
        mobile_journey_rule = css_block(mobile_media, ".journey-layout {")

        self.assertIn("width: 100%", concept_main_rule)
        self.assertNotIn("max-width", concept_main_rule)
        self.assertNotIn("margin: 0 auto", concept_main_rule)
        self.assertEqual(len(grid_tracks(base_journey_rule)), 2)
        self.assertEqual(len(grid_tracks(compact_journey_rule)), 2)
        self.assertEqual(grid_tracks(mobile_journey_rule), ["1fr"])

    def test_local_map_fallback_and_leaflet_assets_are_committed(self):
        fallback = MAP_FALLBACK_FILE.read_text(encoding="utf-8")
        self.assertIn('viewBox="0 0 816 931"', fallback)
        self.assertIn('id="island"', fallback)
        self.assertGreater(LEAFLET_JS_FILE.stat().st_size, 100_000)
        self.assertGreater(LEAFLET_CSS_FILE.stat().st_size, 10_000)
        self.assertIn("BSD 2-Clause License", LEAFLET_LICENSE_FILE.read_text(encoding="utf-8"))

    def test_main_map_activates_local_fallback_without_leaflet(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
globalThis.__mapFallbackTest = {
  ensureCenterMap,
  deactivateCenterMapFallback,
  drawRouteMap
};
`);
const classes = new Set();
const routeClasses = new Set();
const frame = {
  classList: {
    add(value) { classes.add(value); },
    remove(value) { classes.delete(value); },
    contains(value) { return classes.has(value); }
  }
};
const art = {
  complete: true,
  naturalWidth: 816,
  addEventListener() {}
};
const notice = { hidden: true, textContent: "" };
const routeShell = {
  classList: {
    add(value) { routeClasses.add(value); },
    remove(value) { routeClasses.delete(value); }
  }
};
const routeLayer = { innerHTML: "" };
const routeBadge = { textContent: "" };
const routeStatus = { textContent: "" };
const attributes = new Map();
const routeAttributes = new Map();
const liveMap = {
  setAttribute(key, value) { attributes.set(key, value); },
  removeAttribute(key) { attributes.delete(key); }
};
const routeMap = {
  setAttribute(key, value) { routeAttributes.set(key, value); },
  removeAttribute(key) { routeAttributes.delete(key); }
};
const document = {
  querySelector(selector) {
    if (selector === "#mapPanel .map-frame") return frame;
    if (selector === ".route-map-shell") return routeShell;
    return null;
  },
  getElementById(id) {
    return {
      liveMap,
      mapFallbackArt: art,
      mapFallbackNotice: notice,
      routeMap,
      routeMapFallbackLayer: routeLayer,
      routeMapBadge: routeBadge,
      routeMapStatus: routeStatus
    }[id] || null;
  }
};
const context = {
  window: {
    GachibomSavedTrips: null,
    L: null,
    requestAnimationFrame() {},
    setTimeout(callback) { callback(); }
  },
  document,
  console,
  URL,
  Set,
  Map,
  WeakMap
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);
const api = context.__mapFallbackTest;
if (api.ensureCenterMap() !== null) throw new Error("Leaflet absence must use fallback");
if (!classes.has("map-fallback-active")) throw new Error("fallback class must activate");
if (notice.hidden || !notice.textContent.includes("로컬 지도")) throw new Error("visible fallback notice required");
if (attributes.get("aria-hidden") !== "true") throw new Error("hidden live map must be aria-hidden");
api.deactivateCenterMapFallback();
if (classes.has("map-fallback-active") || !notice.hidden) throw new Error("fallback should deactivate cleanly");

api.drawRouteMap([
  { order: 1, location: { latitude: 33.48, longitude: 126.49 } },
  { order: 2, location: { latitude: 33.27, longitude: 126.62 } }
], { geometry: [], distanceKm: 10, durationMinutes: 30 });
if (!routeClasses.has("route-map-fallback-active")) throw new Error("route modal must activate its local fallback");
if (!routeLayer.innerHTML.includes("route-map-fallback-path")) throw new Error("route modal fallback must draw the route");
if ((routeLayer.innerHTML.match(/route-map-fallback-marker/g) || []).length !== 2) throw new Error("route modal fallback must draw every marker");
if (routeAttributes.get("aria-hidden") !== "true") throw new Error("hidden route map must be aria-hidden");

const tileHandlers = {};
const fakeLayer = {
  on(name, handler) { tileHandlers[name] = handler; return this; },
  addTo() { return this; }
};
const fakeMap = {
  on() { return this; },
  removeLayer() {},
  invalidateSize() {}
};
const fakeLeaflet = {
  map() { return fakeMap; },
  control: { zoom() { return { addTo() {} }; } },
  layerGroup() { return { addTo() { return {}; } }; },
  tileLayer() { return fakeLayer; }
};
context.window.L = fakeLeaflet;
context.L = fakeLeaflet;
if (api.ensureCenterMap() !== fakeMap) throw new Error("local Leaflet should initialize the live map");
tileHandlers.tileerror();
tileHandlers.tileerror();
tileHandlers.tileerror();
if (!classes.has("map-fallback-active")) throw new Error("repeated tile failures must activate fallback");
tileHandlers.loading();
tileHandlers.load();
if (classes.has("map-fallback-active")) throw new Error("successful tile load must restore the live map");
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_natural_language_rag_query_and_grounded_citations_are_wired(self):
        index = INDEX_FILE.read_text(encoding="utf-8")
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        self.assertIn('id="ragQueryInput"', index)
        self.assertIn('maxlength="500"', index)
        self.assertIn('id="ragQueryHelp"', index)
        self.assertIn('id="ragRecognizedConditions"', index)
        self.assertIn('id="ragQueryConflict"', index)
        self.assertIn('aria-live="polite"', index)
        self.assertIn("data-rag-example", index)
        self.assertIn("data-clear-rag-query", index)
        self.assertIn("저장 코스나 공유 링크에는 포함하지 않습니다", index)
        self.assertIn('ragQuery: ""', app)
        self.assertIn("function detectRagQueryConditions", app)
        self.assertIn("function renderRagQueryAssist", app)
        payload_source = app[
            app.index("function recommendationPayload") : app.index("function helpRecommendationContext")
        ]
        self.assertIn("query: normalizeRagQuery(state.ragQuery)", payload_source)
        runtime_gate_source = app[
            app.index("function shouldRequestRuntimeApi") : app.index("function shouldRequestRouteProxy")
        ]
        self.assertIn('params.get("api") === "0"', runtime_gate_source)
        self.assertIn("Boolean(normalizeRagQuery(state.ragQuery))", runtime_gate_source)
        self.assertIn("function aiCitationItems", app)
        self.assertIn("safeExternalUrl(citation.source_url)", app)
        self.assertIn("function retrievalEvidenceItems", app)
        self.assertIn("safeExternalUrl(source?.url)", app)
        self.assertIn('rel="noopener noreferrer"', app)
        self.assertIn("grounded-source", app)
        self.assertIn('retrievalStatus === "resource_data_gap"', app)
        self.assertIn("관련 없는 장소를 대신 추천하지 않았습니다", app)
        selected_route_source = app[
            app.index("function selectedRoute") : app.index("function routeEntriesForScenario")
        ]
        self.assertIn('"resource_data_gap", "no_match"', selected_route_source)
        self.assertIn("return [];", selected_route_source)
        self.assertIn("ai-citation-list", styles)
        self.assertIn("rag-query-section", styles)
        self.assertIn("rag-recognized-chip", styles)
        self.assertIn("rag-status-detail", styles)

    def test_profile_modal_edits_are_transactional_and_apply_atomically(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`${message}: expected ${expectedJson}, got ${actualJson}`);
  }
}

const documentListeners = new Map();
const queryInputListeners = new Map();
const bodyClasses = new Set();
const profileModal = {
  hidden: true,
  contains() { return false; },
  querySelector() { return null; }
};
const ragQueryInput = {
  value: "",
  focus() {},
  addEventListener(type, listener) {
    queryInputListeners.set(type, listener);
  }
};
const ragQueryClear = { hidden: true };
const ragRecognizedConditions = { innerHTML: "" };
const ragQueryConflict = { hidden: true, textContent: "" };
const modalScenarioList = { innerHTML: "" };
const modalProfileForm = { innerHTML: "" };
const document = {
  activeElement: null,
  body: {
    classList: {
      add(name) { bodyClasses.add(name); },
      remove(name) { bodyClasses.delete(name); },
      contains(name) { return bodyClasses.has(name); }
    }
  },
  getElementById(id) {
    return {
      profileModal,
      ragQueryInput,
      ragQueryClear,
      ragRecognizedConditions,
      ragQueryConflict,
      modalScenarioList,
      modalProfileForm
    }[id] || null;
  },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener(type, listener) {
    const listeners = documentListeners.get(type) || [];
    listeners.push(listener);
    documentListeners.set(type, listeners);
  }
};

const recommendationRequests = [];
let recommendationResponse = null;
async function fetch(url, options = {}) {
  if (url !== "api/recommendations") {
    throw new Error(`unexpected fetch: ${url}`);
  }
  const body = JSON.parse(options.body || "{}");
  recommendationRequests.push({ url, options, body });
  return {
    ok: true,
    async json() {
      return {
        ...recommendationResponse,
        traveler_summary: body.traveler_summary
      };
    }
  };
}

const window = {
  GachibomSavedTrips: null,
  location: {
    href: "https://example.test/#recommendations",
    search: "",
    hash: "#recommendations"
  },
  history: {},
  requestAnimationFrame(callback) { callback(); },
  setTimeout,
  clearTimeout,
  addEventListener() {}
};
const context = {
  window,
  document,
  navigator: {},
  fetch,
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
};
context.globalThis = context;

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
render = () => {};
globalThis.__profileModalFlowTest = {
  state,
  bindEvents,
  currentRouteSpotIds,
  profileFromScenario,
  recommendationPayload,
  detectRagQueryConditions,
  detectRagQueryConflicts
};
`);
vm.createContext(context);
vm.runInContext(source, context);

const app = context.__profileModalFlowTest;
const seed = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const initialScenario = seed.scenarios.find((scenario) => scenario.id === "recovery_quiet");
const targetScenario = seed.scenarios.find((scenario) => scenario.id === "wheelchair_access");
assert(initialScenario && targetScenario, "transaction fixture scenarios must exist");

app.state.data = seed;
app.state.scenarioId = initialScenario.id;
app.state.profile = app.profileFromScenario(initialScenario);
app.state.ragQuery = "기존 검색어";
app.state.runtimeScenario = null;
app.state.selectedSpotId = app.currentRouteSpotIds(initialScenario)[0];
app.state.mapPopupSpotId = null;
app.state.detailCollapsed = false;

const initialRoute = app.currentRouteSpotIds();
const targetRoute = app.currentRouteSpotIds(targetScenario);
assert(initialRoute.length > 0, "initial scenario must expose a route");
assert(JSON.stringify(initialRoute) !== JSON.stringify(targetRoute), "fixture routes must differ");

const baseline = {
  scenarioId: app.state.scenarioId,
  profile: JSON.parse(JSON.stringify(app.state.profile)),
  ragQuery: app.state.ragQuery,
  runtimeScenario: app.state.runtimeScenario,
  selectedSpotId: app.state.selectedSpotId,
  route: initialRoute
};

function assertLiveStateMatchesBaseline(message) {
  assert(app.state.scenarioId === baseline.scenarioId, `${message}: scenario changed`);
  equal(app.state.profile, baseline.profile, `${message}: profile changed`);
  assert(app.state.ragQuery === baseline.ragQuery, `${message}: query changed`);
  assert(app.state.runtimeScenario === baseline.runtimeScenario, `${message}: runtime result changed`);
  assert(app.state.selectedSpotId === baseline.selectedSpotId, `${message}: selected place changed`);
  equal(app.currentRouteSpotIds(), baseline.route, `${message}: parent course changed`);
}

function clickTarget(selector, dataset = {}, insideProfileModal = false) {
  const target = {
    dataset,
    classList: { contains() { return false; } },
    getAttribute() { return null; },
    closest(candidate) {
      if (candidate === selector) return target;
      if (candidate === "#profileModal" && insideProfileModal) return profileModal;
      return null;
    }
  };
  return target;
}

async function click(target) {
  const listeners = documentListeners.get("click") || [];
  assert(listeners.length === 1, "one delegated click listener should be registered");
  const event = { target, preventDefault() {} };
  for (const listener of listeners) {
    await listener(event);
  }
}

function typeQuery(value) {
  ragQueryInput.value = value;
  const listener = queryInputListeners.get("input");
  assert(listener, "query input listener should be registered");
  listener({ target: ragQueryInput });
}

app.bindEvents();

(async () => {
  const exampleQuery = "제주시 실내 조용한 곳";
  equal(
    app.detectRagQueryConditions("병원은 필요 없고 바다는 피하고 싶어요"),
    ["제외 · 바다", "제외 · 병원"],
    "negated category terms should be presented as exclusions"
  );
  equal(
    app.detectRagQueryConflicts("박물관과 정원, 음식을 원해요", { avoid: ["실내", "숲", "식당 제외"] }),
    ["음식·식당", "숲", "실내"],
    "conflict detection should use the same common aliases as condition recognition"
  );
  await click(clickTarget("[data-open-profile-modal]"));
  assert(!profileModal.hidden, "profile modal should open");
  assert(ragQueryInput.value === baseline.ragQuery, "modal should start with the committed query");

  await click(clickTarget("[data-rag-example]", { ragExample: exampleQuery }, true));
  assert(ragQueryInput.value === exampleQuery, "a quick example should fill the query input");
  assert(app.state.profileModalDraft.ragQuery === exampleQuery, "a quick example should update only the modal draft");
  assert(ragRecognizedConditions.innerHTML.includes("지역 · 제주시"), "the example should recognize its region");
  assert(ragRecognizedConditions.innerHTML.includes("테마 · 실내"), "the example should recognize its indoor theme");
  assert(ragRecognizedConditions.innerHTML.includes("테마 · 휴식"), "the example should recognize its quiet-rest theme");
  assertLiveStateMatchesBaseline("choosing a quick example");
  assert(recommendationRequests.length === 0, "a quick example must not request a recommendation before apply");

  typeQuery("  제주시에서\n 휠체어로  갈 곳  ");
  assert(
    app.state.profileModalDraft.ragQuery === "제주시에서 휠체어로 갈 곳",
    "direct input should normalize whitespace in the modal draft"
  );
  typeQuery("맛집");
  await new Promise((resolve) => setTimeout(resolve, 350));
  assert(!ragQueryClear.hidden, "direct input should reveal the clear button");
  assert(!ragQueryConflict.hidden, "a natural-language request should warn when it conflicts with exclusions");
  assert(ragQueryConflict.textContent.includes("음식·식당"), "the conflict warning should identify food requests");
  assertLiveStateMatchesBaseline("typing a conflicting request");
  assert(recommendationRequests.length === 0, "typing a conflict must not request before apply");

  typeQuery("폐기할 검색어");
  await click(clickTarget("[data-scenario-id]", { scenarioId: targetScenario.id }, true));
  await click(clickTarget("[data-profile-key]", {
    profileKey: "required_accessibility",
    profileValue: "장애인 화장실"
  }, true));

  assertLiveStateMatchesBaseline("editing the modal");
  assert(recommendationRequests.length === 0, "draft edits must not request a recommendation");

  await click(clickTarget("[data-close-profile-modal]"));
  assert(profileModal.hidden, "profile modal should close");
  assert(app.state.profileModalDraft == null, "closing without apply should discard the modal draft");
  assertLiveStateMatchesBaseline("closing without apply");
  assert(recommendationRequests.length === 0, "discarding must not request a recommendation");

  await click(clickTarget("[data-open-profile-modal]"));
  assert(ragQueryInput.value === baseline.ragQuery, "discarded query must not return on reopen");
  await click(clickTarget("[data-scenario-id]", { scenarioId: targetScenario.id }, true));
  await click(clickTarget("[data-profile-key]", {
    profileKey: "required_accessibility",
    profileValue: "장애인 화장실"
  }, true));
  await click(clickTarget("[data-rag-example]", { ragExample: exampleQuery }, true));

  const expectedProfile = app.profileFromScenario(targetScenario);
  expectedProfile.required_accessibility = expectedProfile.required_accessibility.filter(
    (value) => value !== "장애인 화장실"
  );
  recommendationResponse = {
    recommendation: targetScenario.recommendation,
    places: targetScenario.places,
    retrieval: { status: "applied" },
    engine: { scoring: "test" },
    generated_at: "2026-07-14T00:00:00.000Z"
  };

  await click(clickTarget("[data-apply-profile-modal]"));

  assert(profileModal.hidden, "apply should close the profile modal");
  assert(recommendationRequests.length === 1, "one apply click must make exactly one recommendation request");
  assert(app.state.scenarioId === targetScenario.id, "apply should commit the selected scenario");
  equal(app.state.profile, expectedProfile, "apply should commit all detailed conditions together");
  assert(app.state.ragQuery === exampleQuery, "apply should commit the quick example query");
  assert(app.state.profileModalDraft == null, "apply should clear the modal draft");
  equal(app.currentRouteSpotIds(), targetRoute, "parent course should change only after apply");

  const request = recommendationRequests[0];
  assert(request.options.method === "POST", "recommendation should use POST");
  assert(request.body.query === exampleQuery, "request should include the committed quick example query");
  equal(request.body.traveler_summary, expectedProfile, "request should include the same committed profile");
  equal(app.recommendationPayload().traveler_summary, expectedProfile, "payload helper should use committed profile");
  assert(app.recommendationPayload().query === request.body.query, "payload helper should keep query and profile in sync");

  await click(clickTarget("[data-open-profile-modal]"));
  assert(
    ragQueryInput.value === exampleQuery,
    "reopening should retain the previously committed natural-language query"
  );
  await click(clickTarget("[data-scenario-id]", { scenarioId: initialScenario.id }, true));
  assert(app.state.scenarioId === targetScenario.id, "a new scenario choice must remain a draft before apply");
  equal(app.currentRouteSpotIds(), targetRoute, "the wheelchair course must remain visible before the second apply");
  assert(recommendationRequests.length === 1, "the second draft scenario choice must not request early");

  recommendationResponse = {
    recommendation: initialScenario.recommendation,
    places: initialScenario.places,
    retrieval: { status: "applied" },
    engine: { scoring: "test" },
    generated_at: "2026-07-14T00:01:00.000Z"
  };
  await click(clickTarget("[data-apply-profile-modal]"));

  const recoveryProfile = app.profileFromScenario(initialScenario);
  assert(recommendationRequests.length === 2, "the second apply should make one additional recommendation request");
  assert(
    app.state.scenarioId === initialScenario.id,
    "the explicitly selected recovery scenario must not be reclassified from its profile"
  );
  equal(app.state.profile, recoveryProfile, "the recovery scenario should commit its complete profile");
  assert(
    app.state.ragQuery === exampleQuery,
    "changing only the scenario should preserve the committed natural-language query"
  );
  assert(app.state.profileModalDraft == null, "the second apply should clear the modal draft");
  equal(app.currentRouteSpotIds(), initialRoute, "the recovery course should appear after the second apply");

  const recoveryRequest = recommendationRequests[1];
  assert(
    recoveryRequest.body.query === exampleQuery,
    "the recovery request should retain the existing natural-language query"
  );
  equal(
    recoveryRequest.body.traveler_summary,
    recoveryProfile,
    "the recovery request should use the explicitly selected scenario profile"
  );

  await click(clickTarget("[data-open-profile-modal]"));
  assert(
    ragQueryInput.value === exampleQuery,
    "the custom-profile edit should start from the latest committed query"
  );
  await click(clickTarget("[data-clear-rag-query]", {}, true));
  assert(ragQueryInput.value === "", "clear should empty the query input");
  assert(app.state.profileModalDraft.ragQuery === "", "clear should empty only the modal draft query");
  assert(ragQueryClear.hidden, "clear should hide its button once the query is empty");
  assert(
    ragRecognizedConditions.innerHTML.includes("입력하지 않아도 아래 선택 조건만으로 추천할 수 있어요"),
    "clear should restore the empty-query guidance"
  );
  assert(!ragRecognizedConditions.innerHTML.includes("지역 · 제주시"), "clear should remove old recognized conditions");
  await click(clickTarget("[data-profile-key]", {
    profileKey: "mobility_conditions",
    profileValue: "계단 회피"
  }, true));
  assert(app.state.scenarioId === initialScenario.id, "a detailed draft edit must preserve the recovery scenario");
  equal(app.state.profile, recoveryProfile, "a detailed draft edit must not mutate the live recovery profile");
  assert(
    app.state.ragQuery === exampleQuery,
    "clearing the draft query must not mutate the live query before apply"
  );
  assert(recommendationRequests.length === 2, "a custom-profile draft must not request before apply");

  const customRecoveryProfile = app.profileFromScenario(initialScenario);
  customRecoveryProfile.mobility_conditions.push("계단 회피");
  recommendationResponse = {
    recommendation: initialScenario.recommendation,
    places: initialScenario.places,
    retrieval: { status: "applied" },
    engine: { scoring: "test" },
    generated_at: "2026-07-14T00:02:00.000Z"
  };
  await click(clickTarget("[data-apply-profile-modal]"));

  assert(
    recommendationRequests.length === 3,
    "an empty query with a custom profile should make exactly one additional recommendation request"
  );
  assert(app.state.scenarioId === initialScenario.id, "a custom profile must keep its explicitly selected scenario");
  equal(app.state.profile, customRecoveryProfile, "apply should commit the toggled recovery condition");
  assert(app.state.ragQuery === "", "apply should commit the cleared query");
  assert(app.state.profileModalDraft == null, "the custom-profile apply should clear the modal draft");

  const customRecoveryRequest = recommendationRequests[2];
  assert(customRecoveryRequest.body.query === "", "the custom-profile request should contain an empty query");
  equal(
    customRecoveryRequest.body.traveler_summary,
    customRecoveryProfile,
    "the custom-profile request should include the toggled condition"
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT), str(SEED_FILE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fast_recommendation_payload_and_scenario_selection_render_order(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
const __scenarioRenderCalls = [];
let __refreshStarted = 0;
let __resolveRefresh;
const __refreshPromise = new Promise((resolve) => {
  __resolveRefresh = resolve;
});
render = () => {
  __scenarioRenderCalls.push(state.scenarioId);
};
openConceptResultPanel = () => {};
syncStepViewState = () => {};
refreshScenarioRecommendation = () => {
  __refreshStarted += 1;
  return __refreshPromise;
};
globalThis.__fastScenarioTest = {
  state,
  recommendationPayload,
  selectScenarioForResult,
  renderCalls: __scenarioRenderCalls,
  refreshStarted: () => __refreshStarted,
  resolveRefresh: __resolveRefresh
};
`);

const window = {
  GachibomSavedTrips: null,
  location: {
    href: "https://example.test/#recommendations",
    search: "",
    hash: "#recommendations"
  },
  history: { pushState() {} },
  requestAnimationFrame(callback) { callback(); },
  setTimeout,
  clearTimeout,
  addEventListener() {}
};
const document = {
  documentElement: { clientHeight: 900 },
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {}
};
const context = {
  window,
  document,
  navigator: {},
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);

const app = context.__fastScenarioTest;
const emptyProfile = {
  traveler_type: [],
  mobility_conditions: [],
  preferred_themes: [],
  required_accessibility: [],
  avoid: []
};
const scenarioA = {
  id: "scenario_a",
  title: "기존 코스",
  traveler_summary: emptyProfile,
  recommendation: { course: { route: [] } },
  places: []
};
const scenarioB = {
  id: "scenario_b",
  title: "새 코스",
  traveler_summary: {
    ...emptyProfile,
    preferred_themes: ["실내"]
  },
  recommendation: { course: { route: [] } },
  places: []
};
app.state.data = { scenarios: [scenarioA, scenarioB] };
app.state.scenarioId = scenarioA.id;
app.state.profile = emptyProfile;
app.state.ragQuery = "제주시 실내";

assert(
  app.recommendationPayload().use_ai === false,
  "interactive recommendation payload must disable slow AI explanation generation"
);

(async () => {
  const pendingSelection = app.selectScenarioForResult(scenarioB.id);

  assert(app.refreshStarted() === 1, "scenario selection should start one recommendation refresh");
  assert(
    app.renderCalls.length === 1 && app.renderCalls[0] === scenarioB.id,
    "the newly selected scenario must render before the slow refresh resolves"
  );

  let settled = false;
  pendingSelection.then(() => { settled = true; });
  await Promise.resolve();
  assert(!settled, "the controlled recommendation refresh must still be pending");

  app.resolveRefresh();
  await pendingSelection;
  assert(
    app.renderCalls.length === 2 && app.renderCalls[1] === scenarioB.id,
    "the selected scenario should render once more after refresh completion"
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_center_map_clears_stale_routes_and_reuses_identical_route_layers(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
const __roadResolvers = new Map();
globalThis.__centerMapLifecycleTest = {
  state,
  renderCenterMap,
  configure(dependencies) {
    centerMap = dependencies.map;
    centerRouteLayerGroup = dependencies.routeLayerGroup;
    centerMarkerLayerGroup = dependencies.markerLayerGroup;
    centerMarkersBySpotId.clear();
    centerMapRenderSequence = 0;
    centerMapLastFitKey = null;
    centerMapRenderedRouteKey = null;
    ensureCenterMap = () => dependencies.map;
    renderLiveMapStats = () => {};
    scheduleMapHitBoundsSync = () => {};
    runWhenBrowserIdle = (callback) => callback();
    shouldRequestRouteProxy = () => true;
    cachedRouteSummaryWithRoadGeometry = (entries) => {
      const key = routeEntriesCacheKey(entries);
      return new Promise((resolve) => {
        __roadResolvers.set(key, resolve);
      });
    };
  },
  setScenario(scenario) {
    state.data = { scenarios: [scenario] };
    state.scenarioId = scenario.id;
    state.runtimeScenario = null;
    state.mapPopupSpotId = null;
  },
  keyForScenario(scenario) {
    return routeEntriesCacheKey(routeCoordinateEntries(scenario));
  },
  resolveRoadSummary(key, summary) {
    const resolve = __roadResolvers.get(key);
    if (!resolve) {
      throw new Error(\`missing pending road summary for \${key}\`);
    }
    __roadResolvers.delete(key);
    resolve(summary);
  },
  renderedRouteKey: () => centerMapRenderedRouteKey,
  markerIndexSize: () => centerMarkersBySpotId.size
};
`);

const calls = {
  routeClears: 0,
  markerClears: 0,
  polylines: 0,
  markers: 0,
  markerIconUpdates: 0,
  fits: 0,
  invalidates: 0
};
const mapSyncStatus = { textContent: "" };
const routeLayerGroup = {
  clearLayers() { calls.routeClears += 1; }
};
const markerLayerGroup = {
  clearLayers() { calls.markerClears += 1; }
};
const fakeMap = {
  fitBounds() { calls.fits += 1; },
  invalidateSize() { calls.invalidates += 1; }
};
const L = {
  polyline() {
    calls.polylines += 1;
    return { addTo() { return this; } };
  },
  marker() {
    calls.markers += 1;
    return {
      addTo() { return this; },
      on() { return this; },
      setIcon() { calls.markerIconUpdates += 1; return this; }
    };
  },
  divIcon(options) { return options; },
  latLngBounds(points) { return { points }; },
  DomEvent: { stop() {} }
};
const window = {
  GachibomSavedTrips: null,
  L,
  location: {
    href: "https://example.test/#recommendations",
    search: "",
    hash: "#recommendations"
  },
  history: {},
  requestAnimationFrame(callback) { callback(); },
  setTimeout(callback) { callback(); return 1; },
  clearTimeout() {},
  addEventListener() {}
};
const document = {
  documentElement: { clientHeight: 900 },
  getElementById(id) {
    if (id === "mapSyncStatus") return mapSyncStatus;
    return null;
  },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {}
};
const context = {
  window,
  document,
  navigator: {},
  L,
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);

const app = context.__centerMapLifecycleTest;
app.configure({ map: fakeMap, routeLayerGroup, markerLayerGroup });

function scenario(id, points) {
  return {
    id,
    title: id,
    traveler_summary: {},
    recommendation: {
      score: { total: 90 },
      course: {
        route: points.map((point, index) => ({
          order: index + 1,
          spot_id: point.id,
          name: point.id
        }))
      }
    },
    places: points.map((point) => ({
      spot_id: point.id,
      name: point.id,
      category: "indoor",
      accessibility: {},
      location: point.location,
      verification_status: "partial",
      source_summary: [{ title: "테스트 근거", url: "https://example.test/evidence" }]
    }))
  };
}

const routeA = scenario("route_a", [
  { id: "a1", location: { latitude: 33.50, longitude: 126.50 } },
  { id: "a2", location: { latitude: 33.40, longitude: 126.60 } },
  { id: "a3", location: { latitude: 33.30, longitude: 126.70 } }
]);
const routeC = scenario("route_c", [
  { id: "c1", location: { latitude: 33.48, longitude: 126.49 } },
  { id: "c2", location: { latitude: 33.28, longitude: 126.62 } }
]);
const emptyRoute = scenario("route_empty", []);
const onePointRoute = scenario("route_one", [
  { id: "only", location: { latitude: 33.45, longitude: 126.55 } }
]);

(async () => {
  app.setScenario(routeA);
  const routeAKey = app.keyForScenario(routeA);
  app.renderCenterMap(routeA);
  const firstDrawCounts = {
    polylines: calls.polylines,
    markers: calls.markers,
    fits: calls.fits,
    routeClears: calls.routeClears,
    markerClears: calls.markerClears
  };
  assert(firstDrawCounts.polylines === 2, "the first route should create two styled polylines");
  assert(firstDrawCounts.markers === 3, "the first route should create one marker per stop");

  app.renderCenterMap(routeA);
  assert(calls.polylines === firstDrawCounts.polylines, "same route key must not recreate polylines");
  assert(calls.markers === firstDrawCounts.markers, "same route key must not recreate markers");
  assert(calls.fits === firstDrawCounts.fits, "same route key must not refit the map");
  assert(calls.routeClears === firstDrawCounts.routeClears, "same route key must not clear the route layer");
  assert(calls.markerClears === firstDrawCounts.markerClears, "same route key must not clear the marker layer");
  assert(calls.markerIconUpdates === 3, "same route key may update only existing marker icons");

  app.setScenario(emptyRoute);
  app.renderCenterMap(emptyRoute);
  assert(calls.routeClears === firstDrawCounts.routeClears + 1, "an empty route must clear the old polyline layer");
  assert(calls.markerClears === firstDrawCounts.markerClears + 1, "an empty route must clear the old marker layer");
  assert(app.renderedRouteKey() === null, "an empty route must reset the rendered route key");
  assert(app.markerIndexSize() === 0, "an empty route must clear the marker index");

  const afterEmptyCounts = { polylines: calls.polylines, markers: calls.markers };
  app.resolveRoadSummary(routeAKey, {
    provider: "road_route",
    distanceKm: 30,
    durationMinutes: 60,
    geometry: routeA.places.map((place) => place.location)
  });
  await Promise.resolve();
  await Promise.resolve();
  assert(calls.polylines === afterEmptyCounts.polylines, "a delayed old route must not redraw after an empty result");
  assert(calls.markers === afterEmptyCounts.markers, "a delayed old route must not restore old markers after an empty result");

  app.setScenario(routeC);
  const routeCKey = app.keyForScenario(routeC);
  app.renderCenterMap(routeC);
  const beforeOnePointCounts = {
    polylines: calls.polylines,
    markers: calls.markers,
    routeClears: calls.routeClears,
    markerClears: calls.markerClears
  };

  app.setScenario(onePointRoute);
  app.renderCenterMap(onePointRoute);
  assert(calls.routeClears === beforeOnePointCounts.routeClears + 1, "a one-point route must clear the old polyline layer");
  assert(calls.markerClears === beforeOnePointCounts.markerClears + 1, "a one-point route must clear the old marker layer");
  assert(app.renderedRouteKey() === null, "a one-point route must reset the rendered route key");
  assert(app.markerIndexSize() === 0, "a one-point route must clear the marker index");

  const afterOnePointCounts = { polylines: calls.polylines, markers: calls.markers };
  app.resolveRoadSummary(routeCKey, {
    provider: "road_route",
    distanceKm: 20,
    durationMinutes: 40,
    geometry: routeC.places.map((place) => place.location)
  });
  await Promise.resolve();
  await Promise.resolve();
  assert(calls.polylines === afterOnePointCounts.polylines, "a delayed old route must not redraw after a one-point result");
  assert(calls.markers === afterOnePointCounts.markers, "a delayed old route must not restore markers after a one-point result");
  assert(
    mapSyncStatus.textContent.includes("두 곳 이상의 좌표"),
    "the map should explain why a one-point route cannot be displayed"
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_routes_use_the_full_public_place_index(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
globalThis.__savedRouteAppTest = {
  state,
  allowedSavedSpotIds,
  currentRouteSpotIds
};
`);
const context = {
  window: {
    GachibomSavedTrips: null,
    location: { search: "", hash: "", href: "https://example.test/" },
    history: {}
  },
  document: {},
  navigator: {},
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
};
vm.runInNewContext(source, context);
const helpers = context.__savedRouteAppTest;
helpers.state.data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const allowed = helpers.allowedSavedSpotIds();
if (allowed.size !== 91) throw new Error(`expected 91 public places, got ${allowed.size}`);
if (!allowed.has("jeju_tourism_weak_037")) throw new Error("runtime-only place missing");
const runtimeScenario = {
  recommendation: {
    course: {
      route: [
        { spot_id: "jeju_tourism_weak_037" },
        { spot_id: "jeju_indoor_art_museum_033" }
      ]
    }
  },
  places: [
    {
      spot_id: "jeju_tourism_weak_037",
      verification_status: "partial",
      source_summary: [{ title: "공식 근거", url: "https://example.test/weak-037" }]
    },
    {
      spot_id: "jeju_indoor_art_museum_033",
      verification_status: "partial",
      source_summary: [{ title: "공식 근거", url: "https://example.test/museum-033" }]
    }
  ]
};
const route = helpers.currentRouteSpotIds(runtimeScenario);
if (JSON.stringify(route) !== JSON.stringify([
  "jeju_tourism_weak_037",
  "jeju_indoor_art_museum_033"
])) throw new Error(`runtime route was truncated: ${JSON.stringify(route)}`);
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT), str(SEED_FILE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_condition_focus_uses_a_distinct_static_route_when_api_is_disabled(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync(process.argv[1], "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
globalThis.__conditionFocusTest = {
  state,
  currentScenario,
  currentStaticScenario,
  profileFromScenario,
  recommendationPayload,
  requestRuntimeRecommendation,
  selectedRoute,
  selectedPlace
};
`);
const context = {
  window: {
    GachibomSavedTrips: null,
    location: { search: "?api=0", hash: "", href: "https://example.test/?api=0" },
    history: {}
  },
  document: {},
  navigator: {},
  URL,
  URLSearchParams,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console
};
vm.runInNewContext(source, context);
const app = context.__conditionFocusTest;
app.state.data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
app.state.scenarioId = "stroller_family";
app.state.profile = app.profileFromScenario(app.currentStaticScenario());
const baseRoute = app.selectedRoute(app.currentStaticScenario()).map((item) => item.spot_id);

(async () => {
  app.state.conceptFocus = {
    key: "required_accessibility",
    value: "휴식 공간",
    label: "휴식 공간"
  };
  if (app.recommendationPayload().query !== "휴식 공간") {
    throw new Error("the focused condition was not sent as the recommendation query");
  }
  await app.requestRuntimeRecommendation();
  if (!app.state.runtimeScenario) throw new Error("the static condition route was not applied");
  if (app.state.apiState.status !== "static") throw new Error("static fallback status was not retained");
  const focusedRoute = app.selectedRoute(app.currentScenario()).map((item) => item.spot_id);
  if (focusedRoute.length !== 4) throw new Error(`expected four focused places: ${focusedRoute}`);
  if (JSON.stringify(focusedRoute) === JSON.stringify(baseRoute)) {
    throw new Error("the focused route stayed identical to the base route");
  }
  app.state.selectedSpotId = focusedRoute[0];
  const selected = app.selectedPlace(app.currentScenario());
  if (selected?.spot_id !== focusedRoute[0]) {
    throw new Error(`focused place detail was not resolved: ${selected?.spot_id}`);
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
        result = subprocess.run(
            ["node", "-e", harness, str(APP_SCRIPT), str(SEED_FILE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
