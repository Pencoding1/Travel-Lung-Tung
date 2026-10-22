# Phạm vi đã duyệt — Phase 2 và Finalizing phase

18/10/2026 · Codex lập kế hoạch và QA; OpenCode thực thi coding theo brief Codex. Đây là ranh giới đã được duyệt, không phải xác nhận các mục đã hoàn tất.

**ĐÃ ĐƯỢC NGƯỜI DÙNG DUYỆT18/10/2026:** “Duyệt S1–S6 như đề xuất”. Sáu scope dưới đây là ranh giới phase2 đã chốt; không cần hỏi lại quyền cho implementation/QA cần thiết trong đúng phạm vi. Crawler giữ phase5, grow-with-user ngoàiphase2. Thực thi từng gói theo kế hoạch Codex và một writer, không mở rộng ngầm.

**Ưu tiên mới nhất:** phase2 hoàn thiện luồng **nhận nhu cầu người dùng → recommending POI/lịch trình → routing → trả kết quả dùng được** trên dữ liệu OSM hiện có, sau đó chạy thí nghiệm/báo cáo. **Phase5 đổi thành “Finalizing phase”**, tích hợp toàn bộ cơ chế mới như grow-with-user, crawler và các mở rộng đã chốt. Không kéo các cơ chế đó vào đường găng hiện tại.

## Thay đổi đã được người dùng quyết định

- Toàn bộ crawler: legacy Traveloka/Vietravel, ingest xã hội/web P0/P1 và nguồn động P2 **ra khỏi phase2**, chuyển **phase5**. Phase5 chốt kế hoạch nguồn travel agency + mạng xã hội trước triển khai. Không chờ crawler để chạy thí nghiệm hệ thống chính.
- Hệ thống chính dùng bộ POI OSM hiện có theo xác nhận người dùng. Không tìm thêm nguồn hoặc làm giàu bằng API trả phí trong phase2. Bộ frozen có6368raw/6367prepared candidates; chưa phải6367graphnodes đã nghiệm thu. Không bịa OSM IDs/giá/giờ từ file thiếu dữ liệu.
- Grow-with-user: nghiên cứu4hệ/5ticket đã có; implementation P2 đặt trong **phase5 Finalizing**, cùng các cơ chế mới khác; không triển khai/migrate runtime trongphase2.
- Không H1 hoặc viết luận án tiếp trước lựa chọn của người dùng sauphase4.

## Sáu scope đã duyệt

