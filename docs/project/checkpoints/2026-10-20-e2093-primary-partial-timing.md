# Codex checkpoint — E2093 đã dừng, correctness đủ/timing thiếu

20/10/2026. Lượt goal này là progress: chốt prospective release, đo engine thật và phân tích bằng chứng. Full goal SG01–SG19/AC01–AC12 giữ nguyên, chưa đạt completion gate.

## Trạng thái authoritative

- **Handle83883terminalexit1**. Supervisor timeout3600,014994s, childPID33448đã terminate/reap, cleanupfailureNone. Không poll/relaunch/resume batch này nữa. Không suy timeout thành auth/quota; không gọi model hoặc recovery.
- Output gốc `docs/experiments/primary_20261018/runs/e2-e2093-primary/`: journal và `result.json.supervisor.json` có thật; `result.json` cuối **không tồn tại**; `result.json.lock` giữ nguyên do hard termination. Không tạo lại result.json hay xóa lock để tiếp tục cohort cũ.
-6367POI/20.266.161unorderedpairs mỗi radius,150batch/3radii đều hoàn tất. 1/3/5km baseline/optimized accepted sets khớp, FN/FP0. Logical candidate counts906187/4363716/8254110; accepted740159/3678397/7091961. Logicalpruning95,53%/78,47%/59,27%; không là physicaloperationcount.
-15/36timingcells commit:4warmup+11/30measured,21uncommitted/19measuredmissing. 1km đủn5/arm: medians84,2607863s→45,6787213s, ranges83,0231–85,3401 /44,5964–47,7046; descriptive ratio1,84464/giảm45,7889%. 3km baseline0/5,opt1/5;5km0/5cảhai. Không có so sánh latency đáng tin cho3/5km.
- Codex99điều kiện integrity/coverage/source/aggregate/receipt đạt trong `E2-093/parent-primary-result-review.json`; tính phần trăm/ratio ở `parent-primary-summary.json`. Không nhầm với EXP09299test offline/209binding trước đó. Parent review không query lại engine hoặc model.
- Host shared16logicalCPU/~15,6GiB,92%RAMused tại freeze; guestlimitunknown. Driveragent chỉ nhận diệnMemgraph-compatible/Bolt5.2, không independently pin exact runtimebuild. Không suy performance phổ quát.
- Frozen release giữ nguyên. Shell parent dùng slash khác của cùng đường dẫn Windows; dispatch ghi literalargv, QA so flags và resolved paths, không claim argvspellingsbyte-identical. Child report paths/flags khớp source đã chốt.

## Nguồn và báo cáo

Plan/release/manifest: `docs/project/handoffs/E2-093/{prepared-plan.md,release.json,e2-execution.frozen.json,parent-release-acceptance.json}`.
Thực thi/kết quả: `primary-dispatch.json`, `primary-terminal.json`, `parent-primary-result-review.json`, `parent-primary-summary.json`, `E2_PRIMARY_SUMMARY_VI.md`.
Interactive: `docs/reports/2026-10-18/index.html`. Không claim browser/perceptual QA mới nếu chỉ có kiểm tĩnh.

## Phiên tiếp phải tiếp tục đến full scope

1. Đọc FOUR_PHASE_PLAN.md, EXECUTOR_POLICY.md và receipt hiện hành. H2/H3/E2093 cũ giữ bất biến; không rerun/fill missing hoặc đổi timeout của cùng cohort.
2. **Việc tiếp theo: chốt prospective E2 timing cohort đủ36cell/3radii/5measured mỗi arm**, với collection budget/staging phù hợp. Có thể tách timing khỏi phần correctness rất tốn chuyển pair rows, nhưng phải pin correctness artifact từ E2093, cùng source/query/input, verify fresh full graph projection trước timing. Codex lập kế hoạch và ca QA trước khi giao OpenCode; không tự monkeypatch bỏ gate hoặc gọi Python test seams để vượt frozen controls. Giữ nguyên và công bố E2093partial, không ghép thành cohort cũ completed.
3. Actual physical engine distance-function invocations chưa được instrument; yêu cầu đo operations thực vẫn mở. Xác định phép đo có phạm vi đúng (engine/profile hoặc reference algorithm thật và nhãn khác rõ), không dùng logical counts làm thay thế rồi gọi đạt fullE2.
4. Storededgeorientation/duplicate/stalemove/transaction rebuild cần DB dùng riêng; không sửa graph primary đã đóng băng. Hoàn thành kiểm hệ thống và3nhóm đối kháng. Cần cohort H3 mới phải có prospective amendment/quyền tương ứng, không lấy pilot điền14missing.
5. Báo cáo phase4 rồi chờ user chọn H1/viết luận án. H1 hiện0participants; không giả người dùng hoặc tự viết tiếp trước lựa chọn. Phase5Finalizing giữ crawler/new grow-with-user/harness.
6. Checkpoint sau mốc lớn, báo cáo tiếng Việt dễ đọc. Không đánh dấu goalcomplete từ sourcefreeze,99QA hoặc một phần E2.

Mọi guard/secret/domain rules còn nguyên. Quyền recovery/QA/modelbatch cũ một lần đã tiêu thụ không tái dùng. Unknown sessionID hợp lệ, không scan active-list/sessionhistory/config để tìm khóa hoặc ID.

Report QA cuối:409kiểm tra tĩnh/116tham chiếu đạt, E2-093/parent-terminal-static-results.json. Không có browser/perceptual QA mới. Goal vẫn active; next cohort cần prospective plan/freeze, không resume E2093.

