# Codex checkpoint — DEP148 / DEP149 chờ quyền host

Lượt trước là PROGRESS: LIVE143/UI145/B146 và DOC147 đã hoàn tất có giới hạn. Lượt này tiếp tục mục tiêu SG16/T016 bằng kiểm tra định nghĩa deployment hiện tại, không lặp QA app đã đạt.

## Phát hiện mới đã có bằng chứng

Compose integration vẫn là target cũ: bắt buộc Gemini và không khai báo Go/Jev. Provider mặc định là Gemini; nếu bật CLI mà không chốt alias, default code là AI-box có phí. Dockerfile chưa định nghĩa đóng gói OpenCode Linux; không thể giả định binary Windows chạy trong container Linux. Đây là khoảng trống định nghĩa, không phải kết luận đã inspect image.

Root .dockerignore chỉ có5quy tắc, chưa loại env/credential/local runtime khỏi context. COPY cả service directory tạo rủi ro đưa chúng vào image nếu có; chưa kiểm nội dung secret hoặc khẳng định lộ khóa. GraphHopper có context riêng, cần đánh giá riêng.

Cổng17687/18989 đã gán cho native; Compose dùng cùng cổng. Chưa probe occupancy hoặc gọi lại health bị deny. Volume graph riêng là đúng, nhưng chưa có import manifest/bootstrap chứng minh graph có POI; MCP default car không chứng minh foot. latest/readiness/runbook còn lệch mục tiêu. Reviewer độc lập ghi9nhóm gap; parent ghi5nhóm ưu tiên và kiểm lại các nguồn chính.

## Việc tiếp theo đã chốt, chưa chạy

DEP149 brief: chỉ .dockerignore và return.json, OpenCode Go V4.1 tối đa90s; không build/pull/up/engine/model application, không đọc rawenv/config/auth. Chờ user cho phép host CLI cho gói mới do log-path EPERM cũ; không dùng lại quyền UI127. Asyncquestion đã gửi, chưa nhận câu trả lời. Hết thời gian không phải đồng ý. Không dispatch trước quyền.

Sau khi nhận mã: Codex kiểm semantics bằng đường dẫn giả định, source/template vẫn được giữ, không đọc actual secretfiles; chỉ sau đó chuẩn bị gói Compose provider/Linux CLI/ports/bootstrap/readiness. Trước download/build phải xác minh official tools/version và chốt phạm vi/budget/cleanup; không mount primarygraph hoặc dừng demo. Không nhận fullCompose từ cấu hình xanh.

## Bằng chứng và trạng thái

- handoffs/DEP-148/prepared-plan.md
- handoffs/DEP-148/parent-findings.json: sourcehashes,5finding,0Docker/model/secretreads.
- handoffs/DEP-148/independent-gap-review.json:9nhóm mismatch, độc lập read-only.
- handoffs/DEP-149/brief.md: implementation contract, NOT DISPATCHED.

Demo/code/benchmark frozen không đổi. H1=0participants, viết luận văn và Finalizing vẫn chưa được mở. Overall goal IN_PROGRESS. Không model/browser/Docker task nào được khởi chạy trong lượt này. Đây là lần chờ quyền mới đầu tiên của DEP149, chưa đủ điều kiện blocked toàn mục tiêu.

## Follow-up nguồn chính thức

Đã xác minh tuyến OpenCode Linux V2 tồn tại và semantics Dockerignore theo từng context; chưa pin artifact/version/digest hoặc chạy Linux. Go V2 mô tả coding-agent traffic: cần làm rõ suitability cho chatbot tổng quát trước deployment/live cohort mới, không suy quyền sử dụng từ thành công API cũ. Xem DEP-148/official-source-followup.md và source-followup-receipt.json. DEP149 host permission vẫn pending, không process được dispatch.
