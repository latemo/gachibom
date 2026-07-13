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
assert(itineraryMarkup.includes("https://map.kakao.com/link/by/car/"), "full Kakao route should render when coordinates exist");
assert(itineraryMarkup.includes("정보</a>"), "public information link should render");
assert(itineraryMarkup.includes(">전화</a>"), "verified-format phone action should render when available");
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
assert((retiredMarkup.match(/>지도<\/a>/g) || []).length === 1, "retired place must not expose a map link");

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

    def test_site_wires_saved_routes_before_the_main_app(self):
        index = INDEX_FILE.read_text(encoding="utf-8")
        app = APP_SCRIPT.read_text(encoding="utf-8")
        styles = STYLES_FILE.read_text(encoding="utf-8")

        self.assertLess(index.index("saved-trips.js"), index.index("app.js"))
        self.assertIn('id="savedRoutesModal"', index)
        self.assertIn("data-open-saved-routes", index)
        self.assertGreaterEqual(index.count("data-save-current-route"), 2)
        self.assertIn("styles.css?v=20260714-3", index)
        self.assertIn("app.js?v=20260714-3", index)
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
        self.assertIn("저장 코스나 공유 링크에는 포함하지 않습니다", index)
        self.assertIn('ragQuery: ""', app)
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
        self.assertIn("rag-status-detail", styles)

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
  }
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


if __name__ == "__main__":
    unittest.main()
