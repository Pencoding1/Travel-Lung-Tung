# Hợp đồng hành vi theo chức năng — TVLT_2026 (Travel Vo Lo)

- **ID:** `FT-SET-TVLT-002`
- **Version:** `0.2` · **Status:** `DRAFT` → chờ chủ dự án xác thực danh mục, sau đó xác thực từng chức năng
- **Owner/approver:** chủ dự án (người dùng) · **Người soạn:** Hermes (đọc mã, chưa chạy hệ thống)
- **Date:** 2026-10-22
- **Thay đổi so với 0.1:** 0.1 liệt kê module/service như thể là chức năng. 0.2 phân tầng lại: **chức năng (L0) là năng lực độc lập người dùng/người vận hành thực hiện được**; **module (L2) là đơn vị dùng lại, hành vi thay đổi theo pipeline mà nó phục vụ**.
- **Nguồn:** đọc mã ngày 2026-10-22; ADR `docs/decisions/001`–`014`; `docs/audit/ARCHITECTURE_AS_IS.md`; `docs/project/ACCEPTANCE_TRACKER.md`; `docs/project/CURRENT_PROGRESS_2026-10-20.md`.

Nhãn bằng chứng: `VERIFIED FACT (mã)`, `VERIFIED FACT (tài liệu)`, `INFERENCE`, `ASSUMPTION`, `PROPOSAL`, `NOT VERIFIED`.

> Mọi mô tả là hành vi **mã hiện tại thể hiện**. Không dòng nào là tuyên bố đã chạy thật trên môi trường live trong phiên này.

---

## 1. Danh mục chức năng (L0)

| ID | Chức năng | Ai dùng | Outcome quan sát được | Bề mặt |
|---|---|---|---|---|
| F-CHAT | Agent Chat — tư vấn du lịch hội thoại | du khách | gửi câu hỏi, nhận câu trả lời có dẫn chứng POI + chuỗi công cụ, hoặc được hỏi lại / báo không đủ dữ liệu | `POST /chat`, khung chat trong `/travel` |
| F-PLAN | Itinerary Planning — "Vi Vu" | du khách | từ ràng buộc có cấu trúc (ngày, người, ngân sách, quận, sở thích) nhận lịch trình có thứ tự, giờ, tuyến, trạng thái khả thi và danh sách điều chưa xác minh | `POST /generate_itinerary`, form trong `/travel` |
| F-LOOKUP | POI & Route Lookup — tra cứu địa điểm, danh mục, tuyến | agent thay mặt du khách; agent bên ngoài | lấy được POI theo bộ lọc, chi tiết POI, danh mục, ứng viên địa danh, tuyến có hướng giữa các điểm | 5 tool MCP, `GET /pois/{poi_id}` |
| F-MEMORY | Preference & Session Memory — hồ sơ sở thích và ngữ cảnh phiên | du khách | xem/sửa/xoá hồ sơ sở thích của mình; xoá ngữ cảnh phiên; câu trả lời sau đó phản ánh (hoặc không phản ánh) hồ sơ | `/memory/profile` (GET/PUT/DELETE), `/memory/short/clear`, ảnh hưởng lên F-CHAT/F-PLAN |
| F-SAVED | Saved Itinerary — lưu chuyến đi | du khách đã đăng nhập | lưu một lịch trình đã sinh, liệt kê, mở lại, xoá; chỉ thấy của mình | `/api/v1/itineraries` |
| F-INGEST | Graph Ingestion & Spatial Ops — nạp và bảo trì đồ thị POI | người vận hành | nạp lô POI và theo dõi tiến trình; tạo một POI; dựng lại quan hệ NEAR_BY theo quận | `/ingestion/*`, `/management/poi`, `/management/pois/spatial-rebuild` |
| F-ACQUIRE | Data Acquisition — thu thập và chuẩn bị dữ liệu mới | người vận hành | từ GeoJSON/capture web có được bộ POI ứng viên + quyết định accepted/quarantine có thể kiểm lại, không tự ghi vào graph | CLI `primary_dataset`, `acquisition`, `social_ingest`, `/api/v1/crawl` |
| F-SCOPE | Source Scope & Catalog — chọn phạm vi dữ liệu | du khách (chọn trong UI), agent | xem danh sách snapshot/area; chọn một vùng nguồn và mọi kết quả sau đó bị giới hạn đúng vùng đó | `/catalog/snapshots`, `/catalog/source_areas`, `source_scope` trong `/chat` và `/generate_itinerary` |
| F-UI | Demo Web Experience — trải nghiệm web | du khách | một trang duy nhất: chọn nguồn, chat, nhập yêu cầu lịch trình, xem stop trên bản đồ, xem danh sách "chưa xác minh" | `GET /travel` |
| F-OPS | Service Operations — vận hành dịch vụ | người vận hành | biết service sống/chết, readiness của storage, provider/model đang dùng | `/healthz`, `/`, `/health`, `/ready`, metadata `model`/`provider` |

