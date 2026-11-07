# Test plan — Agent Chat MVP (`FT-CHAT-MVP-001`)

- **ID:** `TP-CHAT-001` · **Version:** `0.4` · **Status:** thiết kế kiểm thử thuộc cổng `TA-CHAT-001` đã `APPROVED` ngày 28/10/2026; không còn chờ duyệt kiến trúc 20 + 100 test.
- **0.2:** thêm schema mock Knowledge Database lấy từ dataset thật (§2.1) và cặp đối chứng tồn tại / không tồn tại ở B3 theo yêu cầu chủ dự án.
- **0.3:** sáu quyết định đã chốt (§2.2–§2.5, Q1–Q6); không còn case nào phải chờ để viết assert.
- **0.4:** bộ case trong tệp này trở thành **tầng T1 (20 spec test)** của kiến trúc 120 test; 8 case còn lại làm hạt giống cho tầng T2. Xem `F-CHAT_MVP_TEST_ARCHITECTURE.md`.
- **Dựa trên:** `docs/contracts/F-CHAT_MVP_CONTRACT.md` v1.0 (APPROVED, chủ dự án định nghĩa)
- **Ngày:** 2026-10-22 · **Người soạn:** Hermes
- **Trạng thái thực thi hiện hành:** đã có bộ 20 test đặc tả và 100 test QA, cùng RED baseline ngày 22/10 (T1: 20 fail; T2: 96 fail/4 pass). Chưa chạy lại trong đợt áp dụng biên nhận 28/10. Các mô tả “chưa viết/chưa chạy” ở phần lịch sử bên dưới đã được trạng thái này thay thế. Phê duyệt thiết kế không phải nghiệm thu implementation.
- **Booking hiện hành:** theo `F-BOOKING_MVP_CONTRACT.md`, chọn **Book Ngay** dẫn đến screen booking; lệnh đặt tới dịch vụ ngoài là fake. Các tên handler/field cũ trong case là thiết kế cần đối chiếu với contract này, không chứng minh đặt thật. Không tự sửa test/expected trong lượt cập nhật tài liệu.
- **Phạm vi:** chỉ 8 khối B1–B7 + G. Không thêm behavior ngoài contract.

---

## 1. Quy ước

Ba mức, đúng định nghĩa của chủ dự án:

| Mức | Nghĩa | Dấu hiệu trong câu |
|---|---|---|
| **Dễ** | Agent phát hiện ngay | một hành động, động từ tường minh, không phụ thuộc ngữ cảnh |
| **Khó** | Ẩn một tầng nhưng ý định vẫn rõ | ý định nằm sau câu hỏi, điều kiện, cách nói gián tiếp; cần đọc ngữ cảnh một bước |
| **Phức tạp** | Người dùng chưa rõ ý định, nhiều intent trộn, có xung đột | nhiều hành động ngang hàng, điều kiện rẽ nhánh, ràng buộc mâu thuẫn |

Mỗi khối có **ít nhất 3 case**, một case mỗi mức. Hai ngoại lệ có thêm case vì contract nêu hệ quả cụ thể: B3 thêm cặp đối chứng tồn tại/không tồn tại (E1/E2) — 5 case; B4 thêm case `NOT_FOUND` (N) — 4 case.

ID: `C-<khối>-<D|K|P|N|E>` (`N` = âm bản, `E` = đối chứng tồn tại).

---

## 2. Điều kiện quan sát được

Contract quy định **hành vi**, không quy định **dữ liệu quan sát**. Muốn test phân biệt được "đúng/sai" thay vì chấm điểm văn xuôi, response cần tối thiểu các field sau. Đây là `PROPOSAL`, đã được chủ dự án chấp thuận nguyên tắc ngày 2026-10-22; tên field cụ thể chốt khi viết code.

| Field đề xuất | Kiểu | Dùng để kiểm |
|---|---|---|
| `intent` | `CHITCHAT \| BOOKING \| PLAN` | B2, G |
| `claims[]` | mỗi phần tử `{text, entity_refs[], constraints{}}` | B1 |
| `booking` | `{type, destination, destination_status}` đúng contract B4 | B4 |
| `planning.form` | object, field thiếu = `null`; riêng ngày có `date`, `date_text` (nguyên văn), `date_source` (`explicit`/`converted_from_relative`) | B5 |
| `planning.options[]` | ≥3 phần tử, mỗi phần tử `{poi_ids[], area_ids[], pace, budget, experience_types[]}` — đủ 4 chiều để tính "khác biệt có ý nghĩa" | B6 |
| `handoff` | `{target, payload}` hoặc `null` | B7 |
| `actions[]` | nhật ký feature handler được gọi trong lượt; đúng hai tên: `booking.create`, `planning.start` | B2, G |

