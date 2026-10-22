# Hợp đồng hành vi chức năng — TVLT_2026 (Travel Vo Lo)

- **ID:** `FT-SET-TVLT-001`
- **Version:** `0.1` · **Status:** `DRAFT` → chờ chủ dự án xác thực từng chức năng
- **Owner/approver:** chủ dự án (người dùng) · **Người soạn:** Hermes (đọc mã, không chạy hệ thống)
- **Date:** 2026-10-22
- **Control view:** L0 feature (outcome quan sát được) + L2 module (điểm vào, lỗi, invariant). Không phải kiến trúc cố định.
- **Nguồn dựng contract:** đọc trực tiếp mã nguồn ngày 2026-10-22; ADR `docs/decisions/001`–`014`; `docs/audit/ARCHITECTURE_AS_IS.md`; `docs/project/ACCEPTANCE_TRACKER.md`; `docs/project/CURRENT_PROGRESS_2026-10-20.md`.

Nhãn bằng chứng dùng trong tệp:

- `VERIFIED FACT (mã)` — đọc thấy trong mã nguồn, có đường dẫn.
- `VERIFIED FACT (tài liệu)` — con số/trạng thái lấy từ tài liệu dự án đã được QA nhận, chưa chạy lại trong phiên này.
- `INFERENCE` — suy ra từ mã, chưa quan sát.
- `ASSUMPTION` — giả định cần người dùng xác nhận.
- `PROPOSAL` — đề xuất, chưa phải scope.
- `NOT VERIFIED` — chưa có bằng chứng chạy thật trong phiên này.

> Toàn bộ mô tả dưới đây là **hành vi mà mã hiện tại thể hiện**. Không dòng nào là tuyên bố "đã chạy thật trên môi trường live" trừ khi ghi rõ.

---

## 1. Danh mục chức năng

| ID | Chức năng | Điểm vào chính | Bằng chứng |
|---|---|---|---|
| FT-01 | Chuẩn bị dữ liệu POI gốc (primary dataset) | `crawler_service/app/primary_dataset/` | VERIFIED FACT (mã) |
| FT-02 | Thu thập mở rộng (acquisition, dry-run) | `crawler_service/app/acquisition/` | VERIFIED FACT (mã) |
| FT-03 | Thu thập web/social (offline-first) | `crawler_service/app/social_ingest/` | VERIFIED FACT (mã) |
| FT-04 | Crawler HTTP cũ (Traveloka/Crawl4AI) | `POST /api/v1/crawl` | VERIFIED FACT (mã), hoãn theo chỉ đạo 18/10 |
| FT-05 | Nạp POI vào graph theo lô | `POST /ingestion/batch`, `GET /ingestion/stream/{job_id}` | VERIFIED FACT (mã) |
| FT-06 | Tạo một POI | `POST /management/poi` | VERIFIED FACT (mã) |
| FT-07 | Đọc payload POI cho agent | `GET /pois/{poi_id}` | VERIFIED FACT (mã) |
| FT-08 | Dựng lại quan hệ không gian NEAR_BY | `POST /management/pois/spatial-rebuild` | VERIFIED FACT (mã) |
| FT-09 | Bộ 5 công cụ MCP | `POI_service/app/api/mcp/tools.py` | VERIFIED FACT (mã) |
| FT-10 | Hội thoại `/chat` (định tuyến ý định + ReAct) | `POST /chat` | VERIFIED FACT (mã) |
| FT-11 | Sinh lịch trình `/generate_itinerary` | `POST /generate_itinerary` | VERIFIED FACT (mã) |
| FT-12 | Bộ lập lịch tất định + bộ kiểm định độc lập | `ai_service/domains/planning/` | VERIFIED FACT (mã) |
| FT-13 | Bộ nhớ hai tầng | `POST /chat`, `/memory/*` | VERIFIED FACT (mã) |
| FT-14 | Lưu nháp lịch trình (backend) | `/api/v1/itineraries` | VERIFIED FACT (mã) |
| FT-15 | Trang demo + catalog nguồn | `GET /travel`, `/catalog/*` | VERIFIED FACT (mã) |
| FT-16 | Chọn provider/model và health | `ai_service/main.py`, `backend_service/app/main.py` | VERIFIED FACT (mã) |