Quan hệ giữa các chức năng: `F-SCOPE` là điều kiện đầu vào tuỳ chọn của `F-CHAT` và `F-PLAN`; `F-MEMORY` là đầu vào tuỳ chọn của `F-CHAT`/`F-PLAN` và là chức năng độc lập khi người dùng tự quản lý hồ sơ; `F-SAVED` tiêu thụ đầu ra của `F-PLAN`; `F-INGEST`/`F-ACQUIRE` tạo dữ liệu cho `F-LOOKUP`.

---

## 2. Ma trận module × chức năng

`●` = module tham gia; `—` = không tham gia.

| Module (L2) | F-CHAT | F-PLAN | F-LOOKUP | F-MEMORY | F-SAVED | F-INGEST | F-ACQUIRE | F-SCOPE | F-UI | F-OPS |
|---|---|---|---|---|---|---|---|---|---|---|
| `M-INTENT` định tuyến ý định (Jev) | ● | — | — | — | — | — | — | — | — | — |
| `M-REACT` vòng lặp ReAct | ● | — | — | — | — | — | — | — | — | — |
| `M-MCP` 5 tool đồ thị | ● | ● | ● | — | — | — | — | — | — | — |
| `M-ROUTE` GraphHopper | ● | ● | ● | — | — | — | — | — | — | — |
| `M-GROUND` kiểm chứng/tái dựng bằng chứng | ● | ● | — | — | — | — | — | — | — | — |
| `M-GATE` scope nguồn + transport | ● | ● | — | — | — | — | — | ● | ● | — |
| `M-MEM-WORK` working memory | ● | ● | — | ● | — | — | — | — | — | — |
| `M-MEM-PROFILE` hồ sơ dài hạn | ● | ● | — | ● | — | — | — | — | — | — |
| `M-PLAN-ADAPTER` dựng scenario | — | ● | — | — | — | — | — | — | — | — |
| `M-SCHED` lập lịch tất định | — | ● | — | — | — | — | — | — | — | — |
| `M-VALID` kiểm định độc lập | — | ● | — | — | — | — | — | — | — | — |
| `M-DRAFT` lưu nháp | — | — | — | — | ● | — | — | — | — | — |
| `M-INGEST-BATCH` canary + SSE | — | — | — | — | — | ● | — | — | — | — |
| `M-POI-WRITE` tạo POI + cạnh NEAR_BY | — | — | — | — | — | ● | — | — | — | — |
| `M-SPATIAL` dựng lại NEAR_BY | — | — | — | — | — | ● | — | — | — | — |
| `M-ACQ` pipeline thu thập dry-run | — | — | — | — | — | — | ● | — | — | — |
| `M-IDENTITY` registry định danh | — | — | — | — | — | — | ● | — | — | — |
| `M-CATALOG` proxy discovery | — | — | — | — | — | — | — | ● | ● | — |
| `M-UI` trang tĩnh | — | — | — | — | — | — | — | — | ● | — |
| `M-HEALTH` health/readiness | — | — | — | — | — | — | — | — | — | ● |

