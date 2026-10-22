# Khởi động nhanh demo Travel/POI trên Windows

Nhấp đúp **START_DEMO.bat** ở thư mục gốc dự án. Cửa sổ kiểm tra engine,
khởi động AI/MCP khi cần và chỉ mở giao diện sau khi mọi health check đạt.

```bat
START_DEMO.bat -NoBrowser -NoPause
```

`-NoBrowser` không mở trình duyệt; `-NoPause` không chờ nhấn phím cuối lượt.
Script dùng vị trí file BAT, nên có thể gọi từ thư mục khác hoặc đường dẫn có dấu cách.

## Khi mở lại sau reboot

Nếu cả hai cổng Memgraph17687 và GraphHopper18989 đều trống, launcher tự dùng
binary, package và dữ liệu/cache đã chuẩn bị trong dự án để bật engine qua WSL Ubuntu.
Nó xác minh sáu tệp công khai, cache và hai đường dẫn routing trước khi khởi động.
Nếu một engine vẫn đang chạy nhưng engine kia thiếu, script dừng để tránh khởi động
chồng lên trạng thái chưa rõ. Khi cả hai engine khỏe, script chỉ dùng lại.

AI/MCP đang khỏe và thuộc launcher cũng được dùng lại. Hai PID cũ đã dừng, hai cổng
19101/19102 trống thì launcher có thể khởi động lại bằng cơ chế kiểm ownership sẵn có.
Tiến trình lạ hoặc identity không khớp làm script dừng, không tự kill/restart.

## Điều kiện

Máy cần WSL Ubuntu, runtime Python, OpenCode và engine/cache của dự án đã chuẩn bị
sẵn. Đây không phải trình cài đặt: thiếu/hỏng cache, package hoặc dữ liệu thì dừng;
không tải/cài/import/rebuild. Chat cần kết nối provider; bản đồ nền cần mạng.
Alias sinh nội dung là `opencode-go/deepseek-v4.1-flash`, không tự chuyển AI-box.

Giao diện: http://127.0.0.1:19102/travel. Tạo lịch bằng nút **Tạo lịch trình**;
chức năng tự nhận yêu cầu tạo lịch từ chat vẫn thuộc backlog CHAT153.

## Khi có lỗi và dừng dịch vụ

Đọc thông báo cố định trong cửa sổ, không chia sẻ raw log/config có khóa.
Receipt mỗi lần bật engine nằm riêng ở `.runtime-native/state/demo-startup/<uuid>/`.
Mã thoát0 là thành công; mã khác0 là dừng an toàn, không tự retry.

```bat
.venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py stop
```

Lệnh trên chỉ dừng AI/MCP sau kiểm ownership, không dừng hai engine.

## Bằng chứng hiện có

Ngày21/10/2026 đã khởi động engine từ cache cũ:6367POI,3678397NEAR_BY,car/foot;
AI/MCP health đạt và BAT chạy lại giữ nguyên PID. Helper tích hợp mới giữ nguyên
logic engine đã chạy thành công. Chưa tắt máy/reboot hoặc dừng engine chỉ để chạy
lại toàn bộ nhánh BAT từ trạng thái tắt; không coi đó là ca đã kiểm thực tế.
