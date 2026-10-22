# Checkpoint — quy trình bốn giai đoạn và báo cáo tiếng Việt

Người dùng yêu cầu thu gọn thành: 1 kiểm chứng; 2 hoàn thiện mã theo đề cương; 3 chạy thí nghiệm; 4 báo cáo, rồi chờ người dùng chọn H1 hoặc viết tiếp luận văn. Chỉ đạo này thay thế yêu cầu cũ tự tiếp tục H1/viết luận văn. Đã lưu FOUR_PHASE_PLAN.md và đặt thông báo ưu tiên ở EXECUTION_PROTOCOL.md, NEXT_SESSION_HANDOFF.md.

Codex tập trung kế hoạch, QA và nghiệm thu. OpenCode thực hiện mã/báo cáo bằng kỹ năng cài sẵn. Không mở nhiều gói song song. Hiện chỉ giao OC047: báo cáo tương tác từng mô-đun + kiến trúc bằng tiếng Việt, read-only đối với sản phẩm; được ghi docs/reports/2026-10-18/ và thư mục bàn giao riêng.

OC047 đang chạy process2031, exact session ses_eb4eae415ffeCtfZj1jmrGZK3t, log handoffs/OC-047/events.log. Không chạy lại khi còn sống. Dùng tuyến aibox/ds/deepseek-flash. Phải kiểm tra final reason stop/process exit, artifact/source/evidence/browser QA rồi mới nhận.

Kỹ năng được yêu cầu: C:/Users/duyan/.claude/skills/codebase-analysis/ (SKILL.md, WORKFLOW.md, Gotchas.md) và C:/Users/duyan/.agents/skills/archify/SKILL.md. Giữ xác minh mã; độ dài/auto-init mẫu kỹ năng không được lấn át yêu cầu ngắn của người dùng. Báo cáo không được coi trạng thái cũ trong ARCHITECTURE_AS_IS.md là hiện tại.

Người dùng bổ sung chi phí: AI-box mạnh hơn, có phí, dùng cho việc khó; OpenCode Go thấp hơn, miễn phí theo người dùng, ưu tiên việc đơn giản nếu đúng alias/khả dụng. Go từng báo quota; không giả định hiện dùng được. Không dùng explicit V4.0, không tự đổi cấu hình toàn cục. Giữ OC047 đã chạy, tránh gọi lại tạo phí. Chạy pytest trực tiếp không cần model.

QA độc lập hiện có: 45 passed/2 skipped adapter+source scope (16,87s); 96 passed provider (3,65s). Restricted provider run bị ngắt, không coi là đạt. Xem QA_PHASE1.md cho ma trận trường hợp Codex lập. Chưa đủ nhận toàn bộ các bản giao OC040/042/043/045/046.

Tiếp theo: hoàn thành/duyệt báo cáo OC047, mở overview cho người dùng; kiểm chứng có trọng tâm theo QA_PHASE1.md, rồi mới giao gói sửa cần cho đề cương. Không tự bắt đầu H1 hoặc viết luận văn sau giai đoạn 4.

Chỉ đạo mới hơn: mọi lần bàn giao tiếp theo dùng `/plan` sau khi Codex tự lập kế hoạch; agent chỉ rà soát/thực hiện kế hoạch được giao, không tự lập thay Codex. Kiểm tra hỗ trợ CLI và trạng thái thực tế, không giả vờ bật chế độ chỉ từ văn bản brief. OC047 đã chạy trước chỉ đạo, không khởi chạy lại tạo chi phí.

Làm rõ cuối cùng: người dùng nói `/plan` áp dụng cho **Codex**, không phải yêu cầu OpenCode tự lập/rà soát kế hoạch thay Codex. Ghi chú trước đó về bật `/plan` trong agent đã được sửa trong FOUR_PHASE_PLAN.md. Codex chốt kế hoạch rồi giao agent thực hiện. Không giả vờ thay đổi chế độ nền tảng.

Bổ sung Jev: đã lưu JEV_INTENT_PLAN.md, thêm T055 vào backlog. Tìm thấy kỹ năng Hermes typesafe-ai và xác minh tài liệu TypeSafe chính thức; không khôi phục/trao đổi phiên Hermes. Jev chưa triển khai. OC047 bản đầu terminal exit0, parent phát hiện lỗi lọc CSS và hai cạnh kiến trúc sai; R1 cùng session đang chạy96005 bằng Go V4.1. Lần CLI đầu reject --dir trước modelcall; dùng cwd theo CLI help mới. Go hiện hoạt động; không fallback AI-box. Ghi nhận CUA từ chối file:// vì protocol policy, không bypass bằng server/trình duyệt khác; parent chỉ kiểm tra nguồn và ảnh/receipt có sẵn. Báo cáo cần nói đúng giới hạn kiểm chứng trực tiếp.