---

## 2. Hợp đồng từng chức năng

### FT-01 — Chuẩn bị dữ liệu POI gốc

**Outcome:** từ một tệp GeoJSON đóng băng, sinh ra các payload POI hợp lệ để nạp, kèm lineage và danh sách loại bỏ; không tự nạp vào graph.

**Cases**

| Case | Input/điều kiện | Expected outcome | Nguồn |
|---|---|---|---|
| C-01.1 | GeoJSON FeatureCollection hợp lệ | Prepared payload + lineage + quarantine + duplicate ledger + summary, ghi atomic | mã `primary_dataset/prepare.py` |
| C-01.2 | Hai feature trùng byte-canonical | Gộp một, ghi cả hai chỉ số nguồn và lý do vào duplicate ledger | mã |
| C-01.3 | Identity xung đột hoặc byte nguồn đổi khi chưa có revision được duyệt | Fail closed, không re-identify im lặng | mã `primary_dataset/registry.py` |
| C-01.4 | Payload không qua được domain model POI | Vào quarantine, không vào prepared | mã |
| C-01.5 | Chạy lại với input không đổi | Byte no-op | mã (registry docstring) |

**Invariant**

- `INV-01.1` Input gốc bất biến, có hash; không sửa tệp nguồn.
- `INV-01.2` ID nội bộ do registry cấp, namespaced; không suy ra OSM ID/URL khi nguồn không có.
- `INV-01.3` Tọa độ được kiểm; không có POI "hợp lệ" với toạ độ ngoài miền.
- `INV-01.4` Bản ghi không đủ bằng chứng không được nâng thành accepted.

**Số liệu đã được QA nhận (không chạy lại trong phiên này):** 6368 feature → 6367 POI prepared/accepted, 14 category (`ACCEPTANCE_TRACKER` AC03/AC12, DATA068).

**Ngoài phạm vi:** nạp graph thật, đối chiếu venue ngoài đời, xác thực mọi POI.

---

### FT-02 — Thu thập mở rộng (acquisition)

**Outcome:** chạy dry-run trên nguồn đã khai báo, tạo quyết định accepted/quarantined có thể kiểm lại, không chạm mạng và không ghi vào graph.

**Cases**

| Case | Điều kiện | Expected outcome | Nguồn |
|---|---|---|---|
| C-02.1 | Nguồn hợp lệ + mapping review đủ từng entity | `IngestionDecision` cho từng candidate; JSONL accepted/quarantine | `acquisition/pipeline.py` |
| C-02.2 | Mapping thiếu review ở mức entity (chỉ có default cấp file) | Từ chối cấu hình (`ConfigError`) | `acquisition/resolution.py` |
| C-02.3 | Cùng dataset nhưng `synthetic` vs `real` | Hai state directory tách biệt; chéo scope bị chặn | ADR 013 + `parse_scope` |
| C-02.4 | Candidate mơ hồ/không resolve được | Vào review/quarantine kèm reason code, không accepted | mã |

**Invariant**

- `INV-02.1` Không network, không live ingestion trong pipeline này.
- `INV-02.2` Raw bytes của nguồn được lưu bất biến trước khi parse.
- `INV-02.3` Đồng hồ/quyết định ghi append-only; không sửa lịch sử.
- `INV-02.4` Không có dữ liệu chưa xác minh đi thẳng vào graph tin cậy.

**Ngoài phạm vi:** fetch live, import graph, taxonomy mới ngoài catalog đóng.

---

### FT-03 — Thu thập web/social

**Outcome:** một profile nguồn web được thu và xuất bản ghi chuẩn hoá kèm manifest/mapping; mặc định chạy offline trên capture đã lưu.

**Cases**

