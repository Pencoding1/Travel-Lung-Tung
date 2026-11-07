# FT-CHAT-MVP-001 v1.1 — intent, phân giải và dispatch

Trạng thái: **APPROVED / FROZEN**, chủ dự án duyệt trực tiếp trong chat ngày 28/10/2026. Đây là amendment sau freeze v1.0, không sửa byte snapshot cũ.

## Intent và nhãn phụ

Năm intent chính: `CHITCHAT`, `BOOKING`, `PLAN`, `MANAGE_SAVED`, `MANAGE_MEMORY`.

- CHITCHAT: `LOOKUP` (thông tin có căn cứ), `RECOMMEND` (gợi ý theo preference), `ROUTE` (đường đi thật). Trò chuyện xã giao không bắt buộc một trong ba nhãn này hoặc truy xuất POI.
- PLAN: `CREATE` hoặc `MODIFY`. MODIFY áp vào lịch đã xác định, kiểm quyền/đối tượng, tính lại tuyến và kiểm định lại lịch. Không biến chỉnh lịch đang xem thành cập nhật bản lưu nếu chức năng lưu chưa hỗ trợ cập nhật.
- MANAGE_SAVED: `SAVE`, `LIST`, `OPEN`, `DELETE`; chỉ dữ liệu thuộc người dùng. Không thêm chia sẻ hoặc update nội dung bản lưu.
- MANAGE_MEMORY: `VIEW_PROFILE`, `UPDATE_PROFILE`, `DELETE_PROFILE`, `CLEAR_SESSION`. Xóa phiên và hồ sơ là hai hành động khác nhau; tuân thủ auth và memory enable đã duyệt.
- BOOKING giữ contract riêng: query loại dịch vụ, chọn Book Ngay → screen booking; lệnh đặt ra ngoài fake. Không đặt chỗ thật.

## Năm lớp logic trong cùng AI service

1. Claim Extractor: tách ý độc lập, thực thể, ràng buộc, điều kiện và lời rút lại; giữ tham chiếu câu gốc, không tự thêm yêu cầu.
2. Intent Classifier: gán intent/nhãn phụ cho từng yêu cầu ứng viên, không gán một nhãn duy nhất cho toàn bộ câu có nhiều yêu cầu.
3. Intent Resolver: dùng ngữ cảnh xác định đối tượng và việc cần làm ngay. `NEEDS_CLARIFICATION`, `MULTIPLE_ACTIONS`, `CANCELLED` là trạng thái theo từng yêu cầu, không phải intent nghiệp vụ. Khi đủ rõ, yêu cầu được chọn đi tiếp; yêu cầu bị hủy không làm mất yêu cầu khác còn hiệu lực.
4. Dispatch Gate: kiểm dữ liệu bắt buộc, đối tượng, quyền, scope và xác nhận người dùng theo feature trước khi gọi handler. Không để model vượt quyền hoặc tự xác nhận phương án.
5. Feature Handler: thực hiện chức năng được cho phép; trả kết quả có evidence, trạng thái và nhật ký hành động. Xử lý lỗi không tạo dữ kiện giả.

## Invariant và tương thích

- Một hành động cùng câu hỏi: hành động chính thắng, câu hỏi giữ làm context. Nhiều hành động ngang hàng chưa rõ ưu tiên: hỏi thứ tự, không chạy tất cả.
- Rút Booking nhưng vẫn yêu cầu gợi ý: chỉ Booking CANCELLED; RECOMMEND còn hiệu lực.
- Entity mơ hồ hoặc thiếu quyền: không gọi handler có side effect. History/model không thay quyền sở hữu, scope hoặc mode hiện tại.
- LLM có thể hỗ trợ hiểu ngôn ngữ; mã xác định giữ quyết định cho phép thực thi. Đây là trách nhiệm logic, không yêu cầu thêm 5 service/agent.
- Jev hiện dùng nhãn cũ; khả năng hỗ trợ schema mới NOT VERIFIED cho tới kiểm định thật. Không giả kết quả hoặc âm thầm fallback provider.
- Tên field kỹ thuật của output được chọn khi hiện thực; test phải kiểm hành vi/trace quan sát được, không suy ra schema đã triển khai.
- F-UI thiết kế cuối cùng HOLD. Không mở H1, Finalizing, crawler, booking thật hoặc sửa primary.

## Test và provenance

Case tương ứng: `tests/behavior_specs/chat_v1_1_cases.json`. Đây là đặc tả nghiệm thu, không phải kết quả test PASS. Các ca positive cần identity, graph, routing và model thật; thiếu dependency ghi BLOCKED, không thay mock.

Phiên bản hiện tại được bảo toàn trong `legacy/`, Git ignored. Snapshot source không đảm bảo dependency ngoài máy hoặc provider còn hoạt động; kết quả lỗi live trước giữ nguyên.
