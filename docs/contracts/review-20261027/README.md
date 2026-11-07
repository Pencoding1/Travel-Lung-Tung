# Form duyệt behavior tổng hợp — 27/10/2026

Mở: http://127.0.0.1:19127/ (loopback, không publish).

25 mục: 11 chức năng, 8 điều khoản Chat, quy tắc Chat đã chốt, 2 quyết định bổ sung và 3 mục phạm vi/quy trình. Snapshot v3 ngày 28/10: 24 mục đã duyệt, 1 HOLD, 0 PENDING là trạng thái behavior được ghi nhận, không phải tiến độ triển khai. Snapshot v1/v2 giữ nguyên để đối chiếu; biên nhận TEST-GATE được áp dụng tại `applications/receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb/`.

Nội dung do Codex tổng hợp từ contract và quyết định trực tiếp trong chat. Học lại cơ chế selected_ids, xác nhận/sửa/giữ hoãn và receipt bất biến từ snapshot School News Monitoring; không khôi phục hoặc sử dụng runtime, secrets hay dịch vụ của dự án tham chiếu.

## Dùng form

- Chọn mục cần gửi, chọn quyết định và ghi chú. Mục đã duyệt/HOLD không tự được chọn.
- Nút xem lại cho xem danh sách chính xác trước khi gửi.
- Chỉ gửi thành công mới ghi receipt vào `receipts/`; receipt chứa snapshot server/hash và lựa chọn, comment nguyên văn. Không tự áp dụng vào contract.
- Nháp lưu theo snapshot trong trình duyệt; xuất nháp JSON không phải phê duyệt.
- Báo Codex đọc biên nhận sau khi gửi; không có callback hoặc tự động đánh thức chat.

## Khởi động lại nếu cần

Từ repo: `.venv/Scripts/python.exe docs/contracts/review-20261027/serve.py`

Form phục vụ các route cố định `/`, `/snapshot`, `/submit`; chỉ bind 127.0.0.1. Không có external resource hoặc gọi provider/model.

## Kiểm tra và giới hạn

- 14 kiểm tra validation offline đã đạt trên snapshot trước (`qa-result.json`); harness giả định TEST-GATE PENDING nên cần fixture QA riêng nếu chạy lại sau phê duyệt. Không sửa expected/test trong lượt áp dụng biên nhận.
- 8 kiểm tra HTTP local đã đạt trên snapshot trước (`qa-http-result.json`), gồm origin/host, kiểu payload, traversal, stale snapshot và receipt đúng snapshot/chỉ selected IDs. Đây không phải phép chạy lại trên v3.
- Hai receipt trong `qa-synthetic-receipts/` là synthetic QA, KHÔNG PHẢI PHÊ DUYỆT CỦA CHỦ DỰ ÁN. QA không tạo receipt trong `receipts/`.
- Đã mở và xem trang thực trong IAB; trạng thái 0 mục chọn gửi. Chưa bấm lựa chọn/submit thay owner; chưa kiểm tương tác submit trên browser hoặc tất cả viewport.
- Dispatch OpenCode Go bị automatic approval review từ chối vì quyền xuất nội dung brief chưa có. Không khởi chạy task đó, không gửi brief qua executor khác; Codex hoàn thiện form bằng công cụ local. Không đổi mã sản phẩm, contract approval hoặc frozen tests.
- `brief.md` là kế hoạch dispatch ban đầu, không phải worker return hoặc chứng nhận nghiệm thu.