---

## 3. Cùng module, hành vi khác nhau theo pipeline

Đây là phần mà bản 0.1 làm sai: mô tả module một lần rồi áp cho mọi nơi. Dưới đây là hành vi **theo từng chức năng**.

### 3.1 `M-INTENT` (Jev)
- Chỉ dùng ở `F-CHAT`. Phân loại **một** tin nhắn hiện tại thành `CHITCHAT`/`TRAVEL`.
- `F-PLAN` **không** đi qua Jev: schema request đã là tuyên bố ý định.
- Không fallback provider/model; lỗi ⇒ 503, mơ hồ ⇒ 200 cần làm rõ (tiếng Việt).

### 3.2 `M-MCP` (explore / details / categories / resolve / route)
| Tool | Trong `F-CHAT` | Trong `F-PLAN` | Khi gọi trực tiếp (`F-LOOKUP`) |
|---|---|---|---|
| `resolve_geographic_id` | model tự quyết khi nào gọi, từ khoá do model đặt; kết quả là **ứng viên** đưa vào prompt | mã gọi tất định cho city/district; bắt buộc khớp chính xác duy nhất; district lệch city bị loại; **source mode không gọi** | trả ứng viên, không tự chọn |
| `explore_pois` | args do model đề xuất, `M-GATE` dựng lại selector nguồn; `limit` theo model | mã tự scatter-gather theo category + floor query khi source mode; cap theo mã | AND các filter id; category khớp chính xác |
| `get_poi_details` | model gọi khi cần chi tiết | enrich song song **mọi** candidate, dựng evidence index; thiếu thì để unknown | trả chi tiết + parent context + NEAR_BY |
| `get_available_categories` | model gọi khi cần | bước 2 bắt buộc trước khi scatter | luôn `success=true` + list (có thể rỗng) |
| `get_itinerary_route` | model gọi khi cần chỉ đường | adapter gọi cho từng cặp có hướng trong pool candidate để lấy edge thật | ≥2 stop, mọi toạ độ phải resolve |

### 3.3 `M-GROUND`
- `F-CHAT`: parse envelope tool → tập `source_evidence_ids`; câu trả lời tự do bị dán nhãn `unverified_free_text`; không có bằng chứng ⇒ `insufficient_data`.
- `F-PLAN`: **tái dựng từng field** (tên, toạ độ, giờ, giá, địa chỉ, mô tả) từ evidence; thiếu thì ghi vào `missing_data`; scope của POI quyết định bằng `administrative_context` có cấu trúc, không bằng chuỗi địa chỉ.

### 3.4 `M-GATE`
- `F-CHAT`: chặn từng tool call ngay khi chạy — dựng lại đúng selection, từ chối selection khác, lọc lại evidence trước khi model thấy; áp cả `transport_mode`.
- `F-PLAN`: áp ở biên request và trong adapter (không gọi resolver ở source mode, mọi stop mang claim snapshot); model không có quyền đổi.
- `F-SCOPE`/`F-UI`: chỉ là dữ liệu chọn (snapshot + area), không có tool call.

### 3.5 `M-MEM-WORK`
- `F-CHAT`: compose lịch sử hội thoại đầy đủ (8 lượt), giữ tool messages đúng cặp; lease theo phiên; commit cả lượt.
- `F-PLAN`: giữ lease xuyên retrieval→synthesis→commit; chỉ commit một bản tóm tắt assistant; **không** dùng lịch sử làm bằng chứng lập lịch.
- `F-MEMORY`: `clear` phải chờ lease đang chạy rồi mới xoá.
- Đổi `source_scope` giữa phiên ⇒ `context_reset=true` ở cả `F-CHAT` và `F-PLAN`.

### 3.6 `M-MEM-PROFILE`
- `F-CHAT`: chỉ chèn profile khi ý định là `TRAVEL`.
- `F-PLAN`: chèn vào prompt tổng hợp, nhưng **không** được ghi đè ràng buộc có cấu trúc của request hiện tại.
- `F-MEMORY`: người dùng đọc/sửa/xoá trực tiếp; PUT lệch `expected_version` ⇒ 409.

