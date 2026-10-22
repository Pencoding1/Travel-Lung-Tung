# SYS098 — bộ thu thập hệ thống/đối kháng có biên (OFFLINE)

Trạng thái Codex QA: **đã nhận offline sau SYS100 — 83 test giả lập đạt**.
Bốn gate còn thiếu ở SYS098 đã sửa: danh tính model sau lọc log, chặn lượt sinh
sau lỗi HTTP, dọn khởi động dở qua helper kiểm quyền sở hữu và `not_exercised`.
Xem `docs/project/handoffs/SYS-100/parent-final-acceptance.json`.
Chưa có kết quả đối kháng qua HTTP/model thật; trước khi chạy cần chốt manifest,
runtime, nguồn và ngân sách. Kết quả thất bại SYS098/SYS100 ban đầu vẫn được giữ.
Các lệnh CLI điều phối OpenCode là công việc coding, không phải thí nghiệm.

## Đây là gì

Một launcher/collector tùy chọn cho **một** nghiên cứu tương lai về tiêm lỗi
HTTP có kiểm soát trên môi trường cục bộ, cùng một đối chứng native tự nhiên.
Chín trường hợp cố định, một lần lặp, không suy luận thống kê:

| # | Case | Chế độ | Can thiệp có kiểm soát | Kỳ vọng |
|---|------|--------|------------------------|---------|
| 1 | A_empty | source | mọi `explore_pois` → candidate rỗng hợp lệ | `insufficient_data`, 0 provider |
| 2 | A_enrichment_failed | source | `get_poi_details` → `isError` có kiểm soát | `insufficient_data`, 0 provider |
| 3 | C_no_match_native | current-admin | không | `location_not_resolved`, 0 provider |
| 4 | C_ambiguous | current-admin | resolver → 2 District 1 khác ID | `location_ambiguous`, 0 provider |
| 5 | C_wrong_parent | current-admin | resolver → parent city xung đột | `scope_conflict`, 0 provider |
| 6 | C_partial_collision | current-admin | resolver → chỉ District 10 | `location_not_resolved`, 0 provider |
| 7 | B_unknown_id | source | plan hợp lệ, ID đầu → `SYS098_GHOST_ID` | `unknown_poi`, generation thật |
| 8 | B_unsupported_fields | source | plan hợp lệ + name/address/price/hours/description tự soạn | từ chối rõ ràng **hoặc** trường thực được tái tạo từ bằng chứng MCP |
| 9 | S_native_control | source | không | 2 ID thực, route car đầy đủ, giờ aware tăng dần |

Mọi phản hồi bị thay thế đều được đánh dấu `_sys098.controlled_response_used`
và `injection_exercised`. Chúng **không phải** dữ liệu graph thật, không phải
tần suất lỗi graph tự nhiên, không phải bằng chứng tỷ lệ hallucination/H1 và
không chứng minh sự thật hành chính. Không sửa graph để tạo lỗi.

## Cấu trúc

- `qa_runtime.py` — seam chỉ được cài khi `SYS098_ENABLE_QA=1`; middleware
  `X-TVLT-QA-Case`, ContextVar theo request, proxy MCP gọi thật trước rồi mới
  thay thế đúng stage, wrapper provider gọi thật đúng một lần rồi mới nhiễu
  plan đã parse hợp lệ. Không có patch lúc import, không import ứng dụng lúc
  import.
- `runner.py` — manifest ứng viên (chưa đóng băng), kiểm tra manifest đã được
  phụ huynh phê duyệt trước khi dựng backend, 9 request cố định, ledger JSONL
  bền vững, phân loại `observed_pass` / `observed_failure` / `not_exercised` /
  `missing`, dọn dẹp child thuộc sở hữu trong `finally`.
- `tests/system_adversarial/test_collector.py` — kiểm thử tổng hợp, không có
  tiến trình/HTTP/model thật.

## Chạy offline

```powershell
# Dry-run mặc định: dựng manifest ứng viên, KHÔNG dựng backend/socket/provider.
python -m benchmarks.system_adversarial.runner

# Kiểm thử tổng hợp
python -m pytest tests/system_adversarial/test_collector.py -q
```

`--execute --manifest <frozen.json> --out <new-dir>` chỉ dành cho Codex sau
khi nghiệm thu và đóng băng. Thư mục output phải mới; không resume/ghi đè/retry. Executor
offline **không** chạy lệnh này.

## Ràng buộc đã giữ

- Chỉ thư viện mới trong `benchmarks/system_adversarial/` và test mới; không
  sửa app/helper/test cũ/dữ liệu đóng băng.
- `NativeBackend` được tái sử dụng nguyên vẹn; chỉ chèn một bootstrap QA thử
  nghiệm vào tiến trình AI service, kiểm tra marker chính xác một lần, khôi
  phục helper trong `finally`. MCP child không có injection.
- Guard carriers (`OPENCODE_CONFIG`, `OPENCODE_CONFIG_CONTENT`) không bị thay
  thế; không đọc/ghi bí mật, `.env` hoặc credential. Runtime chỉ đọc header
  chọn ca QA đã chốt; không lưu header xác thực.
- Cổng 19601/19602; cổng demo 19101/19102 bị cấm; engine 17687/18989 chỉ được
  kiểm tra sẵn sàng, không khởi động/phục hồi.
- Tối đa 9 HTTP, 3 request có thể sinh, 15 CLI attempt; timeout 30 giây, một
  attempt mỗi call; không fallback trả phí; không gọi chat/Jev trong collector.
