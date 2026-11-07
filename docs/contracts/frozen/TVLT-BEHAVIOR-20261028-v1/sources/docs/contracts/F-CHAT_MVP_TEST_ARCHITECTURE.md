# Kiến trúc bộ test Agent Chat MVP — 120 test, hai tầng

- **ID:** `TA-CHAT-001` · **Version:** `1.0` · **Status:** `APPROVED` — chủ dự án duyệt ngày 28/10/2026 qua biên nhận `receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb`, mục `TEST-GATE`.
- **Ngày:** 2026-10-22 · **Dựa trên:** `FT-CHAT-MVP-001` (contract đã duyệt) và `TP-CHAT-001` v0.3 (28 case hành vi)
- **Mục tiêu:** 20 test đặc tả + 100 test chống tối ưu-vì-test. Tổng **120**.
- **Vấn đề gốc cần chặn:** agent đọc test rồi làm hệ thống trả đúng chuỗi mà test mong đợi, thay vì xây hành vi đúng.

---

## Quyết định hiện hành — 28/10/2026

- Chủ dự án chọn **“Duyệt kiến trúc và cổng nghiệm thu”**, không có ghi chú sửa đổi, trên snapshot `TVLT-BEHAVIOR-REVIEW-20261028-v2`.
- Giữ cổng nghiệm thu: 20/20 test đặc tả; 100/100 test QA giữ riêng; kiểm tĩnh sạch; mỗi họ D1–D10 có mutation proof ghi tên test đỏ rồi hoàn nguyên. Không sửa kỳ vọng để lấy xanh; thay behavior phải qua change request.
- Test Booking phải phản ánh contract đã duyệt ngày 27/10: query đúng loại dịch vụ, người dùng bấm **Book Ngay** để chuyển screen booking; lệnh đặt ra dịch vụ khác là fake. Việc bàn giao sang screen và việc gửi lệnh đặt chỗ là hai bước khác nhau; không dùng tên `booking.create` để khẳng định đã đặt thật.
- Đây là phê duyệt thiết kế kiểm thử offline, không phải kết quả 120 test đạt hoặc chứng minh model/booking thật. RED baseline ngày 22/10 vẫn là bằng chứng lịch sử, không được nâng thành PASS từ quyết định này.
- Những dòng `PROPOSAL`, `chưa thực hiện` hoặc đường dẫn trước khi tách bộ test ở các phần lịch sử bên dưới không phải trạng thái phê duyệt hiện tại. Phần **Đã hiện thực — hai bộ tách rời** mô tả tổ chức bộ test đã ghi nhận; chưa kiểm lại kết quả chạy trong đợt áp dụng biên nhận này.
- Biên nhận gốc: [receipt](review-20261027/receipts/receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb.json). Báo cáo áp dụng: [APPLIED](review-20261027/applications/receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb/APPLIED.md).

---

## 1. Hai tầng, hai mục đích khác nhau

| Tầng | Số lượng | Ai đọc | Trả lời câu hỏi | Kiểu assert |
|---|---|---|---|---|
| **T1 — Spec tests** | 20 | agent xây dựng được đọc | "Phải xây cái gì, đúng format nào?" | cấu trúc: field, enum, mã lỗi, dạng ngày |
| **T2 — Developer tests** | 100 | chỉ QA/người duyệt đọc | "Hệ thống có thật sự hành xử đúng, hay chỉ khớp 20 input kia?" | bất biến, hoán đổi, phản chứng, thay fixture |

T1 là hợp đồng thi hành được. T2 là **thuốc giải** cho T1: mọi thứ T1 nói đều được T2 kiểm lại bằng một bề mặt khác.

### T1 không được chứa gì

T1 chỉ được assert những gì **không thể hardcode mà vẫn đúng**:

- sự tồn tại và kiểu của field (`claims`, `booking`, `planning`, `handoff`, `actions`);
- enum hợp lệ (`type ∈ {table, vehicle, room, service}`, `destination_status ∈ {FOUND, NOT_FOUND, UNSPECIFIED}`);
- quan hệ logic đọc được từ chính response (nếu `destination_status=FOUND` thì `destination` phải khác null);
- mã lỗi và HTTP status cho các nhánh đã chốt.

T1 **không** được: so khớp nguyên văn câu trả lời, so khớp id cụ thể, hay khẳng định một giá trị mà chỉ fixture hiện tại mới có. Nếu T1 làm vậy, T1 tự tạo đường hardcode.