### 3.7 `M-ROUTE` (GraphHopper)
- `F-PLAN`: mỗi cặp có hướng là một lần gọi thật; thiếu edge ⇒ `route_unknown`, **không** Haversine, **không** 0.
- `F-CHAT`: model có thể gọi để trả lời "đi thế nào"; lỗi ⇒ tool trả mã lỗi, câu trả lời phải nói không đủ.
- `F-LOOKUP`: trả `distance_km`/`time_minutes`/geometry thật; profile ngoài cấu hình ⇒ `invalid_request`.

---

## 4. Hợp đồng từng chức năng

### F-CHAT — Agent Chat

**Outcome:** người dùng gửi tin nhắn, nhận câu trả lời; hoặc được hỏi lại; hoặc được báo không đủ dữ liệu. Không bao giờ nhận câu trả lời trông có căn cứ nhưng không có bằng chứng.

**Cases**

| Case | Điều kiện | Expected outcome |
|---|---|---|
| C-CHAT-1 | Jev trả `ok` + `CHITCHAT` | trả lời hội thoại, `tool_chain=[]`, không gọi tool |
| C-CHAT-2 | Jev trả `ok` + `TRAVEL` | chạy ReAct qua MCP; trả `tool_chain`, `source_evidence_ids`, `grounding_status` |
| C-CHAT-3 | Jev `ambiguous`/`UNCERTAIN` | 200 `needs_clarification`, câu hỏi tiếng Việt, không side effect |
| C-CHAT-4 | Jev lỗi/không cấu hình | 503 `intent_unavailable`, không fallback |
| C-CHAT-5 | `transport_mode` ∉ {`car`,`foot`} đúng byte | 422 trước mọi side effect |
| C-CHAT-6 | `source_scope` sai định dạng | 422 `invalid_source_scope` |
| C-CHAT-7 | Model đề xuất selector nguồn khác request | server từ chối tool call đó |
| C-CHAT-8 | Tool không trả bằng chứng dùng được | `status=insufficient_data`, câu trả lời trung thực |
| C-CHAT-9 | Trả lời tự do có bằng chứng | `grounding_status=unverified_free_text` + evidence ids |
| C-CHAT-10 | `memory_enabled=false` | không tạo phiên, không đọc/ghi cả hai tầng |
| C-CHAT-11 | Vượt 5 lượt model hoặc 8 tool | dừng có `loop_limit`, không treo |

**Invariant:** `INV-CHAT-1` chỉ hai intent được thi hành; `INV-CHAT-2` scope nguồn và transport do server quyết; `INV-CHAT-3` không có bằng chứng thì không được trình bày như sự thật; `INV-CHAT-4` mọi lỗi trả mã, không trả stack.

**Ngoài phạm vi:** đặt vé/thanh toán; dữ liệu ngoài snapshot; đa ngôn ngữ ngoài tiếng Việt/Anh.

---

### F-PLAN — Itinerary Planning

**Outcome:** người dùng nhận lịch trình có thứ tự và giờ do thuật toán tính, kèm trạng thái khả thi do bộ kiểm định độc lập quyết, và danh sách field chưa xác minh.

**Cases**

| Case | Điều kiện | Expected outcome |
|---|---|---|
| C-PLAN-1 | Request đầy đủ, dữ liệu đủ | lịch có ≥1 stop/ngày, giờ tăng dần, `planning` + `validation` kèm theo |
| C-PLAN-2 | Thiếu `target_district` và không có `source_scope` | 422 ngay ở validate request |
| C-PLAN-3 | Budget explicit sai định dạng | fail validation **trước** khi gọi route |
| C-PLAN-4 | Không có tuyến giữa hai stop | stop đó bị loại kèm `route_unknown`, không bịa đường |
| C-PLAN-5 | Giờ mở cửa không parse được | `hours_known=false`, không đoán |
| C-PLAN-6 | Giá menu/offer của POI | không thành chi phí tham quan; cost = unknown |
| C-PLAN-7 | Heuristic không xếp được lịch | `no_plan` + lý do; nội dung không được nói "bất khả thi về mặt toán học" |
| C-PLAN-8 | Model bịa tên/giờ/giá | bị thay bằng evidence hoặc bị loại |
| C-PLAN-9 | Source mode | không resolve hành chính; mọi stop mang claim snapshot; evidence lệch scope bị loại |

