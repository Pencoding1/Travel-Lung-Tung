# Handoff cho agent hỗ trợ — Travel AI

**Chủ trì hiện tại: Codex trong chat này.** Codex đã kiểm tra hệ thống, lập kế hoạch bàn giao, thiết kế QA và kiểm chứng các kết quả ghi dưới đây. Hermes/OpenCode thực hiện các gói được giao; không coi mọi code hoặc kết quả của executor là đã được Codex nghiệm thu.

Workspace: `E:/Project/TVLT_2026`. Ngày18/10/2026, Asia/Saigon. **Dự án chưa hoàn tất; đang phase1 — kiểm chứng.**

## Quyết định của người dùng

Làm theo bốn phase: **kiểm chứng → hoàn thiện code → thí nghiệm → báo cáo**. Sau phase4, chờ người dùng chọn H1 hoặc viết tiếp luận văn. Hiện chưa có người tham gia H1.

Codex lập kế hoạch trước mỗi bàn giao (`/plan` workflow); executor thực hiện, không tự đổi scope hoặc tiêu chí. Trừ websearch, ưu tiên Hermes cho thực thi/OS/test/báo cáo. Hermes có thể gọi OpenCode coding, Codex cũng được bàn giao trực tiếp OpenCode. Dùng Hermes `--provider aibox --model ds/deepseek-flash`; OpenCode AI-box `aibox/ds/deepseek-flash`, V4.1 theo người dùng; không tuyến explicitV4.0. AI-box tính phí: không gọi lặp hoặc dùng model chỉ để chạy lệnh xác định.

Artifact executive: `E:/Agent_Artifact/TVLT_2026/YYYY-MM-DD/<ten-sub-agent>/`. Mỗi gói có brief, session/process thật và evidence. Checkpoint sau task lớn/phase quan trọng.

## Trạng thái đã kiểm chứng

| Phần | Thực trạng |
|---|---|
| Dữ liệu chính | 6.368 feature nguồn → 6.367 ứng viên đã chuẩn bị, 1 bản trùng chính xác. Chưa phải 6.367 POI đã nhập graph. |
| Graph thật | Canary hai POI thật qua repository/source/NEAR_BY đạt và rollback sạch. Chưa full import, durability hoặc Docker. |
| Tuyến đường | GraphHopper11.1 trả tuyến car/foot hai chiều khi dùng đúng tham số. Hàm ứng dụng cho car đạt; foot còn lỗi400 vì thiếu chế độ flexible khi chưa có CH. |
| Chọn nguồn/MCP | 36test offline đạt; graph thật khám phá snapshot/vùng thành công. Truy vấn POI qua MCP lỗi JSON serialization của date `provided_at`; cần sửa. |
| Báo cáo | Có tổng quan tương tác tiếng Việt, chín module và sơ đồ nhúng. 142kiểm tra tĩnh đạt; iframe mới chưa QA render do browser file:// gate. |
| Thí nghiệm | Chưa chạy bộ chính H2/H3. Các mẫu chẩn đoán cũ không thay thế thí nghiệm đã đăng ký. |

Không dùng Ollama/local LLM để phân loại intent: **Jev/TypeSafe đã chốt nhưng chưa triển khai**. Không đổi model sinh nội dung chỉ vì thay bộ phân loại.

## Backlog ưu tiên

| Ưu tiên | Việc cần làm tiếp |
|---|---|
| P0 — T062 | Hai script chống lộ secret: chặn trước tool execution và đọc metadata biến an toàn. Hermes đang viết; Codex QA, rồi mới giao activation hook. Chưa được gọi là guard đã bật. |
| P0 — T057 | Pipeline POI xã hội/web: tên + địa chỉ + mô tả hoặc review, provenance, quality/dedup/quarantine. Bản đầu chưa nghiệm thu. Sáu probe offline xác nhận lỗi namespace ID, thiếu địa chỉ, ghép sai địa chỉ, tọa độ sai, lỗi echo canary và policy fetch gate. |
| P1 — T058 | Hoàn thiện crawler HTTP/web tĩnh; sửa giới hạn byte trước read, DNS pinning/redirect/proxy, kiểm tra license trước fetch. Phải có nguồn reusable thật và CLI/test chạy được. |
| P0 — T061/T049 | Sửa JSON date serialization của source-result qua service/MCP; chạy lại canary graph thật, giữ source scope đến AI/planner. |
| P0 — T051 | Adapter CLI mặc định còn thêm `--pure`, CLI2.0.32 không hỗ trợ. Sửa capability/isolation/tool controls/usage trước live model experiments. |
| Bắt buộc — QA-DATA-01 | Cố định real snapshot binding ở API thư viện; không cho caller thay expected hash để nhận dữ liệu khác dưới nhãn real. |
| P1 — T060 | Sửa routing mode theo profile và kiểm tra foot qua ứng dụng thật; không fallback đường thẳng âm thầm. |
| Bắt buộc | Full import6.367ứng viên sau QA, lineage web server T050, tích hợp dịch vụ/Jev/source scope, đóng băng phiên bản rồi mới chạy H2/H3. |
| P2 — T056/T059 | Memory preference: nghiên cứu đã giao, đề xuất lớp mỏng tái dùng nền tảng hiện có; chỉ triển khai sau đủ4phase, không đợi luận văn. Nguồn web động/chống bot khó deferred; không bypass. |

