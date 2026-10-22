# QA giai đoạn 1 — kiểm chứng mô-đun

Codex xác định hành vi cần kiểm tra và duyệt kết quả. OpenCode hiện thực kiểm thử/sửa mã theo từng gói. Kiểm thử tự động được chạy trực tiếp, không cần gọi model.

| Mô-đun | Tình huống cần kiểm chứng | Điều kiện đạt |
|---|---|---|
| Chuẩn bị dữ liệu | Đầu vào bị sửa, dòng trùng, registry đổi phiên bản, trường bị mất | Từ chối dữ liệu sai trước khi ghi; giữ 6.368 chỉ mục và 6.367 ứng viên; không ghi đè bản đóng băng |
| Adapter graph-ready | Hash đúng/sai; thay cấu hình kỳ vọng ở chế độ real; so sánh từng trường | Chế độ real chỉ nhận đúng bản đã duyệt; thêm metadata không đổi giá trị gốc |
| Graph và nguồn | Metadata sai POI/hash; tạo hai POI thật rồi rollback; chạy lại nhập | Không rò dữ liệu sai nguồn; đúng ID/category; không tăng bản trùng; trạng thái sau rollback được xác nhận |
| Không gian | Qua kinh tuyến 180°, gần cực, đúng biên 3 km, radius cũ không tương thích | Không bỏ sót điểm trong bán kính; quyết định cuối dùng khoảng cách đầy đủ; không xóa trước khi kiểm tra radius |
| MCP và chọn vùng | Cùng tên vùng khác snapshot; kết hợp vùng nguồn với địa giới hiện tại; metadata hỏng | Không lẫn snapshot/vùng; từ chối phạm vi mâu thuẫn; trả giới hạn và dữ liệu chưa xác minh rõ ràng |
| AI/model | Timeout, hủy tác vụ, đầy hàng đợi, tool lồng nhau sai kiểu, tham số model | Không mất permit/chạy vượt giới hạn; tool sai không thực thi; cấu hình và provenance đúng model |
| Planner/validator | Thiếu giờ/giá/tuyến, ngân sách cộng dồn, thời gian ăn/ngày, hướng tuyến | Không bịa dữ kiện; kiểm tra ràng buộc độc lập; không gọi heuristic no-plan là chứng minh vô nghiệm |
| Bộ nhớ | Hai người/hai phiên; ghi đồng thời; xóa và CAS/version; khởi động lại | Không lộ chéo; không mất cập nhật âm thầm; trạng thái lưu trữ và giới hạn rõ ràng |
| Backend/bản nháp | Token sai/người khác, SQLite lỗi, thiếu schema, dữ liệu chưa khả thi | Phân quyền đúng; readiness trung thực; lỗi có kiểm soát; lưu nháp không chứng nhận lịch trình hợp lệ |
| Tuyến đường | Health từ Windows, car/foot, chiều ngược, điểm snap xa, HTTP lỗi | Phân biệt tuyến thật/đường thẳng; giữ profile và đơn vị; không âm thầm dùng fallback |
| Thu thập/đánh giá thí nghiệm | Phiên sai, thiếu usage, lần chạy thất bại, resume, dữ liệu synthetic | Không loại thất bại để làm đẹp kết quả; denominator rõ; không trộn synthetic với quan sát chính |
| Báo cáo tương tác | Mở offline, mọi mô-đun, tab giai đoạn, bằng chứng, màn hình nhỏ | Tiếng Việt dễ đọc; không link hỏng/JS lỗi; không gắn nhãn đã kiểm chứng cho bản giao chưa duyệt |

## Lần chạy độc lập 18/10/2026

- `tests/primary_snapshot_adapter tests/source_snapshot_scope`: **45 passed, 2 skipped, 16,87 giây** trong `.venv-validation`. Hai mục skip là giới hạn phụ thuộc/môi trường cần đọc trước khi nhận đầy đủ, không được tính là đã đạt.
- `tests/ai_provider`: **96 passed, 3,65 giây** trong `.venv-ai-validation`, chạy bình thường trên host. Lần chạy môi trường hạn chế trước đó bị treo lúc thu thập, đã ngắt; không tính là đạt.
- Đây là kiểm thử offline, không phải xác nhận toàn bộ tích hợp/live provider. Còn cần đọc assertions và các probe độc lập; số bài kiểm thử không phải số mẫu thí nghiệm.

## Lỗi phát hiện qua probe độc lập

**QA-DATA-01 — ràng buộc hash chế độ real có thể bị thay bằng tham số thư viện.** Gọi `prepare_snapshot` với bản sao `REAL_EXPECTATIONS` trỏ đến bản manifest chỉ thêm một newline và hash mới vẫn được chấp nhận `real=True`, trả 6.367 bản ghi. Đầu vào đóng băng không thay đổi; không ghi graph hay output graph-ready. CLI dùng hằng mặc định vẫn có ràng buộc hash: đây là lỗ hổng hợp đồng API thư viện, không phải kết luận dữ liệu hiện có đã bị sửa.

Bằng chứng: `handoffs/OC-043/parent-real-profile-binding-probe.json`. Ca hồi quy do Codex viết: `handoffs/OC-043/parent_real_profile_binding_regression.py`. Cần sửa ở giai đoạn 2: cố định hồ sơ real ở ranh giới API và giữ chế độ fixture tách biệt, thêm ca từ chối trước khi tạo output. Chưa giao thêm agent sửa trong khi OC047 còn chạy.

**QA-ROUTING-01 CONFIRMED:** actual configured foot profile fails through MCP function against native11.1 engine (400 without ch.disable); car succeeds, explicit flexible foot routes both directions pass. Injected synthetic POI repo, real HTTP. Root14mocktests passed but miss this real capability/config interaction. T060phase2, not full routing acceptance.

18/10 current reconciliation: audit findings đã đủ chốt phạm vi sửa và chuyển trọng tâm phase2; xem checkpoints/2026-10-18-phase2-focus.md. QA-DATA-01 fixed bounded24tests; QA-ROUTING-01 fixed profile-aware routing và RT064plannerintegration actualcanary. T051/fullimport/deployment còn mở; không suy audit xong là toàn hệ đạt.
