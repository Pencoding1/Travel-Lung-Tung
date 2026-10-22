# Checkpoint CORE085 — Codex, 19/10/2026

**Short-term đã chạy thành công với model và engine thật sau sửa CORE084. Two-tier vẫn thiếu bằng chứng typed; goal tổng ACTIVE/INCOMPLETE, phase2 chưa chốt.**

## Kết quả thật

Người dùng cho phép đúng lệnh CORE085 một lần. Script SHA92ea43d32f108876b6c5a37b428a9139bf9a43c30865feb06234302db199bab6 được kiểm và chạy; handle26238 kết thúc exit1/partial. Quyền đã dùng, không rerun hoặc dùng cho script khác.

- Batch mới `qa-work/memory-after-fix-36464dab3bd9`, không thay CORE079/081 thất bại và không phải primaryH3/H1.
- 3request API,7attempt CLI ghi nhận:6session thành công quan sát đúng opencode-go/deepseek-v4.1-flash,1attempt thất bại chưa quan sát identity/cause. Không gọi đó là7model success hoặc biết tổng billing.
- Short-term: prep và typed thành công; exact-session exports trong RAM chứng minh history marker/schema đầy đủ, không có stored profile, không lộ fixture credential. Hai selectedIDs thuộc source truth1483; source gates được driver kiểm, repaired schedule có giờ aware thực tế.
- Carroute được xác minh:1,645km/2phút làm tròn; hai lượt thăm45phút,09:00–09:45 và09:47–10:32 ngày02/11/2026. Giá/giờ thiếu, global validation vẫn unverifiable; không tuyên bố toàn lịch khả thi.
- Two-tier: PUT/GET profile200; prep có2stage generation thành công,stage3 thất bại. Dừng ngay, chưa gọi typed cho two-tier.1cell đạt/1cell thiếu trong batch2điều kiện; không cộng các batch khác thành thí nghiệm ba điều kiện đồng nhất.
- Cleanup thành công,19601/19602 đóng. Windows passive listener check xác nhận17687/18989 còn chạy.61public pins vẫn khớp. Không WSL/config/recovery/download/install/import/rebuild/guardchange.

## QA và giới hạn

Trước live:16ca fake-only đạt; các lỗi temp fixture ban đầu và startup-case test đòi ledger dù0API đã giữ trong log. Sửa QA setup/oracle theo hành vi0API, không nới pass criteria nguồn. Sau live:14check persisted evidence/source/times/route/cleanup đạt trong parent-final-review.json. Raw response/export không lưu, nên không gọi kiểm tra trên dữ liệu chiếu là replay raw độc lập.

**Thiếu sót bộ ghi bằng chứng do Codex viết:** top-level model_unavailable không nằm trong enum đóng nên thành unknown; reduced per-call receipt bỏ error_code. Nguyên nhân provider failed cuối cùng đã mất khỏi RAM khi process dọn. Không phục hồi bằng bịa/đọc unrelated histories/tìm latest session hoặc gọi thêm model. Không suy quota/auth/schema.

Driver đã thực thi phải giữ nguyên hash. Mọi sửa observation thực hiện ở source collector hoặc harness mới có review riêng; không sửa driver này để rồi chạy bằng quyền cũ.

## Việc cần hoàn thành tiếp

1. **Một gói offline tiếp theo:** Codex lập /plan giao OpenCode sửa nguồn collector ghi closed error enum đầy đủ + từng contributing failed receipt, phân biệt top-level business error với provider error; unknown text phải giữ unknown, tuyệt đối không raw error/body. Không cần modelcall để sửa/kiểm việc này.
2. Cùng gói đó, tạo source baseline mới theo CORE084 và cập nhật binding collector/candidate trước fullfreeze. `parent-freeze-drift.json` chứng minh baseline EXP080 hiện chỉ lệch main.py do sửa CORE084. Giữ nguyên baseline/protocol/failures lịch sử; không bỏ hoặc nới gate. Đừng sửa runner khi task native còn live; CORE085 nay terminal.
3. Native two-tier typed còn thiếu; chốt gói tiếp theo có giới hạn sau sửa attribution, không thử đi thử lại vô hạn hoặc chuyển paid provider cho ứng dụng. Mọi command mới chạm phạm vi deny trước cần quyền mới khi áp dụng; CORE085 exact-once đã dùng.
4. S1–S6/fullfreeze còn mở; sau gate phase2 chạy phase3 H2/H3/E2/system/adversarial theo protocol. Chưa có primary observation, chưa claim H3 effects/pvalues/token-savings.
5. Phase4 báo cáo và người dùng chọn H1 hoặc luận án;0người tham gia. Toàn crawler/social/travelagency/grow-with-user/harness mới ở phase5 Finalizing, không đưa lại vào đường găngphase2.

Codex sở hữu kế hoạch/QA/nghiệm thu/final prose; OpenCode code theo brief; Hermes thực thi OS/evidence trong guard. Executive artifact E:/Agent_Artifact/TVLT_2026/2026-10-19/native-memory-core085. Không liệt kê phiên khác; /api/session/active đã bị auto-review từ chối ởCORE084. Không raw env/config/auth/unrelatedhistory/ALL/globalguard edits/reset/clean/commit/push. Checkpoint sau task/phase quan trọng; tiếp đủ SG01–SG19/AC01–AC12, không gọi riêng batch này là hoàn thành goal.

## Authority

- handoffs/CORE-085/parent-execution-authorization.json
- handoffs/CORE-085/parent-run-dispatch.json
- handoffs/CORE-085/parent-final-review.json
- handoffs/CORE-085/parent_result_review.py
- handoffs/CORE-085/parent-freeze-drift.json
- handoffs/CORE-085/parent-unit-results-r2.txt
- handoffs/CORE-085/qa-work/memory-after-fix-36464dab3bd9/results.json và ledger.jsonl