Ba mức kiểm, từ mạnh tới yếu: **(1)** assert field/call ở trên; **(2)** assert nội dung văn bản trả lời có/không chứa thông tin bịa; **(3)** chấm thủ công theo rubric. Case nào cũng ghi rõ đang kiểm ở mức nào.

### 2.1 Mock Knowledge Database — seam và schema thật

Agent Chat chỉ nhìn thấy kết quả MCP, nên mock đặt đúng seam MCP (`session.list_tools()` / `session.call_tool()`), **không** mock Memgraph: nếu mock ở tầng graph thì test đang kiểm một hệ khác với hệ chạy thật.

Hình dạng payload phải trùng hai model thật, không được tự phát minh field:

| Tool | Shape thật | Nguồn |
|---|---|---|
| `get_poi_details` | `{success, result{POI_ID, POI_Name, POI_Address, POI_Category, latitude, longitude, operation_time, POI_Description{insight, seo_article, review{rating, review}, status}, POI_Contact_Info{website, fanpage, phonenumber}, Offers[{name,price}], NEAR_BY[{poi, distance}], POI_Categories[{id,name,context}], administrative_context{city_id, district_id, city_name, district_name}, administrative_context_status, missing_data[]}}` | `POIGetResponse` → `POIResult`, `get_payload.py:210-254` |
| `explore_pois` | `{success, count, results[POICompoundLite{id, name, full_address, operation_time, categories[], offers[], administrative_context, administrative_context_status}]}` | `POICompoundLite`, `get_payload.py:186-207` |
| Không tìm thấy (details) | `{success:false, code:"not_found", detail:"POI not found.", message:"POI not found."}` | `tools.py:135-144,281-282` |
| Không có kết quả (explore) | `{success:true, count:0, results:[]}` — rỗng là **thành công**, không phải lỗi tool | `tools.py:596-600` |

Fixture lấy từ dataset thật `data/primary_20261016/graph_ready_v2/prepared_pois.jsonl` (6367 POI, input `sha256=713b07a6…e43c`), không viết tay:

| Fixture | Bản ghi | Dùng cho |
|---|---|---|
| F1 — tồn tại, **có** giờ | `hcm_primary_geojson_internal:033dd327cc9b86b52c8768151afad7f2`, name `ca phe betta fish`, Quan 1, `operation_time="06:00-22:00"`, `rating=null`, `menu=[]` | C-B3-D, C-B3-E1 |
| F2 — tồn tại, **thiếu** giờ | `hcm_primary_geojson_internal:0712657078c2c38d3ab0bf28f20b7a71`, name `anh tuong my thuat`, Tan Phu, Attractions, `operation_time=null` | C-B3-K, C-B3-E1 |
| F3 — **không** tồn tại | câu "Quán Cà Phê Bóng Đêm ở Quận 1" — 0/6367 bản ghi khớp | C-B3-E2 |
| F4 — nhiều ứng viên | 3 POI Quan 1 (Coffee/Restaurant) đều `operation_time=null` | C-B3-P |

Ba sự thật của dataset quyết định kỳ vọng, nếu bỏ qua thì test sẽ chấm sai: chỉ **1054/6367** bản ghi có `operation_time`; **0/6367** có `menu`; **0/6367** có `rating`. Nên câu hỏi về giá, thực đơn, đánh giá **luôn** phải trả "không có thông tin" — agent trả lời có giá là bịa, không phải "dữ liệu nghèo".

Hai điều cấm khi dựng fixture: tự đặt id (phải dùng id thật ở trên) và tự điền giờ/giá cho bản ghi vốn `null`.

Để mock không trôi khỏi schema thật, thêm một test **schema fidelity**: so tập key của fixture với `POIGetResponse.model_fields` / `POICompoundLite.model_fields`; lệch key ⇒ fail. Test này rẻ và chặn đúng loại lỗi "mock cũ hơn production".

### 2.2 Định nghĩa đo cho B6 — đã chốt 2026-10-22

"Khác biệt có ý nghĩa" giữa hai phương án = **khác ≥2 chiều** trong bốn chiều `{khu vực, nhịp, ngân sách, loại trải nghiệm}` **và** `poi_ids` không trùng nhau. Chủ dự án chốt quy tắc này; nó thay cho việc chấm cảm tính.

Cách kiểm cho từng cặp phương án `(A, B)` trong `options[]`:

| Chiều | So sánh | Cách tính |
|---|---|---|
| khu vực | `A.area_ids != B.area_ids` | so tập, không so thứ tự |
| nhịp | `A.pace != B.pace` | ví dụ `relaxed` vs `packed` |
| ngân sách | `A.budget != B.budget` | so giá trị, không so khoảng |
| loại trải nghiệm | `A.experience_types != B.experience_types` | so tập |

Một cặp thoả khi `so_khác >= 2` **và** `A.poi_ids != B.poi_ids`. Với ≥3 phương án, mọi cặp phải thoả. Không được "khác" bằng cách chỉ đổi tên quán trong cùng một khu vực, cùng nhịp, cùng ngân sách — đó là vi phạm quy tắc này.

Hệ quả lên schema: mỗi phần tử `options[]` **buộc** phải mang đủ 4 chiều, nếu thiếu chiều nào thì không tính được và test không được coi là pass.

### 2.3 Ngưỡng "đủ thông tin" — đã chốt 2026-10-22

Đủ = có **cả ba**: (1) ít nhất một sở thích/nhu cầu; (2) **ngày khởi hành hoặc ngày đến sử dụng dịch vụ**; (3) **ngân sách**. Thiếu bất kỳ mục nào ⇒ B6 bắt buộc sinh ≥3 phương án.

Khu vực và số người **không** thuộc điều kiện đủ — chúng có thể `null` mà vẫn coi là đủ.

Hệ quả lên các case đã có (cập nhật lại kỳ vọng cho khớp ngưỡng này):

| Case | Có | Thiếu | Nhánh đúng |
|---|---|---|---|
| C-B5-D | khu vực, 2 ngày, 2 người, 3 triệu | sở thích, ngày | form + **3 phương án** |
| C-B5-K | sở thích, ngân sách, "cuối tuần này" | — (mốc tương đối được tính là ngày, §2.4) | form, **không** sinh 3 phương án |
| C-B5-P | sở thích (ghét đông), ngân sách 1 triệu | ngày | form + **3 phương án** |
| C-B5-S (mới) | sở thích, ngày 25/10, ngân sách 2 triệu | — | form, **không** sinh 3 phương án |
| C-B6-D | 2 ngày, TP.HCM | sở thích, ngày, ngân sách | 3 phương án |
| C-B6-K | sở thích | ngày, ngân sách | 3 phương án |
| C-B6-P | sở thích, "tiết kiệm" (không phải số) | ngày, ngân sách dạng số | 3 phương án + nêu mâu thuẫn |

Nhánh "đủ" có **hai** case: C-B5-S (ngày tuyệt đối) và C-B5-K (mốc tương đối đã quy đổi). Nếu thiếu chúng, lỗi "luôn sinh 3 phương án" sẽ lọt qua toàn bộ bộ test.

### 2.4 Mốc thời gian tương đối — đã chốt 2026-10-22

Cách nói tương đối **được tính là ngày**. Agent quy đổi theo ngày hiện tại và **phải ghi rõ** đã quy đổi; không được lặng lẽ biến "cuối tuần này" thành một ngày mà không nói.

Để test tất định, "ngày hiện tại" phải được **tiêm vào**, không đọc đồng hồ hệ thống. Fixture dùng `now = 2026-10-22` (thứ Năm, Asia/Ho_Chi_Minh).

| Cách nói | Quy đổi khi `now = 22/10/2026` | `date_source` |
|---|---|---|
| "mai" | 23/10/2026 | `converted_from_relative` |
| "cuối tuần này" | 24/10/2026 (thứ Bảy; Chủ nhật là 25/10) | `converted_from_relative` |
| "tối nay" | 22/10/2026 | `converted_from_relative` |
| "ngày 25/10" | 25/10/2026 | `explicit` |

Ba field bắt buộc trên form: `date` (giá trị đã quy đổi), `date_text` (nguyên văn người dùng), `date_source`. Thiếu `date_text` hoặc `date_source` ⇒ test fail: người dùng không có cách nào kiểm agent hiểu đúng ngày hay không.

Clock tiêm phải kèm timezone (Asia/Ho_Chi_Minh), không dùng datetime naive: 23:00 UTC ngày 22 đã là 06:00 ngày 23 giờ Việt Nam, đủ để lệch một ngày và làm case "mai" sai.

### 2.5 Ưu tiên ý định khi một câu có nhiều claim — đã chốt 2026-10-22

Ba tình huống, ba luật khác nhau; đừng gộp chúng thành một luật chung:

| Tình huống | Luật | Case |
|---|---|---|
| Một câu **vừa hỏi thông tin vừa yêu cầu hành động** | **Hành động thắng**; câu hỏi trở thành context | C-B2-K |
| Hành động nhưng **đối tượng chưa xác định** | Giữ intent hành động, `destination_status="UNSPECIFIED"`, hỏi đối tượng trước khi làm gì | C-B2-K, C-B4-D |
| **Hai hành động ngang hàng**, chưa rõ thứ tự | Không thực hiện cái nào; hỏi muốn làm cái nào trước | C-B2-P, C-B4-P |

Hệ quả cho C-B2-K: `intent="BOOKING"`, `destination_status="UNSPECIFIED"`, agent hỏi quán nào. Không được trả lời tình trạng bàn như một câu CHITCHAT rồi thôi.

Một sự thật củng cố assert này: trong repo **không có** tool hay service nào kiểm tra tình trạng bàn (`BOOKING`/`availability` xuất hiện 0 lần trong `ai_service`, `POI_service`, `backend_service`; 5 tool MCP không có tool đặt chỗ). Nên mọi câu khẳng định "còn bàn"/"hết bàn" ở thời điểm hiện tại **luôn** là bịa, bất kể intent nào thắng.

---

## 3. Test cases

### B1 — Claim Extraction

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert / bắt lỗi |
|---|---|---|---|---|---|
| C-B1-D | Dễ | "Tìm quán cà phê ở Quận 1." | 1 claim: tìm POI, `category=cà phê`, `area=Quận 1`. Không claim đặt bàn. | B1 | `claims.length == 1`; claim chứa area+category; không có `booking` |
| C-B1-K | Khó | "Nhóm mình 3 người, 8h tối, muốn chỗ ngồi nói chuyện được ở Bình Thạnh, đừng ồn." | Claims tách rời: số người = 3, giờ = 20:00, khu vực = Bình Thạnh, thuộc tính = yên tĩnh. **Không** claim "đặt bàn" vì chưa có hành động đặt. | B1 | `claims` có ≥4 phần tử độc lập; `intent != BOOKING`; không có `booking` |
| C-B1-P | Phức tạp | "Mình muốn đi Bảo tàng Mỹ Thuật, rồi ăn gì dưới 200k/người, nếu mưa thì tìm chỗ gần khách sạn mình ở." | Claims: (1) tham quan POI "Bảo tàng Mỹ Thuật"; (2) ăn ≤200k/người; (3) nhánh điều kiện "nếu mưa"; (4) tham chiếu "khách sạn mình ở" **chưa xác định**. Không tự chọn quán, không tự chọn khách sạn, không gộp 3+4 thành một claim. | B1 | `claims` giữ nhánh điều kiện riêng; entity chưa xác định để `null`, không tự điền; không có POI nào bị bịa thêm vào `claims` |

### B2 — Significant Intent

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-B2-D | Dễ | "Đặt bàn 4 người 19h tối nay." | `intent=BOOKING`, `type=table`, hành động ngay = giữ bàn. Không hỏi lại thứ tự. | B2 | `intent==BOOKING`; `booking.type=="table"`; không hỏi "muốn làm gì trước" |
| C-B2-K | Khó | "Quán này còn bàn không? Nếu còn thì giữ cho mình 4 người 19h." | `intent=BOOKING` — hành động đặt thắng, câu hỏi tình trạng bàn là context (§2.5). Đối tượng chưa xác định → `destination_status=UNSPECIFIED`, phải hỏi quán nào trước khi làm gì. Không khẳng định còn/hết bàn (không có tool nào kiểm tra). | B2, B4 | `intent=="BOOKING"`; `booking.type=="table"`; `destination_status=="UNSPECIFIED"`; `actions` không có `booking.create`; không có câu khẳng định "còn/hết bàn" |
| C-B2-P | Phức tạp | "Đặt bàn nhà hàng X cho 4 người tối nay, xong lên luôn lịch 2 ngày quanh đó, ngân sách 2 triệu." | Hai hành động ngang hàng, chưa xác nhận thứ tự → phải hỏi muốn làm cái nào trước. Không chạy booking, không chạy planning trong lượt này. Claim còn lại giữ làm context. | B2 | `actions` rỗng; văn bản trả lời chứa câu hỏi chọn thứ tự; `intent` có thể là `null` hoặc một trong hai, nhưng **không** có side effect |

### B3 — Grounded Answer

**Ma trận tồn tại** — đây là cặp đối chứng chủ dự án yêu cầu; cả hai ô chéo đều phải bị bắt:

| Trạng thái trong mock DB | Agent trả "có địa điểm này" | Agent trả "không có" |
|---|---|---|
| **Có** bản ghi (F1, F2) | ĐÚNG → C-B3-E1 | **SAI** (false negative) |
| **Không có** bản ghi (F3) | **SAI** (bịa) → C-B3-E2 | ĐÚNG |

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-B3-D | Dễ | "Cà phê Betta Fish ở Võ Văn Kiệt mở cửa mấy giờ?" | F1 có `operation_time="06:00-22:00"` → trả đúng khung giờ này, không thêm giờ nào khác. | B3 | Có ≥1 tool call đọc DB; câu trả lời chứa `06:00` và `22:00`; không chứa giờ nào khác |
| C-B3-K | Khó | "Chỗ đó có chỗ đậu xe không?" (ngay sau khi bàn F2) | Phạm vi = F2, không đổi chủ đề. Schema **không có** field bãi xe → nói không có thông tin. | B3 | Tool call dùng đúng `POI_ID` của F2; câu trả lời không khẳng định có/không bãi xe |
| C-B3-P | Phức tạp | "Quán cà phê nào ở Quận 1 vừa rẻ vừa mở khuya vừa có chỗ đậu ô tô?" | Ba ràng buộc mà dữ liệu không trả lời được: giá (không có field), giờ (chỉ 17% bản ghi có), bãi xe (không có field). Phải nêu rõ không lọc được theo giá/bãi xe, chỉ trả phần giờ nếu có; không nới điều kiện. | B3 | Mọi POI trong câu trả lời có trong kết quả tool (F4); câu trả lời nêu field thiếu; không khẳng định "rẻ" hay "có chỗ đậu xe" |
| C-B3-E1 | Đối chứng **dương** (tồn tại) | "Anh Tường Mỹ Thuật ở Tân Phú có mở cửa không?" | F2 tồn tại → phải xác nhận **có** địa điểm này (đúng tên/địa bàn ưu tiên theo DB), và nói giờ mở cửa không có dữ liệu. | B3, G2 | Câu trả lời khẳng định tồn tại; **không** chứa "không tìm thấy"; không bịa giờ; tool call trả về đúng `POI_ID` của F2 |
| C-B3-E2 | Đối chứng **âm** (không tồn tại) | "Quán Cà Phê Bóng Đêm ở Quận 1 mở mấy giờ?" | F3 rỗng → phải nói không tìm thấy / không có thông tin. Không được trả lời như thể quán tồn tại. | B3, G2 | `explore_pois` trả `count=0`; câu trả lời chứa "không tìm thấy"/"không có thông tin"; không chứa giờ, địa chỉ, mô tả, giá; không có entity id mới |

**Đột biến chứng minh test cắn** (không phải case sản phẩm — chạy một lần để chứng minh test không phải test trang trí):

| ID | Đột biến | Kỳ vọng |
|---|---|---|
| M-B3-1 | Cho agent luôn trả "không tìm thấy" dù tool trả F1/F2 | C-B3-D và C-B3-E1 **phải** fail |
| M-B3-2 | Cho agent bịa giờ/địa chỉ cho F3 (DB rỗng) | C-B3-E2 **phải** fail |

Ghi lại đúng tên test fail ở mỗi lượt đột biến, rồi hoàn nguyên và chạy lại để thấy xanh. Không ghi "đã pass" nếu chưa chạy hai lượt này.

### B4 — Booking Intent Extraction

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-B4-D | Dễ | "Đặt bàn 2 người 7h tối nay." | `intent=BOOKING`, `type=table`, `destination=null`, `destination_status=UNSPECIFIED`. | B4 | Đúng 4 field; `type` thuộc tập cho phép; `destination_status=="UNSPECIFIED"` |
| C-B4-K | Khó | "Mình muốn thuê xe máy ở Phan Xích Long từ 8h sáng mai." | `type=vehicle`; đối tượng là **dịch vụ thuê xe ở Phan Xích Long**; nếu DB có entity → `FOUND` + id thật; nếu không → `NOT_FOUND`; chưa nêu đơn vị cụ thể → `UNSPECIFIED`. Không tự tạo entity. | B4 | `type=="vehicle"`; `destination` hoặc là id có thật trong DB hoặc `null`; không có id tự sinh |
| C-B4-P | Phức tạp | "Đặt phòng khách sạn đó 2 đêm, nếu hết phòng thì đặt bàn nhà hàng luôn." | Hai booking type trong một lượt + điều kiện. Contract cấm thực hiện nhiều intent khi chưa xác nhận → phải chọn một hoặc hỏi. `destination_status` phản ánh DB thật cho từng đối tượng. | B2, B4 | Chỉ một `booking.type` được kích hoạt; `actions` không có 2 lần booking; nhánh dự phòng được ghi lại chứ không thực thi |
| C-B4-N | Âm bản | "Đặt bàn ở nhà hàng Bóng Đêm Quận 7." | `type=table`, `destination=null`, `destination_status=NOT_FOUND`; không tạo entity; không chuyển sang Booking Feature. | B4 | `destination_status=="NOT_FOUND"`; `actions` không có booking; không có id tự sinh |

