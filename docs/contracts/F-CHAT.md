# Hợp đồng chức năng F-CHAT — Agent Chat

- **ID:** `FT-CHAT-001` · **Version:** `0.2` · **Status:** `SUPERSEDED (phần intent)` — mô tả **mã hiện tại**, không còn là contract đích
- **Quan hệ:** định nghĩa intent `CHITCHAT`/`TRAVEL`/`UNCERTAIN` trong tệp này đã bị `F-CHAT_MVP_CONTRACT.md` (v1.0, APPROVED) thay bằng `CHITCHAT`/`BOOKING`/`PLAN`. Tệp này giữ lại như **mô tả hành vi mã đang chạy** và làm bằng chứng cho bản đồ đỏ trong `F-CHAT_MVP_TEST_PLAN.md` §5.
- **Thuộc:** `FT-SET-TVLT-002` · **Ngày:** 2026-10-22
- **Bề mặt:** `POST /chat` (bearer tuỳ chọn), khung chat trong `GET /travel`
- **Actor:** du khách
- **Người soạn:** Hermes, đọc mã; **chưa chạy** request/test nào trong phiên này
- **0.2 bổ sung:** 44 case chia 8 nhóm, 8 luồng end-to-end, 2 phát hiện mới (D-CHAT-4, D-CHAT-5)

---

## 1. Outcome

Người dùng gõ một câu hỏi. Hệ thống quyết định đó là trò chuyện hay cần dữ liệu, rồi trả lời hội thoại hoặc tra đồ thị POI và trả lời kèm bằng chứng. Không đủ dữ liệu thì phải nói không đủ.

Sáu kết cục quan sát được: `success`, `partial`, `failed`, `insufficient_data`, `needs_clarification` (HTTP 200), `unavailable` (HTTP 503).

---

## 2. Thứ tự thực thi (`ai_service/main.py:2265-2407`)

| # | Bước | Module | Sai thì |
|---|---|---|---|
| 1 | Kiểm `source_scope` | `M-GATE` | 422 `invalid_source_scope` |
| 2 | Kiểm `transport_mode` | `M-GATE` | 422 `invalid_transport_mode` |
| 3 | Xác thực bearer nếu có | `M-MEM-PROFILE` | 401 / 503 `auth_not_configured` |
| 4 | Phân loại ý định | `M-INTENT` | 200 clarify / 503 `intent_unavailable` |
| 5 | Đọc hồ sơ (TRAVEL + subject + memory) | `M-MEM-PROFILE` | 503 `memory_store_unavailable` |
| 6 | Lease + compose prompt | `M-MEM-WORK` | 503 `memory_capacity` |
| 7 | Thi hành | `M-REACT`/`M-MCP`/`M-GATE`/`M-GROUND` | HTTP 200 + `status` |
| 8 | Commit + dựng response | `M-MEM-WORK` | — |

Bước 1–4 chạy trước mọi side effect: request sai hoặc không phân loại được không tạo phiên, không đọc hồ sơ, không gọi tool.

---

## 3. Hành vi module

### 3.1 `M-GATE`
- Chỉ áp cho `TRAVEL`. `CHITCHAT` không nhận hướng dẫn nguồn, không nhận profile.
- `transport_mode` phải đúng byte `car`/`foot`; sai → 422 (không trim, không đổi hoa thường, không ép kiểu).
- `transport_mode_source` = `explicit`/`default`.
- Source mode: server tự chạy **một** `explore_pois` với đúng tuple, `limit=6`, **trước** lượt model đầu.
- Mỗi tool call của model qua `ScopeGate.prepare`; selector khác request → **tool call bị từ chối**, không tự sửa.
- Kết quả qua `filter_result`: chỉ bản ghi đúng vùng tới được model/trace/memory.

### 3.2 `M-INTENT` (Jev)
- Phân loại một tin nhắn hiện tại; ba nhãn `CHITCHAT`/`TRAVEL`/`UNCERTAIN`; chỉ hai nhãn đầu thi hành.
- Ngưỡng tin cậy không có mặc định; thiếu cấu hình → 503.
- Tie / `UNCERTAIN` / confidence dưới ngưỡng → `ambiguous` → 200 clarify.
- Lỗi mạng/HTTP/schema/hết retry → `unavailable`/`malformed` → 503.
- Retry có giới hạn (số lần + deadline + backoff ceiling).
- Không fallback provider khác (đã chốt trong `FOUR_PHASE_PLAN.md`).

