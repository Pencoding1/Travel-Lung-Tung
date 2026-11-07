# Rà soát phê duyệt contract — 27/10/2026

## Quyết định đã nhận

- Chủ dự án chọn: “Rà soát và duyệt từng chức năng toàn hệ thống trước khi triển khai”.
- Chưa triển khai thay đổi sản phẩm trong đợt rà soát này.
- FT-CHAT-MVP-001 v1.0 giữ trạng thái APPROVED đã có; không yêu cầu duyệt lại.
- Danh mục được duyệt: giữ 10 chức năng trong FT-SET-TVLT-002 v0.2 và thêm F-BOOKING để định nghĩa riêng; chưa cho phép đặt chỗ thật. Việc duyệt danh mục không duyệt toàn bộ behavior của 11 chức năng.
- F-PLAN: APPROVED cho nội dung cụ thể ở bảng bên dưới.
- F-LOOKUP: APPROVED cho nội dung cụ thể ở bảng bên dưới. Bao gồm yêu cầu không lộ traceback; không đồng nghĩa mã hiện tại đã đạt hoặc mọi sửa đổi REST/JWT/CORS đã được duyệt.

## Nội dung behavior được duyệt trong đợt rà soát

| Chức năng | Nội dung đã xác nhận |
|---|---|
| F-PLAN | Nhận dữ liệu có cấu trúc đã được người dùng xác nhận từ Chat hoặc form; lấy POI đúng scope; model chỉ đề xuất; scheduler tính lịch và validator kiểm độc lập. Trả thứ tự, giờ, tuyến, trạng thái và dữ kiện chưa biết. Không bịa giá, giờ hoặc đường; lịch rỗng không feasible; no_plan không đồng nghĩa bất khả thi toán học. Chưa bao gồm booking, giao thông công cộng nhiều chặng hoặc tối ưu toàn cục. |
| F-LOOKUP | Tra POI, danh mục, ứng viên địa danh và tuyến có hướng; giữ đúng bộ lọc và scope; nhiều ứng viên địa danh thì không tự chọn. Thiếu dữ liệu trả unknown/rỗng có mã rõ; thiếu tọa độ không báo tuyến thành công; không fallback đường thẳng; lỗi không lộ traceback hoặc nội dung thô của provider. Chưa bao gồm ranking cá nhân hóa và tìm mờ quy mô lớn. |
| F-MEMORY | APPROVED: người dùng xem/sửa/xóa hồ sơ sở thích và xóa ngữ cảnh phiên riêng biệt. Hồ sơ dài hạn chỉ thuộc danh tính đã xác thực; khách ẩn danh chỉ có ngữ cảnh phiên. Tắt memory thì không đọc/ghi hai tầng trong Chat/Planning; sở thích cũ không ghi đè ràng buộc mới; đổi scope loại ngữ cảnh nguồn cũ. Cập nhật lệch version trả xung đột; xóa phiên không xóa hồ sơ và ngược lại. Chưa gồm tự suy ra hồ sơ/grow-with-user hoặc đồng bộ đa thiết bị. |
| F-SAVED | APPROVED: người đã đăng nhập lưu, liệt kê, mở lại và xóa lịch trình của mình; ID do server cấp, phân trang có giới hạn. Lưu nguyên payload, không chạy lại planner hoặc tự nâng trạng thái khả thi. Truy cập lịch của người khác trả 404; storage lỗi/chưa cấu hình báo không sẵn sàng; không âm thầm tạo lại DB hỏng. Chưa gồm sửa lịch đã lưu, chia sẻ công khai, phiên bản hóa hay cộng tác. |
| F-SCOPE | APPROVED: xem snapshot/vùng nguồn; chọn một, nhiều hoặc toàn bộ các vùng cụ thể trong cùng snapshot. Server giữ namespace/hash/vùng xuyên Chat, Planning và tra cứu; model không được mở rộng scope. Không có dữ liệu thì báo rõ, lỗi discovery hoặc snapshot trả về sai phải bị chặn. Nhãn vùng nguồn không được coi là địa giới hiện tại; source mode và current-admin mode loại trừ nhau. Chưa gồm chọn nhiều snapshot hoặc sửa dữ liệu nguồn trên UI. |
| F-INGEST | APPROVED: người vận hành nạp lô/tạo POI và dựng lại NEAR_BY, biết rõ số đã ghi và từng lỗi. Kiểm schema/tọa độ/ID, chạy canary trước phần còn lại; canary fail không báo cả lô thành công. Theo dõi job bằng tiến trình/SSE có terminal và replay cho người kết nối muộn; job lạ trả 404. Thiếu DB hoặc hết năng lực nhận job phải báo lỗi, không âm thầm mất dữ liệu. Cập nhật POI và thay cạnh liên quan trong cùng transaction; lỗi không lộ traceback. Chưa gồm idempotency nhiều worker hoặc migration taxonomy trên graph thật. |
| F-ACQUIRE | APPROVED: từ GeoJSON/capture tạo POI ứng viên, lineage và quyết định accepted/quarantine có lý do kiểm lại được. Giữ nguyên dữ liệu nguồn và hash; gộp trùng có ledger, xung đột định danh hoặc mapping chưa review thì chặn; tách synthetic và dữ liệu thật. Capture thiếu/sai hash phải từ chối; chỉ fetch khi yêu cầu rõ và nguồn được phép; không ghi graph trực tiếp, dry-run imported=0, không tự tạo lineage OSM. Chưa gồm fetch hàng loạt, vượt chống bot hoặc tự import. Không mở triển khai crawler trước Finalizing. |
| F-OPS | APPROVED: phân biệt service còn sống với dependency đã sẵn sàng; storage lỗi phải báo not-ready, không che bằng health xanh hoặc tạo lại dữ liệu để vượt kiểm tra. Công bố provider/model thực sự được dùng; không đổi provider ngầm. Lỗi có mã và thông điệp đã sanitize; usage không đo được giữ unknown/null. Trạng thái phải phản ánh kiểm tra hiện tại, không coi checkpoint cũ là uptime. Chưa bao gồm public deployment, tự mở rộng hạ tầng hoặc SLA production. |