### B5 — Planning Input

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-B5-D | Dễ | "Lên lịch 2 ngày ở Quận 1 cho 2 người, ngân sách 3 triệu." | Prefill `days=2`, `area=Quận 1`, `party=2`, `budget=3.000.000`; trường khác `null`; hiện form. Theo §2.3 thiếu sở thích và ngày ⇒ **kèm 3 phương án**. | B5, B6 | Từng field khớp; không field nào bị tự điền ngoài câu; `options.length >= 3` |
| C-B5-K | Khó | "Cuối tuần này mình rảnh 2 ngày, đi với người yêu, thích cà phê với bảo tàng, tiền tầm 2 triệu." | Prefill `days=2`, `party=2`, `preferences=[cà phê, bảo tàng]`, `budget=2.000.000`, `area=null`, `date=24/10/2026`, `date_source=converted_from_relative`, `date_text="cuối tuần này"`. Đủ theo §2.3 ⇒ **không** sinh 3 phương án. | B5 | `area==null`; đúng 2 preference; `date`/`date_text`/`date_source` khớp §2.4; `options` rỗng hoặc không có |
| C-B5-P | Phức tạp | "Đi đâu cũng được miễn dưới 1 triệu, mình ghét chỗ đông, phải về trước 5h chiều." | Prefill `budget=1.000.000`, ràng buộc "tránh đông" và "kết thúc trước 17:00"; `area=null`, `days=null`; form hiện ra, không tự chốt POI. Thiếu ngày ⇒ **kèm 3 phương án**. | B5, B6 | `area==null`, `days==null`; ràng buộc được giữ; `options.length >= 3`; không POI nào bị chốt |
| C-B5-S | Đủ thông tin | "Ngày 25/10 mình muốn đi cà phê và bảo tàng, ngân sách 2 triệu." | Đủ theo §2.3 (sở thích + ngày + ngân sách) ⇒ form prefill, **không** sinh 3 phương án. | B5 | `planning.form.preference` có cà phê+bảo tàng; `date=25/10`; `budget=2.000.000`; `options` rỗng hoặc không có |

### B6 — Scenario Generation

Cả ba case dưới đây đều **không đủ** theo §2.3 (thiếu ngày và/hoặc ngân sách dạng số), nên nhánh sinh ≥3 phương án là bắt buộc — không được trả một lịch duy nhất.

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-B6-D | Dễ | "Gợi ý cho mình 2 ngày ở TP.HCM." | ≥3 phương án; mỗi phương án có tập POI riêng; không tự chọn phương án. | B6 | `options.length >= 3`; mọi cặp thoả quy tắc §2.2 (≥2 chiều khác + `poi_ids` khác); `handoff==null` |
| C-B6-K | Khó | "Mình thích yên tĩnh, thích cà phê, không thích đông." | ≥3 phương án thể hiện **cách** đạt preference khác nhau (khác khu vực / nhịp / ngân sách / loại trải nghiệm), không chỉ đổi tên quán. | B6 | `options.length >= 3`; mọi cặp thoả §2.2; mỗi phương án có `experience_types` phản ánh "yên tĩnh"/"cà phê"; không phương án nào chứa điểm vi phạm "đông" mà không nêu đánh đổi |
| C-B6-P | Phức tạp | "Mình muốn tiết kiệm mà vẫn sang trọng, ghét đông nhưng muốn đi chợ Bến Thành." | Preference xung đột. Mỗi phương án phải nêu rõ đánh đổi, hoặc hỏi lại; không tự chọn; không âm thầm bỏ một preference. | B6 | Mọi preference trong câu được phản ánh hoặc được nêu là mâu thuẫn; mọi cặp thoả §2.2; `handoff==null`; không phương án nào bị chốt |

### B7 — Planning Handoff

| ID | Mức | Hành động | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-B7-D | Dễ | Chọn phương án 2 rồi xác nhận | `handoff.target=="itinerary_planning"`; payload = dữ liệu **đã xác nhận**; planning được kích hoạt; điều hướng sang giao diện planning. | B7 | `handoff` khác `null`; payload khớp phương án 2; `actions` có đúng 1 lần `planning.start` |
| C-B7-K | Khó | Sửa ngân sách từ 2.000.000 → 1.500.000 rồi xác nhận | Payload dùng **1.500.000**, không dùng giá trị gợi ý ban đầu. | B7 | `handoff.payload.budget == 1.500.000`; các field khác giữ nguyên |
| C-B7-P | Phức tạp | Sửa thành `days=0` (hoặc ngân sách 0, hoặc 2 khu vực trái ngược) rồi xác nhận | Cảnh báo mâu thuẫn và **không** handoff; không tự sửa giúp; không âm thầm bỏ ràng buộc. | B7, B5 | `handoff==null`; `actions` không có `planning.start`; câu trả lời nêu đúng field mâu thuẫn |