| Case | Điều kiện | Expected outcome | Nguồn |
|---|---|---|---|
| C-03.1 | Không truyền fetcher/`--fetch` | Chỉ đọc capture index, xác minh hash từng tệp; không chạm mạng | `social_ingest/runner.py` |
| C-03.2 | Có fetcher tường minh | Ghi raw bytes + index; trích xuất; kiểm tra tối thiểu; export chuẩn hoá | mã |
| C-03.3 | Nội dung dưới ngưỡng tối thiểu | Bị loại, không thành POI | mã |
| C-03.4 | Lập kế hoạch nạp | Dry-run; `imported = 0` trừ khi transport báo batch thành công đầy đủ | `social_ingest/ingest.py` |

**Invariant:** `INV-03.1` hash capture phải khớp; `INV-03.2` mapping entity phải đến từ fixture đã review, không tự sinh; `INV-03.3` không tuyên bố dữ liệu mạng xã hội khi mới có capture web.

---

### FT-04 — Crawler HTTP cũ

**Outcome:** `POST /api/v1/crawl` (service token) chạy Crawl4AI để discover/detail một URL và trả kết quả trích xuất.

**Cases:** C-04.1 URL không hợp lệ → `None` → `{"status":"failed"}`; C-04.2 lỗi pipeline → HTTP 500 kèm `detail` là chuỗi lỗi; C-04.3 thành công → `{"status":"success","result":...}`.

**Invariant:** không có persistence DB trong pipeline này (`SYSTEM_INVENTORY` + mã); preprocessor một phần còn stub.

**Trạng thái scope:** hoãn sang Finalizing phase theo chỉ đạo 18/10/2026. **Ngoài phạm vi xác thực core.**

---

### FT-05 — Nạp POI vào graph theo lô

**Outcome:** client gửi mảng POI, nhận `202` + `job_id` khi lô canary (10 bản ghi đầu) đã ghi thành công, phần còn lại chạy nền; tiến trình quan sát được qua SSE.

**Cases**

| Case | Điều kiện | Expected outcome | Nguồn |
|---|---|---|---|
| C-05.1 | ≤ 10 bản ghi hợp lệ | 202, `canary_summary`, job kết thúc ngay bằng terminal event | `endpoint_ingestion.py:103-121` |
| C-05.2 | > 10 bản ghi | 202; phần dư chạy background; tổng kết bao trùm cả lô | `:103-111` |
| C-05.3 | Bản ghi sai schema | 422, body sanitized, `error_type` cụ thể | `:84-97` |
| C-05.4 | DB không sẵn sàng | 503 `database_unavailable` | `:87-91` |
| C-05.5 | Broadcaster đầy | 503 `broadcaster_capacity` trước khi ghi bất cứ gì | `:49-60` |
| C-05.6 | SSE với job lạ/hết hạn | 404 | `:127-131` |
| C-05.7 | SSE kết nối muộn | Replay từ cursor, gồm cả terminal event | broadcaster `:11-16`, TTL 300s, 128 job, 256 event/job |

**Invariant**

- `INV-05.1` Không trả "thành công" khi canary fail.
- `INV-05.2` Lỗi trả về không chứa traceback/exception text.
- `INV-05.3` ID POI do client cung cấp được giữ nguyên; toạ độ được kiểm (ADR 001).
- `INV-05.4` Retry dùng transaction mới (ADR 003).

**Ngoài phạm vi:** idempotency nhiều worker, recovery xuyên process.

---

### FT-06 — Tạo một POI

**Outcome:** `POST /management/poi` (JWT) tạo một POI, trả `201` + payload, hoặc lỗi ánh xạ `422` / `409` / `500`.

**Invariant:** `INV-06.1` POI mutation thay thế các cạnh NEAR_BY liên quan **trong cùng transaction** (ADR 012); `INV-06.2` không tạo entity trùng khi identity đã tồn tại (`conflict`).

---

### FT-07 — Đọc payload POI cho agent

