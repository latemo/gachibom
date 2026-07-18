(function attachSavedTrips(global) {
  "use strict";

  const STORAGE_KEY = "gachibom:saved-routes:v1";
  const SCHEMA_VERSION = 2;
  const LEGACY_SCHEMA_VERSION = 1;
  const MAX_ITEMS = 20;
  const MAX_SPOTS = 4;
  const MAX_CHECKED_IDS = 32;
  const MAX_STORAGE_BYTES = 64 * 1024;
  const MAX_SEARCH_LENGTH = 1024;
  const SPOT_ID_PATTERN = /^[A-Za-z0-9_-]{1,80}$/;
  const CHECK_ID_PATTERN = /^check-[a-f0-9]{8}$/;
  const TRIP_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
  const START_TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

  function allowedSpotSet(values) {
    return values instanceof Set ? values : new Set(Array.isArray(values) ? values : []);
  }

  function normalizedSpotIds(
    values,
    allowedSpots,
    { rejectDuplicates = false, allowUnavailable = false } = {}
  ) {
    if (!Array.isArray(values) || values.length < 1 || values.length > MAX_SPOTS) {
      return null;
    }
    const allowed = allowedSpotSet(allowedSpots);
    const result = [];
    for (const value of values) {
      const spotId = String(value || "").trim();
      if (!SPOT_ID_PATTERN.test(spotId) || (!allowUnavailable && !allowed.has(spotId))) {
        return null;
      }
      if (result.includes(spotId)) {
        if (rejectDuplicates) {
          return null;
        }
        continue;
      }
      result.push(spotId);
    }
    return result.length ? result : null;
  }

  function normalizedCheckedIds(values) {
    if (!Array.isArray(values)) {
      return [];
    }
    return Array.from(new Set(values
      .map((value) => String(value || "").trim().toLowerCase())
      .filter((value) => CHECK_ID_PATTERN.test(value))))
      .slice(0, MAX_CHECKED_IDS);
  }

  function normalizedTripDate(value) {
    const text = String(value || "").trim();
    if (!text) {
      return "";
    }
    const match = TRIP_DATE_PATTERN.exec(text);
    if (!match) {
      return "";
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (year < 2000 || year > 2100) {
      return "";
    }
    const parsed = new Date(Date.UTC(year, month - 1, day));
    return parsed.getUTCFullYear() === year
      && parsed.getUTCMonth() === month - 1
      && parsed.getUTCDate() === day
      ? text
      : "";
  }

  function normalizedStartTime(value) {
    const text = String(value || "").trim();
    return !text || START_TIME_PATTERN.test(text) ? text : "";
  }

  function normalizedOrderedSpotIds(values, spotIds) {
    if (!Array.isArray(values) || values.length !== spotIds.length) {
      return [...spotIds];
    }
    const result = values.map((value) => String(value || "").trim());
    if (
      new Set(result).size !== spotIds.length
      || result.some((spotId) => !SPOT_ID_PATTERN.test(spotId) || !spotIds.includes(spotId))
    ) {
      return [...spotIds];
    }
    return result;
  }

  function normalizedItinerary(value, spotIds) {
    const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return {
      date: normalizedTripDate(source.date) || null,
      startTime: normalizedStartTime(source.startTime) || null,
      orderedSpotIds: normalizedOrderedSpotIds(source.orderedSpotIds, spotIds)
    };
  }

  function orderedSpotIds(item) {
    const spotIds = Array.isArray(item?.spotIds) ? item.spotIds : [];
    return normalizedOrderedSpotIds(item?.itinerary?.orderedSpotIds, spotIds);
  }

  function hashText(value) {
    let hash = 0x811c9dc5;
    for (const character of String(value || "")) {
      hash ^= character.codePointAt(0);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
  }

  function routeId(spotIds) {
    return `route-${(spotIds || []).map((spotId) => String(spotId || "")).join(".")}`;
  }

  function checkId(spotId, label) {
    const safeSpotId = String(spotId || "").slice(0, 80);
    const safeLabel = String(label || "").replace(/\s+/g, " ").trim().slice(0, 180);
    return `check-${hashText(`${safeSpotId}|${safeLabel}`)}`;
  }

  function normalizeItem(value, allowedSpots) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return null;
    }
    // 저장 후 카탈로그에서 내려간 장소가 있어도 코스와 사용자 일정은 보존한다.
    // 새 저장·공유 입력은 계속 현재 allowedSpots 목록으로 제한한다.
    const spotIds = normalizedSpotIds(value.spotIds, allowedSpots, { allowUnavailable: true });
    if (!spotIds) {
      return null;
    }
    const savedAt = String(value.savedAt || "");
    if (!savedAt || Number.isNaN(Date.parse(savedAt))) {
      return null;
    }
    return {
      id: routeId(spotIds),
      spotIds,
      checkedIds: normalizedCheckedIds(value.checkedIds),
      itinerary: normalizedItinerary(value.itinerary, spotIds),
      savedAt: new Date(savedAt).toISOString()
    };
  }

  function normalizeItems(values, allowedSpots) {
    if (!Array.isArray(values)) {
      return [];
    }
    const result = [];
    const seen = new Set();
    for (const value of values) {
      const item = normalizeItem(value, allowedSpots);
      if (!item || seen.has(item.id)) {
        continue;
      }
      seen.add(item.id);
      result.push(item);
      if (result.length >= MAX_ITEMS) {
        break;
      }
    }
    return result;
  }

  function utf8Length(value) {
    if (typeof TextEncoder === "function") {
      return new TextEncoder().encode(value).length;
    }
    return unescape(encodeURIComponent(value)).length;
  }

  function load(storage, allowedSpots) {
    if (!storage) {
      return [];
    }
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw || utf8Length(raw) > MAX_STORAGE_BYTES) {
        return [];
      }
      const document = JSON.parse(raw);
      if (
        !document
        || ![LEGACY_SCHEMA_VERSION, SCHEMA_VERSION].includes(document.schemaVersion)
      ) {
        return [];
      }
      return normalizeItems(document.items, allowedSpots);
    } catch (error) {
      return [];
    }
  }

  function persist(storage, values, allowedSpots, dataVersion = "") {
    let items = normalizeItems(values, allowedSpots);
    if (!storage) {
      return { ok: false, items };
    }
    try {
      let payload = "";
      while (true) {
        payload = JSON.stringify({
          schemaVersion: SCHEMA_VERSION,
          dataVersion: String(dataVersion || "").slice(0, 40),
          items
        });
        if (utf8Length(payload) <= MAX_STORAGE_BYTES || !items.length) {
          break;
        }
        items = items.slice(0, -1);
      }
      storage.setItem(STORAGE_KEY, payload);
      return { ok: true, items };
    } catch (error) {
      return { ok: false, items };
    }
  }

  function upsert(values, spotIds, allowedSpots, { now = new Date().toISOString() } = {}) {
    const normalizedSpots = normalizedSpotIds(spotIds, allowedSpots);
    if (!normalizedSpots) {
      return normalizeItems(values, allowedSpots);
    }
    const items = normalizeItems(values, allowedSpots);
    const id = routeId(normalizedSpots);
    const existing = items.find((item) => item.id === id);
    const next = {
      id,
      spotIds: normalizedSpots,
      checkedIds: existing?.checkedIds || [],
      itinerary: existing?.itinerary || normalizedItinerary(null, normalizedSpots),
      savedAt: new Date(now).toISOString()
    };
    return [next, ...items.filter((item) => item.id !== id)].slice(0, MAX_ITEMS);
  }

  function remove(values, routeIdValue, allowedSpots) {
    return normalizeItems(values, allowedSpots)
      .filter((item) => item.id !== String(routeIdValue || ""));
  }

  function updateCheck(values, routeIdValue, checkIdValue, checked, allowedSpots) {
    const safeCheckId = String(checkIdValue || "").trim().toLowerCase();
    if (!CHECK_ID_PATTERN.test(safeCheckId)) {
      return normalizeItems(values, allowedSpots);
    }
    return normalizeItems(values, allowedSpots).map((item) => {
      if (item.id !== routeIdValue) {
        return item;
      }
      const checkedIds = new Set(item.checkedIds);
      if (checked) {
        checkedIds.add(safeCheckId);
      } else {
        checkedIds.delete(safeCheckId);
      }
      return { ...item, checkedIds: Array.from(checkedIds).slice(0, MAX_CHECKED_IDS) };
    });
  }

  function updateItinerary(values, routeIdValue, updates, allowedSpots) {
    const routeIdText = String(routeIdValue || "");
    const source = updates && typeof updates === "object" && !Array.isArray(updates) ? updates : {};
    const rawDate = String(source.date || "").trim();
    const rawStartTime = String(source.startTime || "").trim();
    const date = normalizedTripDate(rawDate);
    const startTime = normalizedStartTime(rawStartTime);
    const items = normalizeItems(values, allowedSpots);
    if ((rawDate && !date) || (rawStartTime && !startTime)) {
      return items;
    }
    return items.map((item) => {
      if (item.id !== routeIdText) {
        return item;
      }
      return {
        ...item,
        itinerary: {
          ...item.itinerary,
          date: date || null,
          startTime: startTime || null
        }
      };
    });
  }

  function updateSpotOrder(values, routeIdValue, orderedValues, allowedSpots) {
    const routeIdText = String(routeIdValue || "");
    const items = normalizeItems(values, allowedSpots);
    return items.map((item) => {
      if (item.id !== routeIdText) {
        return item;
      }
      const ordered = normalizedOrderedSpotIds(orderedValues, item.spotIds);
      const isValid = Array.isArray(orderedValues)
        && orderedValues.length === item.spotIds.length
        && ordered.every((spotId, index) => spotId === String(orderedValues[index] || "").trim());
      return isValid
        ? { ...item, itinerary: { ...item.itinerary, orderedSpotIds: ordered } }
        : item;
    });
  }

  function buildShareUrl(locationLike, spotIds, allowedSpots) {
    const normalizedSpots = normalizedSpotIds(spotIds, allowedSpots);
    if (!normalizedSpots) {
      return null;
    }
    const current = new URL(String(locationLike?.href || locationLike || ""));
    const url = new URL(`${current.origin}${current.pathname}`);
    url.searchParams.set("share", "1");
    normalizedSpots.forEach((spotId) => url.searchParams.append("spot", spotId));
    url.hash = "#recommendations";
    return url;
  }

  function parseSharedSpotIds(locationLike, allowedSpots) {
    try {
      const url = new URL(String(locationLike?.href || locationLike || ""));
      if (url.search.length > MAX_SEARCH_LENGTH || url.searchParams.get("share") !== "1") {
        return null;
      }
      return normalizedSpotIds(url.searchParams.getAll("spot"), allowedSpots, { rejectDuplicates: true });
    } catch (error) {
      return null;
    }
  }

  global.GachibomSavedTrips = Object.freeze({
    STORAGE_KEY,
    SCHEMA_VERSION,
    MAX_ITEMS,
    routeId,
    checkId,
    orderedSpotIds,
    load,
    persist,
    upsert,
    remove,
    updateCheck,
    updateItinerary,
    updateSpotOrder,
    buildShareUrl,
    parseSharedSpotIds
  });
})(window);