### G — Global Constraints

| ID | Mức | Câu người dùng | Kỳ vọng quan sát được | Clause | Assert |
|---|---|---|---|---|---|
| C-G-D | Dễ | "Quán X có gì ngon?" | `intent=CHITCHAT`; không tạo booking, không tạo planning. | G1 | `actions` không chứa booking/planning |
| C-G-K | Khó | "Cho mình xem thực đơn quán đó." | `CHITCHAT`; trả thông tin có căn cứ; **không** tự đặt bàn dù có ngữ cảnh nhà hàng. | G1 | `intent==CHITCHAT`; `booking` không xuất hiện |
| C-G-P | Phức tạp | "Đặt bàn chỗ đó luôn đi… mà thôi để mình suy nghĩ." | Ý định bị rút lại giữa câu. Phải hỏi lại hoặc dừng; không thực hiện booking. | G1, B2 | `actions` rỗng; câu trả lời không khẳng định đã đặt |

---

## 4. Traceability

| Clause | Case |
|---|---|
| B1 | C-B1-D, C-B1-K, C-B1-P |
| B2 | C-B2-D, C-B2-K, C-B2-P, C-B4-P, C-G-P |
| B3 | C-B3-D, C-B3-K, C-B3-P, C-B3-E1, C-B3-E2 |
| B4 | C-B4-D, C-B4-K, C-B4-P, C-B4-N, C-B2-K |
| B5 | C-B5-D, C-B5-K, C-B5-P, C-B5-S, C-B7-P |
| B6 | C-B6-D, C-B6-K, C-B6-P |
| B7 | C-B7-D, C-B7-K, C-B7-P |
| G1 (không tự thực hiện khi chỉ hỏi) | C-G-D, C-G-K, C-G-P |
| G2 (không dữ liệu không căn cứ) | C-B3-E1, C-B3-E2, C-B4-N |

Tổng: **28 case** (5 khối × 3 = 15, cộng B3 5 + B4 4 + B5 4) và **2 lượt đột biến** M-B3-1/M-B3-2 để chứng minh cặp đối chứng thật sự cắn.

---

## 5. Trạng thái so với mã hiện tại

Đọc mã ngày 2026-10-22, **chưa chạy test**. Đây là bản đồ đỏ: case nào chắc chắn fail với mã hiện tại.

| Khối | Trạng thái | Bằng chứng |
|---|---|---|
| B1 Claim Extraction | `GAP` | Không có module claim; `ai_service/domains/jev_intent.py` phân loại nguyên câu, không tách claim. `grep claim` trong `ai_service` không có hàm trích xuất. |
| B2 Significant Intent | `GAP` | `_router_gate` chỉ xử lý `CHITCHAT`/`TRAVEL`/`UNCERTAIN`; không có khái niệm significant intent giữa nhiều claim; clarify chỉ khi Jev trả `ambiguous`. |
| B3 Grounded Answer | `PARTIAL` | Có truy xuất MCP và `insufficient_data`, nhưng **văn bản trả lời của model không được kiểm từng field** — chỉ bị dán nhãn `unverified_free_text`. Vì vậy phía bịa của cặp đối chứng (E2) hiện **fail**: model có thể mô tả một quán không tồn tại. Thêm vào đó dataset chỉ có **1054/6367** bản ghi có giờ mở cửa và **0** menu/rating, nên câu hỏi giá/menu phải luôn trả "không có thông tin". |
| B4 BOOKING | `GAP` | Không tồn tại `BOOKING`, `type`, `destination`, `destination_status` trong `ai_service`, `POI_service`, `backend_service`. |
| B5 Planning Input | `GAP` | Chat không có form/prefill; `/generate_itinerary` nhận form qua endpoint riêng, không qua hội thoại. |
| B6 Scenario Generation | `GAP` | Không có sinh ≥3 phương án; planner chỉ trả một lịch. |
| B7 Planning Handoff | `GAP` | Không có bàn giao từ chat sang planning; người dùng tự gọi endpoint khác. |
| G Global | `PARTIAL` | G1 đúng một cách tình cờ (chưa có booking để tự thực hiện). G2 chỉ đúng ở mức tool evidence, không ở mức văn bản. |

