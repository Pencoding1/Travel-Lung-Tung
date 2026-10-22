# Checkpoint H3090 — Codex,20/10/2026

**H3 chính đã chạy và dừng sớm theo protocol:1/15ô có lịch trình,14ô thiếu. Không ước lượng được hiệu ứng memory. Không retry.**

Authority: `docs/project/handoffs/H3-090/parent-primary-result-review.json`, decision `ACCEPTED_PARTIAL_PRIMARY_H3_EVIDENCE_NO_MEMORY_EFFECT_ESTIMATE`,33kiểm tra độc lập bằng chứng đã lưu.

Báo cáo tiếng Việt đã đồng bộ partialH3:386staticchecks/106source references đạt. Mirror11artifact công khai tại `E:/Agent_Artifact/TVLT_2026/2026-10-20/codex-h3090-primary-partial/`, không chứa rawlogs/config/SQLite.

## Quyền và engine

User xác nhận đã thửdemo xong, cho phép H3 tối đa33AI/165knownCLI/33Jev, GoV4.1, khôngretry/paidfallback. Preflight thấy cả hai engine dừng qua đêm;0model trước khôi phục. User cấp riêng đúng1lệnh engine-only SHAfee8b839…; handle60507exit0, quyền đã dùng, khôngrerun.

Khôi phục từ binary/data/cache cũ:6381nodes/3684764relationships/3678397NEAR_BY; routinghealth200. Hai routingpath chỉ kiểmRAM; không in/lưu/hashconfig, không tải/cài/import/rebuild/sửa guard. Engineđượcđểchạy. FREEZE088verify sau phục hồi exit0:122public/34package/14bundleartifacts khôngdrift.

## Lệnh chạy và lỗi khởi chạy được giữ lại

Frozen command gốc gọi tệp trực tiếp, bị lỗi `ModuleNotFoundError` ngay top-level import, trước collector/provider/output/model. Đây là lỗi chuẩn bị invocation của Codex, không phải quan sát H3 hoặc lỗi model.

Trước quan sát đầu, Codex kiểm `python -m benchmarks.memory_live.runner --help` rồi dùng module entrypoint từ repo root; cùng source/hash/manifest/output/budget, không chỉnh tiêu chí. Frozencommands lịch sử không bị ghi đè; amendment ở `H3-090/pre-observation-invocation-amendment.json`.

Batch thật handle59461, terminalexit1; quyền H3 đã dùng cho batchnày. **Không rerun/resume/fill missing cells** vào cùng cohort hoặc thay timeout30s sau khi xem kết quả.

## Kết quả thật và mẫu số

Output: `docs/experiments/primary_20261018/runs/h3-freeze088-primary/`.

- Planned15ô:5profile nhân tạo×3condition; delivered1,missing14,setupfailure1.30yêu cầu primary dự kiến được tính đủ:3reserved/closed,27planned_not_attempted(13prep/14score); lifecycle bịskipprovider_fatal,0lifecyclechat.
- Thực tế3localAI model-generating requests:2prep/1typedscore. Collector báo6knownCLIattempts; countsummary từng request3+1+2, maxattempt1 theo source đãpin.
- Cellduynhất `M1/memory_disabled`:typedHTTP200,56,332137s;3POI thuộc nguồn1483,3điểm×45phút, carroute4,272km/5phút travel làm tròn. Arrival/departure09:00–09:45,09:48–10:33,10:35–11:20ngày01/11/2026.
- Route selectedplan coveragecomplete/verified. Globalvalidator **unverifiable**:3unknowncost+3unknownhours, khôngknownviolations. `constraint_valid=null`, không nâng thành feasible.
- Ôtiếptheo M1/short_term:prepHTTP200/statuspartial, businesserror`model_unavailable`; contributingfailedCLIcode **`cli_timeout`**,attempt1,retryabletrue trongmetadata nhưng **khôngretry** theoprotocol. Failedreceipt không có session/modelID; không tự tạo identity hoặc suy quota/auth/outage.
- MộtM1baseline có1/3preferredstops chỉ là mô tả cell, không có matchedcomparison để tínhmemoryeffect/p-value.14ôthiếu không biếnthành khôngthích hay preference0.

## Giới hạn provenance/usage không được che

Trong6contributorreceipts đượcđếm,3individualreceipts được lưu:typedscore1 vàfailedprep2, gồm2successGoobservedIDs/1failurecli_timeout. Successfulprepđầu chỉ giữsummary`provider_ok=true,provider_receipts=3`; individualsessionIDs/usage của3lượtnày khôngpersist. Không đọcrawservice logs hoặc tìm sessionkhác để điền lại. Known6 là countbáocáo cóclosedsummary, không fullbilling/independentreplay cả6identity.

Jevobservedrequestsnull, không phải0; totalusage/chi phí upstreamkhôngđủ để kết luận tokensavings. Collector inputproof1scoredcellproven/rawexportpersistedfalse là evidence cóphạmvi, khôngchứng nhận rawHTTP/export hoặc deployedIdP.

ParentQA banđầu kỳvọng6individualreceipts, bịassertfail; đã sửa review để ghi đúngsummary-onlygap, không sửa outputprimary hoặc fabricatesessionIDs. Receipt và byteskếtquả gốc đượchashtrongreview.

## Cleanup/trạng thái

Collectorcleanupattempted/oktrue. Hostpassivelistenercheck sau terminal:17687/18989up,19601/19602absent. Không stopengine hoặc đổi appdemo. SQLite trong output là fixture synthetic, không bundle nó hoặc rawlogs/config/auth. Không workerprimary đangchạy; hồsơdispatch “activeafterlaunch” là snapshot cũ, terminalreceipt này thay thế.

## Tiếp tục toàn mục tiêu

1. Đồng bộ report/dashboard/SG/AC:đãcó **partialprimary H3**, không còn nói chưa từngchạyH3, cũngkhônggọiH3hoàn tất. Giữ planned15/missing14/error/lifecycle/usagegaps.
2. H2 vẫnchưa chạy:20×2×3=120lượt, timeout120s đãchốt **trước** H3; không phải sửaH3timeout. Moduleentrypoint `python -m benchmarks.live_model.runner --help` đã exit0 trước H2. Rà loop hiện tại dòng1246+:provider_failure được ghi nhưng loop không dừng toànbatch khi nhận mãauth/policydenial; cần tái hiệnfake và bổ sung stoprule trước chạy dài nếu xác nhận. Không đổi endpoints/thresholdeffect hoặc coi missing là failedmodel observations; đóng băng H2release mới nếu đổi source, giữ H3cohort/release cũ nguyên vẹn. Kiểmsource/runtime/output/phạmviquyền thíchhợp; không giả định quyềnbatchH3 đãdùng là unlimitedcall.
3. E2collector EXP089 chỉ nhận offline65test/137checks; còn durableprogress/supervisor và E2manifest/live1/3/5km. System/adversarial3families chưa đủrealobservations.
4. Nếu cần studyH3bổsung, phải có thiết kế/amendment trước batchmới và quyền phùhợp; cohortnày giữ nguyên làpartial, không overwrite hoặc chọnrunđẹp. Khôngbỏgates/đổiendpoint.
5. Phase4báocáo; userchọnH1hoặcviếtluậnán.0H1participants. Phase5Finalizinggiữcrawler/social/travelagency/grow-with-user/harness. Goal vẫnactive/incomplete, khôngthu nhỏSG01–SG19/AC01–AC12.