## Đang chờ

- TA-CHAT-001: APPROVED ngày 28/10/2026 qua biên nhận `receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb`, chỉ mục `TEST-GATE`, lựa chọn “Duyệt kiến trúc và cổng nghiệm thu”, comment rỗng. Đã đối chiếu hash và nội dung snapshot v2 trước khi áp dụng. Giữ 20 + 100 test, mutation proof 10 họ, kiểm tĩnh và quy tắc không sửa kỳ vọng để lấy xanh; Booking theo contract mới. Không suy ra quyền sửa/triển khai mọi chức năng hoặc test đã đạt.
- ĐÃ CHỐT 28/10/2026: sửa trực tiếp trong MVP hiện tại: ẩn chi tiết lỗi nội bộ, token POI bắt buộc có thời hạn và danh tính người dùng (exp/sub), giới hạn địa chỉ giao diện được gọi API có đăng nhập. Kiểm tra token/giao diện đang dùng trước khi sửa để tránh hỏng luồng hiện tại; không public deployment. Không tách thành gói trước MVP hoặc backlog riêng. Quyết định qua chat, không tạo receipt form thay người dùng; chưa triển khai mã.
- F-BOOKING: APPROVED ngày 27/10/2026 theo bản đã sửa ở F-BOOKING_MVP_CONTRACT.md. AI query đúng loại dịch vụ và ràng buộc, hiển thị kết quả có căn cứ; người dùng bấm “Book Ngay” mới chuyển screen booking, giữ đúng đối tượng và thông tin đã có. Không tìm thấy/chưa xác định thì báo/hỏi. Lệnh đặt ra dịch vụ khác là fake, UI phân biệt mô phỏng với đặt thật. Chưa có quyền đặt chỗ thật. Mục này đã đóng, không còn chờ duyệt.
- F-UI: HOLD theo chủ dự án — UI hiện tại chưa giống app OTA; quyết định UI cuối cùng để sau, có thể sử dụng bản draft demo chức năng. Không yêu cầu chốt thiết kế UI cuối cùng trong đợt này. Luồng chức năng được xem riêng với thiết kế hình ảnh.

## Nguyên tắc rà soát

- Form tổng hợp hiện hành: `review-20261027/`, tại http://127.0.0.1:19127/. Snapshot v3 ngày 28/10 áp dụng TEST-GATE đã duyệt, giữ UI HOLD và các quyết định còn lại; không còn mục PENDING trong 25 mục hiện có. Snapshot v1/v2 và biên nhận gốc giữ nguyên. Việc không còn câu hỏi PENDING không đồng nghĩa hệ thống đã được triển khai/kiểm chứng hoặc đã đóng băng toàn bộ schema kỹ thuật.

- Phân biệt behavior đích đã duyệt, mô tả mã hiện có và bằng chứng kiểm chứng.
- Không dùng các đoạn trạng thái lịch sử để phủ nhận baseline test đã ghi sau đó.
- Việc chuẩn bị/rà soát contract không tự mở H1, viết luận văn, Finalizing hoặc triển khai booking thật.
