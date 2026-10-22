# Checkpoint — H2 primary đang chạy

Codex ghi ngày 20/10/2026. Đây là trạng thái dispatch, chưa phải nghiệm thu kết quả.

- Người dùng đã cho phép: **“Cho phép chạy H2 chính”**. Quyền đã được sử dụng cho đúng một batch; không khởi chạy lần nữa.
- Unified exec handle **80818**, đã được kiểm tra lại sau compaction và vẫn hoạt động. Không suy ra process đã chết chỉ vì stdout chưa flush.
- Output duy nhất: `docs/experiments/primary_20261018/runs/h2-h2091-primary/`.
- Seal H2-091 được kiểm trước launch, output chưa tồn tại khi launch. Lệnh chính xác và nguồn quyền: `docs/project/handoffs/H2-091/primary-dispatch.json`, `primary-execution-authorization.json`.
- 120 ô dự kiến (20 × 2 × 3), tối đa120 yêu cầu Go V4.1, mỗi ô một attempt/timeout120s; không retry/resume/AI-box/Jev/live graph.
- Các quan sát đã bắt đầu ghi bền vững vào `calls.jsonl`. Không dùng số đang tăng này làm kết quả cuối.

## Người tiếp tục phải làm

1. Kiểm lại đúng handle80818; không launch/resume collector khác. Chỉ đọc projection có chọn lọc từ ledger và receipt chuẩn hóa của đúng batch, không đọc raw log/config/auth/session khác.
2. Chờ terminal; lưu exit/output có phạm vi. Nếu có authority stop, giữ toàn bộ ô chưa gọi là missing. Không tự sửa tiêu chí hoặc điền kết quả bằng lần chạy lại.
3. Codex kiểm độc lập: denominator120, khóa ô không trùng, attempts/budget/model/source/prompt pins, sidecar hashes, export khớp ledger; phân biệt lỗi provenance, lỗi output, unknown cost/hours và kết quả timing-only.
4. Chạy phân tích offline trên dữ liệu đã kết thúc; không thay kết quả bằng success-only subset. Không coi timing-only là chứng minh tính khả thi toàn cục.
5. Cập nhật báo cáo tương tác tiếng Việt, backlog/handoff và checkpoint terminal; giữ nguyên bằng chứng H3 partial1/15 và các lần lỗi trước.

H1 chưa có người tham gia; phase5 Finalizing vẫn hoãn. H2 đang chạy không phải cho phép tự chạy lại H3 hoặc thao tác engine recovery.