**Invariant:** `INV-PLAN-1` mọi field thực tế đến từ evidence; `INV-PLAN-2` thời gian/chi phí do scheduler tính lại, không tin model; `INV-PLAN-3` thiếu dữ liệu vẫn là unknown trong output; `INV-PLAN-4` lịch rỗng không bao giờ feasible.

**Ngoài phạm vi:** giá vé thật, đặt chỗ, giao thông công cộng nhiều chặng, tối ưu toàn cục.

---

### F-LOOKUP — POI & Route Lookup

**Outcome:** bất kỳ agent nào cũng lấy được dữ liệu POI/tuyến có mã lỗi rõ ràng, không nhận dữ liệu bịa và không nhận lỗi thô của provider.

**Cases:** `explore_pois` với nhiều filter ⇒ AND; category sai ⇒ rỗng, không thay bằng tên hiển thị; `source_discovery` không trộn được với filter hành chính; `get_itinerary_route` thiếu 1 toạ độ ⇒ `stops_unresolved` toàn bộ; profile không hỗ trợ ⇒ `invalid_request`; provider 4xx/5xx ⇒ `route_failed` + `upstream_status`; không có path ⇒ `no_route`.

**Invariant:** `INV-LOOKUP-1` không fallback đường thẳng; `INV-LOOKUP-2` không echo message provider; `INV-LOOKUP-3` thiếu dữ liệu thì để trống/unknown, kèm mã; `INV-LOOKUP-4` tool không tự chọn địa danh khi có nhiều ứng viên.

**Ngoài phạm vi:** tìm kiếm mờ theo tên tự do quy mô lớn; xếp hạng theo cá nhân hoá.

---

### F-MEMORY — Preference & Session Memory

**Outcome:** người dùng kiểm soát được dữ liệu cá nhân: xem, sửa, xoá hồ sơ; xoá ngữ cảnh phiên. Hồ sơ chỉ ảnh hưởng khi được bật và chỉ khi có chủ thể đã xác thực.

**Cases:** GET khi chưa có ⇒ `profile=null`; PUT không hợp lệ ⇒ 422 kèm danh sách lỗi; PUT lệch version ⇒ 409 + `current_version`; DELETE ⇒ `deleted` true/false; `short/clear` ⇒ `cleared` + scope; thiếu bearer ⇒ `anonymous_local_only`, không tạo hồ sơ; durable memory tắt ⇒ 503 khi gọi `/memory/profile`.

**Invariant:** `INV-MEM-1` chủ sở hữu là `sub` đã xác thực, không phải `session_id`/`user_id` client; `INV-MEM-2` không có tệp hồ sơ mặc định; `INV-MEM-3` sở thích đã lưu không ghi đè ràng buộc hiện tại; `INV-MEM-4` xoá phiên không xoá hồ sơ và ngược lại.

**Ngoài phạm vi:** đồng bộ đa thiết bị, hồ sơ do hệ thống tự suy ra.

---

### F-SAVED — Saved Itinerary

**Outcome:** người dùng đã đăng nhập lưu lại lịch trình đã sinh và mở lại sau; không thấy dữ liệu của người khác.

**Cases:** POST ⇒ 201 + `id` do server sinh; GET list ⇒ phân trang có bound; GET/DELETE id của người khác ⇒ 404; id sai định dạng ⇒ 404; storage chưa cấu hình ⇒ 503; JSON quá sâu ⇒ 422; `/ready` ⇒ 503 khi storage hỏng.

