# Áp dụng biên nhận — 28/10/2026

- Receipt: `receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb`.
- SHA-256 biên nhận nguyên bản: `e041ae5a7256e0a08f3bb1eda363e3018aed226e6a0cfe0477383d8f613eb384`.
- Snapshot được duyệt: `TVLT-BEHAVIOR-REVIEW-20261028-v2`, SHA-256 `d1b84d354616f9d83f48c9432059c21aff92b44ed81abfd165d406f5f6a97f83`.
- Chỉ mục được chọn: **TEST-GATE**.
- Hành động: `approve`; lựa chọn nguyên văn: **Duyệt kiến trúc và cổng nghiệm thu**; comment: chuỗi rỗng.

## Đã áp dụng vào tài liệu

`TA-CHAT-001` chuyển PROPOSAL → APPROVED. Cổng được duyệt: 20 test đặc tả + 100 test QA giữ riêng, cả hai bộ đạt; kiểm tĩnh sạch; mutation proof từng họ D1–D10; không sửa kỳ vọng để lấy xanh. Booking theo contract đã chốt, không dùng fake command để chứng nhận đặt chỗ thật.

Cập nhật trạng thái tương ứng trong test plan và sổ rà soát. Form dùng snapshot v3, TEST-GATE đã duyệt; mọi mục khác giữ nguyên so với v2, bao gồm F-UI HOLD.

Biên nhận không được sửa: `application_status=NOT_APPLIED` trong receipt là dữ liệu tại thời điểm gửi, không viết đè thành DOC_APPLIED. Kết quả áp dụng hiện hành nằm trong `application.json` đi kèm báo cáo này.

## Kiểm chứng và giới hạn

Đã đối chiếu byte hash receipt, byte hash snapshot v2, nội dung snapshot trong receipt, selected_ids/decisions và diff v2→v3 chỉ TEST-GATE. Không sửa mã sản phẩm, test hoặc expected, không chạy lại bộ 120 test, không tạo receipt owner mới. Baseline RED cũ giữ nguyên. Không còn câu hỏi PENDING trong danh sách hiện có không có nghĩa implementation đã đạt hoặc toàn bộ schema kỹ thuật đã freeze.