**Outcome:** `GET /pois/{poi_id}` (JWT) trả `POIGetResponse`; 404 khi POI không tồn tại; Document RAG chưa cấu hình thì degrade chứ không fail cả request.

**Cases:** C-07.1 có POI → 200 đầy đủ; C-07.2 không có POI → 404 `success=false`; C-07.3 lỗi nội bộ → 500.

**Invariant:** `INV-07.1` POI existence và attribute correctness là hai claim tách biệt; module này không xác nhận tính đúng của từng field.

**Điểm cần chủ dự án quyết (xem §4, Q3):** nhánh 500 hiện trả cả `str(e)` và chuỗi `traceback` trong body (`endpoint_poi_router.py:54-65`), khác với chuẩn sanitize ở mọi endpoint khác.

---

### FT-08 — Dựng lại NEAR_BY

**Outcome:** `POST /management/pois/spatial-rebuild` (JWT) nhận danh sách district, dựng lại cạnh NEAR_BY theo từng district và trả báo cáo thật của lần chạy.

**Cases**

| Case | Điều kiện | Expected outcome | Nguồn |
|---|---|---|---|
| C-08.1 | Danh sách hợp lệ ≤ 200 | Blocking tới khi xong; trả report `is_success` | `endpoint_spatial_rebuild.py:81-117` |
| C-08.2 | Trùng lặp/ có khoảng trắng | Strip + dedupe, báo `requested`/`deduplicated` | `:33-78,110-112` |
| C-08.3 | > 200, rỗng, phần tử không phải string | 422 `invalid_request` | `:39-77` |
| C-08.4 | Một phần district lỗi | 207 kèm `succeeded`/`failed` | `:119-125` |
| C-08.5 | Toàn bộ lỗi | 502, không bao giờ là success | `:121-125` |
| C-08.6 | Radius cấu hình xung đột với dữ liệu cũ | Rebuild bị gate, không tự đổi ngưỡng | ADR 012 |

**Invariant:** `INV-08.1` prefilter cầu phương sai số âm được thay bằng prefilter bảo thủ (ADR 002); `INV-08.2` NEAR_BY là quan hệ vô hướng; `INV-08.3` lỗi provider chỉ lộ loại lỗi.

---

### FT-09 — Bộ 5 công cụ MCP

**Outcome:** agent gọi đúng 5 tool để lấy dữ liệu có bằng chứng, sai input thì nhận lỗi có mã chứ không nhận dữ liệu bịa.

| Tool | Hành vi chính | Lỗi có mã |
|---|---|---|
| `get_poi_details(poi_id)` | Chi tiết POI + parent administrative context + NEAR_BY | `invalid_request`, `not_found`, `not_implemented`, `internal_error` |
| `explore_pois(...)` | AND các filter id; category khớp chính xác; `source_discovery=snapshots\|source_areas`; `source_scope` chỉ trả bản ghi source-only, không trộn filter hành chính hiện tại | `invalid_request`, `exploration_failed`, `serialization_failed` |
| `get_available_categories()` | Luôn `success=true` + danh sách (có thể rỗng) | `category_fetch_failed` |
| `resolve_geographic_id(keyword)` | Trả **candidates**, không tự chọn khi nhiều kết quả | `invalid_request`, `location_lookup_failed` |
| `get_itinerary_route(ids, vehicle)` | ≥ 2 stop; mọi toạ độ phải resolve được; chỉ profile được cấu hình; CH không có thì `ch.disable=true`; geometry chỉ nhận GeoJSON thật | `stops_unresolved`, `route_failed`, `no_route` |

**Invariant**

- `INV-09.1` Không fallback đường thẳng khi routing lỗi.
- `INV-09.2` Không echo message thô của provider.
- `INV-09.3` Tool không bao giờ trả bản ghi chưa xác minh như "sự thật chắc chắn": thiếu dữ liệu thì để trống/unknown.

---

### FT-10 — Hội thoại `/chat`