### T2 bắt buộc phải có bốn tính chất

1. **Không lặp input của T1.** Fixture của T2 lấy từ pool khác (POI, quận, ngày, ngân sách khác).
2. **Kỳ vọng tính tại lúc chạy** từ fixture, không phải hằng số viết sẵn.
3. **Có cặp đối chứng**: cùng một câu hỏi, hai fixture khác nhau, hai kết quả khác nhau. Hardcode sẽ trượt một trong hai.
4. **Có phép phá**: nếu ta cố tình làm hệ thống trả lời đúng format mà không truy xuất, T2 phải đỏ. (Đây là mutation test cho chính bộ test.)

---

## 2. T1 — 20 spec test

Lấy từ bộ 28 case hiện có, chọn đúng 20 case phủ mỗi điều khoản một lần, ưu tiên case "dễ/khó" (giữ case phức tạp cho T2):

| # | Case | Điều khoản | Nội dung kiểm |
|---|---|---|---|
| 1 | C-B1-D | B1 | một ý ⇒ đúng một claim |
| 2 | C-B1-K | B1 | nhiều thuộc tính ⇒ nhiều claim, không suy ra booking |
| 3 | C-B1-P | B1 | nhánh điều kiện và tham chiếu chưa xác định được giữ riêng |
| 4 | C-B2-D | B2 | một hành động ⇒ intent đúng, không hỏi thứ tự |
| 5 | C-B2-P | B2 | hai hành động ⇒ không side effect, hỏi thứ tự |
| 6 | C-B3-D | B3 | trả lời bằng dữ liệu đã truy xuất |
| 7 | C-B3-E1 | B3 | POI tồn tại ⇒ xác nhận, không phủ nhận sai |
| 8 | C-B3-E2 | B3 | POI không tồn tại ⇒ từ chối, không bịa |
| 9 | C-B4-D | B4 | `type=table`, `destination_status=UNSPECIFIED` |
| 10 | C-B4-P | B4 | hai booking type ⇒ không thực thi hai lần |
| 11 | C-B4-N | B4 | đối tượng không có ⇒ `NOT_FOUND`, không tạo entity |
| 12 | C-B5-D | B5 | prefill đúng field đã nêu, field thiếu = null |
| 13 | C-B5-K | B5 | ngày tương đối quy đổi có khai báo |
| 14 | C-B5-S | B5 | đủ thông tin ⇒ không sinh phương án |
| 15 | C-B6-D | B6 | ≥3 phương án, khác nhau ≥2 chiều |
| 16 | C-B6-K | B6 | phương án mang đúng sở thích đã nêu |
| 17 | C-B7-D | B7 | bàn giao đúng phương án đã chọn |
| 18 | C-B7-P | B7 | dữ liệu mâu thuẫn ⇒ không bàn giao |
| 19 | C-G-D | G1 | hỏi thông tin ⇒ không booking/planning |
| 20 | C-G-P | G1 | ý định bị rút lại ⇒ không thực thi gì |

Tám case còn lại của bộ 28 (`C-B2-K`, `C-B3-K`, `C-B3-P`, `C-B4-K`, `C-B5-P`, `C-B6-P`, `C-B7-K`, `C-G-K`) chuyển sang làm hạt giống cho T2, vì chúng đã là dạng khó/xung đột — đúng chất chống overfit.

---

## 3. T2 — 100 test, mười họ

Mỗi họ nhắm một kiểu "ăn gian" cụ thể. Cột cuối là **cách họ này bắt được hành vi gian**.

| Mã | Họ test | Số | Ăn gian bị chặn |
|---|---|---|---|
| D1 | Diễn đạt lại (paraphrase) | 16 | khớp từ khoá: đổi cách nói, cùng ý định, cùng kết quả |
| D2 | Thay thực thể (held-out POI/quận/loại dịch vụ) | 11 | hardcode tên quán/id/type: đổi sang pool kín |
| D3 | Tiêm bịa (fake model nói sai) | 13 | chuyển nguyên văn model: hệ thống phải sửa hoặc từ chối |
| D4 | Đổi fixture, giữ câu hỏi | 12 | trả lời thuộc lòng: cùng câu hỏi, DB khác, đáp án phải khác |
| D5 | Trộn ý định, đảo thứ tự | 8 | đoán nhãn theo vị trí |
| D6 | Bất biến bề mặt | 10 | so khớp chuỗi thô: hoa/thường, thiếu dấu, khoảng trắng, dấu câu |
| D7 | Biên và giới hạn | 8 | né nhánh khó: 0 ngày, 15 ngày, 0 đồng, 51 người, message rỗng |
| D8 | Tất định | 6 | ngẫu nhiên hoá để "may mắn đúng" |
| D9 | Cô lập phiên | 6 | rò trạng thái giữa phiên |
| D10 | Dò chế độ test | 2 | phát hiện "đang bị test" để đổi hành vi |

