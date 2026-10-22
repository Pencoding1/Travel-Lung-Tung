# Checkpoint — Codex: TIM097 timing đã hoàn tất

20/10/2026. Lượt này là progress/verifiedwait: cùng một batch TIM097 chạy đến terminal, không restart/resume/điền ô cũ. **Không poll handle95078 nữa**, không chạy prelaunchverifier sau khioutputđãcó.

## Kết quả được kiểm chứng

- Handle95078terminal0 quan sát09:04:18UTC; supervisorchild_exit_zero/child16720exit0,08:02:25–09:04:17UTC,3711,734628s. Không timeout/forcedcleanup.36cell=6warmup+30measured,0failed/missing;389kiểm tra độc lập đạt.26source/input/query/proof/runtime/hostpins không đổi.
- Medianbaseline→prefilter:1km102,0762→56,0649s (giảm45,08%);3km108,7268→101,6537s (giảm6,51%);5km117,6202→150,1539s (**tăng27,66%**).N5mỗi nhánh/warmup excluded. Không claim luôn nhanh hoặc cải thiện tương ứng mức giảm ứng viên logic.
- Count-only full6367POI/50anchorbatch mỗi lượt, không APIlatency; shared desktop/RAMload97%/no isolation, mô tả không p/CI/quần thể. Chưa biết nguyên nhân5km chậm hơn; không tự quy cho memory/queryplanner/metric.
- ProofcorrectnessE2093 tái dùng tường minh, fresh fullPOIprojection trước timing,36counts khớp740159/3678397/7091961.0correctnessqueries/receipts mới,0model/Jev/graphwrites. Đây không rawsetcomparison mới/snapshotcôlập.

## Tệp cần đọc

- `docs/project/handoffs/TIM-097/TIM097_PRIMARY_SUMMARY_VI.md`
- `docs/project/handoffs/TIM-097/parent-primary-result-review.json` —389checks/evidencehashes/six medians+ranges.
- `docs/project/handoffs/TIM-097/primary-terminal.json`, `release.json`, `parent-release-acceptance.json`.
- Raw `docs/experiments/primary_20261018/runs/e2-tim097-timing/result.json`, `.journal.jsonl`, `.supervisor.json`.
- `ENGINE_INSTRUMENTATION_NOTES_VI.md`: PROFILElogicaloperatorpulls không là scalarfunctioncalls; sourceGitHubcachemiss không là sourceverification.

Codexownsplan/QA/acceptance/finalprose; TIM096code do OpenCodeAI-boxV4.1 thực hiện và nhận offline. TIM097là chạy mã đã nhận, không thêm paidmodelcall hoặc viện quyền recovery/H2/H3một lần đã dùng. Không đổi frozenqueries/thresholds/source sau kết quả.

## Giữ nguyên lịch sử và công việc tiếp theo

E2093cũ vẫn11/30measured/timeout3600s/resultabsent/lockretained, không gộp vào mẫuTIM097. H2=120attempted/119provenance/1timeoutgap,descriptive/inferenceblocked. H3=1/15delivered/14missing,no memoryeffect. Metricengine khácPython6371theoOPS094/MET095; exactmetricimplementation/historicbuild chưa chứng minh.

Tiếp physicalengineinstrumentationfeasibility, storededge/move/rebuildsemantics trên DB dùng riêng, system và ba nhóm adversarial theo registeredscope, finalclaim/citationaudit. Ghi QA-SPATIAL-PERF-097(P1) về5km chậm hơn; không mở vòng tuning hoặc rerun TIM097 để tìm kết quả đẹp. Sau phase3 giao báo cáo phase4 rồi user chọn H1/writing;H1hiện0participant. Crawler/newharness/grow-with-user integrationphase5deferred. Goal đầy đủ SG01–SG19/AC01–AC12 cònactive, không complete/blocked.
