# Checkpoint Codex — khởi động nghiệm thu và call graph

Ngày 21/10/2026, Asia/Saigon. Người điều phối và người quyết định nội dung: **Codex**.

## Demo đã chạy

- URL: http://127.0.0.1:19102/travel. Codex đã mở IAB, xác nhận catalog 6.367 bản ghi, chọn 26 vùng nguồn, bản đồ nền sẵn sàng và nút chat/tạo lịch hoạt động. Không tự gửi yêu cầu model để nghiệm thu thay người dùng.
- Run `core069-beb386a5b6f0`: MCP PID39716/cổng19101, AI PID22768/cổng19102; ownership và health đạt. Giữ các service và engine chạy cho người dùng.
- Engine khôi phục sau **quyền mới của người dùng trong lượt này**, không tái sử dụng quyền one-shot cũ: Memgraph LinuxPID1401/cổng17687, GraphHopper LinuxPID1612/cổng18989. 6.367 POI, 3.678.397 NEAR_BY, profile car và foot.
- Đã kiểm sáu pin package/binary/JAR/PBF công khai và hai đường dẫn routing trong RAM. Không tải/cài/import/rebuild/gọi model ứng dụng. Launcher bình thường có ghi metadata/fingerprint runtime như người dùng đã được thông báo và cho phép.
- Bằng chứng: `handoffs/START-154/engine-preflight-approved.json`, `engine-result-approved.json`, `parent-final-readiness.json`, ảnh `demo-ready.png`.

## Khởi động nhanh

`E:/Project/TVLT_2026/START_DEMO.bat` dùng root từ `%~dp0`, gọi helper PS1 có quote, giữ exit code và cửa sổ thông báo. Có `-NoBrowser`, `-NoPause`. Chỉ mở trình duyệt sau khi engine, ownership và health đều đạt. Chạy lại giữ cùng run/PID, không nhân đôi service. Chỉ reconcile trạng thái cũ khi đúng hai PID đã mất và hai cổng trống; không dừng process lạ.

**Bổ sung cuối đã nhận:** Khi cả hai cổng engine đều đóng, BAT gọi `scripts/native_runtime/start_cached_engines.py` để bật từ binary/cache cũ qua WSL. Helper production chỉ đổi ROOT, thư mục receipt UUID và nhãn task so với logic startup thực tế vừa đạt; giữ nguyên sáu pin và thân hàm. Khi engine khỏe thì dùng lại; trạng thái chạy một phần hoặc cache không hợp lệ thì dừng. Đã compile/AST/PowerShell parse và Codex cha chạy BAT trên stack khỏe exit0, không tạo trùng. Không tắt demo hoặc reboot Windows để chạy lại cold-BAT; bằng chứng cold engine là lần helper gốc chạy thực tế, còn nối BAT→helper được đọc mã. Hướng dẫn chính: `scripts/native_runtime/QUICKSTART_VI.md`. Cần WSL Ubuntu và runtime/cache đã chuẩn bị; không phải trình cài đặt cho máy mới.

OpenCode Go triển khai launcher theo kế hoạch Codex. Lượt đầu exit0; R1 dừng đúng giới hạn quan sát khoảng90,6s/exit1, thiếu return R1, nhận source nhờ kiểm tra điều phối và lần chạy thực tế thành công. Có interrupt/wait/target-absent/same-server proof trong START154. Bổ sung cold-start qua hai lượt Go: lượt150s hết hạn trước khi sửa mã; một lượt tiếp tục120s giao mã nhưng thiếu return lúc ngắt121,47s. Nhận theo source đối chiếu và kiểm tra độc lập, không tự tăng budget hoặc chuyển paid fallback; các receipt thất bại giữ nguyên. Không quy exit CLI thành whole-system acceptance.

## Call graph tương tác đã giao

- File `docs/reports/callgraph-2026-10-21/index.html`, standalone/offline.
- **Toàn bộ nội dung do Codex cha viết** trong `handoffs/GRAPH-155/content.json`: 12 module, 7 layer, 19 quan hệ, 3 luồng. Đã đối chiếu source references. Sub-agent/OpenCode chỉ hiện thực giao diện, không quyết định facts hay ví dụ.
- Bộ lọc module (module và hàng xóm trực tiếp), layer, luồng; kết hợp bộ lọc; reset; node mở popup input/output, mô tả và source references; hỗ trợ bàn phím/Escape/focus.
- Đây là call graph mức module, không phải trace runtime hay đồ thị mọi hàm. Ví dụ được ghi rõ là minh họa rút gọn; số đo GraphHopper thật được gắn nhãn riêng. Chat → typed planner không có cạnh tự động; CHAT153 vẫn backlog.
- Codex kiểm JSON nhúng khớp hoàn toàn nội dung cha; receipt browser executor khớp HTML hiện tại, 141 assertions đạt; đã đọc assertions và xem ảnh1440x900. Bốn kích thước không tràn ngang; cuộn dọc danh sách quan hệ/giới hạn là document flow được chấp nhận, không ép thu nhỏ chữ.
- SHA HTML hiện tại: `67d59ca704e7290a11c10f24e9324abfa0e8b55c54a420e17932456504052e30`. SHA nội dung cha: `482059d6753910eb59394940953b3d37604141a40070a2a3f8dc3a8540f2c263`.
- IAB từ chối protocol file://; không dựng server hoặc đổi browser để vượt chính sách. Giao file HTML để người dùng tự mở. Browser QA/ảnh executor được ghi riêng với giới hạn thứ tự thời gian. Không nhận đã mở preview call graph trong IAB.
- Giới hạn điều phối cần giữ nguyên: sau thông báo dừng browser cho coordinator, worker đã được giao trước đó vẫn tạo receipt browser mới lúc06:47:46UTC; nhận định ban đầu rằng toàn bộ QA xảy ra trước thông báo đã được rút lại. Runner chỉ ghi session ID lúc kết thúc nên không ngắt sớm được; đã interrupt/wait và xác nhận target absent ở deadline. Không chạy thêm browser để sửa bằng chứng. Các dispatch sau phải lưu exact session ID ngay khi nhận được để có thể dừng worker tức thì.
- Auxiliary Archify overview chưa hoàn tất; không có showcase delivery thành công. HTML custom là artifact chính, không gán chứng nhận Archify cho nó. Worker hết480s, quan sát482,18s rồi interrupt/wait0, target absent; chưa có worker return.json. Coordinator receipt không giả làm worker report; exact session `ses_ea2cf5fbdffew4NlaI9W8dNn6L`.

## Handoff tiếp

Chờ người dùng nghiệm thu. Không tự mở vòng QA mới, H1, viết luận văn, crawler/grow-with-user hoặc DEP149. Giữ các kết quả khoa học H2/H3/TIM/SYS đã đóng băng và các giới hạn cũ. Các scope này không được coi hoàn thành chỉ vì demo đã bật.

Các artifact executive theo ngày21/10 ở `E:/Agent_Artifact/TVLT_2026/2026-10-21/demo-start-bat/` và `callgraph-renderer/`.
