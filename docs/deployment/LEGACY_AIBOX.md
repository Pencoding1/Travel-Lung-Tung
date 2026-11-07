# AIbox cho legacy demo

**Cập nhật mới nhất:** classifier gọi **TypeSafe Jev trực tiếp**, model `jev-1.13.0`, dùng `TYPESAFE_API_TOKEN`, qua adapter legacy `domains/jev_intent.py`. Model sinh câu trả lời gọi **API AIbox trực tiếp**, model `ds/deepseek-flash`, qua `scripts/aibox_adapter.py`. Không dùng OpenCode CLI trong hai nhánh hiện tại. Lượt chat thật và nhánh hỏi lại đã kiểm tra thành công. Không fallback provider khi lỗi.

Chạy `legacy.bat` khi engine local đã sẵn sàng. Trang: http://127.0.0.1:19202/travel.

Launcher cài adapter HTTP thật ở `scripts/aibox_adapter.py` vào app lúc khởi động, không sửa167file source snapshot. Adapter sinh nội dung gọi `https://api.ai-box.vn/v1/chat/completions`, model `ds/deepseek-flash`. Model từ API quan sát ngày28/10: `deepseek-flash`.

Classifier giữ nhãn CHITCHAT/TRAVEL/UNCERTAIN và quy tắc hỏi lại/chặn dispatch khi chưa rõ. AI service vẫn kiểm soát công cụ nghiệp vụ. Hai wrapper classifier tạm thời OpenCode và AIbox còn giữ như lịch sử, không được launcher hiện tại nạp.

Key mang tên `AIBOX_API`: dùng biến process nếu có, nếu không dùng đúng key đó trong `.env` root qua loader giới hạn. Không ghi key vào source, log, CLIconfig hoặc tham số lệnh. Giá trị process rỗng/không hợp lệ sẽ báo lỗi thay vì chuyển nguồn. Không tự đổi provider khi có lỗi.

Chỉ áp dụng cho launcher legacy này. Chạy `ai_service/main.py` riêng vẫn theo cơ chế provider sẵn có của service, không tự chuyển sang AIbox. Engine demo riêng dùng Memgraph17687 và GraphHopper18989, hiện có profilecar.

Test adapter offline: `.venv/Scripts/python.exe -m unittest discover -s tests/aibox_adapter -v`. Không nhầm những test này với nghiệm thu behavior thật. Lượt chat thật đã thành công, kiểm tra toàn bộ luồng du lịch/lập lịch vẫn là việc riêng.

Tài liệu gốc: https://home.ai-box.vn/docs và https://docs.truongblack.me/#/integrations/opencode.
