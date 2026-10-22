# Checkpoint — demo chatbot và bản đồ 3D

Codex, 20/10/2026. Đầu mối tiếp tục công việc: Codex lập kế hoạch, QA và nghiệm thu; OpenCode triển khai mã. User ưu tiên demo trọn luồng, chưa chọn H1 hoặc viết luận văn. Crawler/grow-with-user mới thuộc Finalizing phase.

## Đã hoàn thành

- UI127: OpenCode AI-box `aibox/ds/deepseek-flash` (V4.1 theo user) dựng chatbot, thiết lập chuyến đi, MapLibre/OpenFreeMap TP.HCM 3D, ghim đỏ và thẻ POI. Worker dừng đúng ngân sách 480s; không có báo cáo cuối của worker. Codex nghiệm thu dựa trên mã và bằng chứng QA.
- UI129: Go `opencode-go/deepseek-v4.1-flash` sửa hai dòng bảo vệ single-flight khi tạo lịch trình. Cả hai worker đã terminal, có interrupt/wait; không poll hoặc relaunch.
- QA: 8 nhóm Node, 11 kiểm tra catalog/static và 18 kiểm tra race độc lập đạt. Không cộng thành cỡ mẫu khoa học.
- BROWSER130: Chrome headless riêng render thật 123 polygon tòa nhà; desktop/mobile không tràn ngang. Codex đã xem hai ảnh. Không model/Jev.
- BROWSER131: bấm Gửi và Tạo lịch trình trên giao diện với backend thật. Chat và typed API đạt 18 kiểm tra: Jev, source scope, session/memory, xe hơi, hai POI khác nhau, thời gian có múi giờ và tuyến đầy đủ. Hai ghim đúng tọa độ trả về. Dùng 4 Go/4 CLI attempt + 1 Jev; không retry hoặc AI-box fallback.
- BROWSER133: click ghim mở thẻ và click thẻ chọn POI đã đạt trên trình duyệt thật với **hai POI giả lập**. Không có model/Jev thật. Codex đã xem ảnh popup.
- DOC132 cập nhật báo cáo tương tác bằng tiếng Việt và giữ lịch sử kết quả bất lợi.

## Chưa xác nhận

BROWSER131 kết thúc exit1/PARTIAL: timeout sau khi chứng minh hai ghim, trước receipt click/popup. Không đủ dữ liệu xác định timeout ở click hay chờ popup, cũng chưa chứng minh lỗi backend. Không sửa/rerun kết quả đó. BROWSER133 là QA fixture riêng, không biến BROWSER131 thành full pass.

Không có hình học đường đi trong payload backend: UI hiển thị POI và thông tin tuyến, không vẽ đường nối giả thành tuyến đường thật. Giá/giờ mở cửa và feasibility toàn cục còn chưa xác minh. Render headless không phải quan sát tab cá nhân/IAB hoặc nghiên cứu người dùng.

## Tiếp tục phiên sau

1. Đọc checkpoint này, FOUR_PHASE_PLAN.md, EXECUTOR_POLICY.md và brief/review UI127, BROWSER131, BROWSER133. Không đọc raw env/config/auth hoặc dùng lại quyền one-shot cũ.
2. Nếu cần chốt full UI journey, lập ca **không gọi model trước** để quan sát camera/overlay/hit-test cho ghim ở các vị trí bản đồ; kiểm nút `.map-pin` sau camera đứng yên. Không mặc định lỗi từ suy đoán. Chỉ giao OpenCode sửa khi có lỗi tái hiện, một writer và brief Codex chốt trước.
3. Không tự gọi thêm model để lấy kết quả đẹp. Lần live mới phải có kế hoạch/ngân sách riêng, giữ nguyên BROWSER131.
4. Có thể cho người dùng thử giao diện ở http://127.0.0.1:19102/travel nếu dịch vụ vẫn đang chạy. Dịch vụ demo được giữ lại; hai browser QA đã đóng. Không khẳng định uptime tương lai.
5. Giao báo cáo phase4 cùng giới hạn; chờ user chọn H1 hoặc viết luận văn. Không mở Finalizing trước quyết định.

## Bằng chứng và tiến trình

- HTML SHA256: `b4ad71e21ef8c0d6c8a1bd385928ca0ceb910d9e628b0874f05ab587c7a702fe`.
- UI127 SID `ses_ea6cfc9a7ffe1vVYA4U1vX37qC`, handle56725 terminal1; UI129 SID `ses_ea6c55456ffe0MphJQ9mEnUcaJ`, handle11020 terminal0; cả hai có wait0. Không restart.
- BROWSER131 driver `997ffc5e2e58d510bdb61f24f27ffde2f0b301fbc5926120fa2eb2c9e824fc4d`; handle55754 terminal1, owned browser closed. Result/journal/independent review trong `handoffs/BROWSER-131/`; 163 backend pins trước/sau không đổi.
- BROWSER133 handle41926 terminal0, owned browser closed; `handoffs/BROWSER-133/result.json`, `pin-card.png`. Fixture POST bị intercept, không chuyển đến backend.
- Report: `docs/reports/2026-10-18/index.html`, `report-data.json`; DOC132/applied.json là receipt editorial, không phải worker return hoặc live scientific study.

Giữ frozen H2 (119 provenance + 1 gap), H3 (1/15), E2093, TIM097 (5km chậm 27,66%), SYS101 (8 supported/1 inconclusive). SYS119 B2 riêng đã nhận; không gộp thành SYS101 9/9. H1 có 0 người tham gia; luận văn vẫn working draft. Mục tiêu tổng thể IN_PROGRESS.
