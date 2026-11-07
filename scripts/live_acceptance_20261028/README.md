# LIVE behavior acceptance — 2026-10-28

Suite này do Codex soạn để nghiệm thu qua HTTP/service/model thật, không phải unit hoặc mock suite. Không sửa implementation để lấy PASS trong lượt này.

- `freeze.py`: snapshot allowlist contract/receipt và pin mã công khai; không đọc secret/config.
- `cases.py`: 28 tình huống Chat và tiêu chí chốt trước request.
- `service_entry.py`: khởi động module sản phẩm thật, cấu hình process local; không fake/inject dependency.
- `run.py`: lượt mới có out path chưa tồn tại; gọi HTTP thật, pipeline chuẩn bị GeoJSON thật, giữ blocked/not-exercised; dừng generation sau failure.
- `provider_probe.py`: probe component transport thật độc lập nếu chưa có generation failure; không phải thay thế E2E hoặc đường vòng sau deny. Trong lượt 001 probe này KHÔNG chạy.
- `allowed_domains.txt`/`allowed_domain.txt`: local list 127.0.0.1, api.typesafe.ai, opencode.ai; không sửa global.

Không chạy lại bằng out cũ. Xem `docs/reports/live-acceptance-2026-10-28/REPORT_VI.md` trước lượt tiếp. Nhãn PASS của kiểm tra biên không chứng minh acceptance toàn feature. Những thành công Chat mới chưa đủ oracle được giữ NOT_VERIFIED; không tự cộng thành PASS.

Lượt 001 đã terminal: engineering acceptance còn BLOCKED bởi generation và dependency. Không dùng script để giả lập kết quả hoặc thay bộ offline 20 + 100.