### 3.3 `M-MEM-WORK`
- Khoá phiên = SHA-256 của tuple `(scope_kind, subject, session_id)`; không va chạm chuỗi.
- 8 lượt hoàn tất/phiên; 128 phiên; TTL 1800 giây.
- Tóm tắt trích xuất chỉ từ tin nhắn USER cũ (≤20 dòng × 240 ký tự).
- Lease tuần tự hoá request cùng phiên; release khi refcount = 0.
- Đổi scope nguồn → `context_reset=true`.
- `memory_enabled=false` → không tạo phiên, không đọc/ghi.

### 3.4 `M-MEM-PROFILE`
- Chèn khi `TRAVEL` + subject đã xác thực + `memory_enabled` + store cấu hình; ≤800 ký tự.
- Sở thích đã lưu không ghi đè ràng buộc hiện tại.
- Header vắng hẳn → anonymous; header có nhưng hỏng → 401, không hạ cấp.

### 3.5 `M-REACT` + `M-MCP` + `M-GROUND`

| Quy tắc | Giá trị | Khi chạm |
|---|---|---|
| Lượt model | 5 | `partial` + `loop_limit=true` + thông điệp giới hạn |
| Lượt tool | 8 | như trên |
| Bootstrap nguồn | 6 tool call, **tính vào ngân sách 8** | model còn 2 lượt tool |
| Bootstrap 0 evidence | — | `insufficient_data`, **không gọi model** |
| Tool lạ | — | `rejected_tool`, không thực thi |
| Args không parse được | — | `malformed_arguments` |
| Tool call vượt ngân sách | — | cắt bớt trước khi lưu, `loop_limit=true` |
| Envelope lỗi | — | chỉ mã server-owned, không echo upstream |
| Không có POI evidence | — | `insufficient_data`, không trả lời tự do |
| Trả lời tự do có evidence | — | `unverified_free_text` |

---

## 4. Cases

### A. Biên request (kiểm trước mọi side effect)

| ID | Input | Expected |
|---|---|---|
| C-A01 | `session_id` dài 200 | hợp lệ |
| C-A02 | `session_id` dài 201 hoặc rỗng | 422 |
| C-A03 | `message` rỗng | 422 |
| C-A04 | `message` dài 8000 | hợp lệ |
| C-A05 | `message` dài 8001 | 422 |
| C-A06 | `message` chỉ khoảng trắng | **qua validation** (không strip) → đi tới Jev; thường rơi vào clarify |
| C-A07 | body có field lạ | bị bỏ qua, request vẫn xử lý |
| C-A08 | `transport_mode=null`/`"Car"`/`" car"` | 422 |
| C-A09 | `source_scope` thiếu `input_sha256` | 422 |
| C-A10 | `source_scope` có cả `source_area_id` và `source_area_ids` | 422 |

### B. Xác thực

| ID | Điều kiện | Expected |
|---|---|---|
| C-B01 | Không header Authorization | anonymous, 200 |
| C-B02 | Bearer hợp lệ, có `sub`+`exp` | chủ thể đã xác thực |
| C-B03 | Token hết hạn | 401 `token_expired` |
| C-B04 | Chữ ký sai | 401 `invalid_token` |
| C-B05 | `Basic xyz` hoặc `Bearer` trần | 401 |
| C-B06 | Token thiếu `sub` | 401 `invalid_subject` |
| C-B07 | `JWT_SECRET` không cấu hình | 503 `auth_not_configured` |

### C. Phân loại ý định

| ID | Jev trả | Expected |
|---|---|---|
| C-C01 | `ok` + `CHITCHAT` | dispatch chitchat |
| C-C02 | `ok` + `TRAVEL` | dispatch travel |
| C-C03 | `ok` + `UNCERTAIN` | 200 `needs_clarification` |
| C-C04 | tie xác suất | 200 clarify, `router.error_code=probability_tie` |
| C-C05 | confidence **bằng** ngưỡng | `ok` (điều kiện là `<`) |
| C-C06 | confidence dưới ngưỡng | 200 clarify |
| C-C07 | HTTP 429 có `Retry-After` | retry trong giới hạn; hết budget → 503 |
| C-C08 | HTTP 401 | không retry → 503 |
| C-C09 | Schema response sai | `malformed` → 503 |
| C-C10 | Thiếu key/ngưỡng | `unconfigured` → 503 |
| C-C11 | Message vượt giới hạn Jev | 503, `router.attempts` ghi `input_too_long` |

### D. Bộ nhớ

