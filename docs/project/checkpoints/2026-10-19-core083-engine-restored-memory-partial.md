# Checkpoint CORE083 — Codex, 19/10/2026

**Lệnh được người dùng cho phép đã chạy đúng một lần, handle55328 kết thúc exit1. Quyền đã dùng hết; không chạy lại tự động.** Đây là kết quả cuối thay cho checkpoint “authorized-running”, CORE082 active và CORE081 chưa chạy trong các snapshot cũ.

## Đã hoàn thành

- Khôi phục engine từ cache/dữ liệu cũ: 6.381 node, 3.684.764 quan hệ, gồm 3.678.397 NEAR_BY; GraphHopper health200. Không tải/cài/import/rebuild hoặc sửa guard.
- Kiểm tra cổng độc lập trên Windows:17687/18989 còn lắng nghe; stack thử19601/19602 đã đóng. Probe socket trong sandbox trả false không đáng dùng để kết luận runtime dừng; lưu cả giới hạn này.
- Hash driver đúng7230d0e1…dcbe và58 tệp công khai vẫn khớp pin. Mã bridge/collector không bị sửa bởi batch.
- Batch CORE081 riêng đã dùng2 request API,4 lượt CLI sinh nội dung được ghi nhận, source catalog1483 đầy đủ. Không phải primaryH3, không thay thế batch CORE079 cũ.

## Kết quả memory: chưa nghiệm thu đầy đủ

Short-term prep thành công. API lập lịch trả HTTP200 nhưng status=failed; provider session trả thành công với đúng opencode-go/deepseek-v4.1-flash. Export đúng session đã kiểm tra trước đó cho thấy marker short-term có trong input và JSON đầu ra thiếu top-level stops, có itinerary. Không suy thành lỗi quota/provider hoặc lỗi memory mất history.

Mã validator yêu cầu stops. Minimal reproducer thiếu stops trả plan_invalid trước khi xét evidence. Đây không phải replay đầy đủ output hoặc mã lỗi thực tế của response đã không được lưu (mã đó vẫn unknown). Lần export kiểm lại trong sandbox exit khác0; không retry/đổi executor; không lưu raw diagnostics. Không suy nguyên nhân exit đó.

Batch có0/2 cell đạt,2 cell thiếu; two-tier chưa gọi. Đã dọn stack thử; engine giữ chạy. Chưa chứng minh credential absence của input gốc sau khi issuer RAM được dọn. Không nới validator, tự map itinerary→stops hoặc chạy đi chạy lại để lấy kết quả đẹp.

## Bàn giao tiếp theo — Codex sở hữu kế hoạch/QA

1. Phân biệt model không tuân thủ schema với lỗi truyền prompt/hợp đồng thật bằng nguồn và bằng chứng đã có; chưa giao sửa production nếu chưa xác định lỗi mã. Lập /plan trước khi giao OpenCode AI-box ds/deepseek-flash; không để executor tự đặt tiêu chí.
2. Bằng chứng native two-tier và full study freeze vẫn thiếu. Quyết định gói kiểm định tiếp theo có giới hạn, giữ các thất bại cũ; mọi lần chạy mới liên quan phạm vi từng bị guard chặn cần quyền cụ thể mới khi áp dụng. Không tái dùng quyền CORE083/CORE079/MEM072.
3. Sau gate phase2, thực hiện phase3 H2/H3/E2/system/adversarial theo giao thức, công bố cả nondelivery. Không yêu cầu mọi output phải thành công mới giữ mẫu số.
4. Phase4 báo cáo rồi người dùng chọn H1 hoặc luận án. H1 hiện0 người; không tự tuyển/viết luận án. Toàn crawler/social/travelagency/grow-with-user/harness ở phase5 Finalizing.

Không reset/clean/commit/push; không đọc raw env/config/auth, không đổi guard/global allowlist hoặc dùng ALL. Giữ frozen primary và thay đổi người dùng. Checkpoint sau mỗi mốc lớn. Goal tổng vẫn ACTIVE/INCOMPLETE; không dừng ở riêng gói QA này.

## Bằng chứng

- docs/project/handoffs/CORE-083/parent-execution-authorization.json
- docs/project/handoffs/CORE-083/parent-run-result.json
- docs/project/handoffs/CORE-083/parent-failed-stage-export-review.json
- docs/project/handoffs/CORE-083/parent-final-review.json
- docs/project/handoffs/CORE-083/parent-host-listeners.json
- docs/project/handoffs/CORE-081/qa-work/remaining-memory-1c5230904fc4/results.json và ledger.jsonl
