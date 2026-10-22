# Checkpoint — kiểm chứng luồng đồ thị thật

Giai đoạn 1. Lượt goal trước là **progress**: đã giao báo cáo tương tác, cập nhật phạm vi bốn giai đoạn/Jev và tạo regression dữ liệu. Lượt này tiếp tục một trọng tâm: cấu hình thuộc tính cạnh và luồng repository thật. Không giao agent mới, không gọi model hay chạy thí nghiệm khoa học.

## Bằng chứng mới

- `handoffs/OC-046/parent_application_canary.py` — ca QA do Codex viết, không sửa mã sản phẩm. Ownership preflight kiểm tra PID2618/startticks318416, đường exe, SHA256 binary, command đầy đủ, data-dir mới, token và đúng ba listener loopback. Đây là quan sát ngày 18/10; phải kiểm tra lại ở lần dùng sau.
- `handoffs/OC-046/evidence/parent-application-canary-20261018.json`: **passed=true**, không lỗi. `SHOW CONFIG` xác nhận `storage_properties_on_edges=true`, mặc định binary là false.
- Hai POI thật, cùng vùng nguồn, cách nhau khoảng 19,922 m theo engine. Batch tạo/lặp không tăng số POI; metadata roundtrip đúng; category ID chính xác; source-only không xuất hiện trong truy vấn địa giới hiện tại; chọn đúng snapshot/vùng trả hai bản ghi gọn; sai snapshot trả rỗng.
- Cạnh NEAR_BY tạo được và xây lại từ cả hai đầu vẫn chỉ có một cạnh, radius3km và đơn vị mét/km nhất quán. Radius5km bị từ chối trước xóa cạnh. Hash nguồn bị sửa trong giao dịch bị loại, không được nâng thành dữ liệu địa giới hiện tại.
- **Luôn rollback** giao dịch kiểm thử. Trước/sau và kiểm tra cuối: **0 nút, 0 quan hệ**. Hash bốn tệp mã cùng raw/prepared/lineage giữ nguyên. Không nhập lâu dài và không thay dữ liệu gốc.
- `parent-config-checks-20261018.json`: bash syntax và cả hai Compose quiet config đều exit0, dùng env example và không resolve env files. Development Compose có warning biến tunnel chưa đặt; không bật tunnel/engine. Parent deployment tests **40 passed, 2,53s**.

## Kết luận có giới hạn

- **T054 VERIFIED** cho cấu hình native engine + khai báo Compose + đường ghi thuộc tính cạnh thực tế. Không phải xác nhận Docker runtime, đóng gói/chạy toàn hệ thống hay generic helper hardening.
- **T053 VERIFIED** cho sửa hàm không gian tương thích và ca repository thật đã ghi/đọc được cạnh. Bằng chứng trước đó 1.113 trường hợp biểu thức vẫn giữ nguyên; không dùng hai POI này thay kiểm tra toàn tập, đồng thời, hiệu năng hay persistence.
- OC045: truy vấn source-scope/compact projection/corruption đã có bằng chứng native engine ở phạm vi hai bản ghi. Service discovery, MCP/API, toàn tập và AI/planner selected-scope vẫn cần QA/tích hợp; không nhận toàn bộ task.
- OC046 được nhận về cấu hình có giới hạn, giữ sai lệch scope của executor đã ghi: rollback edge probe ngoài brief no-write và transient scratch. Không tuyên bố toàn bộ lịch sử tuân thủ scope.
- Lần inspect git diff theo baseline chứa dòng credential cũ đã bị xóa bởi công việc trước. Không chép giá trị vào hồ sơ/báo cáo; tránh dump diff baseline ở lần sau. Không có credential mới được thêm trong mốc này.

## Tiếp tục đúng bốn giai đoạn

Hiện vẫn giai đoạn1: tiếp theo kiểm chứng provider R1/cấu hình CLI hiện cài, adapter dữ liệu (đã có QA-DATA-01), source discovery/MCP và routing. Gom lỗi cần cho đề cương rồi mới giao OpenCode gói sửa ở giai đoạn2; Jev đã có kế hoạch, chưa triển khai. Phase3 mới chạy bộ thí nghiệm; sau phase4 chờ người dùng chọn H1 hoặc viết tiếp luận văn.

Báo cáo mô-đun đồ thị được cập nhật bằng biên tập nội dung; giữ sơ đồ kiến trúc và receipt như bản chụp lúc giao trước mốc QA này vì cấu trúc mã không đổi. Không gán trạng thái cũ trong card của sơ đồ cho tiến độ mới.
