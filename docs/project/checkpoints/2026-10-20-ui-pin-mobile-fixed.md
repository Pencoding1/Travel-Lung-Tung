# Checkpoint Codex — sửa ghim và thẻ POI trên mobile

20/10/2026. Tiếp tục mục tiêu demo chatbot theo chỉ đạo user. Turn trước là
**PROGRESS**: đã giao mã UI, render và bằng chứng API thật; không phải vòng chờ.

## Kết quả mới

Đã tái hiện và sửa ba lỗi giao diện:

1. Chọn POI từng ghi đè lớp CSS MapLibre, làm ghim chuyển từ `absolute` sang
   `static`. UI135 chỉ thêm/bỏ lớp `selected`, giữ các lớp định vị.
2. Bảng lịch trình từng che ghim trong hai bố trí desktop. UI135 tính khoảng
   chừa camera theo vùng bị bảng che, thay vì luôn chừa 56px.
3. Popup mobile cao hơn khung bản đồ nên bị cắt thông tin và nút đóng. UI137
   dùng cùng thẻ DOM an toàn trong luồng trang ở màn hình <=620px; desktop vẫn
   dùng popup MapLibre. Không thay API, session, memory, source scope hay routing.

Codex lập kế hoạch/QA/nghiệm thu; OpenCode Go `opencode-go/deepseek-v4.1-flash`
thực hiện hai gói nhỏ. Không dùng AI-box trả phí cho đợt sửa này.

## Kiểm chứng

- BROWSER134 trên mã cũ giữ nguyên kết quả thất bại: cả sáu ca mất lớp định vị;
  hai ca desktop có ghim bị bảng lịch trình che. Không dùng các timeout click
  ghim ở xa sau zoom để khẳng định lỗi: camera có thể hợp lệ đưa ghim ra ngoài.
- BROWSER136: sáu bố trí desktop/mobile đạt hit-test, định vị và chọn POI. QA
  ảnh tiếp tục phát hiện card mobile bị cắt; giữ raw result và finding riêng.
- BROWSER138 trên mã mới: **6/6 bố trí** đạt ghim ban đầu không bị che, click
  mở đúng thẻ, chọn thẻ đúng POI, giữ lớp MapLibre/absolute; cả thẻ, thông tin
  địa chỉ/giờ và nút đóng đọc được đầy đủ. Parent đã xem ảnh desktop/mobile.
- 8 nhóm Node và 18 kiểm tra race vẫn đạt trên mã cuối. Đối chiếu byte chứng
  minh UI135 và UI137 chỉ đổi các khối đã giao; 163 backend pins giữ nguyên.

BROWSER138 là browser thật chạy **HTML/catalog/POI giả lập**, không gọi native
service, model hay Jev; asset bản đồ từ host đã duyệt. Không được gọi đây là
live itinerary hoặc nghiên cứu người dùng. BROWSER136 cũng là fixture API.

## Giới hạn và việc tiếp theo

- BROWSER131 lịch sử vẫn PARTIAL: chat/typed thật và hai ghim đúng tọa độ đạt,
  click/popup timeout; 4 Go/4 CLI +1 Jev. Không sửa, chạy lại hay suy nguyên
  nhân timeout đó từ các lỗi vừa tái hiện. Chưa chạy live lại trên mã cuối.
- Probe health phụ bằng urllib trong sandbox bị PermissionError13/Win10013.
  Đã dừng, không đổi executor để thử lại endpoint bị chặn; không suy service
  down. BROWSER138 không truy cập localhost/health, chỉ kiểm HTML giả lập.
- Có thể cho user thử lại demo cục bộ bằng refresh giao diện. Không khẳng định
  uptime từ kết quả trước hoặc full deployment. Luồng core native thật có bằng
  chứng riêng; UI mới chưa có một receipt live đầy đủ sau bản sửa.
- Giao báo cáo phase4 cùng giới hạn. Chờ user chọn H1 hoặc viết tiếp luận văn;
  H1 hiện0 participants. Crawler/new harness/grow-with-user vẫn Finalizing.
- Không tự mở batch model mới, rerun frozen H2/H3/E2/TIM097/SYS101 hoặc dùng
  lại quyền one-shot cũ. Mục tiêu tổng thể IN_PROGRESS, chưa được chứng nhận đủ.

## Điểm tiếp tục chính xác

Mã cuối: `ai_service/static/travel.html`, SHA256
`355c713bce7f3ab227fc1d0321cb1af5199c4e35c41c57b8ab1c75db5bb3c679`.

UI135 SID `ses_ea6ac5b2affeTMnYUUn6FNg6v7`, handle67686 terminal0,
interrupt0/wait0. UI137 SID `ses_ea6a66382ffe0S512atReJEMO4`, handle99156
terminal0, interrupt0/wait0. Đều có worker return.json; không relaunch.
B136 handle84759 terminal0; B138 handle51243 terminal0; browser sở hữu đã đóng.

Evidence: handoffs/UI-135, BROWSER-134, BROWSER-136, UI-137, BROWSER-138.
Report cập nhật DOC139 tại docs/reports/2026-10-18/index.html. CLI metadata ở
E:/Agent_Artifact/TVLT_2026/2026-10-20/ui135-pin-fix/ và ui137-mobile-card/.
Đọc FOUR_PHASE_PLAN.md và EXECUTOR_POLICY.md trước bàn giao mới; một writer,
Codex chốt /plan workflow, OpenCode coding; không đọc raw env/config/auth.