Tổng mới trong `tests/ai_chat_mvp/test_d*.py`: **92**. Cộng 8 case phức tạp đã viết trước đó (nay tính vào T2, nằm trong các tệp `test_b*.py`): **100 developer test**. Tổng cả bộ: 20 T1 + 100 T2 = **120**, đã đếm bằng `pytest --collect-only`.

### 3.1 D4 — họ quan trọng nhất, và là câu trả lời trực tiếp cho "data leakage"

Cơ chế: **một câu hỏi, hai fixture**. Test chạy cùng một message hai lần với hai bộ dữ liệu khác nhau, kỳ vọng tính từng lần từ fixture tương ứng.

Ví dụ với `C-B3-D`:

| Lần | Fixture | Kỳ vọng |
|---|---|---|
| 1 | POI `X` có `operation_time="06:00-22:00"` | câu trả lời chứa 06:00 và 22:00 |
| 2 | cùng POI `X`, `operation_time="07:30-19:00"` | câu trả lời chứa 07:30 và 19:00, **không** chứa 06:00 |

Một hệ thống hardcode "06:00-22:00" sẽ đỏ ở lần 2. Một hệ thống không truy xuất cũng đỏ ở lần 1. Đây là dạng test không thể qua bằng cách học thuộc.

### 3.2 D10 — dò chế độ test, gồm cả kiểm tra tĩnh

Hai lớp:

- **Động:** gửi cùng một yêu cầu với `session_id` trông giống test (`test-…`, `pytest-…`) và với session bình thường; hai phản hồi phải cùng lớp hành vi. Nếu hệ thống đổi hành vi khi thấy dấu hiệu test, đỏ.
- **Tĩnh:** quét mã sản phẩm, cấm tham chiếu hạ tầng test: không `import pytest`, không đọc `PYTEST_CURRENT_TEST`, không nhánh `if "test" in session_id`, không import gì từ `tests/`.

### 3.3 Bảng vector rò rỉ và test đối chứng

| Vector rò rỉ | Ví dụ cụ thể | Test chặn |
|---|---|---|
| Hardcode id POI | `if poi_id == "hcm_primary_geojson_internal:033dd…": return {"hours": "06:00-22:00"}` | D2, D4 |
| Hardcode chuỗi kỳ vọng | trả đúng câu `"Ca phe betta fish mở cửa 06:00-22:00."` | D1, D4 |
| Bỏ truy xuất khi thấy tên quán | nhận diện tên riêng rồi trả lời luôn | D3, D4 |
| Trả JSON đúng shape nhưng rỗng | `claims: []` cho mọi input | D1, D2 (phải có nội dung đúng) |
| Nhận diện input theo độ dài/ký tự | `len(message) == 47` | D6, D7 |
| Đổi hành vi khi có dấu hiệu test | `if "test" in session_id` | D10 |
| Trả lời đúng nhưng không dẫn chứng | text khớp, `source_evidence_ids` rỗng | D4 (kỳ vọng gồm evidence) |
| Chọn phương án thay người dùng để "đúng" B7 | luôn set `handoff` | T1 #18, D1 |
| Che lỗi bằng câu chung | "không có thông tin" cho mọi thứ | D4 lần 1 (phải trả lời được khi có dữ liệu) |

---

## 4. Luật để T1/T2 không tự phá nhau