**Outcome:** người dùng gửi tin nhắn; hệ thống phân loại ý định, chỉ xử lý `CHITCHAT`/`TRAVEL`, trả lời kèm chuỗi công cụ và trạng thái grounding, hoặc dừng an toàn khi không phân loại được.

**Cases**

| Case | Điều kiện | Expected outcome | Nguồn |
|---|---|---|---|
| C-10.1 | Jev trả `ok` + `CHITCHAT` | Trả lời hội thoại, `tool_chain=[]` | `main.py:2212-2262` |
| C-10.2 | Jev trả `ok` + `TRAVEL` | Chạy ReAct qua MCP, trả `tool_chain`, `source_evidence_ids`, `grounding_status` | `:759-836` |
| C-10.3 | Jev `ambiguous`/`UNCERTAIN` | 200 `needs_clarification`, câu hỏi tiếng Việt, không gọi model/MCP | `:2157-2195` |
| C-10.4 | Jev lỗi/không cấu hình | 503 `intent_unavailable`, không fallback provider khác | `:2185-2195` |
| C-10.5 | `transport_mode` khác `car`/`foot` (kể cả hoa/thừa khoảng trắng) | 422 trước mọi side effect | `:2283-2289`, `payloads._strict_transport_mode` |
| C-10.6 | `source_scope` sai định dạng | 422 `invalid_source_scope` | `:2272-2282` |
| C-10.7 | Model đề xuất tool arg khác selection | Server từ chối, không âm thầm thay | `domains/source_gate.py` |
| C-10.8 | Không có bằng chứng tool | `status=insufficient_data`, không bịa | `chat_agent.py:395-411` |
| C-10.9 | Câu trả lời tự do có bằng chứng | `grounding_status=unverified_free_text` + evidence ids | `chat_agent.py:423-448` |

**Invariant**

- `INV-10.1` Vòng lặp bị chặn: tối đa 5 lượt model, 8 lần gọi tool (`chat_agent.MAX_TURNS/MAX_TOOL_CALLS`).
- `INV-10.2` Tool lạ hoặc args không phải object: không thực thi.
- `INV-10.3` Nguồn được chọn phía server; model không được mở rộng/thay đổi phạm vi nguồn.
- `INV-10.4` `memory_enabled=false` bỏ qua cả hai tầng bộ nhớ.

---

### FT-11 — Sinh lịch trình `/generate_itinerary`

**Outcome:** từ yêu cầu có cấu trúc, hệ thống lấy bằng chứng POI thật, để model đề xuất, rồi **tính lại** lịch bằng bộ lập lịch tất định và **kiểm định độc lập** trước khi trả về.

**Luồng 8 bước (mã `main.py:1179-1760`)**

1. Resolve city + district (khớp chính xác duy nhất; district phải thuộc city).
2. Lấy category từ tool thật.
3. Scatter-gather candidate (district + city; source mode có floor query riêng).
4. Enrich song song từng candidate.
5. Scope evidence theo `administrative_context`; fail closed nếu thiếu.
6. Model tổng hợp (Gemini mặc định; prompt không chứa provenance nội bộ).
7. Validate + tái dựng **mọi** field thực tế từ evidence.
8. Lập lịch tất định + validator độc lập; coverage theo từng ngày.

**Cases chính:** thiếu `target_district` mà không có `source_scope` → 422 ngay ở model request; `source_scope` sai → 422; budget explicit sai định dạng → fail validation trước khi gọi route; route thiếu → `unknown`, không thay bằng 0/đường thẳng; giờ mở cửa không parse được → `hours_known=false`; giá menu không thành chi phí tham quan.

**Invariant**

- `INV-11.1` Không field nào của model được copy vào kết quả nếu không có evidence.
- `INV-11.2` `no_plan` do heuristic **không** chứng minh bài toán bất khả thi.
- `INV-11.3` Thiếu giá/giờ/tuyến vẫn là unknown trong output, không làm tròn thành 0.
- `INV-11.4` Kết quả mang `planning` + `grounding` + `model`/`provider` để kiểm lại.

---

