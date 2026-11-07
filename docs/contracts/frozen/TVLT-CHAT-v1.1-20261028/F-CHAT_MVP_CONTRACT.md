# Feature: Agent Chat — MVP Behavior Contract

- **ID:** `FT-CHAT-MVP-001` · **Version hiện hành:** `1.1` (amendment được duyệt 28/10/2026)
- **Amendment hiện hành:** [CHAT_INTENT_AMENDMENT_2026-10-28.md](CHAT_INTENT_AMENDMENT_2026-10-28.md). Năm intent và năm lớp xử lý ở amendment thay phần intent/pipeline tương ứng bên dưới; nguyên văn v1.0 giữ để truy vết. Snapshot frozen v1.0 không đổi.
- **Status:** `APPROVED` — chủ dự án tự định nghĩa và giao làm cơ sở cho test
- **Owner/approver:** chủ dự án (người dùng) · **Ngày ghi vào repo:** 2026-10-22
- **Nguồn:** nội dung do chủ dự án cung cấp trong phiên 2026-10-22 (nguyên văn bên dưới)
- **Quan hệ:** thay thế phần định nghĩa intent của `FT-CHAT-001 v0.2` (CHITCHAT/TRAVEL/UNCERTAIN). Ba intent hiện hành: `CHITCHAT`, `BOOKING`, `PLAN`.
- **Điều contract này không định nghĩa:** schema response, tên field quan sát được, payload bàn giao sang Booking/Itinerary Planning. Các điểm này ghi ở `F-CHAT_MVP_TEST_PLAN.md` §2 và §6.

---

## Nội dung contract (nguyên văn)

### 1. Feature Definition

Agent Chat là giao diện hội thoại hỗ trợ người dùng tìm kiếm thông tin du lịch tại TP.HCM, yêu cầu đặt dịch vụ và khởi tạo kế hoạch du lịch.

Feature hỗ trợ ba nhóm intent:

| Intent | Chức năng |
|---|---|
| `CHITCHAT` | Hỏi đáp, tìm kiếm thông tin, giá cả, địa điểm, dịch vụ |
| `BOOKING` | Khởi tạo yêu cầu đặt bàn, vé phương tiện, phòng hoặc dịch vụ khác |
| `PLAN` | Khởi tạo quy trình lập lịch trình du lịch |

Booking types: `table`, `vehicle`, `room`, `service`.

Agent Chat chỉ điều phối sang Booking hoặc Itinerary Planning; việc thực hiện đặt dịch vụ và sinh lịch trình thuộc các feature tương ứng.

### 2. Intent Resolution

**Pipeline:** User Message → Claim Extraction → Intent Classification → Intent Resolution → Feature Handler.

**B1 — Claim Extraction**

- Trích xuất các yêu cầu và thông tin thành atomic claims, mỗi claim biểu diễn một ý độc lập.
- Giữ nguyên các thực thể, địa điểm, ràng buộc và ngữ cảnh cần thiết.
- Không suy diễn thêm yêu cầu chưa được người dùng cung cấp.

**B2 — Significant Intent**

- Xác định intent chính dựa trên hành động mà người dùng yêu cầu thực hiện ngay.
- Các claim khác được giữ làm context, không tự động kích hoạt feature khác.
- Nếu không xác định được significant intent giữa nhiều yêu cầu, hỏi người dùng muốn thực hiện yêu cầu nào trước.
- Không thực hiện nhiều intent trong cùng lượt nếu chưa được xác nhận.

### 3. CHITCHAT

**B3 — Grounded Answer**

- Xác định phạm vi và đối tượng của câu hỏi.
- Truy xuất thông tin từ Knowledge Database trước khi trả lời.
- Chỉ đưa ra thông tin thực tế có căn cứ từ dữ liệu truy xuất.
- Đối với câu hỏi về địa điểm, địa điểm phải tồn tại trong Knowledge Database.
- Nếu địa điểm không tồn tại hoặc không có dữ liệu đủ để trả lời, thông báo không có thông tin phù hợp; không tự suy đoán.

### 4. BOOKING

**B4 — Booking Intent Extraction**

Khi người dùng thể hiện yêu cầu đặt dịch vụ, Agent trích xuất:

```json
{
  "intent": "BOOKING",
  "type": "vehicle | table | room | service",
  "destination": "entity_id | null",
  "destination_status": "FOUND | NOT_FOUND | UNSPECIFIED"
}
```

- `FOUND`: Đối tượng đặt dịch vụ được xác định trong database.
- `NOT_FOUND`: Người dùng nêu đối tượng nhưng database không tìm thấy.
- `UNSPECIFIED`: Người dùng chưa cung cấp đối tượng cụ thể.
- Không tự tạo entity không tồn tại.
- Chuyển yêu cầu sang Booking Feature sau khi xác định intent và đối tượng.

### 5. PLAN

**B5 — Planning Input**

- Nhận diện các trường thông tin lập lịch trình đã có trong hội thoại: nhu cầu, địa điểm, ngân sách và sở thích.
- Điền trước các trường có dữ liệu.
- Hiển thị form cho phép người dùng bổ sung hoặc chỉnh sửa.
- Cho phép các trường tùy chọn nhận giá trị `null`.

**B6 — Scenario Generation**

Nếu người dùng không cung cấp đủ thông tin:

- Tạo ít nhất ba phương án đề xuất từ các preference đã cung cấp.
- Các phương án phải có sự khác biệt có ý nghĩa.
- Cho phép người dùng chọn và chỉnh sửa phương án.
- Không tự xác nhận phương án thay người dùng.

**B7 — Planning Handoff**

Sau khi người dùng xác nhận:

- Chuyển dữ liệu đã xác nhận sang Itinerary Planning.
- Kích hoạt quá trình lập lịch trình.
- Điều hướng sang giao diện Itinerary Planning.

### 6. Global Constraints

- Không tự thực hiện Booking hoặc Planning khi người dùng mới yêu cầu thông tin.
- Không tạo dữ liệu thực tế không có căn cứ.
