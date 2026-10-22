# Kế hoạch Codex — chuyển phân loại ý định sang Jev

Chỉ đạo người dùng ngày 18/10/2026: bỏ Ollama/local LLM ở bước phân loại ý định, yêu cầu OpenCode dùng Jev. Phạm vi thuộc giai đoạn 2; hiện **chưa triển khai**. Codex lập kế hoạch và ca QA trước; agent thực hiện đúng kế hoạch, không tự mở rộng.

## Căn cứ

- Đã đọc kỹ năng Hermes tại `C:/Users/duyan/AppData/Local/hermes/skills/typesafe-ai/SKILL.md`. Không tuyên bố đã trao đổi với Hermes hoặc khôi phục lịch sử phiên: chỉ tìm thấy và đọc kỹ năng cài sẵn. Một lần đọc SQLite lịch sử ở chế độ read-only không mở được; không sửa DB.
- Đối chiếu tài liệu chính thức ngày 18/10/2026: [intent routing](https://docs.typesafe.ai/patterns/intent-routing), [API](https://docs.typesafe.ai/api), [Choice](https://docs.typesafe.ai/primitives/choice), [index](https://docs.typesafe.ai/llms.txt). Các URL .md cho API/Choice lỗi qua web; trang thường đọc được.
- Mã hiện tại `ai_service/main.py` có `_router_prompt`, yêu cầu CHITCHAT/TRAVEL qua model provider. Không coi ghi chú Ollama cũ là bằng chứng còn chạy Ollama. Phải kiểm tra chính xác caller trước khi sửa.

## Kế hoạch triển khai có giới hạn

1. Rà caller của router, hợp đồng response và bộ kiểm thử hiện có; lập danh sách tệp sửa chính xác trước bàn giao triển khai. Giữ nguyên planner, MCP, grounding và model sinh nội dung.
2. Tách adapter phân loại ý định Jev với client có thể inject để test. Dùng API TypeSafe hiện hành: POST `/v1/systemone`, câu hỏi Choice có tập nhãn/tiêu chí đóng và kết quả không khớp/mơ hồ. Đọc đầy đủ schema trả về hiện hành trước khi viết parser. Không dùng Jev như API chat OpenAI-compatible hoặc yêu cầu trả JSON tự do.
3. Cấu hình khóa phía server, timeout và giới hạn retry rõ; không log khóa hay toàn bộ lịch sử người dùng. Không tự tìm/copy khóa từ Hermes. Xác định tên biến cấu hình qua kế hoạch triển khai, không giả vờ đã có khóa.
4. Trả nhãn cùng phân phối/độ tin cậy có kiểm tra kiểu, số hữu hạn và tập giá trị. Khi mơ hồ hoặc dịch vụ lỗi, dùng kết quả hỏi lại/báo tạm không khả dụng theo hợp đồng đã chốt; không âm thầm gọi Ollama hay model khác.
5. Chọn ngưỡng từ dữ liệu kiểm chứng thay vì sao chép số minh họa tài liệu. Giữ prompt/tiêu chí và phiên bản có thể tái lập. Có thể dùng alias cấu hình khi phát triển, nhưng thí nghiệm phải ghi model thực tế trong response và đóng băng phiên bản/cấu hình.
6. Tính cả latency/usage/lỗi Jev trong chi phí toàn luồng; hai nhánh thí nghiệm có cùng điều kiện phân loại hoặc công bố tách biệt. Thay đổi chỉ áp dụng các lần chạy mới; không viết lại bằng chứng lịch sử.
7. OpenCode thực hiện; Codex đọc diff, kiểm thử và probe độc lập rồi mới nhận. Cập nhật báo cáo kiến trúc: Jev là dự kiến cho đến khi có mã và bằng chứng; không vẽ như tích hợp đã chạy.

## Ca QA do Codex xác định

- Tiếng Việt có/không dấu, chào hỏi, tìm POI, lập lịch trình, câu trộn chào + yêu cầu du lịch, câu chỉ nhắc tên địa danh, câu không rõ mục đích.
- Prompt injection trong nội dung không đổi tập nhãn hay cho phép thực thi tool; phân loại không cấp quyền hoặc đổi vùng nguồn người dùng đã chọn.
- Nhãn ngoài tập, thiếu answers, thiếu model, confidence sai kiểu/NaN, phân phối bất hợp lệ: từ chối hoặc trả trạng thái chưa xác định, không tự gán TRAVEL.
- Timeout, hủy, 401, 429/retry-after, 5xx, hết retry: thời gian hữu hạn, lỗi được ghi đúng, không fallback Ollama và không gọi model sinh nội dung ngoài ý định.
- Kiểm tra không còn call tới Ollama/local classifier trên luồng intent; model trả lời vẫn dùng provider được chọn và planner giữ nguyên.
- Kiểm thử mocked không tính là đo chính xác Jev. Live smoke/đánh giá có usage và danh tính model chỉ sau khi cấu hình sẵn và đến đúng giai đoạn; không chạy paid experiment trong gói báo cáo.

Đầu ra trước mắt: cập nhật báo cáo và backlog theo thay đổi này. Chưa giao thêm agent sửa mã khi OC047 đang chạy; giữ trọng tâm một gói việc.

## Rà hợp đồng mới nhất — Codex18/10, chưa dispatch

CLI060 đang sở hữu provider source; Jev chưa được giao triển khai. Phần ghi OC047 đang chạy ở trên là lịch sử, không phải ownership hiện tại.

Codex đọc lại [API](https://docs.typesafe.ai/api) và [Choice](https://docs.typesafe.ai/primitives/choice): request có `state`, `model`, `questions`; mỗi Choice dùng `instructions` và `criteria`. Response có model thực tế, answers theo question id, usage input/output; Choice có `choice`, `probabilities`, `confidence`. Không coi confidence bằng xác suất cao nhất hoặc tự tính một thay cho trường thiếu. Kiểm phân phối đúng tập nhãn, hữu hạn, tổng gần1; choice phải là một cực đại. Ngưỡng quyết định phải được khai báo và hiệu chuẩn trước đánh giá chất lượng; ví dụ docs không phải ngưỡng dự án.

Caller hiện tại `/chat` lấy `router['intent']` rồi gọi nhánh travel cho mọi giá trị khácCHITCHAT, đồng thời tests còn yêu cầu fallbackTRAVEL khi router malformed. Vì vậy chuyểnJev cần sửa CẢcaller và contracttests: ambiguous/unavailable phải dừng trước sinh nội dung/MCP/memorycommit, trả kết quả hỏi lại hoặc lỗi xác định; không chỉ thay HTTPclient. Intent không cấp quyền/tool/source scope. Chỉ sửa các test gắn với hành vi fallback đã bị yêu cầu thay đổi, giữ regression tenant/history/auth còn lại. Đây là caQA Codex chốt trước, không phải mã hay năng lực Jev đã có.
