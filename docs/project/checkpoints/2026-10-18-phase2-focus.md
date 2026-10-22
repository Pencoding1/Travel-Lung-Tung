# Chốt phạm vi audit, tập trung giai đoạn 2

Quyết định Codex18/10/2026: chuyển trọng tâm từ audit ban đầu sang **hoàn thiện mã theo phạm vi đã chốt**. Điều kiện này không đồng nghĩa mọi mô-đun đã được nghiệm thu hoặc có thể chạy thí nghiệm chính.

Theo FOUR_PHASE_PLAN, đầu ra phase1 là rà soát các mô-đun quan trọng, xác định lỗi/giới hạn và chốt phạm vi sửa. AC01/SG01 có source audit; QA_PHASE1 bao phủ chuẩn bị dữ liệu/adapter/graph/spatial/MCP/AI/planner/memory/backend/routing/experiments/docs. Chín mô-đun báo cáo đều có QA, bằng chứng và gaps rõ. Các bản sửa giờ đã được quản lý bằng brief, root counterexamples, acceptance và checkpoint:

- Data binding, source contract/serialization và spatial: gate cục bộ/engine đã kiểm, fullimport/density/durability còn phạm vi phase2 rõ (T049/T050/T053).
- Acquisition/social: CR057 gate và CR062 fixes đã kiểm, CR061 capture vẫn partial/quarantine; không nhận dữ liệu mới vào primary.
- AI: AI059 source canary, AI063 Jev offline/API pilot đã nhận có giới hạn; T051 actual CLI engine gate vẫn là lỗi chặn tích hợp đã xác định, không phải unknown được coi là pass.
- Planner/routing: RT064 giữ car/foot xuyên nguồn và lịch, actual2POI/4HTTP rollbackcanary đạt; fullsnapshot/deployedHTTP/liveprovider còn mở.
- Memory/backend/experiment tooling đã có QA offline và giới hạn trong module report; không suy thành benchmark/H1. AgentMemory mới chỉ P2research sau4phase.
- Báo cáo có QA tĩnh/refs/JS; lần cập nhật mới chưa browser render. Giới hạn này giữ rõ, không gọi browser/server để lách filepolicydenial.

Phase2 phải hoàn tất T051, native-source/fullsnapshot/client selection, cấu hình Jev/service và deployment khả thi, rồi freeze mã/dữ liệu/config. Phase3 **chưa bắt đầu**: chưa20pairedH2, chưa5x3H3, chưa3nhómđốikháng modelthật. Phase4 userchoice vẫn giữ; chưa H1 volunteers và không tự viết luận án tiếp.

QA tiếp tục sau mọi sửa đổi; checklist/acceptance chưa đạt vẫn mở. Phase label chỉ thể hiện trọng tâm công việc hiện tại, không phải phần trăm hoàn thành hoặc chứng nhận toàn hệ thống. Đọc checkpoint RT064 để biết proof và giới hạn chính xác.