| Mã | Luật | Vì sao |
|---|---|---|
| R1 | Assert của T2 phải **tính từ fixture lúc chạy**, không có hằng số kỳ vọng trong mã test | Hằng số là thứ agent có thể đọc và hardcode |
| R2 | Fixture T2 lấy từ pool kín, **không** dùng lại POI/ngày/ngân sách xuất hiện trong contract hay T1 | Tránh dạy agent đúng bộ dữ liệu |
| R3 | Không assert nguyên văn `reply`; chỉ assert (a) cấu trúc, (b) sự hiện diện/không hiện diện của **dữ kiện có thể kiểm** (giờ, id, ngưỡng) | Văn xuôi tự do không phải hợp đồng |
| R4 | Mọi họ T2 phải có ít nhất một cặp đối chứng âm/dương | Không có cặp thì test chỉ kiểm một phía |
| R5 | Mã sản phẩm không được tham chiếu `tests/`, `pytest`, hay tên fixture | Kiểm tĩnh, chạy cùng bộ |
| R6 | T2 do vai QA viết, người/tác nhân xây dựng chỉ thấy T1 + contract | Kiểm soát quy trình, không chỉ kỹ thuật |
| R7 | Mỗi họ T2 phải chứng minh cắn bằng một lượt đột biến có ghi tên test đỏ | Tránh test trang trí |

R6 khớp với phân vai trong `AGENTS.md`: Codex viết test và QA độc lập, OpenCode thi công.

---

## 5. Cổng chất lượng

Một chức năng chỉ được gọi là đạt khi:

1. **20/20 T1 xanh** — đúng format và cấu trúc.
2. **100/100 T2 xanh** — không overfit.
3. **Chứng minh cắn:** mỗi họ D1–D10 có một lượt đột biến ghi lại đúng tên test đỏ, rồi hoàn nguyên.
4. **Kiểm tĩnh sạch:** không tham chiếu hạ tầng test trong mã sản phẩm.
5. **Không case nào bị sửa kỳ vọng** để lấy xanh; thay đổi phải qua change request.

Báo cáo phải tách rõ: `T1 pass`, `T2 pass`, `mutation proof`, `static check`. Không được gộp thành "120/120" mà không nêu bốn mục trên.

---

## 6. Việc cần làm để hiện thực hoá

| Bước | Nội dung | Ghi chú |
|---|---|---|
| 1 | Tách 28 case hiện có thành T1 (20) và hạt giống T2 (8) | mã đã có, chỉ đổi tổ chức |
| 2 | Dựng pool fixture kín cho T2 (POI/quận/ngày khác T1) | lấy từ `prepared_pois.jsonl`, id thật |
| 3 | Viết bộ sinh tham số cho D1, D2, D4 (paraphrase/substitution/fixture-swap) | bảng dữ liệu + `pytest.mark.parametrize`, không 100 hàm thủ công |
| 4 | Viết D3, D5, D6, D7, D8, D9 thủ công | mỗi họ 4–14 case |
| 5 | Thêm kiểm tĩnh R5 và dò D10 | script nhỏ, chạy chung bộ |
| 6 | Chạy toàn bộ trên mã hiện tại, ghi RED baseline 120 | dự kiến đỏ gần hết |

Chưa bước nào được thực hiện tại thời điểm viết tệp này.

## 6. Đã hiện thực — hai bộ tách rời

| Bộ | Thư mục | Số | Ai đọc |
|---|---|---|---|
| `--evaluate` | `tests/ai_chat_mvp/` | 20 | agent xây dựng được đọc để align |
| `--test` | `tests/ai_chat_mvp_hidden/` | 100 | chỉ QA/người duyệt; tự chứa (có harness riêng) |

Chạy bằng một script duy nhất:

```bash
uv run --with pytest python scripts/run_chat_tests.py --evaluate
uv run --with pytest python scripts/run_chat_tests.py --test
```

Script kiểm ba thứ trước khi chạy: (a) đủ file test của bộ, (b) đủ **cả 9 điều khoản** B1–B7, G1, G2, (c) số test thu được đúng 20/100. Thiếu bất kỳ mục nào thì **từ chối chạy** chứ không chạy bộ thiếu.

Nếu thư mục 100 test đã bị cắt ra khỏi repo, `--test` tự báo và chạy bộ `--evaluate` (20) thay vì lỗi.

## 7. Điều tệp này không nói

- Không nói T2 có thể chứng minh "không có lỗi nào khác" — chỉ chặn các kiểu ăn gian liệt kê ở §3.3.
- Không thay thế đánh giá chất lượng model thật; fake model trong test không phải model production.
- Không đảm bảo agent không đọc T2 nếu T2 nằm cùng repo và agent có quyền đọc — đó là kiểm soát quy trình (R6), không phải kiểm soát kỹ thuật.
