# RED baseline — Agent Chat MVP tests (2026-10-22)

- **Lệnh chạy:** `uv run --with pytest python -m pytest tests/ai_chat_mvp -q --tb=line`
- **Kết quả bộ 120 (trước khi tách):** 116 failed, 4 passed (2,40 s).
- **Kết quả sau khi tách hai bộ:**
  - `--evaluate` (20 test đặc tả): **20 failed, 0 passed** (1,34 s)
  - `--test` (100 test ẩn): **96 failed, 4 passed** (1,96 s)
- **Ý nghĩa:** đây là baseline RED hợp lệ. Test được viết từ hợp đồng `FT-CHAT-MVP-001`, không từ mã hiện tại; đỏ nghĩa là chức năng chưa đạt hợp đồng.
- **Môi trường:** 20 + 100 = 120, cả hai bộ đều phủ đủ 9 điều khoản B1–B7, G1, G2 (kiểm tự động bởi `tests/chat_test_coverage.py`).

## Bốn test xanh và vì sao chúng hợp lệ

| Test | Đo cái gì | Vì sao xanh là thật |
|---|---|---|
| `D10_product_code_has_no_test_infrastructure_reference` | quét `ai_service/` tìm `pytest`, `PYTEST_CURRENT_TEST`, import từ `tests/`, `unittest.mock` | Mã sản phẩm hiện **không** tham chiếu hạ tầng test. Đây là kết quả thật, và là điều cần giữ |
| `D7_oversized_session_id_is_rejected` | `session_id` 201 ký tự | Validate sẵn có trả 422; hành vi đã đúng hợp đồng |
| `D7_whitespace_only_message_asks_for_content` | message chỉ khoảng trắng | Model trả nội dung rỗng ⇒ lượt bị đánh `failed`, không có câu trả lời tự tin |
| `D9_session_metadata_reports_the_scope` | `memory.enabled` + `memory.scope` | Hệ thống thật sự báo scope của phiên |

Bốn case này không phải "pass rỗng": chúng đo hành vi đã tồn tại và đúng. Mười bảy case khác từng xanh ở lượt chạy trước đã bị siết lại vì xanh vì lý do sai (chỉ kiểm sự vắng mặt của thứ chưa tồn tại, hoặc so hai kết quả cùng rỗng).

## Vì sao 116 case còn lại đỏ

| Nhóm | Case | Lý do đỏ (nguyên văn từ assertion) | Điều được chứng minh |
|---|---|---|---|
| Thiếu bề mặt dữ liệu | B1 ×3 | `response has no 'claims' field` | Không có bước trích claim; phản hồi chỉ có `reply`/`intent`/`tool_chain` |
| Gate chặn intent mới | B2 ×3, B4 ×4, B5 ×4, B6 ×3, B7 ×3, G-P | `the turn was rejected ... intent_unavailable` | Hệ thống không có `BOOKING` lẫn `PLAN`; intent lạ bị coi là "dịch vụ phân loại không khả dụng" |
| Không truy xuất khi hỏi thông tin | B3-D, B3-K, B3-E1 | `an answer about a POI must be backed by a retrieved record, got evidence=[]` | `CHITCHAT` trả lời thẳng bằng model, **không** gọi MCP dù câu hỏi về một POI |
| Văn bản model đi thẳng tới người dùng | B3-P, B3-E2 | `got reply='quán betta fish rẻ nhất quận 1 và có chỗ đậu ô tô.'` và `got reply='quán cà phê bóng đêm mở cửa 08:00-23:00.'` | Model bịa giá, bãi xe, và bịa giờ cho một quán **không tồn tại**; hệ thống chuyển nguyên văn |
| Thiếu nhật ký hành động | G-D, G-K | `response has no 'actions' field` | Không quan sát được feature handler nào được gọi |

**18 trong 28 case dừng ở cùng một cửa**: intent `BOOKING`/`PLAN` bị từ chối trước khi bất kỳ hành vi nào chạy. Đây là thông tin xếp thứ tự quan trọng — mở intent ra sẽ làm bản đồ đỏ chi tiết hơn ở 18 case đó.

## Ba lỗi thật, không phải lỗi giả lập

1. **Hỏi về địa điểm không truy xuất gì cả.** `CHITCHAT` đi thẳng vào model; chỉ `TRAVEL` mới mở MCP. Hợp đồng B3 nói ngược lại: mọi câu hỏi về địa điểm phải truy xuất trước.
2. **Văn bản model không bị kiểm.** Bằng chứng tại B3-E2: một quán không tồn tại trong 6367 bản ghi vẫn được trả lời kèm giờ mở cửa `08:00-23:00` do model tự đặt. Đây đúng là lỗi mà hợp đồng G2 cấm, và trước hôm nay chưa có phép đo nào bắt được nó.
3. **Không có khái niệm BOOKING.** Không chỉ thiếu field: toàn bộ intent bị gate từ chối trước khi bất kỳ hành vi nào xảy ra.

## Điều baseline này **không** chứng minh

- Không nói gì về `TRAVEL`/`F-CHAT` cũ có đúng hay không — đó là hợp đồng đã bị thay thế.
- Không chứng minh B5–B7 sai ở tầng sâu: 10 case đó hiện dừng ở cùng một cửa (intent `PLAN` bị từ chối), nên form/phương án/handoff chưa được đo tới.
- Không chứng minh test cắn: phép đột biến M-B3-1/2 chỉ có nghĩa sau khi case tương ứng chuyển xanh.
- Không đánh giá chất lượng model thật; model trong test là fake cố định.

## Bước tiếp theo

1. Mở intent `BOOKING`/`PLAN` ở tầng phân loại và gate — 18 case sẽ đi qua cửa này, bản đồ đỏ chia nhỏ theo từng hành vi thật.
2. Thêm bề mặt `claims[]` và `actions[]` — 5 case chuyển sang đo hành vi thay vì đo field.
3. Buộc `CHITCHAT` truy xuất trước khi trả lời, và chặn văn bản model chứa dữ kiện không có trong evidence — 5 case B3.
4. Mỗi khối: chuyển test xanh → chạy đột biến → ghi tên test fail → hoàn nguyên.
