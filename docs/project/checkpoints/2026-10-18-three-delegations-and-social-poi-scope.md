# Checkpoint — ba gói được người dùng yêu cầu,18/10/2026

## Trạng thái và chủ sở hữu
- OC048 nhúng sơ đồ: native /root/embed_system_diagram đã xong, OpenCode Go process80652 terminal exit0, session ses_eb4cb2850ffe6yHG46h7RkzKny. Root chạy lại17/17staticchecks và142reportchecks/48source refs đạt, hash diagram/spec giữ nguyên. Chấp nhận mã/cú pháp có giới hạn; không QA iframe render do file:// policy gate, không workaround. Báo cáo: docs/reports/2026-10-18/index.html.
- RS049 Agent Memory P2: nghiên cứu Hermes + Letta + LangGraph đã giao. Root đã đọc recommendation/report/sources, mở nguồn chính chủ để đối chiếu điểm quyết định: Hermes curated profile/frozen snapshot và cảnh báo shared home; Letta README pinned xác nhận V1server retired và current harness letta-code; LangGraph stores. Đồng ý hướng nghiên cứu lớp memory mỏng tái dùng nền tảng hiện có; đây là đề xuất, không implementation/benchmark/acceptance runtime. P2_ACCEPTANCE là dự thảo; triển khai sau đủ bốn phase, không đợi viết luận án. Chi tiết version/license/tag còn giới hạn ghi trong SOURCES.md; không coi docs live là contract đã pin.
- OC050 social POI: native /root/social_poi_ingest đang làm theo brief Codex đã chốt. Đây là sub-agent thứ ba/cuối theo yêu cầu; không tạo thêm. AI-box coding được phép vì pipeline phức tạp; lưu process/session thật khi có. Chưa nghiệm thu mã, chưa graph import.

## Phạm vi ingest mới
T057 P0 nguồn fetch nhanh + pipeline có tối thiểu tên/địa chỉ/(mô tả hoặc review), evidence và quality/quarantine qua acquisition; T058 P1 crawler HTTP/web tĩnh có CLI và tests; T059 P2 nguồn động/anti-bot khó deferred, không bypass. Finding gốc chỉ là dữ liệu khảo sát cũ, bản sao/hash ở docs/research/social-poi/inputs/. Không tự áp old taxonomy/ID/admin/giá API vào mã mới.

OC050 chỉ ghi đúng thư mục trong brief, không primary/graph/runtime/HTML/trackers. Mọi mẫu real/synthetic riêng, imported=0, full server web lineage T050 còn bắt buộc trước import thật. Không paid Serp/Tavily hoặc truy cập key app khác. Root phụ trách QA độc lập và nhận/trả mã sau terminal.

## Lỗi mới phải xử lý phase2 trước live experiment
QA-PROVIDER-CLI-01: OpenCode hiện v2.0.32 không hỗ trợ --pure, trong khi runtime adapter mặc định DEFAULT_CLI_PURE=True vẫn thêm cờ này. Parent parser-only probe rejected cả --pure và sentinel, exit1 trước model; không có live model call. Evidence handoffs/OC-040/parent-cli-capability-20261018.json. Offline nested-schema probe đã trả invalid_tool_arguments đúng;96offline tests trước đó không chứng minh CLI mới tương thích. T051 chưa đạt runtime. Cần Codex lập gói sửa capability/version+isolation/tool-deny/export/usage cho CLI mới; không chỉ tắt guard hoặc dùng fallback âm thầm để chạy. Gemini mặc định không đổi.

## Tiếp tục
1. Chờ đúng OC050 native, không tự relaunch/poll external process do child sở hữu. Root không sửa paths child đang ghi.
2. Đọc code/tests/evidence, chạy independent regression + counterexamples network/minimumfields/identity/revisions/ingest/no-write trước nghiệm thu. Nêu rõ thiếu key/nguồn/lineage, không ép accepted.
3. Cập nhật user report/checkpoint sau mốc mã/QA; giữ phase1 rồi phase2 theo FOUR_PHASE_PLAN. Các gate dữ liệu QA-DATA-01, source/MCP/AI scope, routing, full import và CLI vẫn chưa hoàn tất. Không bắt đầu H1/thesis, không triển khai P2memory trước bốn phase.

## OC050 dispatch xác nhận
Native xác nhận external process84098, session ses_eb4c1ddbdffeuY1Csq3XPgrHJP, exact aibox/ds/deepseek-flash; events handoffs/OC-050/events.log. Lần standard log đầu EPERM trước tạo session; retry elevated đã được chấp thuận. Hiện đang chạy, không coi là terminal/success. Native sở hữu poll/QA, root không relaunch.
