# F-BOOKING — luồng booking MVP

- Ngày: 27/10/2026.
- Trạng thái: APPROVED — chủ dự án duyệt bản đã sửa ngày 27/10/2026.
- Phạm vi: luồng chức năng và điều hướng trên UI draft; lệnh đặt chỗ tới dịch vụ khác được làm giả.
- Liên quan: FT-CHAT-MVP-001, B1/B2/B4; không thay logic nhận diện intent, đối tượng và ràng buộc đã duyệt.

## Luồng đích

1. AI nhận diện yêu cầu BOOKING theo logic intent đã chốt; giữ loại dịch vụ, đối tượng và các ràng buộc người dùng cung cấp.
2. Query dữ liệu đúng loại hình dịch vụ người dùng mong muốn: table, vehicle, room hoặc service. Không suy ra dịch vụ có thể đặt chỉ từ việc POI tồn tại.
3. Hiển thị kết quả có căn cứ và hành động “Book Ngay” gắn với dịch vụ cụ thể. Khi chưa xác định được đối tượng hoặc không có kết quả phù hợp, hỏi/báo rõ; không tạo đối tượng giả để cho qua luồng.
4. Người dùng bấm “Book Ngay” thì chuyển tới screen booking với dịch vụ đã chọn và thông tin liên quan đã có. Nhận diện intent hoặc query kết quả không tự kích hoạt lệnh đặt chỗ.
5. Lệnh đặt chỗ từ screen booking tới dịch vụ khác là fake trong MVP. Giao diện phải phân biệt kết quả mô phỏng với xác nhận đặt chỗ thật.

## Invariant

- Chỉ hỏi thông tin không tự kích hoạt BOOKING; nhiều intent chưa rõ ưu tiên vẫn hỏi lại theo contract Chat.
- Không bịa dịch vụ, tồn chỗ, giá hoặc xác nhận từ nhà cung cấp. Dữ liệu thiếu vẫn là chưa biết.
- Chọn sai loại dịch vụ hoặc chuyển screen với đối tượng khác lựa chọn là lỗi.
- Fake áp dụng cho lệnh đặt chỗ ra ngoài; không lấy fake command làm bằng chứng tích hợp booking thật.

## Nghiệm thu dự kiến

- Yêu cầu từng loại dịch vụ dẫn tới query đúng loại, kết quả đúng dữ liệu và ràng buộc có thể kiểm chứng.
- Chưa bấm “Book Ngay” thì chưa chuyển screen do booking và chưa gọi lệnh đặt chỗ.
- Bấm “Book Ngay” chuyển tới screen booking, giữ đúng đối tượng đã chọn và thông tin liên quan.
- Không tìm thấy/chưa xác định đối tượng thì không bàn giao đối tượng bịa.
- Fake booking không gửi lệnh tới nhà cung cấp; UI không tuyên bố đã đặt thật.

## Giới hạn

- Chưa bao gồm thanh toán thật, kiểm tồn chỗ trực tiếp, gửi yêu cầu thật hoặc hủy/hoàn tiền thật.
- Bố cục OTA, thiết kế hình ảnh và UI cuối cùng đang HOLD, không phải tiêu chí phê duyệt trong contract này.
- Đây là contract đích, chưa phải bằng chứng triển khai hoặc nghiệm thu chạy thật.
