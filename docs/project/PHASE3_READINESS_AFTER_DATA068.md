# Điều kiện vào phase 3 — sau DATA068

**Cập nhật sau CORE071 / MEM072, 18/10:** provider Go/Jev, full graph và luồng foot/car đã được Codex nhận trong phạm vi cụ thể; không mở lại các gate này. S5 chưa nhận: lần chạy native được người dùng cho phép đã dừng do oracle của script QA dùng `expected_version=0` để tạo profile chưa tồn tại; ba ca auth-denial đạt,0modelcalls,stack đã dọn. Bản sửa oracle chờ quyền chạy mới. DOC073 đang đồng bộ interactive docs; collector/freeze vẫn chưa chốt. Các dòng “CORE069 đang thực thi” dưới đây là lịch sử.

**Sẵn sàng dữ liệu giờ mở cửa (đo offline, không phải thí nghiệm):** Codex chạy production `parse_operation_time` trên đúng payload6367POI/SHA37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1:5313absent,626unsupported,104daily_window,324always_open. Tổng428chuỗi có cú pháp được hỗ trợ; nhãn nguồnQuan1 có92. Có thể chọn ordinary scenarios với dữ liệu giờ nguồn parseable bên cạnh sparse/refusal cases; không được đồng nhất parseable với giờ đã xác minh độc lập/độ mới. Giá vẫn unknown. Script/receipt tái lập: `handoffs/EXP-074/parent_primary_hours_readiness.py`, `parent-primary-hours-readiness-reproducible.json`. Chưa chọn/freeze20case, chưa đo route cho các case đó và chưa chạy H2/H3.

Codex rà soát18/10/2026 trong khi CORE069 đang thực thi. Đây là kiểm tra sẵn sàng, **chưa chạy hoặc đóng băng thí nghiệm chính**.

| Hạng mục | Bằng chứng hiện tại | Còn phải chốt |
|---|---|---|
| Dữ liệu chính | DATA068/root:6367POI,14category,3678397NEAR_BY; upsert/restart và toàn tập cạnh đúng | Freeze manifest cho graph/code/config cuối sau CORE069; không dùng count ứng viên thay accepted count |
| Luồng dịch vụ | Canary cũ có model kiểm soát; CORE069 đang nối actual connector/HTTP/UI/provider | Codex nhận S1/S3/S4/S5/S6 theo scope đã duyệt trước primary runs |
| H2 | Protocol v2 có yêu cầu20scenario, cùng facts/routes/model giữa2nhánh; validator/evaluator đã tồn tại | Freeze20case từ POI chính/qualified source area, actual routes và feasibility review trước scoring; giữ initial proposal/repair/refusal/missing facts |
| Manifest cũ | benchmarks/planning/scenarios.json tự ghi synthetic-engineering-fixtures/excluded_from_original_dataset | Không đổi nhãn20fixture thành primary scenarios; chỉ tái dùng cấu trúc/harness phù hợp |
| Collector cũ | benchmarks/live_model/capture.py dùng V1 inline agent config; runner.py còn help/command contract export/pure cũ | Không chạy blind trên CLI2.0.32. Đường primary phải dùng provider gate/native contracts đã nhận, giữ exact-session identity và ledger/denominators; một gói adapter nhỏ nếu cần sau CORE069, không thêm harness mới |
| H3 | Protocol5profile×3condition; memory/evaluator fixtures hiện có | Freeze profile/category IDs và lượt update/contradict/delete/restart/unknown; actual runtime/auth/isolation phải QA. Fixture không phải người H1 |
| Usage | CLI067 main-session usage có thể thiếu auxiliary generation; CORE069 có bounded title/nativefake check | Chỉ kết luận total-token savings nếu đủ coverage. Nếu chưa đủ, báo phần đo được và unknown overhead, không bịa total |
| Sparse facts | Nguồn thiếu giá, upstreamIDs/license/freshness; chỉ1055rawhours nonblank | Giữ unknown, kiểm parser/binding thực trước chọncase. Không tự thêm giá/giờ hoặc dùng review-only overlay làm fact. Budget chỉ đánh giá khi có dữ liệu so sánh; temporal/route metrics vẫn ghi theo phạm vi xác minh được |
| H1/thesis | Chưa có người tham gia; user yêu cầu chờ quyết định sauphase4 | Không khởi động H1 hoặc viết luận án tiếp. Đây không chặn phần hệ thống/H2/H3 khả thi |

Ghi chú lịch sử: completion paragraph trong EXPERIMENT_PROTOCOL.md và checkpoint17/10 còn mô tả lỗi degrees/radians/fullimport cũ. Các lỗi đó đã có bằng chứng sửa và DATA068 đã nhận; đọc checkpoint mới thay vì mở lại workstream đã xong. Khi chốt primary freeze, bảo toàn protocol v2 và ghi revision mới phản ánh trạng thái/phạm vi hiện hành trước khi thu kết quả.

Crawler, grow-with-user, fact enrichment/nguồn mới và runtime harness mới thuộc **phase5 Finalizing**, không trở lại làm gatephase2/3. Không thay yêu cầu thí nghiệm bằng việc chạy toàn bộfixture tổng hợp hoặc toàn bộcase từ chối.