### FT-12 — Bộ lập lịch tất định + validator

**Outcome:** hàm thuần `schedule(scenario)` và `validate(scenario, plan)` cho cùng input → cùng output, không I/O, không random.

**Bound cứng:** 14 ngày, 200 POI, 50 người, 100 000 vòng lặp; thời gian là **phút nguyên** từ epoch; tiền/distance là `Decimal`; edge có hướng, thiếu edge = unknown.

**Invariant:** `INV-12.1` validator không import helper của scheduler và không tin `status`/`sequence`; `INV-12.2` lịch rỗng không bao giờ feasible; `INV-12.3` `no_plan` có stop vẫn bị kiểm đầy đủ; `INV-12.4` không dùng khoảng cách đường chim bay thay travel time.

---

### FT-13 — Bộ nhớ hai tầng

**Outcome:** hội thoại có ngữ cảnh ngắn hạn theo phiên và hồ sơ dài hạn do người dùng tự khai; cả hai đều có thể tắt và có biên xoá.

| Tầng | Hành vi | Bound |
|---|---|---|
| Working memory | 8 lượt hoàn tất/phiên, tóm tắt trích xuất từ tin nhắn USER cũ, giữ system prompt đúng một lần, lease theo phiên, reset khi đổi scope nguồn | 128 phiên, TTL 1800s, message ≤ 8000 ký tự |
| Durable profile | Chỉ bật khi có `MEMORY_DB_PATH`; chủ sở hữu là `sub` đã xác thực; PUT có `expected_version` → 409 khi lệch; validate → 422 | prompt ≤ 800 ký tự |

**Cases:** C-13.1 `memory_enabled=false` → không đọc/ghi cả hai tầng; C-13.2 đổi `source_scope` giữa phiên → `context_reset=true`; C-13.3 thiếu bearer → scope `anonymous_local_only`, không tạo hồ sơ; C-13.4 `POST /memory/short/clear` chờ lease đang chạy rồi mới xoá; C-13.5 vượt 128 phiên → 503 `memory_capacity`.

**Invariant:** `INV-13.1` không dùng `user_id`/`session_id` của client làm chủ hồ sơ; `INV-13.2` không có tệp hồ sơ mặc định; `INV-13.3` sở thích đã lưu không được ghi đè ràng buộc hiện tại của người dùng.

---

### FT-14 — Lưu nháp lịch trình (backend)

**Outcome:** người dùng đã đăng nhập lưu/liệt kê/đọc/xoá **nháp của chính mình**.

**Cases:** POST → 201 `DraftDetail`; GET list → phân trang có bound; GET/POST id của người khác → 404 (không phân biệt được với không tồn tại); id sai định dạng → 404; chưa cấu hình storage → 503 `storage_unavailable`; JSON quá sâu → 422 `payload_too_deep`; `GET /ready` → 503 khi repository không available.

**Invariant:** `INV-14.1` payload lưu nguyên văn, không chạy lại, không tự xác nhận khả thi; `INV-14.2` lọc theo owner ở tầng lưu trữ; `INV-14.3` startup fail-closed nếu DB có sẵn nhưng không hợp lệ.

---

### FT-15 — Trang demo + catalog nguồn

**Outcome:** `GET /travel` phục vụ một trang tĩnh (chat + form lịch trình + bản đồ + danh sách "chưa xác minh"); `GET /catalog/snapshots` và `/catalog/source_areas` chỉ proxy discovery của MCP, ép kiểu và loại bản ghi không đúng hợp đồng.

**Cases:** thiếu `travel.html` → 404 `ui_not_installed`; catalog lỗi transport → 502 `catalog_unavailable`; snapshot echo khác request → 502 `catalog_contract_mismatch`; snapshot rỗng → `status="empty"`.

**Invariant:** `INV-15.1` nhãn vùng nguồn là nhãn dataset, không phải địa giới hành chính hiện tại; `INV-15.2` catalog không gọi model, không đọc tệp.

---

### FT-16 — Provider/model và health

