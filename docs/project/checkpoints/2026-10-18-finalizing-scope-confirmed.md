# Checkpoint — chốt Finalizing phase

Chủ trì: Codex. Quyết định người dùng ngày 18/10/2026.

- Phase 1: xác minh hệ thống hiện có.
- Phase 2: hoàn thiện S1–S6 đã duyệt, ưu tiên luồng nhận nhu cầu → đề xuất POI/lịch trình → routing → trả kết quả dùng được, dựa trên bộ POI OSM hiện có.
- Phase 3: chạy thí nghiệm sau khi luồng chính qua QA và được freeze.
- Phase 4: báo cáo kết quả; người dùng quyết định H1 hoặc tiếp tục viết luận án.
- Phase 5 — **Finalizing phase**: tích hợp toàn bộ cơ chế mới đã được chọn, gồm grow-with-user, crawler travel agency/mạng xã hội và các mở rộng khác. Không lấy các cơ chế này làm điều kiện hoàn thành phase 2–4.

Scope chi tiết: `../PHASE2_SCOPE_FOR_APPROVAL_VI.md`. Không mở lại nghiên cứu/coding crawler hoặc harness trong đường găng hiện tại.

Trạng thái tại checkpoint: DATA068 có receipt 64 batch, tổng 6367 accepted, chưa ghi nhận lỗi validation/database/spatial trong receipt. Đây là tiến độ executor, chưa phải nghiệm thu import toàn bộ. Handle 62783 vẫn hoạt động; chờ verification/replay/persistence và Codex QA, không chạy import trùng hoặc sửa source đang có writer.