**Invariant:** `INV-SAVED-1` payload lưu nguyên văn, không chạy lại, không tự xác nhận khả thi; `INV-SAVED-2` lọc owner ở tầng lưu trữ; `INV-SAVED-3` startup fail-closed nếu DB có sẵn nhưng không hợp lệ.

**Ngoài phạm vi:** chia sẻ công khai, phiên bản hoá nội dung, cộng tác nhiều người.

---

### F-INGEST — Graph Ingestion & Spatial Ops

**Outcome:** người vận hành nạp được lô POI và biết chính xác cái gì đã ghi, cái gì lỗi; tạo được một POI; dựng lại NEAR_BY có báo cáo thật.

**Cases:** ≤10 bản ghi ⇒ 202 + terminal ngay; >10 ⇒ 202 + nền; sai schema ⇒ 422; DB lỗi ⇒ 503; broadcaster đầy ⇒ 503 trước khi ghi; SSE job lạ ⇒ 404; SSE kết nối muộn ⇒ replay gồm terminal; tạo POI lẻ ⇒ 201/422/409; rebuild ≤200 quận ⇒ 200/207/502.

**Invariant:** `INV-INGEST-1` không báo thành công khi canary fail; `INV-INGEST-2` lỗi sanitize, không traceback (trừ điểm Q3 bên dưới); `INV-INGEST-3` ID client giữ nguyên, toạ độ kiểm; `INV-INGEST-4` thay cạnh NEAR_BY trong cùng transaction khi sửa một POI.

**Ngoài phạm vi:** idempotency nhiều worker, migration taxonomy trực tiếp trên đồ thị thật.

---

### F-ACQUIRE — Data Acquisition

**Outcome:** người vận hành chạy được pipeline offline để biến nguồn thành ứng viên POI + quyết định có thể kiểm lại, biết ngay cái gì bị loại và vì sao.

**Cases:** GeoJSON hợp lệ ⇒ prepared + lineage; trùng byte ⇒ gộp + ledger; identity xung đột ⇒ fail closed; mapping thiếu review entity ⇒ từ chối; dataset thật và synthetic ⇒ state tách biệt; capture thiếu/khác hash ⇒ từ chối; không truyền `--fetch` ⇒ không chạm mạng; nạp thử ⇒ `imported=0`.

**Invariant:** `INV-ACQ-1` dữ liệu nguồn bất biến + hash; `INV-ACQ-2` không có đường nào ghi thẳng vào graph; `INV-ACQ-3` không tự tạo lineage OSM khi nguồn không có; `INV-ACQ-4` synthetic không lẫn vào accepted thật.

**Ngoài phạm vi:** fetch live hàng loạt, vượt cơ chế chống bot, import tự động.

---

### F-SCOPE — Source Scope & Catalog

**Outcome:** người dùng thấy được các snapshot/area và chọn một vùng; mọi kết quả trong phiên bị giới hạn đúng vùng đó, hoặc hệ thống báo không đủ dữ liệu trong vùng.

**Cases:** không có snapshot ⇒ `status="empty"`; discovery lỗi ⇒ 502; `dataset_namespace` có khoảng trắng ⇒ 422; `input_sha256` sai dạng ⇒ 422; echo snapshot khác request ⇒ 502 `catalog_contract_mismatch`; chọn `source_area_ids` nhiều vùng ⇒ canonical sort, loại trùng, từ chối sentinel toàn cục.

**Invariant:** `INV-SCOPE-1` nhãn vùng là nhãn dataset của snapshot, **không** phải địa giới hành chính hiện tại; `INV-SCOPE-2` model không được mở rộng/thay selection; `INV-SCOPE-3` source mode và current-admin mode loại trừ nhau.

**Ngoài phạm vi:** biên tập dữ liệu nguồn từ UI, chọn nhiều snapshot cùng lúc.

---

### F-UI — Demo Web Experience

**Outcome:** một trang mở được, chọn nguồn, chat, nhập yêu cầu, xem stop trên bản đồ và danh sách "chưa xác minh".

