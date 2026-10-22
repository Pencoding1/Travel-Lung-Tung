# Checkpoint Codex — ưu tiên hoàn thiện luồng chính

Người dùng phản hồi tiến độ bị kéo dài bởi QA. Codex nhận trách nhiệm về việc chưa chốt được luồng sử dụng hoàn chỉnh. Checkpoint này cập nhật ưu tiên, không thay thế bằng chứng kỹ thuật trước đó.

## Trạng thái xác nhận

- Docker Desktop đã được người dùng mở. Codex kiểm tra chỉ đọc `docker info --format '{{.ServerVersion}}|{{.OSType}}'`: sandbox trả permission denied tại named pipe; cùng lệnh qua quyền host được duyệt trả `29.2.1|linux`, exit 0. Không kết luận engine đang tắt từ lỗi quyền sandbox.
- Dữ liệu chính đã nhập 6.367 POI; bằng chứng import/replay/restart nằm ở DATA-068. Không nhập lại chỉ để báo tiến độ.
- CORE-069 R1 có UI/catalog và mã tích hợp, nhưng actual itinerary HTTP 200 có body failed với `export_non_text_content`. Chưa có bằng chứng toàn luồng gợi ý và định tuyến thành công.
- CORE-069 R2 đang chạy: session `ses_eb201dea0ffe88oB4UGIXhOmrr`, handle `12839`, model `aibox/ds/deepseek-flash`. Lần poll tại checkpoint chưa kết thúc. Không khởi động lại hoặc tạo writer trùng.

## /plan — thứ tự thực hiện tiếp

1. Nhận kết quả R2 về khởi động/cấu hình/ownership; giữ các sửa lỗi đã có. Không đổi backend đang chứa dữ liệu chỉ vì Docker vừa sẵn sàng. Nếu dùng Docker, kiểm tra cấu hình và dữ liệu đích trước, tránh tạo một stack trống hoặc trùng dịch vụ.
2. Chốt lỗi tương thích export OpenCode trong một nhiệm vụ code giới hạn, kế hoạch và acceptance do Codex viết; OpenCode thực thi. Không đổi alias model, không bỏ kiểm tra tool/identity, không thử gọi paid model lặp lại khi chưa sửa nguyên nhân.
3. Chạy luồng người dùng thật: nhập yêu cầu và phạm vi → gợi ý POI/lịch trình → route đúng car/foot → kết quả hiển thị có dữ liệu tuyến thực. HTTP 200 kèm failed không đạt.
4. Chỉ chạy regression trực tiếp liên quan phần thay đổi và một lần kiểm chứng độc lập cho luồng tích hợp. Không lặp suite đã đạt khi code liên quan không đổi; chỉ mở lại nếu có lỗi cụ thể chặn luồng chính hoặc rủi ro dữ liệu/bí mật/quyền.
5. Chốt phần S1–S6 còn thiếu bằng checklist ngắn, checkpoint/handoff, sau đó phase 3 thí nghiệm và phase 4 báo cáo theo phạm vi đã duyệt.

Phase 5 tên **Finalizing phase**: toàn bộ cơ chế mới gồm crawler, nguồn xã hội/travel agency, grow-with-user/harness và enrichment. Không lấy chúng làm điều kiện chặn hoàn thành phase 2. H1 và viết luận án chờ lựa chọn của người dùng sau phase 4.

## Quy tắc báo cáo

Báo rõ đã chạy được gì và còn lỗi nào ngăn người dùng sử dụng. Không dùng số lượng test thay cho mức hoàn thiện sản phẩm. QA đủ để nghiệm thu hành vi; không mở vòng gia cố không có điểm dừng. Lưu checkpoint sau mỗi mốc lớn.

## Dispatch triển khai đã thực hiện

Codex gửi kế hoạch `handoffs/CORE-069/revision-3-delivery.md` vào cùng session qua official session.prompt/steer. Receipt exit0, inbox `msg_14e53a4760013w36juRwmAO4zx`. Đây là proof admitted, chưa phải consumed/completed. Scope thêm provenance.py + focused provider tests, không thêm agent. Handle12839 vẫn live khi poll. Python urllib schema fetch trả403, không retry/workaround; schema công khai đã được Codex đọc qua web trước đó, executor nhận facts đã chốt trong brief.