Hệ quả: **6/8 khối GAP**, 2 khối PARTIAL. Bộ test này khi viết ra sẽ đỏ gần như toàn bộ — đó là trạng thái RED hợp lệ, không phải test hỏng.

---

## 6. Câu hỏi mở (chặn việc viết test)

| ID | Câu hỏi | Vì sao chặn |
|---|---|---|
| ~~Q1~~ | **ĐÃ GIẢI QUYẾT 2026-10-22:** chủ dự án đồng ý thêm field quan sát vào response, đồng thời yêu cầu bổ sung cặp đối chứng tồn tại/không tồn tại ở B3. Đã thêm C-B3-E1, C-B3-E2 và hai lượt đột biến M-B3-1/2. | — |
| ~~Q2~~ | **ĐÃ GIẢI QUYẾT 2026-10-22:** khác ≥2 chiều trong {khu vực, nhịp, ngân sách, loại trải nghiệm} và `poi_ids` không trùng. Quy tắc đo ở §2.2; assert của C-B6-D/K/P đã cập nhật. | — |
| ~~Q3~~ | **ĐÃ GIẢI QUYẾT 2026-10-22:** đủ = ít nhất 1 sở thích + ngày khởi hành (hoặc ngày đến sử dụng dịch vụ) + ngân sách. Quy tắc ở §2.3; đã thêm C-B5-S cho nhánh "đủ" và cập nhật kỳ vọng B5/B6. | — |
| ~~Q6~~ | **ĐÃ GIẢI QUYẾT 2026-10-22:** mốc tương đối được tính là ngày, quy đổi theo ngày hiện tại, form phải ghi rõ `date_text` + `date_source`. Quy tắc ở §2.4; C-B5-K chuyển sang nhánh "đủ". | — |
| ~~Q4~~ | **ĐÃ GIẢI QUYẾT (hỏi lại 2026-10-22):** chưa có Booking service; test dùng **fake handler** tên `booking.create`. Phần tích hợp thật với Booking Feature giữ `NOT VERIFIED` — mock chỉ chứng minh hợp đồng giả định, không chứng minh tích hợp. | — |
| ~~Q5~~ | **ĐÃ GIẢI QUYẾT (hỏi lại 2026-10-22):** hành động đặt thắng — `intent=BOOKING`, `destination_status=UNSPECIFIED`, hỏi quán nào trước khi làm gì. Luật tổng quát ở §2.5; assert của C-B2-K đã chốt. | — |

---

## 7. Nơi đặt test và cách chạy (đề xuất, chưa làm)

- Thư mục đề xuất: `tests/ai_chat_mvp/` với `conftest.py` dựng fake Jev (trả intent theo kịch bản), fake MCP (fixture F1–F4 ở §2.1), fake model (trả văn bản cố định), **fake Booking handler** (`booking.create`, ghi lại payload) và **clock tiêm cố định** `2026-10-22T09:00+07:00` (không đọc giờ hệ thống, không dùng datetime naive).
- Tích hợp thật với Booking Feature: `NOT VERIFIED`. Fake handler chứng minh hợp đồng `actions[]`/`booking{}` đúng như thiết kế, không chứng minh có dịch vụ đặt chỗ thật — điều này phải ghi rõ trong báo cáo, không được gọi là "đã tích hợp".
- Không gọi provider thật, không gọi đồ thị thật; mọi case chạy offline.
- Lệnh dự kiến: `PYTHONPATH=src python -m pytest tests/ai_chat_mvp -q` (repo hiện dùng `uv run`; sẽ chốt khi có test thật).
- Chưa tạo tệp test nào.

## 8. Bằng chứng đã đọc

`ai_service/main.py` (`/chat`, `_router_gate`, `_dispatch_intent`, `route_intent`), `ai_service/domains/jev_intent.py:76-941`, `ai_service/domains/chat_agent.py:34-601`, `ai_service/domains/payloads.py:179-199`, `ai_service/static/travel.html:1495-1560`; `POI_service/app/api/mcp/tools.py:135-144,281-282,596-600`; `POI_service/app/core/domain/get_payload.py:186-254`; dataset `data/primary_20261016/graph_ready_v2/prepared_pois.jsonl` (6367 bản ghi) và `data/primary_20261016/hcm_pois_final.geojson` (6368 feature). Tìm `BOOKING`/`destination_status` trong 3 service: 0 kết quả.

Các con số dataset trong tệp này (6367 bản ghi, 1054 có giờ, 0 menu/rating, 1483 POI Quận 1, "bóng đêm" 0 khớp) được đếm trực tiếp từ `prepared_pois.jsonl` trong phiên này, không lấy từ tài liệu.