**Outcome:** mặc định Gemini; chế độ CLI chỉ được bật tường minh và không tự fallback; mỗi phản hồi mang `model` + `provider`; health tách khỏi readiness.

**Cases:** `/healthz` → `{"status":"ok"}`; `/` (POI) → trạng thái + `dependency_health`; `/health` (backend) luôn 200 kèm trạng thái repository; `/ready` → 503 khi storage không available; provider lỗi → lỗi có mã, không lộ stack.

**Invariant:** `INV-16.1` không chuyển provider ngầm giữa lượt; `INV-16.2` số token không có thì để `None`, không ước lượng.

---

## 3. Bản đồ test hiện có (chưa chạy trong phiên này)

`tests/` có 164 tệp `test_*.py` thuộc 31 nhóm: `acquisition`, `agent_guardrails`, `ai_chat_memory`, `ai_grounding`, `ai_intent_jev`, `ai_itinerary_memory`, `ai_planning_integration`, `ai_provider`, `backend_workflows`, `core_flow`, `demo152`, `deployment`, `domain_identity`, `evaluation`, `graph_lifecycle`, `ingestion`, `live_model`, `mcp_contracts`, `memgraph_spatial_runtime`, `memory_live`, `planning`, `primary_dataset`, `primary_provenance`, `primary_snapshot_adapter`, `social_poi_ingest`, `source_snapshot_scope`, `spatial`, `spatial_live`, `startup`, `system_adversarial`.

`NOT VERIFIED` trong phiên này: chưa chạy bất kỳ test nào; chưa gọi dịch vụ thật.

---

## 4. Câu hỏi mở cần chủ dự án quyết

| ID | Vấn đề | Vì sao chặn contract | Trạng thái |
|---|---|---|---|
| Q1 | Danh sách FT-01…FT-16 có đúng là tập chức năng cần xác thực? | Nếu thiếu/sai chức năng, mọi hợp đồng phía sau lệch | `APPROVAL_NEEDED` |
| Q2 | (theo từng chức năng) Behavior mô tả có đúng ý định sản phẩm? | Không code/không freeze khi behavior chưa được xác nhận | `APPROVAL_NEEDED` |
| Q3 | `GET /pois/{poi_id}` trả `traceback` trong body khi 500 — giữ hay bỏ? | Đây là rò rỉ thông tin nội bộ, trái chuẩn sanitize của các endpoint khác; đổi là thay đổi interface | `APPROVAL_NEEDED` |
| Q4 | POI_service chấp nhận JWT **không có `exp`**, trong khi `ai_service`/`backend_service` bắt buộc `exp`+`sub` — có phải chủ đích? | Là khác biệt bảo mật giữa các service, ảnh hưởng hợp đồng xác thực | `APPROVAL_NEEDED` |
| Q5 | CORS POI_service đang `allow_origins=["*"]` + `allow_credentials=True` | Tổ hợp này bị trình duyệt từ chối và không phải cấu hình an toàn; cần chốt hành vi mong muốn | `APPROVAL_NEEDED` |

---

## 5. Freeze và cổng xác thực

- **Đã freeze:** không có. Version `0.1` là DRAFT.
- **Điều kiện chuyển từng chức năng sang `APPROVED`:** chủ dự án xác nhận outcome + cases + invariant của chức năng đó, và Q3–Q5 được trả lời cho các chức năng liên quan.
- **Điều kiện chuyển sang `execute-mini-goal`:** chỉ sau khi chức năng tương ứng `APPROVED`, có expected output kiểm được, và (nếu sửa mã) có test command + evidence.
- **Commit gate:** chưa commit gì trong phiên này; repo đang có 37 tệp modified + 34 untracked của người dùng — không đụng, không commit.

## 6. UAT/regression link

| UAT case | Người xác nhận | Regression test |
|---|---|---|
| Theo từng FT, ghi khi chủ dự án xác thực | chủ dự án | `<chưa có / trỏ tới tests/<nhóm>>` |