**Cases:** thiếu `travel.html` ⇒ 404 `ui_not_installed`; chat khi chưa chọn nguồn ⇒ chế độ hiện tại; chọn snapshot ⇒ nút vùng bật; plan trả về ⇒ render stop + unknown; lỗi ⇒ hiển thị thông điệp, không treo.

**Invariant:** `INV-UI-1` UI không tự gọi model; `INV-UI-2` nhãn vùng không bị đổi thành "quận hiện tại"; `INV-UI-3` stop thiếu dữ liệu phải hiện trong danh sách unknown.

**Trạng thái:** `PARTIAL` theo `ACCEPTANCE_TRACKER` (B130 render đạt; B131 live chat đạt phần chat/typed; pin/popup live timeout; B133 fixture click đạt riêng).

---

### F-OPS — Service Operations

**Outcome:** người vận hành phân biệt được "sống", "sẵn sàng", "storage hỏng", và biết model/provider nào đang phục vụ.

**Cases:** `/healthz` ⇒ ok; `/` POI ⇒ trạng thái + dependency; `/health` backend ⇒ 200 + trạng thái repository; `/ready` ⇒ 503 khi storage không available; provider lỗi ⇒ mã lỗi; không có số token ⇒ `usage` để `None`.

**Invariant:** `INV-OPS-1` health không che readiness; `INV-OPS-2` không chuyển provider ngầm; `INV-OPS-3` mỗi phản hồi mang `model`+`provider`.

---

## 5. Câu hỏi mở

| ID | Vấn đề | Ảnh hưởng | Trạng thái |
|---|---|---|---|
| Q1 | Danh mục F-CHAT…F-OPS (10 chức năng) có đúng tập cần xác thực? | Quyết định toàn bộ phần đào sâu module phía sau | `APPROVAL_NEEDED` |
| Q2 | Behavior từng chức năng có đúng ý định sản phẩm? | Chưa freeze, chưa code | `APPROVAL_NEEDED` |
| Q3 | `GET /pois/{poi_id}` trả `traceback` trong body khi 500 | Rò rỉ nội bộ, trái chuẩn sanitize; sửa là đổi interface của `F-LOOKUP` | `APPROVAL_NEEDED` |
| Q4 | POI_service nhận JWT **không có `exp`**; ai/backend bắt buộc `exp`+`sub` | Ba hợp đồng xác thực khác nhau trên cùng hệ; ảnh hưởng `F-INGEST`, `F-LOOKUP`, `F-MEMORY` | `APPROVAL_NEEDED` |
| Q5 | CORS `allow_origins=["*"]` + `allow_credentials=True` | Trình duyệt từ chối; không an toàn cho API có JWT; ảnh hưởng `F-UI` → `F-LOOKUP` | `APPROVAL_NEEDED` |
| Q6 | `F-UI` đang `PARTIAL` (pin/popup live chưa xác nhận) | Ảnh hưởng phạm vi "demo chạy được" của luồng lõi | `NOT VERIFIED` |

---

## 6. Freeze và cổng

- **Đã freeze:** không có. `0.2` là DRAFT.
- **Chuyển một chức năng sang `APPROVED`:** chủ dự án xác nhận outcome + cases + invariant của chức năng đó, và trả lời Q3–Q5 nếu chức năng bị ảnh hưởng.
- **Đào sâu cấp module:** sau khi danh mục L0 được chốt, mỗi chức năng sẽ có bảng module × hành vi × lỗi × invariant riêng, thay vì mô tả module một lần cho tất cả.
- **Commit gate:** chưa commit gì; repo đang có 37 tệp modified + 34 untracked của người dùng — không đụng.

## 7. UAT/regression link

| UAT case | Người xác nhận | Regression test |
|---|---|---|
| Ghi dần khi từng chức năng được duyệt | chủ dự án | `<chưa có / trỏ tests/<nhóm>>` |

Bản đồ test hiện có: 164 tệp `test_*.py` trong 31 nhóm dưới `tests/`. Chưa chạy nhóm nào trong phiên này (`NOT VERIFIED`).