| ID | Điều kiện | Expected |
|---|---|---|
| C-D01 | anonymous + `memory_enabled=true` | phiên theo `session_id`, `scope=anonymous_local_only` |
| C-D02 | subject + có hồ sơ + `TRAVEL` | `profile_injected=true` |
| C-D03 | subject + có hồ sơ + `CHITCHAT` | profile **không** chèn |
| C-D04 | `memory_enabled=false` | không tạo phiên; lượt 2 không thấy lượt 1 |
| C-D05 | 129 phiên đang mở | 503 `memory_capacity` |
| C-D06 | Chờ quá TTL 1800s | lượt sau là phiên mới, mất lịch sử |
| C-D07 | Đổi `source_scope` giữa phiên | `context_reset=true`, không kế thừa evidence |
| C-D08 | `short/clear` khi request cùng phiên đang chạy | chờ lease, clear sau, response cũ không repopulate |
| C-D09 | Lượt thứ 9 | lượt 1 bị đẩy, summary có dòng `- ...`, `discarded_turns=1` |
| C-D10 | Hai request cùng `session_id` | chạy tuần tự, không chồng |

### E. Source mode

| ID | Điều kiện | Expected |
|---|---|---|
| C-E01 | Không `source_scope` | chế độ hiện tại, resolver hành chính như cũ |
| C-E02 | `source_scope` một area | bootstrap 6 bản ghi trước model; `bootstrap.origin=server_bootstrap` |
| C-E03 | `source_area_ids` nhiều vùng | canonical sort, loại trùng, không sentinel toàn cục |
| C-E04 | Bootstrap trả 0 POI | `insufficient_data`, **không gọi model** |
| C-E05 | Model gửi selector khác | tool call bị từ chối, `tool_chain` ghi mã rejection |
| C-E06 | Model gọi `get_itinerary_route` với POI ngoài vùng | evidence bị lọc trước khi tới model |
| C-E07 | Đổi vùng giữa phiên | reset ngữ cảnh như C-D07 |
| C-E08 | `source_scope` + Jev `CHITCHAT` | không bootstrap, không hướng dẫn nguồn, trả lời hội thoại |
| C-E09 | Bootstrap chạy xong | model còn **2** lượt tool (6/8 đã dùng) |

### F. Vòng lặp tool

| ID | Điều kiện | Expected |
|---|---|---|
| C-F01 | Model trả lời ngay, không gọi tool, không evidence | `insufficient_data` (không dùng câu trả lời tự do) |
| C-F02 | Gọi 1 tool trả POI, model trả văn xuôi | `success` + `unverified_free_text` + evidence ids |
| C-F03 | Tool thành công nhưng không trả POI (vd categories) | ghi `no_poi_evidence`, không tính evidence |
| C-F04 | Tool envelope lỗi | `tool_error`/`tool_protocol_error`, không echo upstream |
| C-F05 | Model gọi tool không tồn tại | `rejected_tool`, không thực thi |
| C-F06 | Args không phải JSON object | `malformed_arguments` |
| C-F07 | 9 tool call trong một lượt | cắt còn ngân sách, `loop_limit=true`, `partial` |
| C-F08 | 5 lượt đều gọi tool | `partial` + thông điệp giới hạn |
| C-F09 | Model lỗi ở lượt 2 **sau khi có evidence** | `partial`, `reply=null`, `grounding_status=unverified_free_text` |
| C-F10 | Model lỗi, chưa có evidence | `failed`, `reply=null` |
| C-F11 | MCP không mở được session | `failed` + `agent_unavailable` |

### G. Hợp đồng response

| ID | Điều kiện | Expected |
|---|---|---|
| C-G01 | Nhiều evidence trùng | `source_evidence_ids` sắp xếp, không trùng |
| C-G02 | CHITCHAT | không có `grounding_status`/`source_evidence_ids` (chỉ thêm khi khác null) |
| C-G03 | Provider không trả usage | token `null`, không ước lượng |
| C-G04 | Mọi trace | không chứa `authorization`/`bearer`/`api_key`/`token` |
| C-G05 | `reply=null` | UI hiện "Trợ lý chưa trả lời nội dung nào." kèm meta trạng thái |

### H. Tương tác UI

| ID | Response | UI |
|---|---|---|
| C-H01 | `status=failed` | cảnh báo "Chưa tạo được câu trả lời." |
| C-H02 | `needs_clarification` | cảnh báo "Cần làm rõ thêm yêu cầu." |
| C-H03 | `status=success` | "Đã có trả lời. Có thể hỏi tiếp hoặc tạo lịch trình." |
| C-H04 | 401/422/503 | `requestJson` ném lỗi → hiện khối lỗi, không thêm bubble giả |

---

## 5. Luồng end-to-end