## Phân chia sub-agent và chủ sở hữu

| Gói / agent | Quyết định và việc còn lại |
|---|---|
| Native `embed_system_diagram` / OC048 | Đã xong, đã release scope. Sơ đồ nhúng vào báo cáo; QA tĩnh có giới hạn đã nhận. Không tự mở lại hoặc sửa HTML đang được Codex quản lý. |
| Native `agent_memory_p2_research` / RS049 | Đã xong nghiên cứu Hermes + Letta + LangGraph. Khuyến nghị còn là proposal; không coding/migration P2 lúc này. |
| Native `social_poi_ingest` / OC050 | Đã dừng, không còn writer. Code giữ lại, chưa nhận P0/P1; graph import0. Chuẩn bị correction theo probe Codex sau gói guard. Không resume phiên cũ chứa thông tin nhạy cảm. |
| Hermes HM053 — đang chạy | Xây đúng hai script + test synthetic bằng file tools. Process66480; session `20261018_022217_f03a78`. Owner: Codex. Không chạm các đường dẫn này: `scripts/agent_guardrails/`, `tests/agent_guardrails/`, artifact `secret-guardrails/`. Chờ terminal, root QA rồi giao cài hook bảo toàn domain guard. |
| Agent hỗ trợ nhận file này | Bắt đầu read-only: rà soát đề xuất sửa MCP date serialization và luồng giữ source scope vào AI/planner; trả file:dòng, test cần có và phạm vi sửa cho Codex. **Chưa tự sửa, chạy model, tạo agent hoặc chạm scope HM053.** Nếu muốn nhận implementation, cần Codex chốt file ownership trong brief tiếp theo. |

Ba native sub-agent trên được người dùng yêu cầu riêng; không tự sinh thêm native agent/chat. Hermes/OpenCode là executor CLI, không phải chat mới.

## An toàn và nguồn dữ liệu

Khóa OpenCode Go bị lộ trước đó đã retired **theo xác nhận người dùng**. Không đọc file incident riêng tư, không gửi vào prompt hoặc báo cáo. Không dò env/auth/history để tìm sessionID; Codex ghi ID từ CLI. Khi cần kiểm tra secret, dùng safe metadata helper sau khi QA; không in giá trị/prefix/suffix/hash.

Dùng local `allowed_domains.txt`; hook cài hiện đọc `allowed_domain.txt` nên có bản tương thích cùng folder. Không `ALL`, không sửa global allowlist. Social task chỉ duyệt Wikivoyage cho public text có attribution/sharealike; global/domain guard vẫn có hiệu lực, local list không phải sandbox. VietnamTravel reuse bị hạn chế: không fetch thêm/không nhận vào dữ liệu tin cậy. Không đổi lệnh/tool để né deny, không CAPTCHA/login/stealth bypass.

## Đọc tiếp / bằng chứng

- `docs/project/FOUR_PHASE_PLAN.md`, `EXECUTOR_POLICY.md`, `BACKLOG.md`, `NEXT_SESSION_HANDOFF.md`.
- Báo cáo: `docs/reports/2026-10-18/index.html`.
- Guard đang xây: `docs/project/handoffs/HM-053/brief.md`.
- Social QA: `docs/project/handoffs/OC-050/parent-contract-probes-20261018.json`, `codex-qa-targets.md`.
- MCP thật: `docs/project/handoffs/OC-045/parent-mcp-real-canary-20261018-serialization.json`.
- Routing: `docs/project/handoffs/OC-042/parent-final-http-20261018-host/summary.json`.

**Phân biệt bằng chứng:** test mock không phải graph thật; canary rollback không phải import đã commit; artifact có file không tự chứng minh nghiệm thu; proposal không phải tính năng đã triển khai. Giữ nguyên dữ liệu primary và thay đổi người dùng trong working tree.
