# Checkpoint bàn giao — Codex, 18/10/2026 20:51 (Asia/Saigon)

Lưu theo yêu cầu người dùng. Chủ trì và người lập checkpoint: **Codex**. Dự án còn đang thực hiện; checkpoint này không phải nghiệm thu toàn bộ hay yêu cầu dừng worker.

## Đã hoàn thành, có bằng chứng

- Core Jev + Go DeepSeek V4.1 đã chạy luồng HTTP/SSE nhận yêu cầu → đề xuất → routing; có bằng chứng foot và car. Chưa xác minh giao diện bằng browser hoặc public deployment; giá/giờ chưa đủ để kết luận toàn lịch trình khả thi.
- Đã nhập 6.367 POI, 14 category vào graph. Giữ giới hạn nguồn, chất lượng và độ mới đã công bố.
- Memory hiện có: MEM072R1 đạt 15/15 kiểm tra với 4 chat thật; stack riêng đã dọn. Đây chưa phải H3 hoặc grow-with-user. Quyền chạy script đúng một lần đã dùng hết, không chạy lại.
- EXP074 collector production V2 đã nhận: 29 kiểm tra độc lập + 208 regression.
- EXP076 đóng băng riêng đầu vào 20 H2: 827 kiểm tra/replay đạt; dry-run tạo 120 observation, không phải kết quả model. Không sửa frozen input hoặc receipt đã bind.
- EXP077 endpoint đo tính khả thi theo thời gian đã nhận: 38/38 kiểm tra độc lập + 247 regression. Giữ riêng đánh giá global với chi phí chưa biết. Không lặp QA đã đạt nếu không có thay đổi/lỗi mới.
- Báo cáo tương tác tiếng Việt: docs/reports/2026-10-18/index.html; 341 kiểm tra tĩnh/84 tham chiếu. Sơ đồ giữ nguyên artifact đã nhận. Không tuyên bố đã visual QA bằng browser.

## Đang làm — EXP078, chưa nghiệm thu

OpenCode theo kế hoạch cố định của Codex, model `aibox/ds/deepseek-flash` (V4.1 theo xác nhận người dùng).

- Handle: **83026**; session: **ses_eb0c6cdc3ffeADV1uUYE8iakvq**.
- Thư mục executor: `E:/Agent_Artifact/TVLT_2026/2026-10-18/native-memory-study`.
- Lần poll khi lưu checkpoint: client còn chạy, không có output mới; chưa xác nhận worker idle qua API. Không suy ra hoàn thành từ im lặng hoặc timeout.
- Đã thấy `benchmarks/memory_live/__init__.py` (407 bytes); chưa thấy runner.py hoặc tests/memory_live trong lần inventory này. events.log cập nhật gần nhất 20:50:42, chỉ kiểm tra metadata, không in nội dung thô.
- Ngân sách đã giao 25 phút; đã steer một lần để tập trung code. Phiên sau đối chiếu thời điểm dispatch/log an toàn để xử lý đúng ngân sách, không tự mở lại một worker trùng.
- Phạm vi ghi: collector mới, focused offline tests, candidate manifest chưa freeze và artifact task. App/helper/evaluator/frozen H2 chỉ đọc. Không cho phép gọi model/HTTP/runtime thật trong giai đoạn code này.
- `docs/project/handoffs/EXP-078/parent_contract_qa.py` đã chuẩn bị, chưa chạy trước khi nguồn nhả và xác nhận idle.

## Phiên tiếp theo bắt buộc tiếp tục

1. Đọc AGENTS.md, EXECUTOR_POLICY.md, FOUR_PHASE_PLAN.md, master handoff và EXP078/brief.md. Kiểm tra đúng handle/session đang có; không dispatch lại do timeout. Client thoát chưa đủ chứng minh worker idle: dùng official interrupt/wait/active cho đúng session khi cần.
2. Hoàn tất bàn giao EXP078 trong ngân sách, xác nhận nhả nguồn; Codex kiểm tra readonly hashes, contract/fake-backend/lifecycle/ledger/projection/privacy và focused regression. Giữ mọi thất bại và sửa có mục tiêu, tránh vòng QA không cần thiết.
3. Chỉ sau QA, đóng băng code/config/data/prompt/model/settings và execution manifests; sau đó chạy phase 3. H2: 120 observation dự kiến (20×2×3). H3: 15 primary + 15 prep + tối đa 3 lifecycle, tổng trần 33 chat; 5 profile giả lập, không phải H1. Không retry/best-of hoặc thay failure bằng kết quả đẹp.
4. Hoàn tất spatial/system/adversarial experiments còn thiếu, phân tích và báo cáo phase 4. Chờ người dùng chọn H1 hoặc viết luận án. Chưa có người tham gia H1, không dựng dữ liệu người dùng.
5. Phase 5 **Finalizing** mới tích hợp crawler travel agency/mạng xã hội, harness/grow-with-user và cơ chế mới. Giữ research/backlog, không đưa lại thành blocker của luồng core.
6. Cập nhật checkpoint sau mỗi task lớn/phase quan trọng; tiếp tục đến khi hoàn thành toàn bộ việc còn lại trong scope đã duyệt, không chỉ báo cáo rồi dừng.

## Quy tắc tiếp tục

Codex lập kế hoạch trước và giao `/plan` với kế hoạch đã chốt; OpenCode thực thi code, Hermes hỗ trợ OS/evidence/report khi dùng được. App/experiments dùng `opencode-go/deepseek-v4.1-flash`; không explicit V4.0. Jev dùng TYPESAFE_API_TOKEN, Go dùng OPENCODE_API qua loader hẹp; không đọc/in giá trị .env. Probe nhạy cảm chỉ dùng safe_secret_probe.py đã review. Không đọc lịch sử/config không liên quan, không ALL/wildcard/global allowlist, không vượt guard sau deny. Không reset/clean/commit/push. CLI 2.0.32 không có --dir/--pure/--steps. Không workaround browser refusal của báo cáo.

Bằng chứng chi tiết: docs/project/handoffs/{CORE-069,CORE-070,CORE-071,DATA-068,MEM-072,EXP-074,EXP-076,EXP-077,EXP-078}/; master: docs/project/HANDOFF_CODEX_CURRENT_2026-10-18.md. Mọi kết quả accepted đều có giới hạn; **chưa có primary H2/H3 outcomes hoặc full execution freeze**.
