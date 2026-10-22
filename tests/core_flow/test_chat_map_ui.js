"use strict";

/*
 * UI127 deterministic UI harness.
 *
 * Loads the inline script from ai_service/static/travel.html, runs it against a
 * small fake DOM with fake fetch/MapLibre seams, and drives the real handlers.
 * No network, browser, MapLibre, model or backend is used.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const HTML_PATH = path.join(ROOT, "ai_service", "static", "travel.html");
const html = fs.readFileSync(HTML_PATH, "utf8");
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(scriptMatch, "inline script found");
const scriptSource = scriptMatch[1];

const SELECTION = {
  dataset_namespace: "hcm_primary_geojson",
  input_sha256: "a".repeat(64),
  source_area_id: "area_hcm_quan_1",
};

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function settle(rounds = 8) {
  for (let i = 0; i < rounds; i += 1) await flush();
}

class FakeText {
  constructor(text) {
    this.nodeType = 3;
    this.tagName = "#text";
    this._text = String(text);
    this.children = [];
    this.parentNode = null;
  }
  get firstChild() { return null; }
  get textContent() { return this._text; }
  set textContent(value) { this._text = String(value); }
}

class FakeNode {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.nodeType = 1;
    this.id = "";
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.listeners = {};
    this._text = "";
    this._className = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this.type = "";
    this._selectedIndex = undefined;
  }
  get firstChild() { return this.children.length ? this.children[0] : null; }
  get className() { return this._className; }
  set className(value) {
    this._className = String(value || "");
    this.attributes.class = this._className;
  }
  get classList() {
    const node = this;
    return {
      contains(name) { return node._className.split(/\s+/).includes(name); },
      add(name) {
        const set = new Set(node._className.split(/\s+/).filter(Boolean));
        set.add(name);
        node.className = Array.from(set).join(" ");
      },
      remove(name) {
        node.className = node._className.split(/\s+/)
          .filter((part) => part && part !== name).join(" ");
      },
    };
  }
  get textContent() {
    let out = this._text || "";
    for (const child of this.children) out += child.textContent;
    return out;
  }
  set textContent(value) {
    this.children = [];
    this._text = value === undefined || value === null ? "" : String(value);
  }
  get options() { return this.children.filter((child) => child.tagName === "OPTION"); }
  get selectedIndex() {
    if (this._selectedIndex === undefined) return this.options.length ? 0 : -1;
    return this._selectedIndex;
  }
  set selectedIndex(index) {
    this._selectedIndex = Number(index);
    this.options.forEach((option, i) => { option.selected = i === this._selectedIndex; });
  }
  get value() {
    if (this.tagName === "SELECT") {
      const option = this.options[this.selectedIndex];
      return option ? option.value : "";
    }
    return this._value || "";
  }
  set value(value) {
    if (this.tagName === "SELECT") {
      const index = this.options.findIndex((option) => option.value === String(value));
      this.selectedIndex = index >= 0 ? index : -1;
      return;
    }
    this._value = value === undefined || value === null ? "" : String(value);
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    if (child.id && this.ownerDocument) this.ownerDocument.register(child);
    return child;
  }
  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    child.parentNode = null;
    return child;
  }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "id") {
      this.id = String(value);
      if (this.ownerDocument) this.ownerDocument.register(this);
    }
    if (name === "class") this.className = value;
    if (name === "hidden") this.hidden = String(value) !== "false";
    if (name === "disabled") this.disabled = String(value) !== "false";
    if (name === "checked") this.checked = String(value) !== "false";
    if (name === "value") this.value = value;
  }
  getAttribute(name) {
    if (name === "class") return this._className;
    if (name === "id") return this.id;
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name] : null;
  }
  addEventListener(type, handler) {
    (this.listeners[type] = this.listeners[type] || []).push(handler);
  }
  dispatchEvent(event) {
    event.target = event.target || this;
    event.currentTarget = this;
    const handlers = (this.listeners[event.type] || []).slice();
    handlers.forEach((handler) => handler(event));
    return !event.defaultPrevented;
  }
  click() { return this.dispatchEvent({ type: "click" }); }
  focus() { if (this.ownerDocument) this.ownerDocument.activeElement = this; }
}

class FakeDocument {
  constructor(markup) {
    this.registry = new Map();
    this.allNodes = [];
    this.readyState = "loading";
    this.activeElement = null;
    this.htmlUsed = false;
    this.parsedMarkup = markup;
    this.indexMarkup();
  }
  register(node) {
    node.ownerDocument = this;
    if (!this.allNodes.includes(node)) this.allNodes.push(node);
    if (node.id) this.registry.set(node.id, node);
  }
  indexMarkup() {
    const tagPattern = /<([a-zA-Z][\w-]*)\b([^>]*)>/g;
    let match;
    while ((match = tagPattern.exec(this.parsedMarkup)) !== null) {
      const tag = match[1].toLowerCase();
      if (tag === "script" || tag === "style" || tag === "meta" || tag === "title") continue;
      const rawAttrs = match[2] || "";
      const node = new FakeNode(tag);
      this.register(node);
      const attrPattern = /([:\w-]+)="([^"]*)"/g;
      let attr;
      while ((attr = attrPattern.exec(rawAttrs)) !== null) {
        node.setAttribute(attr[1], attr[2]);
      }
      if (/(?:^|\s)checked(?:\s|$|=)/.test(rawAttrs)) node.checked = true;
      if (/(?:^|\s)disabled(?:\s|$|=)/.test(rawAttrs)) node.disabled = true;
      if (/(?:^|\s)hidden(?:\s|$|=)/.test(rawAttrs)) node.hidden = true;
    }
  }
  createElement(tag) {
    const node = new FakeNode(tag);
    this.register(node);
    return node;
  }
  createTextNode(text) {
    const node = new FakeText(text);
    node.ownerDocument = this;
    return node;
  }
  getElementById(id) { return this.registry.get(id) || null; }
  querySelectorAll(selector) {
    if (!selector.startsWith(".")) return [];
    const wanted = selector.slice(1);
    return this.allNodes.filter((node) => node.classList.contains(wanted));
  }
  addEventListener() {}
}

class FakeMap {
  constructor(options) {
    this.options = options;
    this.handlers = {};
    this.layers = [];
    this.sources = {};
    this.controls = [];
    this.markers = [];
    this.style = {
      sources: { openmaptiles: { type: "vector", url: "fake" } },
      layers: [{ id: "poi_label", type: "symbol" }],
    };
  }
  on(type, handler) { (this.handlers[type] = this.handlers[type] || []).push(handler); }
  fire(type) { (this.handlers[type] || []).slice().forEach((handler) => handler({ type })); }
  addControl(control, position) { this.controls.push({ control, position }); }
  addSource(id, source) { this.sources[id] = source; this.style.sources[id] = source; }
  addLayer(layer, before) { this.layers.push({ layer, before }); }
  getStyle() { return this.style; }
  getLayer(id) {
    const found = this.layers.find((entry) => entry.layer.id === id);
    return found ? found.layer : null;
  }
  flyTo(options) { this.lastFlyTo = options; }
  easeTo(options) { this.lastEaseTo = options; }
  fitBounds(bounds, options) { this.lastFitBounds = { bounds, options }; }
  remove() { this.removed = true; }
}

class FakeMarker {
  constructor(options) { this.options = options; this.element = options.element; this.removed = false; }
  setLngLat(lngLat) { this.lngLat = lngLat; return this; }
  addTo(map) { this.map = map; map.markers.push(this); return this; }
  remove() { this.removed = true; }
}

class FakePopup {
  constructor(options) { this.options = options; this.content = null; this.removed = false; }
  setLngLat(lngLat) { this.lngLat = lngLat; return this; }
  setDOMContent(node) { this.content = node; return this; }
  addTo(map) { this.map = map; this.map.popup = this; FakePopup.instances.push(this); return this; }
  remove() { this.removed = true; }
}

class FakeBounds {
  constructor() { this.coords = []; }
  extend(coord) { this.coords.push(coord); return this; }
}

FakePopup.instances = [];

function fakeMapLibre() {
  return {
    Map: FakeMap,
    Marker: FakeMarker,
    Popup: FakePopup,
    NavigationControl: function NavigationControl(options) { this.options = options; },
    LngLatBounds: FakeBounds,
  };
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function catalogFetch(overrides = {}) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({
      url,
      options,
      body: options && options.body ? JSON.parse(options.body) : null,
    });
    if (url === "/catalog/snapshots") {
      return jsonResponse({
        status: "ok",
        notice: "Nhãn vùng nguồn không phải ranh giới hành chính hiện hành.",
        snapshots: [{
          dataset_namespace: SELECTION.dataset_namespace,
          input_sha256: SELECTION.input_sha256,
          valid_record_count: 1483,
          source_area_count: 2,
        }],
      });
    }
    if (url.startsWith("/catalog/source_areas")) {
      return jsonResponse({
        source_areas: [
          {
            source_area_id: SELECTION.source_area_id,
            source_area_label: "Khu Quận 1",
            raw_city: "Hồ Chí Minh",
            raw_area: "Quận 1",
            area_assignment: "qualified",
            valid_record_count: 1483,
            selection: SELECTION,
          },
          {
            source_area_id: "area_hcm_quan_3",
            source_area_label: "Khu Quận 3",
            raw_city: "Hồ Chí Minh",
            raw_area: "Quận 3",
            area_assignment: "qualified",
            valid_record_count: 700,
            selection: {
              dataset_namespace: SELECTION.dataset_namespace,
              input_sha256: SELECTION.input_sha256,
              source_area_id: "area_hcm_quan_3",
            },
          },
        ],
      });
    }
    if (url === "/chat") {
      if (overrides.chat) return overrides.chat(url, options);
      return jsonResponse({
        status: "success", intent: "TRAVEL", reply: "Gợi ý nhẹ nhàng trong vùng đang chọn.",
        transport_mode: "car", source_scope: SELECTION,
      });
    }
    if (url === "/generate_itinerary") {
      if (overrides.plan) return overrides.plan(url, options);
      return jsonResponse(overrides.planBody || successfulPlanBody());
    }
    throw new Error("unexpected fetch: " + url);
  };
  fetch.calls = calls;
  return fetch;
}

function makePoi(id, name, longitude, latitude, extra = {}) {
  return Object.assign({
    id,
    name,
    poi_categories: [{ id: "c1", name: "Quán ăn", context: null }],
    tag: null,
    longitude,
    latitude,
    address: {
      street_name: "12 Nguyễn Huệ",
      ward: null,
      district: null,
      city: null,
      nation: null,
    },
    contact_info: null,
    operation_time: null,
    operation_time_feasibility: "unverified",
    rating: null,
    menu: [],
    source_snapshot_area: {
      dataset_namespace: SELECTION.dataset_namespace,
      input_sha256: SELECTION.input_sha256,
      source_area_id: SELECTION.source_area_id,
      raw_city: "Hồ Chí Minh",
      raw_area: "Quận 1",
      source_area_label: "Khu Quận 1",
      area_assignment: "qualified",
      current_admin_status: "source_snapshot_area_only",
    },
  }, extra);
}

function makeStop(poi, visitTime, endTime) {
  return {
    date: "2026-11-03",
    visit_time: visitTime || "2026-11-03T09:00:00+07:00",
    end_time: endTime || "2026-11-03T09:45:00+07:00",
    description: "neutral",
    description_grounded: false,
    budget: null,
    budget_is_estimate: true,
    poi,
  };
}

function successfulPlanBody() {
  const first = makePoi("poi_1", "<img src=x onerror=alert(1)>", 106.7012, 10.7765);
  const second = makePoi("poi_2", "Bảo tàng nhỏ", 106.7055, 10.7802);
  const missing = makePoi("poi_3", "Điểm thiếu toạ độ", null, 10.781);
  return {
    status: "success",
    reply: {
      id: "itin_test",
      id_source: "server",
      stops: [
        makeStop(first),
        makeStop(second, "2026-11-03T10:15:00+07:00", "2026-11-03T11:00:00+07:00"),
        makeStop(missing),
      ],
    },
    planning: {
      total_distance_km: 3.4,
      total_travel_minutes: 12,
      total_cost_party: null,
      repaired_schedule: {
        days: [{
          date: "2026-11-03",
          stops: [
            { poi_id: "poi_1", travel_from_prev_distance_km: null, travel_from_prev_minutes: null },
            { poi_id: "poi_2", travel_from_prev_distance_km: "1.2", travel_from_prev_minutes: 6 },
          ],
        }],
      },
      totals: {
        legs: [
          { poi_id: "poi_1", travel_from_prev_distance_km: null, travel_from_prev_minutes: null },
          { poi_id: "poi_2", travel_from_prev_distance_km: "1.2", travel_from_prev_minutes: 6 },
        ],
      },
      days: [{
        stops: [{ poi_id: "poi_2", travel_from_prev_distance_km: "99", travel_from_prev_minutes: 99 }],
      }],
      limitations: [],
      unknown_reasons: [],
    },
    grounding: { missing_data: ["stops[2].longitude"] },
  };
}

function boot(options = {}) {
  const doc = new FakeDocument(html);
  const fetch = options.fetch || catalogFetch();
  const loader = options.loader || (async () => fakeMapLibre());
  const windowObject = { document: doc, fetch, addEventListener() {} };
  const factory = new Function("window", "document", scriptSource + "\nreturn window.TravelUI;");
  const ui = factory(windowObject, doc);
  assert.ok(ui && typeof ui.createTravelApp === "function", "TravelUI factory exposed");
  const app = ui.createTravelApp({
    document: doc,
    fetch,
    loadMapLibre: loader,
    now: () => 1700000000000,
  });
  return { app, doc, fetch, windowObject };
}

async function bootReady(options = {}) {
  const booted = boot(options);
  await settle();
  return booted;
}

function mapOf(app) { return app.state.map; }

function markersOf(app) { return app.state.markers; }

function pinText(app) {
  return markersOf(app).map((marker) => marker.element.textContent).join(",");
}

function postCalls(fetch, url) {
  return fetch.calls.filter((call) => call.url === url);
}

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

test("a) repeated sends append real messages and send the exact payload", async () => {
  const fetch = catalogFetch();
  const { app, doc } = await bootReady({ fetch });
  const message = doc.getElementById("message");
  const ask = doc.getElementById("ask");
  const chatLog = doc.getElementById("chat-log");

  message.value = "Xin chào, tôi muốn đi nhẹ nhàng.";
  ask.click();
  await settle();
  message.value = "Gợi ý thêm một quán ăn địa phương.";
  ask.click();
  await settle();

  const chats = postCalls(fetch, "/chat");
  assert.equal(chats.length, 2, "two explicit /chat POSTs");
  assert.equal(chatLog.children.length, 4, "two user plus two assistant bubbles");
  assert.match(chatLog.textContent, /Xin chào, tôi muốn đi nhẹ nhàng\./);
  assert.match(chatLog.textContent, /Gợi ý nhẹ nhàng trong vùng đang chọn\./);

  for (const chat of chats) {
    assert.deepEqual(chat.body.source_scope, SELECTION, "exact source tuple");
    assert.equal(chat.body.transport_mode, "car");
    assert.equal(chat.body.memory_enabled, true);
    assert.equal(chat.body.session_id, chats[0].body.session_id, "same session");
  }

  message.value = "Gửi bằng Enter.";
  message.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false, preventDefault() {} });
  await settle();
  assert.equal(postCalls(fetch, "/chat").length, 3, "Enter sends exactly once");

  const before = postCalls(fetch, "/chat").length;
  message.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: true, preventDefault() {} });
  await settle();
  assert.equal(postCalls(fetch, "/chat").length, before, "Shift+Enter does not send");
  assert.equal(app.state.busy, false);
  assert.equal(ask.disabled, false);
});

test("b) map import and style failures stay truthful while chat works", async () => {
  const fetch = catalogFetch();
  const { app, doc } = await bootReady({
    fetch,
    loader: async () => { throw new Error("offline CDN"); },
  });
  const mapStatus = doc.getElementById("map-status");
  const retry = doc.getElementById("map-retry");
  assert.match(mapStatus.textContent, /không khả dụng/i);
  assert.equal(retry.hidden, false, "manual retry visible");
  assert.equal(app.state.map, null);
  assert.equal(app.state.mapReady, false);

  doc.getElementById("message").value = "Vẫn chat được khi bản đồ lỗi?";
  doc.getElementById("ask").click();
  await settle();
  assert.match(doc.getElementById("chat-log").textContent, /Gợi ý nhẹ nhàng/);
  assert.equal(postCalls(fetch, "/chat").length, 1);

  const style = boot();
  await settle();
  const styleApp = style.app;
  assert.ok(styleApp.state.map, "map object created before style load");
  mapOf(styleApp).fire("error");
  assert.match(style.doc.getElementById("map-status").textContent, /phong cách bản đồ/i);
  assert.equal(style.doc.getElementById("map-retry").hidden, false);
  assert.equal(styleApp.state.map, null, "failed map cleared for retry");
  doc.getElementById("message").value = "";
});

test("c) 2 real pins, pin/card selection, safe popup text, missing coords listed", async () => {
  const { app, doc } = await bootReady();
  mapOf(app).fire("load");
  assert.equal(mapOf(app).layers.length, 1, "one 3D building layer added");

  doc.getElementById("message").value = "Hai điểm, đi xe hơi.";
  doc.getElementById("plan").click();
  await settle();

  const markers = markersOf(app);
  assert.equal(markers.length, 2, "only the two valid coordinates are pinned");
  assert.deepEqual(markers[0].lngLat, [106.7012, 10.7765]);
  assert.deepEqual(markers[1].lngLat, [106.7055, 10.7802]);
  assert.equal(pinText(app), "1,2");
  assert.match(doc.getElementById("coord-unavailable").textContent, /thiếu toạ độ hợp lệ/);
  assert.match(doc.getElementById("coord-unavailable").textContent, /Điểm thiếu toạ độ/);

  markers[0].element.click();
  assert.ok(markers[0].element.className.includes("selected"));
  const popup = app.state.popup;
  assert.ok(popup && popup.content, "popup got a DOM card");
  assert.equal(popup.setHTML, undefined, "no setHTML authoring");
  const text = popup.content.textContent;
  assert.match(text, /<img src=x onerror=alert\(1\)>/, "injection text rendered literally");
  assert.match(text, /12 Nguyễn Huệ/, "street_name address is shown");
  assert.match(text, /Quán ăn/);
  assert.match(text, /Giá:.*chưa rõ/s);
  assert.match(text, /Giờ mở cửa:.*chưa rõ/s);
  assert.match(text, /Vùng dữ liệu: Khu Quận 1/);
  assert.equal(doc.htmlUsed, false);

  const secondCard = doc.getElementById("stops").children[1];
  secondCard.click();
  assert.ok(markers[1].element.className.includes("selected"));
  assert.ok(!markers[0].element.className.includes("selected"));
  assert.deepEqual(mapOf(app).lastFlyTo.center, [106.7055, 10.7802]);
  assert.match(app.state.popup.content.textContent, /1\.2 km/);
  assert.match(app.state.popup.content.textContent, /6 phút/);
  assert.doesNotMatch(app.state.popup.content.textContent, /99 km/);
  assert.match(doc.getElementById("stops").textContent, /1\.2 km/);
  assert.match(doc.getElementById("stops").textContent, /Thời gian: 10:15 – 11:00/);
});

test("d) source/mode switches clear state, rotate session and discard in-flight results", async () => {
  let resolvePlan;
  let resolveChat;
  const fetch = catalogFetch({
    plan: () => new Promise((resolve) => { resolvePlan = resolve; }),
    chat: () => new Promise((resolve) => { resolveChat = resolve; }),
  });
  const { app, doc } = await bootReady({ fetch });
  mapOf(app).fire("load");
  const originalSession = app.state.sessionId;

  // Mode switch while a plan is in flight.
  doc.getElementById("message").value = "Kế hoạch cũ.";
  doc.getElementById("plan").click();
  await settle();
  assert.equal(postCalls(fetch, "/generate_itinerary").length, 1);
  const postCount = fetch.calls.filter((call) => call.url === "/chat" ||
    call.url === "/generate_itinerary").length;

  doc.getElementById("transport-car").checked = false;
  doc.getElementById("transport-foot").checked = true;
  doc.getElementById("transport-foot").dispatchEvent({ type: "change" });
  assert.equal(fetch.calls.filter((call) => call.url === "/chat" ||
    call.url === "/generate_itinerary").length, postCount,
  "mode change does not call the model");

  resolvePlan(jsonResponse(successfulPlanBody()));
  await settle();
  assert.equal(markersOf(app).length, 0, "stale plan result cannot add pins");
  assert.equal(doc.getElementById("itinerary-wrap").hidden, true);
  assert.match(doc.getElementById("status").textContent, /đã được xoá/i);

  // In-flight chat discarded after an area switch.
  doc.getElementById("message").value = "Câu hỏi cũ.";
  doc.getElementById("transport-car").checked = true;
  doc.getElementById("transport-foot").checked = false;
  doc.getElementById("ask").click();
  await settle();
  const area = doc.getElementById("area");
  area.selectedIndex = 1;
  area.dispatchEvent({ type: "change" });
  resolveChat(jsonResponse({ status: "success", reply: "KẾT QUẢ CŨ KHÔNG ĐƯỢC HIỆN" }));
  await settle();
  assert.doesNotMatch(doc.getElementById("chat-log").textContent, /KẾT QUẢ CŨ/);
  assert.notEqual(app.state.sessionId, originalSession, "session rotated");
  assert.equal(area.value, "1");

  // Successful fresh plan after the switch uses the new area session.
  await settle();
  doc.getElementById("message").value = "Kế hoạch mới.";
  doc.getElementById("plan").click();
  await settle();
});

test("e) chips/map/pin/card never model-call; explicit buttons each POST once", async () => {
  const fetch = catalogFetch();
  const { app, doc } = await bootReady({ fetch });
  mapOf(app).fire("load");
  doc.getElementById("message").value = "Tạo lịch trình.";
  doc.getElementById("plan").click();
  await settle();
  assert.equal(postCalls(fetch, "/generate_itinerary").length, 1);
  assert.ok(markersOf(app).length === 2);

  const before = fetch.calls.length;
  const chip = doc.querySelectorAll(".chip")[0];
  chip.click();
  assert.match(doc.getElementById("message").value, /buổi chiều nhẹ nhàng/);
  assert.equal(fetch.calls.length, before, "chip fills composer only");

  markersOf(app)[0].element.click();
  assert.equal(fetch.calls.length, before, "pin click does not fetch");
  doc.getElementById("stops").children[0].click();
  assert.equal(fetch.calls.length, before, "card click does not fetch");

  const retry = doc.getElementById("map-retry");
  retry.click();
  assert.equal(fetch.calls.length, before, "map retry does not fetch model");

  const askedBefore = postCalls(fetch, "/chat").length;
  doc.getElementById("ask").click();
  await settle();
  assert.equal(postCalls(fetch, "/chat").length, askedBefore + 1, "ask POSTs once");
  assert.equal(postCalls(fetch, "/generate_itinerary").length, 1, "no combined hidden plan call");
});

test("f) failed/empty generation clears stale pins; failed network unlocks controls", async () => {
  let planMode = "success";
  let chatMode = "success";
  const fetch = catalogFetch({
    plan: () => {
      if (planMode === "empty") {
        return Promise.resolve(jsonResponse({ status: "success", reply: { stops: [] } }));
      }
      if (planMode === "network") {
        return Promise.reject(new Error("network down"));
      }
      return Promise.resolve(jsonResponse(successfulPlanBody()));
    },
    chat: () => {
      if (chatMode === "network") return Promise.reject(new Error("network down"));
      return Promise.resolve(jsonResponse({ status: "success", reply: "Ổn." }));
    },
  });
  const { app, doc } = await bootReady({ fetch });
  mapOf(app).fire("load");

  doc.getElementById("message").value = "Lịch trình đầu.";
  doc.getElementById("plan").click();
  await settle();
  assert.equal(markersOf(app).length, 2);

  planMode = "empty";
  doc.getElementById("plan").click();
  await settle();
  assert.equal(markersOf(app).length, 0, "empty generation clears pins");
  assert.equal(doc.getElementById("itinerary-wrap").hidden, true);

  planMode = "network";
  doc.getElementById("message").value = "Lịch trình lỗi.";
  doc.getElementById("plan").click();
  await settle();
  assert.equal(markersOf(app).length, 0);
  assert.equal(doc.getElementById("ask").disabled, false);
  assert.equal(doc.getElementById("plan").disabled, false);
  assert.match(doc.getElementById("status").textContent, /Không tạo được lịch trình/);

  chatMode = "network";
  doc.getElementById("message").value = "Chat lỗi mạng.";
  doc.getElementById("ask").click();
  await settle();
  assert.match(doc.getElementById("chat-log").textContent, /Không gọi được trợ lý/);
  assert.equal(doc.getElementById("ask").disabled, false, "controls unlocked");
  assert.equal(doc.getElementById("plan").disabled, false);
  assert.equal(doc.getElementById("error-box").hidden, false);
});

test("g) no fabricated road line, unknown price/hours stay visible", async () => {
  assert.doesNotMatch(scriptSource, /LineString/);
  assert.doesNotMatch(scriptSource, /type:\s*["']line["']/);
  assert.doesNotMatch(html, /address\.full|display_name/);
  assert.match(scriptSource, /repaired_schedule/);
  assert.match(scriptSource, /totals\.legs/);
  assert.match(scriptSource, /Thứ tự điểm dừng; bản đồ chưa hiển thị đường đi chi tiết\./);

  const { app, doc } = await bootReady();
  mapOf(app).fire("load");
  doc.getElementById("message").value = "Kiểm tra giá và giờ.";
  doc.getElementById("plan").click();
  await settle();

  const layers = mapOf(app).layers.map((entry) => entry.layer);
  assert.equal(layers.some((layer) => layer.type === "line"), false, "no line layer");
  const building = layers.find((layer) => layer.type === "fill-extrusion");
  assert.ok(building, "3D building layer exists");
  assert.equal(building["source-layer"], "building");
  assert.ok(building.paint["fill-extrusion-height"]);
  assert.ok(building.paint["fill-extrusion-base"]);
  assert.ok(building.paint["fill-extrusion-height"].toString().includes("render_height"));

  const itinerary = doc.getElementById("stops").textContent;
  assert.match(itinerary, /Giá: chưa rõ/);
  assert.match(itinerary, /Giờ mở cửa: chưa rõ \(chưa xác minh\)/);
  assert.match(doc.getElementById("unknowns").textContent, /stops\[2\]\.longitude/);
});

test("h) static allowlist, safe DOM and map contract", async () => {
  const lower = html.toLowerCase();
  assert.ok(!lower.includes("innerhtml"));
  assert.ok(!lower.includes("insertadjacenthtml"));
  assert.ok(!lower.includes("sethtml"));
  assert.ok(!lower.includes("localstorage"));
  assert.ok(!lower.includes("sessionstorage"));
  assert.ok(!lower.includes("authorization"));
  assert.ok(!lower.includes("bearer"));
  assert.ok(!lower.includes("<script src"));
  assert.ok(html.includes("<link rel=\"stylesheet\" href=\"https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.css\">"));
  assert.ok(html.includes("https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.mjs"));
  assert.ok(html.includes("https://tiles.openfreemap.org/styles/bright"));
  assert.ok(html.includes("https://tiles.openfreemap.org/planet"));

  const allowed = new Set([
    "https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.css",
    "https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.mjs",
    "https://tiles.openfreemap.org/styles/bright",
    "https://tiles.openfreemap.org/planet",
  ]);
  const urls = html.match(/https?:\/\/[^\s"'<>)]+/g) || [];
  for (const url of urls) {
    assert.ok(allowed.has(url), "unexpected external URL: " + url);
  }
  assert.ok(!html.includes("http://"));
  assert.match(scriptSource, /Popup\.setDOMContent|setDOMContent\(/);
  assert.match(scriptSource, /document\.createElement/);
  assert.match(scriptSource, /textContent/);
  assert.match(scriptSource, /new state\.maplibre\.Marker/);
  assert.match(scriptSource, /fill-extrusion/);
  assert.match(scriptSource, /attributionControl:\s*true/);
});

(async () => {
  let failed = 0;
  for (const entry of tests) {
    try {
      await entry.fn();
      console.log("ok - " + entry.name);
    } catch (error) {
      failed += 1;
      console.log("not ok - " + entry.name);
      console.log("  " + (error && error.stack ? error.stack.split("\n").join("\n  ") : error));
    }
  }
  console.log(failed === 0
    ? `\n# all ${tests.length} UI127 checks passed`
    : `\n# ${failed} of ${tests.length} UI127 checks failed`);
  process.exit(failed === 0 ? 0 : 1);
})();
