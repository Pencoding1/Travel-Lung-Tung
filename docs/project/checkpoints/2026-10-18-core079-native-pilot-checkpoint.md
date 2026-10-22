# Checkpoint — CORE079 / Codex — 18/10/2026 23:10 (+07)

Trạng thái cập nhật: **pilot đã kết thúc exit 1; đạt 1/3 điều kiện, chưa nghiệm thu toàn bộ native bridge**. Receipt độc lập: `../handoffs/CORE-079/parent-native-result-review.json`. Disabled bypass đạt với hai POI hợp lệ, tuyến car 2.521km/3 phút và giờ đến/đi thật; giá/giờ mở cửa vẫn unknown. Short-term preparation trả HTTP503/unavailable; dừng trước typed score và toàn bộ two-tier. Tổng 3 request đã gửi, 3 CLI attempts biết được; không đủ dữ liệu xác định nguyên nhân 503 hoặc tổng billing. Stack đã dọn, kiểm tra lại cả hai cổng 19601/19602 đều không lắng nghe; source bindings giữ nguyên. Quyền một lần đã dùng, không chạy lại. Phần “đang chạy” dưới đây là bản chụp lúc23:10, đã được kết quả cuối này thay thế.

## Đã hoàn thành

- CORE079 nối working memory của `/chat` vào `/generate_itinerary`; nghiệm thu offline có giới hạn: 15 ca ASGI độc lập, 10 ca focused, 357 hồi quy đạt; 47 binding được bảo vệ giữ nguyên. Receipt: `../handoffs/CORE-079/parent-offline-acceptance.json`.
- Script pilot đã review SHA256 `3ebb7b7e161c16ffd400e2d2c8cfd550ce71d62b055fcc8cb2759c20b17c0873`; 2 kiểm tra điều phối giả lập đạt. Không tính các kiểm tra này thành kết quả model thật.
- Hermes handle 68862/session `20261018_230043_468f24` kết thúc client exit 0 nhưng báo **BLOCKED_PRECHECK_GUARD_DENIAL**. Script chưa khởi chạy, 0 request ứng dụng. Báo cáo nằm tại `E:/Agent_Artifact/TVLT_2026/2026-10-18/typed-itinerary-native-pilot/`. Giả thuyết `.exe` bị nhận nhầm thành download là suy luận, chưa chứng minh nguyên nhân bằng mã guard.
- Người dùng sau đó cấp quyền mới: **“Cho phép Codex chạy đúng lệnh một lần”**. Codex xác minh hash và đã khởi chạy đúng lệnh một lần; không đổi hoặc tắt guard. Quyền này đã dùng, không được chạy lại tự động.

## Tác vụ đang chạy — không khởi chạy bản thứ hai

Lệnh: `E:/Project/TVLT_2026/.venv-mcp-validation/Scripts/python.exe -X utf8 E:/Project/TVLT_2026/docs/project/handoffs/CORE-079/parent_native_pilot.py`

- Handle **85489**; tiếp tục đọc bằng `write_stdin`, không gọi lại lệnh.
- Thư mục kết quả: `E:/Project/TVLT_2026/docs/project/handoffs/CORE-079/qa-work/native-pilot-9723e621f760/`.
- Tối đa 6 request sinh model, `opencode-go/deepseek-v4.1-flash`; không retry, không paid fallback. Stack riêng 19601/19602, danh tính/SQLite giả lập, cleanup phần task sở hữu.
- Ba điều kiện engineering: disabled bypass / short-term / two-tier; `/chat` chuẩn bị rồi typed itinerary. Đây **không phải H3 primary**, không H1, không bằng chứng hiệu quả hay tiết kiệm token.
- Chỉ đọc kết quả đóng/sanitized; không dump log helper, env, config, auth hoặc raw session export.

## Việc phiên tiếp theo phải hoàn thành

1. Thu exit code đúng handle, đọc `results.json`, ledger và projection đã sanitize; kiểm tra source binding, provider/input flags, selected route và giờ thật; kiểm tra cleanup cổng 19601/19602. Giữ mọi failure/missingness. Không coi client exit 0 của Hermes là pilot pass.
2. Cập nhật checkpoint này, current handoff và evidence register bằng kết quả thật. Nếu thất bại, không dùng lại quyền chạy một lần.
3. Sau native bridge đạt mới sửa protocol H3 trước chạy, thích nghi collector typed scoring và xử lý 4 focused failures; review baseline mới/full freeze. Không tắt old hash gate, không sửa receipt cũ/frozen H2 để qua gate.
4. Hoàn thành phase 3 thí nghiệm H2/H3/E2/system/adversarial rồi phase 4 báo cáo. H1 chưa có người tham gia; chờ người dùng chọn H1 hoặc viết luận án. Phase 5 Finalizing chứa crawler/social/travel agency/grow-with-user/harness.

Codex tiếp tục giữ vai trò lập kế hoạch, QA và nghiệm thu; OpenCode/Hermes thực thi theo kế hoạch `/plan` do Codex soạn. Không mở rộng scope hoặc chạy lại cả bộ QA đã đạt. Không reset/clean/commit/push; không đọc secrets; không ALL/wildcard/global guard edits. Xem master handoff và SG01–SG19/AC01–AC12 để tiếp tục toàn bộ backlog còn lại.
