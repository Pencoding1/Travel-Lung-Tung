# Tiến độ Travel AI — Codex, 18/10/2026

**Dự án đang ở phase 2; chưa chạy thí nghiệm chính.** Mã nối lịch sử hội thoại vào API lập lịch đã qua QA offline. Pilot thật mới đạt 1/3 điều kiện: tắt memory đúng và tạo được lịch hai điểm cùng tuyến xe. Lượt chuẩn bị short-term trả HTTP 503 nên dừng; hai điều kiện còn lại chưa đủ bằng chứng.

Pilot đã gửi 3 request, ghi nhận 3 lượt CLI và dọn stack riêng. Codex kiểm tra lại cổng và mã nguồn đều đúng. Nguyên nhân 503 chưa xác định; quyền chạy một lần đã dùng, không tự chạy lại.

OpenCode đang sửa collector theo kế hoạch EXP080 do Codex soạn: chuẩn bị qua `/chat`, lấy lịch có cấu trúc qua `/generate_itinerary`, kiểm tra nguồn và ghi nhận đầy đủ lỗi. Giao thức v5 đã sửa trước primary. Còn QA collector, bằng chứng native cho memory đang bật và đóng băng phiên bản trước khi chạy thí nghiệm.

Các phần đã kiểm chứng có giới hạn:

- Nhập 6.367 POI, 14 nhóm và 3.678.397 cạnh NEAR_BY; giữ rõ giới hạn của nguồn.
- Jev, Go V4.1, chọn phạm vi dữ liệu và routing đi bộ/xe đã chạy thật.
- Bộ nhớ MEM072 đạt 15 kiểm tra với 4 chat thật; đây là bằng chứng riêng, không thay cho bridge mới hoặc H3.
- CORE079 đạt 15 ca ASGI độc lập, 10 ca focused và 357 hồi quy. Model/MCP/Jev được giả lập trong các kiểm thử này.
- Đã đóng băng riêng 20 đầu vào H2; chưa có kết quả H2 chính. Báo cáo tiếng Việt đạt 360 kiểm tra tĩnh với 93 tham chiếu, chưa có kiểm chứng giao diện bằng trình duyệt.

Thứ tự tiếp tục: nhận mã EXP080 và QA → hoàn tất gate native/đóng băng → phase 3 chạy H2/H3/E2/system/adversarial → phase 4 báo cáo và chờ bạn chọn H1 hoặc viết luận án. Chưa có người tham gia H1. Crawler, nguồn xã hội/travel agency và grow-with-user/harness nằm ở phase 5 Finalizing.

[Handoff](E:/Project/TVLT_2026/docs/project/HANDOFF_CODEX_CURRENT_2026-10-18.md) · [Checkpoint](E:/Project/TVLT_2026/docs/project/checkpoints/2026-10-18-core079-partial-native-exp080-active.md) · [Báo cáo tương tác](E:/Project/TVLT_2026/docs/reports/2026-10-18/index.html) · [SG01–SG19](E:/Project/TVLT_2026/docs/project/SG_REQUIREMENT_STATUS_2026-10-18.md)

Toàn bộ mục tiêu chưa hoàn tất. Giá, giờ, nguồn gốc, ranh giới hành chính và usage thiếu vẫn được ghi là chưa biết. Bản tiến độ trước được giữ trong `checkpoints/archive/pre-exp080-CURRENT_PROGRESS_2026-10-18.md`.
