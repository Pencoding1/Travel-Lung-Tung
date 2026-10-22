# Checkpoint — Codex: pilot native chưa đủ; collector typed đang triển khai

Ngày18/10/2026. Goal ACTIVE/INCOMPLETE. Đây là tiến bộ có bằng chứng: thu kết quả thật, kiểm tra cleanup/source, sửa thiết kế trước primary và bàn giao đúng gói mã còn thiếu. Không H1/H3 primary mới.

## Kết quả thật đã đối chiếu

- CORE079 offline đã nhận:15ASGI độc lập/10focused/357hồi quy đạt,47bindings giữ nguyên.
- Pilot handle85489 đã **exit1**: chỉ disabled bypass đạt; source1483,2POI/tuyến car2.521km/3phút, giờ đến/đi thật. Toàn kế hoạch vẫn unverifiable do thiếu giá/giờ.
- Request short-term prep trả503/unavailable; dừng, không typed short-term hoặc two-tier.3request/3knownCLIattempts,2/3engineeringcells chưa hoàn tất. Không suy quota/auth từ503; pilot chưa giữ closed error code của failed response nên nguyên nhân chưa biết.
- Cleanup thực hiện và kiểm tra lại cổng19601/19602 đều đóng; accepted source hashes khớp. Receipt `handoffs/CORE-079/parent-native-result-review.json`, root QA `parent_native_result_review.py` đã chạy đạt. Kết quả gốc/ledger không sửa. Quyền user chạy script một lần đã dùng, không rerun.
- Protocol v5 sửa lỗi kế hoạch của Codex: prep/chat → score/generate_itinerary cùngowner/session/source; cùngtypedbody ngày1/11,09–16+07,3stops/visit45/car/party1/unknownbudget. Oldprotocol/design/baseline giữ nguyên; fullfreeze/primary execution vẫn đóng.
- Báo cáo VI đã cập nhật:360staticchecks/93refs đạt, không browser/perceptualproof; lần staticcheck đầu do keyword cũ đã giữ riêng và sửa QA để nhận đúng tên endpoint, không sửa production để chiều test.

## Writer hiện tại — không chạy trùng

**EXP080 OpenCode**, model `aibox/ds/deepseek-flash` theo user V4.1; handle **37269**, session **ses_eb0336ac3ffe5n9qgmY4jvwdD2**. Budget1200s tính từ `handoffs/EXP-080/dispatch-prepared.json`, trước CLI. Thư mục `E:/Agent_Artifact/TVLT_2026/2026-10-18/h3-typed-collector-exp080/`.

**Quan sát mới:** client37269 đã exit0, nhưng same-session revision steer đã được giao và worker vẫn active qua API chính thức, serverPID28328. Receipt `EXP-080/parent-worker-observation.json`: waittimeout không là terminal. Không poll lại terminalclient để suy idle. Hai mục sửa trong `revision-path-bindings.md`: đường dẫn/hash manifest phải cùng tệp; failed prep/lifecycle phải giữ closed diagnostics, không raw error body.21focusedpass của bản đầu chưa là nghiệm thu. Root QA thêm metadata binding và failure-code/secret-body exclusion. Vẫn cùng budget1200s; không restart hoặc thêm gói mới.

Kế hoạch Codex `/plan`: `handoffs/EXP-080/prepared-plan.md`. Chỉ sửa collector/test/README/candidate chưa freeze + ownreport. Production/data/evaluator/helper/parent* readonly. **0actualapplicationcalls**, không native/service/export/env/config/auth/install. Giữ `_validate_shape`, `validate_execution_manifest`, `_validate_readonly_sources` AST bodies. Baseline mới ghi actualmain CORE079, không sửa baseline cũ. Candidate mặc định trước dispatch không tồn tại; đã ghi rõ, không đụng frozen H2 hoặc h3_profile_candidates.

## Phiên sau phải tiếp tục

1. Poll đúng37269; timeout không phải terminal. Không restart. Quá budget thì officialinterrupt exactsession/wait/targetinactive cùngserver theo EXECUTOR_POLICY, khôngkillbằngport. Xác minh terminal và source release trước QA.
2. Root QA đã soạn riêng `handoffs/EXP-080/parent_typed_collector_qa.py`: scriptedHTTP không chatplanning, exacttypedbody,15typedscore/18chat tốiđa, owner/session, source hai tầng, inputunknown/mismatch,503stop, lifecycle/cleanupfail, full15denominator, unknownusage và dryrun/unfrozengate. **Chưa chạy lúc checkpoint**. Review/rerun focusedtests và root test; không đổi tiêu chí để che lỗi, chỉ sửa oracle nếu thực sự sai hợp đồng và giữ failure.
3. Review protectedhashes/AST/oldfrozenbytes và manifest/provenance mới. Wholecollector vẫn chưa được nhận chỉ vì workerexit0. Native active-memory vẫn chưa chứng minh; không gọi fakepass là nativeproof, không fullfreeze/primarycall sớm.
4. Sau các gate thật: phase3H2/H3/E2/system/adversarial, phase4report và chờuserH1/thesis. H1chưa cóparticipants;phase5Finalizing toàncrawler/newharness/grow-with-user. Tiếp tục fullSG01–SG19/AC01–AC12, không thu nhỏ goal thành bộtest đãđạt.

Codex sở hữu kế hoạch/QA/nghiệm thu; executor làm theo kế hoạch cố định. Không rawsecrets/config/auth/privateincidentexcerpt/env-enumeration; safeprobeabsolute chỉpresence/type/length. KhôngALL/wildcards/globalguardedits, khôngreset/clean/commit/push. Guarddeny dừng action; không đổiexecutor/rephrase/rename để lách. Bảo toàn thay đổi người dùng và mọi thất bại. Lưu checkpoint sau mốc quan trọng.