**L1 — Khách ẩn danh, hai lượt.** "Xin chào" → Jev CHITCHAT → 200 success, `tool_chain=[]`. Sau đó "Quán cà phê ở Quận 1" → Jev TRAVEL → tool → 200 success/partial. Lượt 2 thấy lượt 1 trong ngữ cảnh (`scope=anonymous_local_only`).

**L2 — Khách có hồ sơ.** Bearer hợp lệ, hồ sơ có `pace=relaxed` → hỏi gợi ý → `profile_injected=true`; sửa hồ sơ qua `PUT /memory/profile` → lượt sau phản ánh hồ sơ mới; xoá hồ sơ → `profile_injected=false`.

**L3 — Chọn vùng dữ liệu.** Chọn snapshot + area → hỏi trong vùng → bootstrap 6 POI, câu trả lời chỉ dùng POI trong vùng. Hỏi địa điểm ngoài vùng → evidence rỗng → `insufficient_data`, không bịa.

**L4 — Đổi vùng giữa phiên.** Lượt 1 vùng A → lượt 2 vùng B → `memory.context_reset=true`, không kế thừa POI vùng A.

**L5 — Câu mơ hồ.** "Tư vấn cho tôi" → Jev UNCERTAIN → clarify; người dùng nói rõ → TRAVEL → xử lý bình thường.

**L6 — Jev sập.** Jev 500 hai lần → 503 `intent_unavailable`; UI hiện lỗi; người dùng thử lại sau. Không có câu trả lời thay thế, không gọi model.

**L7 — Tool lỗi giữa lượt.** TRAVEL → `explore_pois` lỗi → model được báo lỗi → nếu không có evidence khác → `insufficient_data` + câu nói không đủ dữ liệu.

**L8 — Hai tab cùng phiên.** Hai request cùng `session_id` gửi gần nhau → request sau chờ lease; kết quả không trộn tool message giữa hai lượt.

---

## 6. Invariant

- `INV-CHAT-1` Chỉ `CHITCHAT`/`TRAVEL` được thi hành.
- `INV-CHAT-2` Selection nguồn và transport do server quyết.
- `INV-CHAT-3` Không evidence ⇒ không trình bày như sự thật.
- `INV-CHAT-4` Lỗi trả mã ổn định, không stack, không secret.
- `INV-CHAT-5` Request sai định dạng không tạo side effect.
- `INV-CHAT-6` Token hết hạn không bị hạ cấp thành anonymous.
- `INV-CHAT-7` Bootstrap của server không bao giờ được ghi như tool call của model (`origin=server_bootstrap`).

---

## 7. Điểm chưa thống nhất

| ID | Hiện trạng | Vì sao cần quyết |
|---|---|---|
| D-CHAT-1 | Thông điệp hệ thống lẫn ngôn ngữ: clarify/unavailable tiếng Việt; fallback/insufficient/loop-limit/model-unavailable tiếng Anh; UI tiếng Việt | Người dùng thấy hai ngôn ngữ trong một khung chat |
| D-CHAT-2 | Lượt TRAVEL thất bại vẫn HTTP 200 + `status=failed` | Đã khớp cách UI đọc `body.status`; coi là chốt nếu anh xác nhận |
| D-CHAT-3 | Token hết hạn ⇒ 401 | An toàn hơn nhưng chặn người dùng có token cũ |
| D-CHAT-4 | `partial` khi model lỗi **sau khi đã có evidence** trả `reply=null` dù đã có dữ liệu | UI hiện "Trợ lý chưa trả lời nội dung nào" — mất giá trị của evidence đã lấy được |
| D-CHAT-5 | Source mode: bootstrap 6 tool call chiếm 6/8 ngân sách, model chỉ còn 2 | Với câu hỏi cần nhiều bước, hệ thống có thể chạm giới hạn sớm hơn chế độ thường |

---

## 8. Ngoài phạm vi

Đặt vé/thanh toán; dữ liệu ngoài snapshot; ngôn ngữ ngoài Việt/Anh; streaming từng token; rate limit/spam ở tầng AI.

## 9. Bằng chứng đã đọc

`ai_service/main.py:2128-2407`, `:279`, `:366`, `:513`; `ai_service/domains/chat_agent.py:34-58`, `:256-601`; `ai_service/domains/jev_intent.py:76-941`; `ai_service/domains/source_gate.py`; `ai_service/domains/memory.py:37-316`; `ai_service/domains/memory_auth.py:66-125`; `ai_service/domains/payloads.py:179-199`; `ai_service/static/travel.html:1495-1560`.

Chưa chạy: không request, không test, không gọi Jev/Gemini/MCP (`NOT VERIFIED` về runtime).