| Mã | Phạm vi | Hiện có / phần phải chốt | Điều kiện dừng phase2 của scope |
|---|---|---|---|
| S1 | **Đường AI: Jev + DeepSeek qua CLI** | Jev đã QA/pilot thật. CLI067 đang sửa deadline/lifecycle/QA giữ guard. Chốt cấu hình runtime có chủ đích và một smoke call thật sau gate; không đổi model/default global. | Jev chặn/định tuyến đúng; CLI kiểm policy trước model, dùng đúng alias, export/usage/error/cleanup trung thực. Không còn lỗi chặn đường gọi model. |
| S2 | **Bộ POI OSM hiện có → graph** |6367ứngviên đã chuẩn bị, IDs/category/lineage snapshot đã có. Chốt import toàn bộ tập đủ điều kiện; hồ sơ thiếu/không hợp lệ tách rõ, không ép đạt6367accepted. | Có số liệu đầu vào/accepted/rejected/trùng, nguồn và version; import tái chạy không nhân bản, dữ liệu còn sau restart; không tự tạo metadata upstream chưa biết. |
| S3 | **Tích hợp dịch vụ/API và client hiện có** | Canary2POI đã chạy qua graph/MCP trong tiến trình; còn luồng HTTP và snapshot đầy đủ. Dùng native runtime đã có, sửa tối thiểu client để chọn đúng phạm vi nguồn nếu thiếu. | Một luồng thực từ API/client→AI→MCP→graph→routing→kết quả; auth/source scope/health/error paths hoạt động, có lệnh chạy lại. Không bắt buộc sửa Docker hoặc dựng hạ tầng mới nếu native đủ. |
| S4 | **Planner/ràng buộc/tuyến đường hiện có** | car/foot đã qua canary thật nhỏ. Chốt với snapshot/luồng tích hợp: thời gian, chi phí khi có dữ liệu, giờ mở cửa, nguồn từng stop, lịch sau repair. | Không mất/sai scope hoặc travel mode; ràng buộc được kiểm, dữ liệu chưa biết được báo rõ. Không thêm thuật toán tối ưu mới hoặc hứa mọi lịch đều khả thi. |
| S5 | **Memory hiện có để sẵn sàng đánh giá H3** | Working history/profile SQLite/CAS và sửa lỗi có110test offline. Giữ khả năng bật/tắt/đọc/ghi/xóa và request constraints ưu tiên hơn profile theo contract hiện có. | Kiểm luồng tích hợp với model thật, không mất lịch sử/nhầm owner/scope; harness có thể chạy các điều kiện đã đăng ký. Không thêm tự học, harness mới hoặc migration. |
| S6 | **QA tập trung, freeze và báo cáo tiến độ** | Codex kiểm bản sửa và luồng thiết yếu, giữ lỗi/giới hạn; dùng bộ test/harness đã có. Không tái audit toàn dự án sau từng sửa nhỏ. | Freeze mã/dữ liệu/cấu hình; smoke tích hợp và regression liên quan đạt; manifest/commands/evidence/checkpoint và báo cáo tương tác tiếng Việt đồng bộ. Các lỗi còn lại phân loại không chặn thí nghiệm. |

**Điều kiện sang phase3:** S1–S6 đã chốt trong phạm vi trên, không còn lỗi chặn và có phiên bản tái lập. Không đợi crawler, dữ liệu nguồn mới, grow-with-user, H1 hay bản luận án cuối.

## Các scope ngoài phase2 — không được âm thầm kéo trở lại

| Đích | Công việc |
|---|---|
| Phase3 | Thí nghiệm chính H2:20cặp tình huống; H3:5profile×3điều kiện; kiểm đối kháng/đo hệ thống theo protocol. Không coi QA module là kết quả thí nghiệm. |
| Phase4 | Phân tích kết quả, báo cáo tương tác tiếng Việt, giới hạn và handoff; dừng để người dùng chọn H1 hoặc viết luận án tiếp. |
| **Phase5 — Finalizing phase** | Tích hợp **toàn bộ cơ chế mới** theo kế hoạch chốt riêng: grow-with-user (5ticket từ research Hermes/Letta Code/LangGraph/Mastra), crawler travelagency/mạngxãhội và các mở rộng khác đã được chọn. Crawler cần chốt nguồn/trường dữ liệu/access/reuse/công cụ/chi phí trước triển khai. T056–T059/legacy đều ngoài đường găngphase2; P0/P1/P2 cũ chỉ ưu tiên nội bộphase5. Không tự thay runtime/harness. |
| Sau lựa chọn của người dùng | H1 với người tham gia thật/consent; viết và hoàn thiện luận án. |
| Không tự mở | Docker repair/infra migration, UI redesign, thêm nguồn POI, SERP/Tavily trả phí, geocoding/enrichment, thêm model/harness, mở rộng guardrail toàn hệ khi không có lỗi cụ thể. |

## Cách duyệt

Đã duyệt toàn bộ **S1–S6** qua trả lời của người dùng18/10/2026. Codex triển khai/QA theo danh sách này, không hỏi lại cùng phạm vi. R1 CLI067 đang chạy theo quyền đã cấp; status và handle xem checkpoint mới nhất. Mọi thay đổi thêm/bỏ scope về sau cần cập nhật quyết định mới, không tự mở rộng từ backlog lịch sử.
