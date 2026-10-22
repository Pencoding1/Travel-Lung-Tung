**Codex21/10 — PLAY156:** Call graph đã thêm Phát/Tạm dừng/Tiếp bước/Chạy lại,1x/2x cho4chức năng. Từng bước có giải thích, chiều trả kết quả; số cạnh là mã tra cứu. Nội dung/sequence do Codex cha soạn, graph và12popup giữ nguyên.20nhóm NodeDOM vàsyntax đạt; khôngclaimbrowservisual/geometry mới. Tải lại file/tab để xem. Checkpoint: `checkpoints/2026-10-21-callgraph-playback.md`; demo/BAT/engine không đổi.

**Codex 21/10 — START154 / GRAPH155:** Demo đang chạy tại http://127.0.0.1:19102/travel; engine6367POI/3678397NEAR_BY và car/foot đã khôi phục bằng quyền mới. Có START_DEMO.bat (tự bật engine khi cả hai tắt từ cache cũ đã chuẩn bị; dùng lại stack khỏe) và call graph offline12module/7layer/19quan hệ, lọc+popup input/output. Nội dung do Codex cha viết, renderer không quyết định facts. Checkpoint hiện tại: `checkpoints/2026-10-21-demo-start-and-callgraph.md`. CHAT153 vẫn backlog; không mở H1/writing/Finalizing/DEP149. Các thông báo bên dưới là lịch sử.

**DEMO152 mới nhất — đã làm1/2/4 theo user:** chat vẫn gửi được khi tạo lịch (cùngphiên xửlýlầnlượt), cóHủy chờ; chọnnhiều/toàn26vùng nguồn; vẽrouteGraphHopper thật. Mục3 ởCHAT153backlog. Demo đãrestart, giữchạy19101/19102. QA/limits: `checkpoints/2026-10-20-demo152-items-1-2-4.md`; khôngnhậntoàngoalcomplete hoặc phépDEP149.

**Trạng thái điều phối mới nhất: chờ quyền/quyết định, đang chốt BLOCKED goal.** DEP149 chưa dispatch; câu hỏi host vẫn pending. Các QA độc lập đã trả, không có worker thuộc gói đang chạy để poll. Xem `checkpoints/2026-10-20-awaiting-owner-decisions.md` và `handoffs/DEP-149/blocked-audit.json`. Mục tiêu đầy đủ chưa hoàn tất; không phải pause theo yêu cầu user.

**DEP148 mới nhất:** Compose readiness có9nhóm gap từ source; không build/start hoặc probe Docker/localhost. DEP149 chỉ sửa build-context exclusions, đã chốt brief và chờ quyền host mới; chưa dispatch. Xem `checkpoints/2026-10-20-compose-readiness-dep148.md`. Phase4/demo không đổi.

**Hiện tại — Codex20/10, DOC147 / phase4:** LIVE143 đã chạy đúng một lần được user duyệt, terminal0:31 kiểm tra luồng chat → lịch → hai ghim/chọn đúng POI;4Go/4CLI+1Jev. Ảnh live còn popup bị che; UI145 chỉ sửa CSS, JS giữ nguyên; B146 kiểm riêng đúng cặp POI nguồn trong fixture, toàn thẻ hiển thị rõ, không bị che; chưa kiểm hành động nút đóng. Không gọi lại model hoặc hồi tố ảnh live. Báo cáo phase4 đã giao, chờ user chọn H1 hoặc viết tiếp; mục tiêu tổng thể IN_PROGRESS. H1=0participants; Compose còn thiếu; crawler/grow-with-user thuộc Finalizing. AUD140/REF141/REF142 đã có gap map và audit Markdown, không sửa chương/DOCX/PDF. Không worker model/browser nào của gói còn chạy; quyền LIVE143 một lần đã dùng. Checkpoint: `checkpoints/2026-10-20-live143-and-thesis-audit.md`. Các thông báo phía dưới là lịch sử, không phải task đang chạy.

**Cập nhật Codex20/10 — sửa xong ghim và card mobile:** UI135/137 dùng OpenCode Go, đều terminal0/interrupt0/wait0. BROWSER138 đạt6/6 bố trí desktop/mobile với HTML/catalog/POI fixture, toàn thẻ đọc được;0 native API/model/Jev. 8Nodegroups/18race đạt;163backendpins nguyên. Mã cuối355c713b…; B131live cũ vẫn PARTIAL, chưa chạy lại trên mã cuối. Xem `checkpoints/2026-10-20-ui-pin-mobile-fixed.md`; report DOC139. Không worker/browser QA còn chạy.

**Checkpoint Codex 20/10 — UI demo mới:** UI127/129 đã dừng và qua QA; BROWSER130 render thật 123 polygon. BROWSER131 chat + typed backend thật đạt, hai ghim đúng tọa độ; click/popup timeout nên kết quả PARTIAL (4 Go/4 CLI + 1 Jev). BROWSER133 click/card đạt trên browser với fixture riêng, 0 model/Jev; không thay kết quả live. Xem `checkpoints/2026-10-20-ui-demo-live-partial.md`. Không worker nào trong gói UI/demo còn chạy; không rerun one-shot cũ.

**Mới nhất SYS119 — Codex20/10/2026:** Một B2 mới đạt8so sánh nguồn gồm địa chỉ,2POI/tuyếncomplete;1HTTP/1GoV4.1/1CLIattempt/88MCPcalls,khôngretry. Codex191/reviewer206checks,163pins+4SYS101files nguyên; SYS101vẫn8supported/1inconclusive. SauQA /travel+/healthz/routing200 và19601/2bindable. DOC122report áp dụng146refs/JS/embeddedmatch; DOC121runbook một trang. Chưa currentbrowserjourney: UI120không thấy đúngwindow,0input; khôngblindretryCUA. Parent58484terminal0,khôngpoll/rerun. Đọc [checkpoint](checkpoints/2026-10-20-sys119-b2-live-and-demo.md). Tiếp phase4report công bốgap hoặc browser khi quan sát được; H1/writing do userchọn,Finalizinghoãn. Hermesdeniedprepare.lock vẫn dừng.

Các cập nhật bên dưới là snapshot lịch sử; trạng thái mới nhất ở trên thay phần pendingB2 cũ.

**GRAPH115 / demo / báo cáo — Codex20/10/2026:** Lifecycle thật7/7ca/83assertion,53offline và219review độc lập đạt;15pins, cleanup container/volume tạm đúngID,0primary/provider. LỗiGRAPH108là QA dùnglạiUOW; chỉ sửa harness, không app. Native demo114đã bật19101/19102, routing200; catalog117xácnhận đúngtuple1483POI(~6s). DOC116report đã áp dụng188proposalchecks/143finalrefs; AUD106rà31SG/AC. Chưa currentbrowserjourney do CUAkhởi tạo lỗi, chưa B2liveproof mới. Đọc checkpoints/2026-10-20-graph115-demo-report.md. Các worker cũ terminal, khôngpoll/relaunch; H2/H3/E2/SYS101frozen. Tiếp browser/B2riêng→phase4; H1/writingđợiquyếtđịnh,phase5hoãn.

**GRAPH103 — Codex20/10/2026:** Image3.13.2 tải/pin xong; UOWtypeimport đã tách, actualimport/7regression đạt. Harness38/41offline,8parent safety đạt; thiếu journal/boundedconnection/exactversion và3test còn lỗi. Chưa nhận/chạy graph;0container/0write. Worker17399/72347terminal; khôngpoll/relaunch. Tiếp bounded delivery theo review GRAPH-103/parent-final-review.json trước live release; xem checkpoint2026-10-20-graph103-image-uow-partial.md.4SYS101primaryhash nguyên; không dùng oldsourcepins cho currentUOW.

**SYS102 đã nhận offline — Codex20/10/2026:** Bộ đo địa chỉ sửa xong,140test độc lập đạt(83cũ+28parent+29executor).153currentpins+2executedarchiveskhớp,4SYS101artifactsnguyên. SYS101vẫn8supported1inconclusive,khôngrerun/nângB2pass. Goabsolute-pathcorrectionđãterminalhandle68880/wait0/client1;khôngpoll/relaunch. Xem checkpoints/2026-10-20-sys102-address-instrument-accepted.md;currentinstrumentđãđổihash,oldreleasegiữhistorical.

**SYS102 — Codex20/10/2026:** Lượt sửa addressinstrumentGo180s chưa giao mã;toolerrors4/nguyênnhânunknown,khôngpaidfallback/rerunstudy.155pins/4primaryhashesSYS101khớp;B2vẫninconclusive. Plan+28parentcasesđãchuẩnbị,chưaaccepted. Đọc checkpoints/2026-10-20-sys102-address-repair-undelivered.md;handle66387terminal,khôngpoll/relaunch. Tiếp độc lập system/graphsemantics/finalaudit trongkhibộđo chưađược sửa.

**SYS101 đã kết thúc — Codex20/10/2026:** HTTPthật9/9ca,221checks/155pinskhớp,247toolcalls/3Go/3CLIattempts,cleanupreportedTrue. Raw8pass/1failuregiữ nguyên; review8outcomehỗtrợ/1inconclusive do bộ đo địa chỉobject-vs-string. Khôngclaimapplicationleak/9pass/rerun. Xem checkpoints/2026-10-20-sys101-controlled-http-completed.md và SYS-101/SYSTEM_ADVERSARIAL_SUMMARY_VI.md. Handle8750terminal0; khôngpoll/relaunch.

**SYS100 — Codex20/10/2026:** Bốn gateSYS098 đã sửa,83test độc lập đạt/0lỗi; bộ thu được nhận OFFLINE.93publicpins/3collectorreadonlypins khớp, app/data không đổi. Go-only240s+180s đãterminal/wait0/client1; khôngpoll/relaunch. Chưa freeze/chạy controlledHTTP/model thật. Xem checkpoints/2026-10-20-sys100-offline-accepted.md và SYS-100/parent-final-acceptance.json. Các note64pass/4gaps bên dưới là lịch sử.

**REF099 — Codex20/10/2026:** Đã rà12primaryrecords/9phầnfulltext; sửa phạm vi37%ChinaTravel và pinGERecv2/titlevariant. L07PDFsize/currentmethodology và allmanuscript/Fseries còn thiếu; không viết lại luận văn. SYS098vẫn64testđạt/4gatefail/chưalive, workerđãterminal. Xem checkpoints/2026-10-20-ref099-bounded-citation-audit.md; không xem auditdẫnchứng lànghiệm thutoànhệ.

**SYS098 R1 — Codex20/10/2026:** Sáu lỗi ban đầu đã sửa;64test đạt nhưng4gate bổ sung còn lỗi (modelidentity/transportstop/cleanuptruth/not_exercised). Bộ thu CHƯA nhận/freeze/chạy live;93pin cũ giữ nguyên. Worker62744 đã interrupt/wait0/client1 theo budget420s, không poll/relaunch; không giao vòng sửa tự động nữa. Xem checkpoints/2026-10-20-sys098-r1-partial.md và SYS-098/parent-r1-final-review.json. TIM097/H2/H3/E2093 bất biến. Các note running bên dưới là lịch sử.

**SYS098 — Codex20/10/2026:** Bộ kiểm định đối kháng mới chưa nhận: QA độc lập47đạt/6lỗi;93pin nguồn cũ giữ nguyên. Một lượt sửa offline420s đang giao OpenCode, handle62744/sessionexact trong SYS-098/dispatch-r1.json; kiểm lại handle, không launch thêm. Chưa freeze/chạy live/model mới. Xem checkpoints/2026-10-20-sys098-initial-qa-returned.md; TIM097/H2/H3/E2093 giữ nguyên. Các snapshot dưới là lịch sử.

**TIM097 đã hoàn tất — Codex20/10/2026:** Handle95078terminal0, child16720exit0; đủ36cell=6warmup+30measured,0failed/missing,389checks. Medianbaseline→prefilter1/3/5km=102,08→56,06 /108,73→101,65 /117,62→150,15s;5km chậm hơn27,66%, không claim luôn nhanh. Count-only/full6367POI/n5/arm,sharedhost97%RAM/no isolation; mô tả, không APIlatency/p/CI. ProofE2093 tái dùng+projectionmới/countsmatch,0correctnessqueriesmới. E2093/H2/H3 giữ nguyên, không resume/ghépcohort. Đọc checkpoints/2026-10-20-tim097-timing-completed.md và handoffs/TIM-097/TIM097_PRIMARY_SUMMARY_VI.md. Tiếp physicalops/semantics/system/adversarial; các note running bên dưới là lịch sử, không poll/relaunch handle đã terminal.

**TIM097 đang đo — Codex20/10/2026:** Cohort timing mới đã khởi chạy, unifiedhandle95078; không launch/resume lại. Release26publicpins/50checks/6negativegates đạt; proofE2093 đã kiểm và fresh fullPOIprojectionpassed. 36cell/6warmup/30measured/1,3,5km,7200s+cleanup10s,0model/Jev/graphwrites. Chưa nghiệm thu timing; kiểm live bằng đúnghandle, journal chỉ là completedprefix. Host97%RAM/shared/no isolation đã ghi nhận, không đổi tài nguyên/tiêu chí giữa chừng. Đọc checkpoints/2026-10-20-tim097-timing-running.md; H2/H3/E2093 bất biến. Các trạng thái bên dưới là lịch sử.

**TIM096 đã nhận offline — Codex20/10/2026:** Hai lỗi proof/path đã sửa. Suite128pass và12ca proof bổ sungpass (3ca trùng;137ca riêng), 273kiểm tra bảo toàn đạt. OpenCode R1 dừng đúng budget420s/wait0/client1, không còn giao coding vòng mới; executorreport còn thiếu, Codex viết giải thích README và kết luận. Chế độ timing-only7200s giữ36cell/1,3,5km, proofE2093pin+projectionmới, không correctnessquerymới/không resumeE2093. Chưa freeze/launch cohort mới. Đọc checkpoints/2026-10-20-tim096-offline-accepted.md và handoffs/TIM-096/parent-final-acceptance.json. H2/H3/E2 cũ giữ nguyên; phần bên dưới là lịch sử.

**OPS094/MET095/TIM096 — Codex20/10/2026:** Đã đo thực tế74.322.496lần gọi hàm Python trên6367POI; không phải số lần gọi vật lý trong Memgraph. Probe literal chứng minh point.distance của engine khác Haversine6371km; không đổi ngưỡng/source cũ để ép khớp. SHOWVERSION hiện tại3.13.2, không hồi tố buildE2093. TIM096 đang trả sửa:99test cũ và proof thật đạt,2ca mới phát hiện lỗi đường dẫn resolve và tổng pair universe. R1 chỉ code/test, chưa chạy cohort mới; không resumeE2093. H2/H3/E2 cũ bất biến. Đọc checkpoints/2026-10-20-tim096-initial-qa-returned.md và handoffs/MET-095/METRIC_FINDINGS_VI.md. Các trạng thái trước bên dưới là lịch sử.

**E2093 đã dừng — Codex20/10/2026:** Handle83883terminal1 theo budget3600s; child33448đã thu hồi. Correctness đủ3/3radii/150batch,FNFP0; timing11/30measured(15/36cells),19measuredmissing. 1kmn5/arm median84,26→45,68s;3/5kmchưa đủtiming. Logicalpruning1/3/5km=95,53/78,47/59,27%,không làphysicaloperationcounts. Không resume/relaunch/xóa lock/dựng result.json. Đọc checkpoints/2026-10-20-e2093-primary-partial-timing.md và E2-093/E2_PRIMARY_SUMMARY_VI.md. Tiếp prospective timing cohort đủ3radii/36cells và instrumentation/system/adversarial; H2/H3không đổi. Running notes bên dưới là lịch sử.

**E2093 đang đo thật — Codex20/10/2026:** E2 đã freeze và launch một batch chỉ đọc; unified exec handle83883, không relaunch/resume. Kiểm đúng handle, không suy liveness từ lock/journal. Xem checkpoints/2026-10-20-e2093-primary-running.md và E2-093/primary-dispatch.json. 6367POI/3radii/36timingcells,3600s+<=10s cleanup,0model/graphwrite. Source EXP092accepted99tests/209bindings. H2/H3giữ nguyên; mọi note chưa freeze/chưa chạy E2 phía dưới là lịch sử trước launch.

**EXP092 — Codex20/10/2026:** Bộ thu E2 journal/supervisor đã nhận offline:99test độc lập/209bindingchecks. Ba lỗi ban đầu88pass/3fail đã sửa trong R1; query/criteria/H2/H3 giữ nguyên. Chưa đo engine thật; candidate vẫn unfrozen. Tiếp E2 source/runtime freeze và measurement, không lặp QA đã đạt. Xem checkpoints/2026-10-20-exp092-e2-durability-accepted.md. H2 vẫn120attempted/119provenance+1gap, H3 vẫn1/15partial. Các trạng thái worker active hoặc journal chưa có bên dưới là lịch sử.

**H2 chính đã kết thúc — Codex20/10/2026:**120/120attempted,119quan sát có provenance,1gap cli_timeout tại P12/Hybrid/r2; không retry/resume. Handle80818terminal0, quyền đã dùng hết. Hybrid56lịch (18thiếu yêu cầu)/LLM-only45lịch; timing-only53/32lịch không vi phạm,0/10lịch có vi phạm; globalfeasible0/0 và inference bị chặn do incompletecoverage. Không kết luận xác nhận H2. H3giữ1/15partial; E2/system/đối kháng còn thiếu. Đọc checkpoints/2026-10-20-h2091-primary-completed.md và handoffs/H2-091/H2_PRIMARY_SUMMARY_VI.md. Các ghi chú running/chưa chạy bên dưới là lịch sử, không phải lệnh khởi chạy lại.

**H2 primary đang chạy — Codex20/10/2026:** Người dùng đã cho phép và batch duy nhất đã khởi chạy. Unified exec handle80818; không launch/resume lại. Ledger nằm tại docs/experiments/primary_20261018/runs/h2-h2091-primary/calls.jsonl. Số quan sát đang tăng, chưa phải kết quả đã nghiệm thu. Xem checkpoints/2026-10-20-h2091-primary-running.md và H2-091/primary-dispatch.json. Các ghi chú chưa thực thi bên dưới là lịch sử trước launch.

**H2091 —20/10/2026:** H2collector đã sửa/QA quy tắc dừng khi provider từ chối quyền; release H2 riêng124publicfiles/34packages đãseal, chưaprimaryH2calls. OldFREEZE088 sẽ nhận ra H2runnerđổi; sourcecũđãarchive/H3primarybytes1/15partial giữnguyên. Xem checkpoints/2026-10-20-h2091-authority-stop-release.md và H2-091/parent-release-acceptance.json. Không đổi H3timeout,cohort,sourcefacts/prompts/temporalrules. Worker đãinterrupt/wait0/clientexit1; executivehandoffpartial,khôngrestart.

**H3090 —20/10/2026:** H3 chính đã chạy và dừng provider_fatal:1/15ô delivered,14missing;3AIrequests/6knownCLIattempts,failedCLI `cli_timeout`/business `model_unavailable`, khôngretry/đổi timeout/paidfallback. MộtM1/memory_disabled tạo3điểm/car4,272km nhưng globalunverifiable; không có matched memorycomparison hoặc tokensavings.33kiểm tra bằng chứng đạt; stack19601/2đãdọn,engineđểchạy. Xem checkpoints/2026-10-20-h3090-primary-partial.md. Các dòng “chưa từng chạyH3/engineđangtắt” cũ là snapshot lịch sử. H2/E2/system/adversarial còn thiếu; không mở lại cohortH3này.

**EXP089 —20/10/2026:** bộ thu E2 chỉ đọc được nhận offline sau sửa timingcount/terminalauthdeny;65test độc lập/137bindingchecks đạt, không queryengine thật hoặc modelcall ứng dụng. H2/H3 FREEZE088 không đổi. Cần chốt E2manifest/runtime và lưu tiến độ/supervisor trước batch dài; chưa primarymeasurements. Xem checkpoints/2026-10-20-exp089-offline-e2-accepted.md. Worker R1 đã interrupt/wait0/clientexit1, source được nhận bằng QA, không restart chỉ vì clientexit1.

**FREEZE088 — bản H2/H3 trước thí nghiệm đã chốt** (19/10/2026):122tệp public/67pins cũ khớp; lock34package/52dependency,181điều kiện nghiệm thu đạt. H2execution20×2×3=120lượt và H3execution5×3=15cell đã có manifest riêng; candidate/input lịch sử giữ nguyên. Không modelcall hoặc primary outcome mới. Xem checkpoints/2026-10-19-freeze088-h2-h3-release.md và FREEZE-088/parent-final-acceptance.json. Các đoạn pendingfullfreeze trước đây là snapshot cũ. Tiếp phase3 có kiểm soát sau preflight/quyền mới khi cần; không thu thập cạnh tranh lúc user dùng demo19101/19102. Giữ phase4choice/H1/phase5.

# Current execution — 18/10/2026, Codex

**CORE087 đã nhận native two-tier:**2requestAI/3CLI, profile+history+schema/fixturecredential proof và lịch2điểm/car1,645km đạt;15check độc lập/67pins khớp, QAstack đóng. Cùng mainCORE084 với short-term CORE085; không ghép batch thànhH3 hoặc nâng globalunverifiable. Quyềnmộtlầnđãdùng. Khoảngthiếu nativeactive-memory đã kiểm định có giới hạn; tiếp FREEZE088 chốt fullfreeze S6, không mở smoke loop mới. Đọc checkpoints/2026-10-19-core087-two-tier-native-accepted.md. Chưa primary/fullstudyfreeze.

**EXP086 đã nhận offline:** collector giữ riêng lỗi top-level/per-call và lọc chuỗi lạ;90mã bổ sung,34ca độc lập+11freeze mutation đạt. Binding mới theo CORE084 khớp46readonly,3gateAST giữ nguyên; candidate vẫnunfrozen/chưa primary. CORE085 short-term native đạt, two-tier vẫn thiếu; nguyên nhân lỗi cũ không được khôi phục. Đọc checkpoints/2026-10-19-exp086-closed-evidence-accepted.md. Tiếp chỉ gói two-tier còn thiếu, không rerun short-term/quyền cũ.

**CORE085 kết quả cuối:** short-term native tạo lịch2điểm/car1,645km thành công sau sửa CORE084; history/schema/absence-profile/fixturecredential proof đạt. Batch3API/7attemptCLI, two-tier prep stage3failed, typedchưagọi; nguyên nhânunknown do thiếu closed error attribution. Cleanup19601/2đóng,enginecònchạy,61pinskhớp. Quyềnmộtlầnđãdùng;khôngrerun. Đọc checkpoints/2026-10-19-core085-short-term-native-accepted.md. Native two-tier/fullfreeze/primary vẫnchưađạt.

**Mới nhất CORE084:** lỗi cắt current synthesis ở8.000ký tự khi bật memory đã sửa/nhận offline;32ca độc lập+10AST đạt. mainSHA d866c52f…;không application modelcall mới. Native two-tier/fullfreeze/primary còn thiếu; old pins/quyền CORE083 không áp dụng bản mã mới. Đọc checkpoints/2026-10-19-core084-full-current-prompt-accepted.md. Các snapshot trước chưa bao gồm bản sửa này.

**Cập nhật cuối CORE083:** lệnh một lần đã kết thúc exit1; engine khôi phục, stack thử dọn. Batch memory2API/4CLI dừng vì typed response failed; export đã ghi nhận history marker nhưng JSON thiếu stops. Two-tier chưa chạy, chưa primaryH3/fullfreeze. Quyền đã dùng; không rerun. Đọc checkpoints/2026-10-19-core083-engine-restored-memory-partial.md. Các dòng running/engine down/CORE081 chưa chạy bên dưới là snapshot cũ, không phải trạng thái hiện hành.

Authoritative status: checkpoint 2026-10-20-ui-demo-live-partial.md, DOC132 and bounded SYS119/GRAPH115 receipts. H2/H3/TIM097 results recorded with missing/adverse outcomes; overall goal remains incomplete.

| Scope | Current status |
|---|---|
| S1/S2/S3/S4 | Native Jev+Go/fullgraph/HTTP-SSE/foot/car accepted bounded; unknowncosts/hours retained |
| S5 | Accepted bounded: R1 15/15checks,4realGo chats,8CLIattempts; ownedcleanupstopped |
| S6 | H2 descriptive/H3partial/E2timing recorded. GRAPH115 lifecycle and SYS101 three families tested; SYS119 separate B2 accepted. Physical engine operations/fullscale concurrency remain gaps. No cohort resume/pooling. |
| Phase3/4 | Deliver report and chatbot demo: B131 live chat/typed+pins passed, click timeout; B133 separate fixture click pass. Keep scientific gaps; await H1/writing choice. Fullgoal incomplete. |
| Phase5Finalizing | Allcrawlers/newmemorygrowwithuser/harness/enrichment deferred; notphase2gate |

Old task narratives below retain historical evidence. Current bounded receipts override stale phrases such as no fullimport, no realprovider, CLI060active or crawlmandatoryphase2; no deleted history or scientificresult substitution. Pre-DOC073 preambles are archived under checkpoints/archive/.

# Persistent backlog

**D014/latest:** phase5 đổi thành **Finalizing phase** cho toàn bộ cơ chế mới, gồmT056grow-with-user, T057–T059crawler và các mở rộng đã chọn. Phase2S1–S6 đã duyệt, tập trung thông tinuser→recommending→routing→kếtquả dùngđược, rồi thínghiệm/báocáo. Không kéo tínhnăngmới vào đườnggăng.

**User approval18/10/2026:** “Duyệt S1–S6 như đề xuất”. Danh sách PHASE2_SCOPE_FOR_APPROVAL_VI.md đã chốt; bỏ trạng thái chờduyệt của note ngay dưới. Chỉ coreOSM/AI/HTTP/planner/existingmemory/QAfreeze; toàn bộcrawlerphase5 vàadvancedmemoryngoàiphase2.

**Scope override18/10/2026 mới nhất:** user chuyển toàn bộ crawler legacy + social/web T057–T059 ra khỏiphase2, sang **phase5 finalize** để chốt nguồn travel agency/mạng xã hội rồi mới triển khai. P0/P1/P2 cũ chỉ thứ tự bên trong phase5, không chặn phase2/3. Giữ OSM làm dữ liệu chính. Grow-with-user vẫnP2 sau4phase. Xem PHASE2_SCOPE_FOR_APPROVAL_VI.md: đề xuất S1–S6 chờ user duyệt trước gói implementation mới; CLI067R1 đang chạy là sửa đã được cấp quyền. Các note “crawl bắt buộc phase2” bên dưới đã bị supersede.

Updated 2026-10-16. All listed tasks are MANDATORY except T020 (SUPPORTING). READY requires prerequisites and resources; source generation alone never verifies a task. No optional work queued. Current reconciliation is in NEXT_SESSION_HANDOFF.md and the latest checkpoint; earlier evidence entries are historical.

## T001 — Audit services
- Parent Goal: SG01 / AC01
- Origin: Audit
- Priority: P0
- Status: VERIFIED
- Dependencies: —
- Classification: MANDATORY
- Description: Inspect every service and trace interfaces
- Acceptance Criteria: Five audit artifacts with source evidence
- Evidence: docs/audit/{SYSTEM_INVENTORY,ARCHITECTURE_AS_IS,THESIS_GAP_MATRIX,ASSUMPTION_REGISTER,IMPLEMENTATION_ROADMAP}.md; Codex source inspection. Hermes failed, not evidence.
- Blocker: Source-audit deliverable complete; runtime verification tracked separately.

## T002 — Map thesis requirements
- Parent Goal: SG02 / AC09
- Origin: Audit
- Priority: P0
- Status: VERIFIED
- Dependencies: —
- Classification: MANDATORY
- Description: Map MT1–MT6 and RQ1–RQ4 from supplied proposal
- Acceptance Criteria: Every objective has status, evidence and acceptance criteria
- Evidence: THESIS_PROPOSAL_EXTRACT.txt; THESIS_GAP_MATRIX.md; user-authorized LEGACY_RECONSTRUCTION.md maps rebuilt RQ1–4/subquestions to MT/H and evidence gates.
- Blocker: Requirements reconstruction complete; actual results and final manuscript remain separate tasks.

## T003 — Survey authorized sources
- Parent Goal: SG03 / AC02
- Origin: Audit
- Priority: P1
- Status: VERIFIED
- Dependencies: T001
- Classification: MANDATORY
- Description: Verify source licensing and accessibility
- Acceptance Criteria: Feasibility matrix with dated primary sources
- Evidence: docs/research/DATA_SOURCE_SURVEY.md; dated primary policy URLs
- Blocker: Policy survey complete; actual source acquisition remains T005/T028.

## T004 — Design acquisition contracts
- Parent Goal: SG04 / AC02
- Origin: Audit
- Priority: P1
- Status: VERIFIED
- Dependencies: T001,T003
- Classification: MANDATORY
- Description: Extend crawler capabilities and trusted boundaries
- Acceptance Criteria: Reviewed design and explicit contracts
- Evidence: docs/architecture/DATA_ACQUISITION_DESIGN.md, DATA_CONTRACTS.md, POI_TAXONOMY.md
- Blocker: Live taxonomy inventory is separate T008 dependency.

## T005 — Implement acquisition adapters
- Parent Goal: SG05 / AC02
- Origin: Audit
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: T004
- Classification: MANDATORY
- Description: Two complementary authorized source families
- Acceptance Criteria: Executed acquisition and contract tests
- Evidence: OC026R1 parent140acquisitiontests; OC012 actual30OSM+2Wikidata exports with hashes and32quarantined/0accepted.
- Blocker: Accepted catalog/admin/entity review and explicit legacy-state migration remain; immutable dataset/class state contract accepted locally.

## T006 — Normalize and resolve POIs
- Parent Goal: SG06 / AC03
- Origin: Audit
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T001
- Classification: MANDATORY
- Description: Stable identity, coordinates, closed taxonomy, provenance and review
- Acceptance Criteria: Invalid/ambiguous inputs quarantined; idempotency tests pass
- Evidence: T022 stable identity32tests; OC026R1 acquisition140tests including pre-existing contradictory-state rejection; real-source review queue retained.
- Blocker: Real-record catalog/admin/entity review and cross-source merge unsupported; no accepted payload yet.

## T007 — Integrate graph ingestion
- Parent Goal: SG07 / AC04
- Origin: Audit
- Priority: P1
- Status: DISCOVERED
- Dependencies: T006
- Classification: MANDATORY
- Description: Snapshot graph and integrate accepted records
- Acceptance Criteria: Real repeated ingestion and retrieval succeed
- Evidence: Ingestion/SSE/mutation contracts tested with fake drivers; actual expansion32quarantined/0accepted.
- Blocker: Accepted source payload, primary snapshot and operational Docker/Memgraph unavailable; live repeated ingestion remains required.

## T008 — Verify schema and spatial calculations
- Parent Goal: SG08 / MT2 / AC04
- Origin: Audit
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T001
- Classification: MANDATORY
- Description: Correct prefilters and batch failure semantics
- Acceptance Criteria: Boundary tests and measured benchmark; live graph validation
- Evidence: OC-003 corrective source reviewed; independent65 tests pass; synthetic benchmark labelled
- Blocker: Live graph/spatial concurrency and explicit legacy-radius migration still unverified; mocked stale-edge lifecycle corrected in OC014/017.

## T009 — Complete agent tools and grounding
- Parent Goal: SG09 / MT3 / AC05
- Origin: Audit
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: T001
- Classification: MANDATORY
- Description: Inspect and repair MCP, router, ReAct and graph grounding
- Acceptance Criteria: Tool contracts and end-to-end grounded responses
- Evidence: OC-005/007 corrections accepted;190 combined grounding/chat-memory tests and178 MCP regression tests, overlapping prior counts.
- Blocker: Live model/MCP/graph flow remains; OC016R1 actual itinerary endpoint integration accepted with fake providers.

## T010 — Verify planner and routing
- Parent Goal: SG10 / MT4 / AC05
- Origin: Audit
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: T009
- Classification: MANDATORY
- Description: Validate constraints and explicit route failures
- Acceptance Criteria: Road-route tests and feasible itinerary validation
- Evidence: OC007 directed route contracts; OC016R1 parent255AI+126planner tests including endpoint and cumulative budget correction.
- Blocker: Live directed routes/model and real scientific comparison remain unavailable; tests use fake providers.

## T011 — Verify memory
- Parent Goal: SG11 / MT5 / AC05
- Origin: Audit
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: T009
- Classification: MANDATORY
- Description: Working and long-term memory with explicit current constraints
- Acceptance Criteria: Controlled multi-profile tests and isolation
- Evidence: OC-009/015 historical offline corrections; MEM072R1/parent-final-acceptance.json now accepts15nativechecks/4realGo chats, owner/auth/CAS/history/disable/restart/delete; temporaryissuer, ownedcleanupstopped.
- Remaining: H3 five-profile/three-condition controlled preference influence and cost-coverage evaluation still missing; do not substitute native readiness for scientific results.

## T012 — Verify literature
- Parent Goal: SG12 / MT1 / AC06
- Origin: Audit
- Priority: P2
- Status: VERIFIED
- Dependencies: —
- Classification: MANDATORY
- Description: Read at least 12 relevant original publications
- Acceptance Criteria: Verified bibliography, balanced matrix and chapter synthesis
- Evidence: docs/research/LITERATURE_REVIEW_MATRIX.md (12 primary sources); docs/thesis/CHAPTER_2_RELATED_WORK.md; final TP-RAG PDF read
- Blocker: Bounded related-work review complete; reconstructed theory exists under authorized legacy reconstruction; final full thesis remains T017.

## T013 — Run four experiment families
- Parent Goal: SG13 / AC07
- Origin: Audit
- Priority: P2
- Status: IN_PROGRESS
- Dependencies: T008,T010,T011
- Classification: MANDATORY
- Description: Freeze scenarios, baselines, seeds and raw outcomes
- Acceptance Criteria: Reproducible metrics; at least 20 planning scenarios and 5 profiles
- Evidence: docs/experiments/EXPERIMENT_PROTOCOL.md; synthetic spatial benchmark separate
- Blocker: Real dataset/model/runtime runs remain.

## T014 — Execute adversarial evaluation
- Parent Goal: SG14 / MT6 / AC08
- Origin: Audit
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T009
- Classification: MANDATORY
- Description: Empty candidates, unsupported details, out-of-scope areas
- Acceptance Criteria: All three families executed; failures retained
- Evidence: Corrected mocked grounding/chat suites pass; OC-016 extends actual itinerary integration adversarial tests.
- Blocker: No deployed/model evaluation yet.

## T015 — Conduct voluntary user study
- Parent Goal: SG15 / MT3 / AC07
- Origin: Audit
- Priority: P2
- Status: BLOCKED
- Dependencies: T009
- Classification: MANDATORY
- Description: Prepare protocol then recruit 10–15 authorized volunteers
- Acceptance Criteria: Real consent and counterbalanced paired observations
- Evidence: docs/experiments/HUMAN_STUDY_PROTOCOL.md (no responses)
- Blocker: Requires real participants/consent, frozen stimuli and owner retention/supervisor process.

## T016 — Verify deployment and full workflow
- Parent Goal: SG16 / MT6 / AC05
- Origin: Audit
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: T007,T010,T011
- Classification: MANDATORY
- Description: Build Compose and execute full acquisition-to-response workflow
- Acceptance Criteria: Recorded live integration and deployment outcomes
- Evidence: Native core HTTP/SSE + foot/car receipts CORE069–071; Docker server reachable29.2.1 on18/10/2026 at21:50 (EXP-078/parent-docker-readonly-readiness.json). Native proof is bounded and does not certify Compose deployment.
- Blocker: Historical Docker-unavailable condition cleared by read-only server probe. Full deployment/build/isolation/end-to-end verification remains work, not an external blocker. Do not restart occupied native engines or mutate primary graph without scoped plan.

## T017 — Complete manuscript and figures
- Parent Goal: SG17 / AC10
- Origin: Audit
- Priority: P2
- Status: IN_PROGRESS
- Dependencies: T002,T012,T013,T014
- Classification: MANDATORY
- Description: Five chapters, appendices, Mermaid sources and rendered figures
- Acceptance Criteria: Evidence-aligned 60–70 page manuscript with disclosed limitations
- Evidence: Chapters1–5 and reconstructed theory/RQs; source-driven27page working manuscript all pages inspected; OC029 fixed-layout figure alternative active.
- Blocker: Correct figures/native Word equations/current-source rebuild/full empirical results and final60–70page manuscript missing; lost original text is not recoverable verbatim.

## T018 — Verify scientific claims
- Parent Goal: SG18 / AC09,AC11,AC12
- Origin: Audit
- Priority: P0
- Status: DISCOVERED
- Dependencies: T017
- Classification: MANDATORY
- Description: Reconcile bibliography, metrics, scope and conclusions
- Acceptance Criteria: Every major claim maps to inspectable evidence
- Evidence: Pending
- Blocker: None currently established; dependencies still apply

## T019 — Final handoff and completion gate
- Parent Goal: SG19 / AC10
- Origin: Audit
- Priority: P1
- Status: DISCOVERED
- Dependencies: T018
- Classification: MANDATORY
- Description: Synchronize evidence, status and reproducible continuation
- Acceptance Criteria: Gate evaluated; all remaining actions explicit
- Evidence: Pending
- Blocker: None currently established; dependencies still apply

## T020 — Restore isolated test runtime
- Parent Goal: SG01,SG16 / AC01
- Origin: Audit
- Priority: P0
- Status: VERIFIED
- Dependencies: —
- Classification: SUPPORTING
- Description: Use a working interpreter without overwriting broken venv
- Acceptance Criteria: Dependency imports and targeted tests execute
- Evidence: Existing .venv-validation/.venv-ai-validation/.venv-mcp-validation used for independent suites; original baseline records retained.
- Blocker: Validation environments work. Original ignored .venv was recreated by OC027 out-of-scope uv run; documented side effect, not claimed preserved or validated.

## T021 — Remove hard-coded deployment credential
- Parent Goal: SG16 / AC11
- Origin: Audit
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T001
- Classification: MANDATORY
- Description: Environment-based credential and optional tunnel
- Acceptance Criteria: No literal token; configuration checks pass; owner rotation noted
- Evidence: OC008/013 sanitized config and isolated Compose tests accepted; no hard-coded deployment token in current configuration.
- Blocker: Owner rotation of historical exposed token not verified; cannot infer revocation from source removal. Live deployment/image digest pinning remain separate gates.

## T022 — Preserve POI identity and validate coordinates
- Parent Goal: T006 / AC03
- Origin: Test
- Priority: P0
- Status: VERIFIED
- Dependencies: T020
- Classification: MANDATORY
- Description: Remove validation-time identity mutation, reject blank identifiers/names and invalid coordinates.
- Acceptance Criteria: Original 24 tests plus 8 focused contract tests pass; supplied IDs survive reclassification.
- Evidence: handoffs/OC-001/pytest_baseline.txt; handoffs/OC-002/pytest_oc002.txt; independent Codex run 32 passed.
- Blocker: None; historical duplicate migration remains T007.

## T023 — Repair spatial prefilter and neighbor retrieval
- Parent Goal: T008 / MT2
- Origin: Audit
- Priority: P0
- Status: VERIFIED
- Dependencies: T020
- Classification: MANDATORY
- Description: Conservative geographic filtering, cross-district candidates and undirected retrieval.
- Acceptance Criteria: No reference false negatives across boundary/randomized tests at 1/3/5km; raw synthetic benchmark counts.
- Evidence: handoffs/OC-003/repair_report.md; independent65pass; benchmarks/spatial/
- Blocker: Verified isolated math/query construction; live Cypher and stale cleanup remain T008.

## T024 — Repair ingestion and SSE failure contracts
- Parent Goal: T007 / AC04
- Origin: Audit
- Priority: P0
- Status: VERIFIED
- Dependencies: T020,T022
- Classification: MANDATORY
- Description: Fresh UoW, record accounting, retained pre-subscription events and terminal outcomes.
- Acceptance Criteria: Mixed/malformed batches, retries, partial failure, late SSE subscriber and small jobs tested.
- Evidence: handoffs/OC-004/repair_report.md; independent74pass including42 ingestion/runtimeHTTP tests
- Blocker: Process-local SSE limitation; live DB writes remain T007.

## T025 — Enforce AI evidence identity and exact geography
- Parent Goal: T009 / AC05,AC08
- Origin: QA
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T022
- Classification: MANDATORY
- Description: Reject returned-ID mismatch, unknown scope, substring district collisions and out-of-trip dates; reconstruct supported facts.
- Acceptance Criteria: Corrected adversarial HTTP tests and independent QA pass; unknown scope causes no model call.
- Evidence: OC-005/repair_report.md; independent88 grounding tests passed.
- Blocker: Live end-to-end grounding remains unverified; structured upstream contract now available.

## T026 — Repair MCP compound search, evidence and route completeness
- Parent Goal: T009,T010 / AC05
- Origin: QA
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T023
- Classification: MANDATORY
- Description: Structured graph geography, exact IDs before limit, truthful missing fields, complete ordered route mapping.
- Acceptance Criteria: Executed actual tool contracts with fake collaborators; live graph/route tests later.
- Evidence: OC-007/report.md; independent178 MCP/audit/domain/spatial tests passed (overlapping counts).
- Blocker: Live Cypher and routing unverified; isolated contract accepted.

## T027 — Freeze experiment and human-study methods
- Parent Goal: T013,T015
- Origin: Research
- Priority: P1
- Status: VERIFIED
- Dependencies: T012
- Classification: SUPPORTING
- Description: Define matched baselines, failure accounting, repeated observations and real-human protocol before runs.
- Acceptance Criteria: Four families, measures, denominators, limitations and study design explicit.
- Evidence: docs/experiments/EXPERIMENT_PROTOCOL.md; HUMAN_STUDY_PROTOCOL.md
- Blocker: Protocol completion does not satisfy execution or participation.

## T028 — Acquire and review actual expansion source records
- Parent Goal: T005 / AC02,AC12
- Origin: Research
- Priority: P1
- Status: READY
- Dependencies: T003,T004
- Classification: MANDATORY
- Description: Obtain bounded licensed OSM and Wikidata exports, retain raw hashes/licenses, review admin/category mapping, run pipeline after T005.
- Acceptance Criteria: Actual-source records separated from synthetic fixtures/original dataset; source-level counts and rejected reasons; no unsupported facts.
- Evidence: OC012 completed;30OSM+2Wikidata actual exports independently checked;32quarantined/0accepted; rerun32duplicates. OC026R1 state scope/entry consistency independently140tests accepted.
- Blocker: Original catalog/admin/entity evidence review unavailable; preserve legacyv2 outputs and use explicit migration/new directory, never reset evidence silently.

## T029 — Repair persistent preference and memory lifecycle
- Parent Goal: T011 / MT5
- Origin: Audit
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: T026
- Classification: MANDATORY
- Description: Avoid preference Cypher UNWIND-empty dropping tag/category updates; add explicit update/delete/session isolation and integrate bounded short-term/long-term memory.
- Acceptance Criteria: Five-profile controlled tests, updated preference persistence and isolation; usage measured honestly.
- Evidence: OC-009/015 memory corrections andOC-014 independent preference writes tested with fakes.
- Blocker: Live preference persistence and real-model influence remain unverified.

## T030 — Deterministic planner and independent constraint validation
- Parent Goal: T010,T013 / MT4
- Origin: Audit
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T026
- Classification: MANDATORY
- Description: Bounded heuristic plus independently computed temporal/budget/unknown-fact checks; freeze20 synthetic engineering scenarios before execution.
- Acceptance Criteria: No fabricated route/time/cost facts; integration into actual endpoint; matched real-model comparison remains separately required.
- Evidence: OC016R1 production endpoint/planner integration independently255AItests and126planner tests; cumulative current-day budget fixed.
- Blocker: Real-model comparison/direct routes and actual source data still missing; mock integration is accepted locally.

## T031 — Graph-only lifecycle without Firebase requirement
- Parent Goal: T016 / MT6
- Origin: QA
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T026
- Classification: MANDATORY
- Description: Optional Firebase initialization and correct startup/cleanup/health, preserving JWT checks.
- Acceptance Criteria: Actual import/lifecycle tests with fakes, no Firebase import in graph-only mode; live startup separately verified.
- Evidence: OC-011 completed; startup47tests independently covered in291-test combined regression; OC-013 isolated config verified.
- Blocker: Docker engine unavailable for live startup.

## T032 — Integrate spatial mutation and terminal reports
- Parent Goal: SG08,SG16 / AC04
- Origin: Independent QA
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T008,T031
- Classification: MANDATORY
- Description: Single-POI transactional replacement, accepted-ID bulk coverage and observable manual rebuild outcomes.
- Acceptance Criteria: Correct mutation rollback; counts separate from spatial outcome; incompatible application radius rejected; live checks separately required.
- Evidence: OC017R1 terminal; independent47lifecycle tests with1optional skip, uniform5km and missing legacy metadata gate verified.
- Blocker: Livegraph/concurrency/legacy migration unverified; no OC017 worker active.

## T033 — Implement trustworthy paired experiment evaluator
- Parent Goal: SG13 / AC07,AC11
- Origin: Protocol implementation and QA
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T013
- Classification: MANDATORY
- Description: OfflineH2/H3 metrics preserve planneddenominators, provenance, missingness andproviderusage.
- Acceptance Criteria: No contradictory outcomes accepted; paired repetitions comparable; unknowncategory cannotinflateexactshare; actualexperiments remainseparate.
- Evidence: OC024 reporting correction independently67tests passed; synthetic demo and explicit denominators accepted at offline engineering scope.
- Blocker: Original snapshot/model runs absent; actual scientific evaluation remains pending.

## T034 — Controlled DeepSeek-Go live experiment collector
- Parent Goal: SG13 / MT4 / AC07
- Origin: User-authorized provider alternative and implementation gap
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: T033, frozen scenario and planner contracts
- Classification: MANDATORY
- Description: Fresh-session, tools-denied CLI calls using opencode-go/deepseek-v4.1-flash; same facts/model/settings across paired conditions; validated raw records with provider usage and provenance.
- Acceptance Criteria: Fake-event failure tests pass, independent QA accepts collector, bounded real smoke succeeds, then planned paired observations execute without fabricated repairs. Synthetic scenarios remain engineering evidence, separate from original dataset.
- Evidence: OC023R1 local collector contract accepted96independenttests; fresh S01 diagnostic2timeouts/0validrecords/2gaps.
- Blocker: DS002 confirms Go usage limit exceeded; provider restoration/selection question pending. Original graph snapshot unavailable for primary thesis runs.

## T035 — Assemble and render editable thesis manuscript
- Parent Goal: SG17 / AC10
- Origin: Required deliverable
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: Working Chapters1–5 and approved references
- Classification: MANDATORY
- Description: Assemble current Vietnamese prose as an honest editable working draft; verify every rendered page and preserve incomplete experiment gates.
- Acceptance Criteria: DOCX and actual page renders exist, correct chapter/reference structure, no clipping or fabricated page/results claims; final thesis still requires actual studies.
- Evidence: OC022R1 source-driven DOCX, actual27page PDF/PNGs all parent-reviewed; current Chapter4source newer than DOCX.
- Blocker: Correct figures/native Word equations/rebuild and real scientific results still pending; working draft is not a complete60–70page thesis.

## T036 — Preserve experiment evidence across continuation
- Parent Goal: SG13 / AC07,AC11
- Origin: Independent end-to-end probe
- Priority: P0
- Status: VERIFIED
- Dependencies: T034 collector contract
- Classification: MANDATORY
- Description: Replace destructive resume/export handling with validated immutable run state and lossless structured-record merge; align hybrid experiment with production planner.
- Acceptance Criteria: No-op resume preserves prior bytes/results; interrupted continuation retains all completed observations; incompatible settings/source hashes rejected before writes; failures retained; actual production scheduling path evaluated.
- Evidence: OC023R1 parent96tests plus direct selection-drift rejection/allbytespreserved; actual production scheduler imported via category-weight adapter.
- Blocker: Local preservation gate passed; actual live evidence still absent. Literal model order/day assignments are not honored; disclose adapter semantics.

## T037 — Complete authenticated backend itinerary-draft workflow
- Parent Goal: SG09,SG16 / AC05 / MASTER_GOAL section3.7
- Origin: Core application workflow audit
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: Tested AI itinerary response contract; backend storage configuration
- Classification: MANDATORY
- Description: Existing backend has repository/domain classes but empty itineraryendpoint and no FastAPIentrypoint. Add scoped authenticated save/list/get/delete draft API with durablelocalstorage andhonestverificationstatus.
- Acceptance Criteria: ActualASGI workflow/restartdurability/userisolation/strictJWT/payloadbounds/unknownstatuspreservation verified; no unconditionalFirebase dependency orsilentfallback; deployedintegrationseparatelyrequired.
- Evidence: OC028 terminal; parent52tests4.15s and reviewed schema/file/restoration assertions accept local draft/readiness contract, superseding OC027 probe rejection.
- Blocker: Locked packaging/Compose/liveFirebase and deployment unverified; deliberate startup initialization is separate from probes. Original OC027 worker recreated ignored .venv; R1/OC028 did not repeat mutation.

## T038 — Separate initialization from observational readiness
- Parent Goal: SG16 / AC05,AC11
- Origin: OC027 independent failure probe
- Priority: P0
- Status: VERIFIED
- Dependencies: T037 local draft workflow
- Classification: MANDATORY
- Description: Prevent readiness/ordinary CRUD from recreating lost SQLite storage or schema.
- Acceptance Criteria: Missing or malformed schema503 without mutation; missing file stays absent; original restoration recovers existing drafts; safe startup boundary.
- Evidence: OC028 parent52tests4.15s; reviewed actualASGI/SQLite assertions; E044.
- Blocker: None at local contract scope; production operation remains T016/T037.

## T039 — Produce accurate readable publication figures
- Parent Goal: SG17 / AC10
- Origin: OC025R1 independent visual rejection
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: Current architecture/experiment methods
- Classification: MANDATORY
- Description: Fixed-coordinate SVG/PNG alternative after automatic layout left overlaps and false model/edge relationships.
- Acceptance Criteria: All4images parent-inspected, readable at16cm, correct architecture/outcomes/planned experiment analyses and honest captions; no claims of live success.
- Evidence: OC029brief; process12770/session ses_ebbeeec61ffeaZHrUAKgoqldXR.
- Blocker: Executor active; image QA pending, source generation alone not acceptance.

## T040 — Package backend and wire isolated integration stack
- Parent Goal: SG16 / AC05,AC11
- Origin: Backend workflow completion
- Priority: P0
- Status: VERIFIED
- Dependencies: T038
- Classification: MANDATORY
- Description: Reconcile locked direct dependencies, runnable Docker entrypoint and isolated SQLite/JWT Compose wiring.
- Acceptance Criteria: Actual locked backend/AI/POI export, safe quiet config validation, source tests for entrypoint/port/volume/auth; live deployment separately required.
- Evidence: OC030 terminal; parent40deploymenttests2.13s, quiet isolatedCompose config0, actual offline lockcheck and backend/AI/POI exports all0; runnableCMD/ownSQLitevolume/JWT source reviewed.
- Blocker: Packaging/configuration accepted; actual Docker build/start/image digests and live integration remain T016. No OC030 worker active.

## T041 — Audit and integrate supplied primary GeoJSON
- Parent Goal: SG06,SG07,SG13 / AC03,AC04,AC07,AC12
- Origin: User supplies missing primarydataset and revises200to1000+processedPOIs
- Priority: P0
- Status: IN_PROGRESS
- Dependencies: Stable identity/schema contracts
- Classification: MANDATORY
- Description: Audit/freeze6368features, preserve source/provenance/unknowns, resolve quality/identity/category/admin then integrate actual primarysnapshot for system/experiments.
- Acceptance Criteria: Immutable rawhash/count, deterministic quality/duplicate audit, faithfulschema/IDmapping, explicitly accepted graphcounts and repeatable realingestion/retrieval; inputfeatures never equatedwithuniqueacceptednodes.
- Evidence: E048; OC032process30712/session ses_ebbd7a09dffeFue824VOyO9upT ownsderiveddataset audit, docsdata and ownhandoff; rawfileimmutable.
- Current: DATA068 full frozen primary import/upsert/persistence accepted by Codex;6367POI/14Category/3678397NEAR_BY and independent full graph QA passed. Actual HTTP/client/liveprovider integration remains T049/CORE069. No venue-quality or upstream-identity claim.

## T042 — Bind live model provenance to exact CLI session export
- Parent Goal: SG13 / AC07,AC11
- Origin: Successfulactualaliasdiagnostic has no modelidentity in JSONeventstream
- Priority: P0
- Status: VERIFIED
- Dependencies: T036 immutablecollectorcontract
- Classification: MANDATORY
- Description: Readonlyexactsession sidecar validatedagainst rawsession/message/text/finish/usage, preserving rawbytes and versionedrunfingerprints.
- Acceptance Criteria: ActualDS004metadata bindsqualifiedmodelaibox/ds/deepseek-flash; forged/mismatched/stale/ambiguousmetadata rejected; existingresume/denominators/testcontractsretained; parentboundedpairafterlocalacceptance.
- Evidence: OC033R1terminal; parent153tests5.85s anddirectnestedbinding/invalidusageprobespass; actualfreshS01pair2completed/2engineeringrecords/0gaps withsession-exportprovenance.
- Blocker: Localcontractverified; actualprimarydatasetfacts/routes andfull20scenarioH2stillneedfreeze. Alias4.1unknown/disclosed; S01notprimaryscientificresult.

## T043 — Prepare primary POI import candidates and local identity registry
- Parent Goal: SG06,SG07 / AC03,AC04,AC12
- Origin: Independentlyaccepted6368datasetcharacterization
- Priority: P0
- Status: VERIFIED
- Dependencies: T041 audit stage
- Classification: MANDATORY
- Description: Existingcrawlercapability prepares actualPOIschema-validatedcandidates, persistentlocalIDs/lineage/explicitduplicateledger and sourcecategorycatalog withoutlivewrites.
- Acceptance Criteria: All6368sourceindicesaccounted; rawunchanged, samebrandbranchesdistinct, exactduplicateexplicit, repeat/reorderIDstability, unknownsnotinvented, preparednotgraphaccepted.
- Evidence: OC034R1 terminal; parent169tests8.02s, actual6367model validations, all6368indices accounted, two byte-identical no-op runs; E057.
- Blocker: Candidate preparation/local registry accepted after OC039 chronological alternative39tests/direct parent probes/full actual copy checks. Provenance/admin/live graph integration remain separate T046/T048/T049, not claimed complete.

## T044 — Refresh publication labels and resolve full-page review findings
- Parent Goal: SG17 / AC10,AC11
- Origin: Parentall36pagevisualreview/newuserproviderdecision
- Priority: P1
- Status: IN_PROGRESS
- Dependencies: NativeOMML/figureintegration in T035; T042 localcollectoracceptance
- Classification: MANDATORY
- Description: Updatefigurecollectorlabels/captions/currentevidence; correctspillpages/orphanheaders/ref/formpagination andrerenderwithoutshrinking/deletingprose.
- Acceptance Criteria: Nativeequations/sourcefidelity/16cmfigures retained, exactaliasuncertainty/newdataset153tests+S01engineeringhonest, allnewpagesparent-reviewed.
- Evidence: OC035 terminal; parent all33pages reviewed, requested layout fixes accepted; E056/publication-refresh-layout-acceptance checkpoint.
- Blocker: Appendix D stale collector/build status to reconcile at next substantive rebuild; final full thesis/results remain separate and incomplete.

## T045 — Preserve explicit category/tag IDs through bulk ingestion
- Parent Goal: SG07 / AC04,AC11
- Origin: OC036 production integration audit confirmed bulk merges by name while single paths use ID
- Priority: P0
- Status: VERIFIED
- Dependencies: T041 audit; actual immutable snapshot preparation in T043
- Classification: MANDATORY
- Description: Correct bulk Category/Tag MERGE keys to explicit IDs using existing trusted ingestion path, without migrating persisted IDs or inventing taxonomy.
- Acceptance Criteria: Actual production model/repository preserve same-name distinct IDs; parameterized query contract and focused regressions pass; fake tests never called live graph proof.
- Evidence: OC037 terminal; parent7new/4category/21ingestion-domain checks pass; E059/checkpoint2026-10-17-bulk-identity-acceptance.md.
- Blocker: Local category/tag identity contract verified; provenance/qualified administration/live engine stages remain separate.

## T046 — Persist source provenance and qualify source-only administrative data
- Parent Goal: SG07,SG09 / AC03,AC04,AC11
- Origin: OC036 production audit and primary dataset source-snapshot semantics
- Priority: P0
- Status: VERIFIED
- Dependencies: T045 explicit category identity; frozen snapshot output portion of T043
- Classification: MANDATORY
- Description: Extend actual POI boundary/writes/reads with typed bounded provenance, unknowns, source-only address scope, safe null-address handling and exclusion from current jurisdiction claims.
- Acceptance Criteria: Source metadata persists/round-trips; malformed evidence rejected; all write/read paths consistent; source-only legacy labels never ordinary current containment; previous grounding and spatial contracts retained.
- Evidence: OC038 brief/process14937; pending independent QA.
- Blocker: Implementation/QA pending; actual frozen payload adapter and live import remain subsequent stages.

## T047 — Implement coherent primary registry revision chronology
- Parent Goal: SG06 / AC03,AC11,AC12
- Origin: Independent null-hash and revisited-revision counterexamples after OC034R1
- Priority: P0
- Status: VERIFIED
- Dependencies: Frozen exact snapshot portion of T043; original repair attempt exhausted
- Classification: MANDATORY
- Description: Bounded alternative with explicit chronological history, strict existing hash/scope consistency and content-bound immutable backups; preserve frozen outputs.
- Acceptance Criteria: A->B->A->B survives reload with ordered history and stable IDs; no unreviewed changes; invalid/prospective/save states fail before output writes; actual frozen data unchanged.
- Evidence: OC039 terminal; parent39tests4.66s, independent revision probes/cycle3backups/full6368input-copy model/no-op/ID/hash checks; E060.
- Blocker: Local revision contract verified; no authenticated tamper/concurrency/crash guarantee or live graph acceptance claim. Acquisition regression in OC038 remains separate.

## T048 — Bind frozen primary lineage into versioned graph-ready payloads
- Parent Goal: SG06,SG07 / AC03,AC04,AC12
- Origin: Optional provenance schema changes require an explicit output-version step
- Priority: P0
- Status: VERIFIED bounded offline adapter gate — DATA068 root fresh prepare_snapshot validates6367records/6368lineage accounting and graph_ready_v2 bytes+manifest match. Durable fullimport remains S2, not claimed here.
- Dependencies: T046 locally accepted metadata/persistence; exact snapshot IDs from T043
- Classification: MANDATORY
- Description: Adapt6367frozen candidates and complete6368feature lineage/duplicate accounting into a fresh graph-ready output version through actual POI validation; retain prepared-v1/raw/registry bytes.
- Acceptance Criteria: All IDs/categories preserved, complete source bindings including unknowns, all actual-model valid, deterministic no-op in the new directory, immutable raw/v1 hashes; no invented upstream identities or graph count claim.
- Evidence: Existing app/core/utils/primary_snapshot.py and graph_ready_v2; DATA-068/parent-readiness.json freshly verifies counts/models/categories/lineage/output equality. Frozen raw/v1 preserved; no nativeupstreamIDs invented.
- Remaining: S2 full primary import/upsert/persistence accepted DATA068 (parent-final-review.json); HTTP/client/liveprovider source selection remains T049/CORE069. Frozen snapshot bytes preserved.

## T049 — Support explicit source-snapshot area retrieval and planning selection
- Parent Goal: SG07,SG09,SG10 / AC04,AC05
- Origin: Excluding all source-only records from current jurisdiction queries alone does not make the supplied dataset usable
- Priority: P0
- Status: IN_PROGRESS — server and AI/planner contract verified at bounded actual-canary scope
- Dependencies: T046 qualified persistence; T048 adapter
- Classification: MANDATORY
- Description: Extend existing tools/services with explicit snapshot namespace/hash and qualified source city/area selection, distinct from current administrative containment; retain current-request unknown/refusal behavior when no mapping exists.
- Acceptance Criteria: Source-only records selectable through an explicit source-snapshot path, qualified evidence survives routing/planning, no input-ID or free-text promotion to current jurisdiction, no silent permanent exclusion of all supplied records.
- Evidence: OC045 realgraph/sourceMCP gates; AI059 independent162grounding/126planning on lockedMCP1.26.0,15HTTPboundaryprobes and actual6stage realgraph/MCP/routing/controlmodel canary with clean0/0rollback. Initial516regressions also pass; QA-SOURCE-SCHEDULE-META-01 found and corrected through same-sessionR1, originalproof preserved.
- Remaining: client discovery/selector supply and liveprovider/actual HTTPMCP/native service integration in CORE069. DATA068 fullsnapshot import/upsert/restart accepted with independent full spatial-set QA; concurrent updates/all spatial lifecycle are not covered by that import gate.

## T050 — Carry genuine acquisition-source provenance into graph acceptance
- Parent Goal: SG05,SG06,SG07 / AC03,AC04,AC12
- Origin: Primary internal-identity provenance is a bounded case; separate32OSM/Wikidata candidates still require resolution/acceptance
- Priority: P0 within phase5 new-source integration
- Status: DEFERRED_TO_PHASE5_FINALIZING for new acquisition sources. Primary OSM-snapshot/internal lineage and import remain core S2/T048/T049; do not defer those or invent native OSM IDs.
- Dependencies: T046 source metadata foundation; acquisition immutable scope contract; individual candidate review
- Classification: MANDATORY
- Description: Extend reviewed provenance support to genuine source-native IDs/lineage without mislabelling them as primary internal IDs; resolve permitted-source candidates through the same ingestion boundary and retain separate dataset manifests.
- Acceptance Criteria: Actual eligible new-source records accepted/retrievable with source/license/freshness truthfully recorded; unresolved records stay quarantined; no cross-source merge or fake internal/upstream equivalence; primary/expansion scopes remain distinct.
- Evidence: Existing expansion32records/0accepted; further implementation/quality review pending.
- CR061 followup: actual Wikivoyage capture replay yields252listings/161minimumfields, all252quarantined/0accepted-imported. Capture workflow onlypartial (4GETfor3URLs); native/rootcheckedhashes/counts, no T050graphlineageacceptance. See checkpoints/2026-10-18-three-followups-reviewed.md.
- Blocker: Native-source lineage contract, candidate resolution and live graph pending.

## T051 — Support the authorized CLI model route in actual AI runtime verification
- Latest authority: DATA068/CORE069–071 parent receipts, DOC073/parent-final-acceptance.json, MEM072/parent-r1-prepared.json; historical paragraphs below are preserved, not current active instructions.
- Parent Goal: SG09,SG10,SG11,SG13 / AC05,AC07,AC08
- Origin: User explicitly authorized OpenCode DeepSeek as the Gemini alternative; collector works but actual AI service still defaults to Gemini/key dependency
- Priority: P0
- Status: IN_PROGRESS — native Go/Jev/chat/car accepted CORE069–071; S5 readiness and S6 collector accepted bounded; primary freeze pending.
- Dependencies: Accepted exact-session CLI provenance contract T042; current AI provider interface audit
- Classification: MANDATORY
- Description: Add an explicit opt-in, per-run model adapter for the authorized aibox/ds/deepseek-flash route to the existing AI flow; preserve Gemini default and avoid silent fallback/global provider changes. The CLI supplies model responses, not a replacement planner/tool authority.
- Acceptance Criteria: Actual router/chat/planning/memory flow can use the selected CLI model with bounded prompts/time/retries and exact identity/usage evidence; no CLI shell/file/tool authority leaks; controlled live intent/chitchat checks precede graph-dependent trials; both scientific arms remain matched; identity is user-confirmed DeepSeek V4.1 Flash on exact aibox/ds/deepseek-flash, never explicitlyV4.0; independent provider attestation must not be fabricated.
- Evidence: User provider decisions and DS004/OC033 S01 evidence; OC040310parentofflinechecks pass; independent concurrency/schema/control probes reject full acceptance; bounded R1process17682. Label correction accepted editorially. No adapter live calls yet.
- Blocker: No remaining provider-call blocker in accepted native scope; S5 revised QA accepted bounded; primary experiments/freeze not done.

18/10 E106/CLI067 supersedes old active CLI060 notes: initial20173terminal1/R17747terminal0, no writer. Root189provider/16policy/4lifecycle pass; nativefake54checks+9actualargvchecks pass. SeeCLI-067/parent-final-review.json andcheckpointcli067-native-transport-accepted. No realapplicationpaidmodel/fullHTTP proof yet. Fakeendpointobservesauxiliarygeneration: mainusage nottotalbilling; bind/control/disclose before costexperiments. Preserve defaultpurefailclosed, no globalconfig/keyread or carrier clearing.

## T052 — Verify the real engines through isolated native workspace runtimes
- Latest authority: DATA068/CORE069–071 parent receipts, DOC073/parent-final-acceptance.json, MEM072/parent-r1-prepared.json; historical paragraphs below are preserved, not current active instructions.
- Parent Goal: SG07,SG08,SG10,SG13,SG16 / AC04,AC05,AC07,AC11
- Origin: Docker unavailable, but verified Ubuntu24.04/glibc2.39 permits a same-product portable verification path
- Priority: P0
- Status: VERIFIED — bounded native Memgraph/GraphHopper/Windows connectivity and full primary integration, DATA068/CORE070/071.
- Dependencies: Official package/version/security metadata; fresh workspace-owned state and loopback ports
- Classification: MANDATORY
- Description: Prepare isolated portable Memgraph and patched GraphHopper runtime capabilities for real Cypher/routes without system installs or historical data access; native results supplement pending Docker proof.
- Acceptance Criteria: Exact package/version/hashes/ownership recorded, real Windows-host connectivity and core queries/routes verified, bounded safe startup/status/stop, source/raw untouched; no fake Docker/MAGE/full-system claim. Routing runtime must be patched for the official advisory.
- Evidence: OC041 brief/process57252 targets Memgraph3.13.2 first; native routing preparation remains subsequent. Official download docs/advisory and corrected runtime inventory recorded.
- Blocker: No native engine blocker demonstrated in accepted scope. Docker/public deployment not proven and not required to block approved native S3.


T052 update2026-10-17: parent actual native archives independently reviewed (148Memgraph/9libatomic members, no unsafepaths/links/devices; libatomic hash/10466BmatcheslocalUbuntuAPTmetadata), scope-deviation retained. Native routing OC042 nowrunning50832 with whollyseparate newdirectories and1GiBheap; replaces earlier deferreddispatchstatus, does not claim success. See ownbrief/latesthandoff.


## T053 — Correct and verify native Memgraph spatial-query compatibility
- Parent Goal: SG07/SG08/SG16; AC04/AC05/AC11
- Status: VERIFIED (bounded native compatibility/application canary); full-scale integration remains separate; P0
- Evidence: OC041parentrollbackcanary confirms actualbatchCRUD/idempotency/provenance/category/sourcequalificationworks, but spatialfailsFunctiondegreesdoesnotexist; rollbackleft0nodes. Parentmathprobeconfirmsradiansalsomissing,cos/pi/abs/arithmeticavailable.
- Required: preserveconservativesphericalgeometry/lower6300km/dateline/pole/3km/fullprecisiondistance/lifecycle semantics with supportedarithmetic; actualgeneratedqueryevaluationplusparentrollbackcanary mustpass. OC044briefprepared, notyetdispatched. No broadrepositorychanges ordatawrites byexecutor.


T053 update2026-10-17: OC044 actuallydispatched52250/ses_eb5b57c64ffenGCpKNM9aFxdLy ondisjointutility/tests. Earliercapacitywait superseded. T052routing: WSLhealthOKafterendpointfix; expectedownedJavalistenersIPv4mappedloopback, butparentWindowsrequestsrefused10061. Parentactualproof+targetedperprocessIPv4candidate inOC042/parent-readiness-review.md; fullhostroutegatepending. No globalnetworkchangesauthorized orperformed.



T046 update2026-10-17: terminalOC038R1 acceptedboundedprovenancefoundation; finalparentprobes/all6367binding/6368conservation/46+175overlappingtestchecks. T041overallgraphintegrationinprogress. T049 serverportionOC045 nowrunning30918/ses_eb5adbaf3ffeZTSG4O2GB314oN inreleasedPOIpaths; AI/plannergatependingafterproviderwriterrelease. T053spatial044alreadyactive52250, no longerdeferred.



## T054 — Enable and independently verify relationship properties
- Parent Goal: SG07/SG08/SG16; AC04/AC05/AC11
- Priority: P0; Classification: MANDATORY; Status: VERIFIED (bounded native configuration + application canary, E070)
- Origin: Actual application rollback canary failed because Memgraph3.13.2 defaults relationship properties to false.
- Delivery: OC046 terminal7077/session ses_eb5a80f67ffeUCVxAVKgTgyumZ; native helper and both Compose commands now explicitly enable the flag; executor reports fresh owned store and runtime checks.
- Acceptance: Independently inspect ownership/scoped diff/configuration and rerun the genuine application rollback canary, verifying edge properties and zero state after rollback. No full import/deployment claim from executor evidence.
- Qualification: Executor performed an uncommitted edge probe despite the no-graph-write brief and transient external scratch; disclose during QA.

2026-10-18 reconciliation: OC040 R1, OC042, OC043, OC045 and OC046 all terminal exit0, awaiting independent acceptance. OC044 expression accepted on 1113 actual-engine cases; T053 full application gate remains IN_PROGRESS, now dependent on T054 and current source-scope integration. OC042 claims Windows four-route success after IPv4 fix; parent final review pending. T049 still requires AI/planner scope retention. Read checkpoints/2026-10-18-progress-and-review-queue.md; older live-process notes are superseded.


## T055 — Chuyển phân loại ý định sang Jev theo thay đổi phạm vi
- Latest authority: DATA068/CORE069–071 parent receipts, DOC073/parent-final-acceptance.json, MEM072/parent-r1-prepared.json; historical paragraphs below are preserved, not current active instructions.
- Status: VERIFIED — bounded Jev pilot + real service chat CORE070; representative scientific evaluation remains phase3.
- Yêu cầu: Không dùng Ollama/local LLM cho intent classification; dùng Jev/TypeSafe. Codex lập kế hoạch và QA trước, OpenCode thực hiện.
- Kế hoạch/kết quả: AI063 initial86871/R153795terminal0 cùng session ses_eb2c4e654ffecQ3FBMl7zcycCa. Root522offline+23probeđạt; pilotAPI30/30HTTP200, observedjev-1.13.0, threshold0,69 chọn pilot/freeze trước holdout. Holdout15: nhãn15/15, auto9đúng/0sai/6hỏi lại; chỉ engineeringQA tổng hợp. TYPESAFE_API_TOKEN được bộ nạp sử dụng an toàn; không sửa.env/productionpolicy. Xem checkpoint2026-10-18-jev-live-pilot-accepted.md; còn rollout+serviceHTTP+datasetđại diện.
- Acceptance: adapter typed Choice/uncertainty/lỗi hữu hạn, không fallback Ollama; dữ liệu tiếng Việt và lỗi API được kiểm thử; model/latency/usage có provenance; giữ nguyên model sinh nội dung và user-selected source scope.

QA-DATA-01 (giai đoạn1): parent regression xác nhận API thư viện graph-ready cho phép real=True với binding do caller thay; fixed-default CLI chưa bị chứng minh bypass. frozen inputs không đổi. Xem QA_PHASE1.md và OC043/parent-real-profile-regression-result.json; sửa trong giai đoạn2 sau kế hoạch Codex.


2026-10-18: OC047/R1 terminal2031/96005; báo cáo tương tác tiếng Việt +9module+kiến trúc đã giao. Parent140staticchecks/48refs đạt, executor109browserchecks và finalArchifyvisual-check đạt có giới hạn derivative/parentbrowsergate; xem parent-review.md. Hiện vẫn phase1 theo FOUR_PHASE_PLAN.md; T055 Jev planned, QA-DATA-01 tái hiện. Không nhận toàn bộ sản phẩm/thí nghiệm. Checkpoint interactive-report-delivery ghi kế hoạch tiếp theo và scope/model/scratch qualifications.


2026-10-18 E070: T054 VERIFIED for native edge-property configuration and explicit Compose declarations, supported by real application rollback canary and40parent config tests. T053 VERIFIED for arithmetic compatibility + actual NEAR_BY write/rebuild gate. Fullgraph integration/T041/T049/T052 remain IN_PROGRESS. No primary import or full server/planner/deployment acceptance. See native-graph-canary-acceptance checkpoint.


## T056 — Agent Memory để lưu preference và grow with customer
- Priority: P2 theo người dùng18/10/2026. Status: RESEARCH_REVIEWED (RS058; Hermes/Letta Code/LangGraph/Mastra); implementation **DEFERRED_TO_PHASE5_FINALIZING** theo scope mới nhất. RS061 đã có5ticket, không lặp nghiên cứu/coding trước phase5plan.
- Origin: Người dùng yêu cầu thêm một sub-agent nghiên cứu Hermes và2–3 harness so sánh; chọn harness phù hợp, component memory hoặc tự xây lớp kiểm soát riêng.
- Scope: Preference lâu dài/phiên/chuyến đi, provenance/conflict/correction/consent/tenant, phản hồi khách hàng, chống poisoning, khả năng đo chất lượng/chi phí và user control. Giữ nền tảng hiện có, planner/MCP/source scope và Jev intent theo scope mới.
- Schedule: Nghiên cứu read-only có thể song song; coding/migration/integration sau đủ4phase, KHÔNG đợi viết luận án; không tự mở H1. Không chặn đường găng phase1–4.
- Deliverables: docs/research/agent-memory-p2/{RECOMMENDATION_VI.md,SOURCES.md,P2_ACCEPTANCE.md}; Codex duyệt trước mọi triển khai.
- Acceptance: Hermes+đúng2–3 ứng viên, nguồn primary/version/license/unknowns, đọc mã memory hiện tại, khuyến nghị rõ và tiêu chí QA có thể kiểm tra, không bịa benchmark hay coi proposal là capability đã có.


## T057 — Ingest POI từ nguồn xã hội/web lấy nhanh
- Priority: P0 bên trong phase5; Status: DEFERRED_TO_PHASE5 theo user18/10/2026. Không phải gatephase2; OC050/CR057/CR061/CR062 có kết quả giới hạn chưa thành fullingest.
- Plan: handoffs/OC-050/brief.md do Codex lập trước khi giao. Native /root/social_poi_ingest giám sát, OpenCode AI-box aibox/ds/deepseek-flash thực hiện mã.
- Scope: nguồn công khai fetch nhanh; mỗi POI có tên + địa chỉ + (mô tả hoặc review), provenance từng field, quality/dedup/quarantine qua acquisition hiện có. SerpApi/Tavily enrichment chỉ injectable/fake tests khi chưa có quyền gọi trả phí.
- Acceptance: actual extraction → normalized web adapter → existing dry-run; số lượng từng tầng, stable IDs, real/synthetic riêng, không mất mô tả/review, không giả geocode/license/admin. Imported=0 ở task; T050 vẫn là gate lineage server trước nhập thật.
- Evidence: docs/research/social-poi/inputs/finding-manifest.json; brief OC050. Finding là dữ liệu khảo sát cũ, không phải chỉ dẫn hay quyền vượt hạn chế nguồn.

## T058 — Crawler nguồn dễ/web tĩnh chạy được
- Priority: P1 bên trong phase5; Status: DEFERRED_TO_PHASE5 theo user18/10/2026. Không mở thêm agent/coding cho crawler trước chốt kế hoạchphase5.
- CR062 accepted bounded fix18/10: capture filename portable/contained/80stem + ingest OSError constantredaction; root326suite/23+5probespass. CR061252real-listings/161minimumfields remainquarantined0import; actualresumableworkflow/pacing/categoryreview/T050lineage remainopen. See checkpointcr062-crawler-fixes-accepted.
- Scope: HTTP-only, JSON-LD/HTML cấu trúc hoặc bảng công khai; allowlist/redirect/SSRF/size/timeout/rate bounds; nhiều POI/trang không lẫn evidence; CLI và test có thể tái lập.
- Acceptance: source policy matrix, parser/network/error tests và legacy acquisition regression; 403/429/login/challenge phải báo lỗi/hạ ưu tiên, không né chống bot. Không browser, tài khoản riêng hay graph POST thật.

## T059 — Nguồn động hoặc chống bot khó
- Priority: P2 bên trong phase5. Status: DEFERRED_TO_PHASE5; chỉ nghiên cứu/phân loại/đề xuất sau kế hoạchphase5, không tự bypass nguồn động.
- Scope: nguồn cần JavaScript, login hoặc hạn chế chống bot. Ưu tiên API/chương trình truy cập được phép hoặc dữ liệu do chủ nguồn cung cấp; không xây bypass CAPTCHA/login/proxy/stealth.
- Dependency: P0/P1 đã QA và quyết định truy cập/chi phí phù hợp trước mọi triển khai. Không đưa vào đường găng bốn phase.

T051 update18/10/2026: QA-PROVIDER-CLI-01 confirmed. CurrentCLI2.0.32 rejects default --pure; offline96pass not actual transport proof. Phase2 must adapt capability/isolation/tool-deny/export/usage without silently weakening controls; no live model call in parent probe.

T056 update18/10/2026: RESEARCH_DELIVERED, recommendation reviewed as proposal (thin memory layer; Hermes/Letta/LangGraph comparison). Implementation still deferred until all four phases; no runtime/benchmark acceptance.

## T060 — Configurable GraphHopper profile routing mode
- Priority: P1 mandatory before enabled-foot experiments. Status: VERIFIED bounded integration18/10/2026; fullsystem gates remain separate. SG10/SG16, AC05/AC07/AC11.
- Shipped: profile-specific ch.disable and RT064 strictrequestcar|foot; mode/provenance through MCP/edge/scenario/constraints, sanitized mismatch refusal/no fallback. Defaultcar disclosed separately from explicit selection.
- Independent evidence: RT-064/parent-final-review.json, parent-contract-after.json, parent-http-mode-results.json, parent-real-mode-{car,foot}.json. Root234plannerfinal+162groundinginitial/15ASGI/15contractpass; actual2POI/4HTTP with registeredinprocessMCP+realgraph+realGraphHopper, modelcontrolled, rollback0/0 and frozenhashesunchanged. Tiny20mcase not quality/performance/fullsnapshot/deployedHTTP/liveprovider proof. Initialsanitizationfailure fixed inR1; tempwriteviolation retained. Handles86936/29806terminal0.

T057/T058 update18/10: OC050 interrupted terminalexit1 for credential incident, code preserved pending independentQA/correction, no live writer. P0/P1 not accepted; imported0. See routing-hermes-local-domain-checkpoint. T059 staysdeferred.


## T061 — Source result date serialization through MCP
- Latest authority: DATA068/CORE069–071 parent receipts, DOC073/parent-final-acceptance.json, MEM072/parent-r1-prepared.json; historical paragraphs below are preserved, not current active instructions.
- Current status: VERIFIED — bounded source serialization and full primary MCP/HTTP path, DATA068/CORE069/070.
- Parent: T049/SG07/SG08/AC04/AC05. Priority: P0. Status: DISCOVERED. Origin: actual in-process FastMCP + owned graph rollback canary.
- Description: snapshot/area discovery pass but source POI projection is Python-mode model_dump containing date in source_metadata.provided_at; json.dumps fails and MCP returns exploration_failed.
- Acceptance: JSON-safe explicit domain serialization with provenance types/fields preserved, regression with populated date + actual registered-tool/real graph rollback canary pass; source scope/mixed-filter/corrupt qualification intact.
- Evidence: OC045/parent-mcp-real-canary-20261018-serialization.json; 36offline tests passed1.19s miss populated date. No fix dispatched yet.

## T062 — Prevent secret disclosure and metadata-only inspection
- Latest authority: DATA068/CORE069–071 parent receipts, DOC073/parent-final-acceptance.json, MEM072/parent-r1-prepared.json; historical paragraphs below are preserved, not current active instructions.
- Status: VERIFIED — bounded two guard scripts and default-home registration HM055; MEM072 local download false-positive remains disclosed.
- Scope: exactly2production scripts block_secret_exposure.py and safe_secret_probe.py, synthetic tests, staged Hermes hook deployment after CodexQA; preserve domain guard/approvals. Codex also updates sensitive-read workflow.
- Acceptance: pre-execution block of dangerous env/config disclosure; helper only presence/type/length; no raw values, fragments, hashes or errors echo; helper spoof/chaining failclosed; real hook activation evidence + bounded threat-model limits.
- Owner: Codex plan/QA; Hermes AI-box file-only implementation process66480/session20261018_022217_f03a78. No writer overlap. Key previously exposed retired per user, do not re-request it.

18/10 Codex superseding review: T061 VERIFIED at bounded actualgraph/in-processMCP gate(E083), wholeT049/E2E remainsopen. T062F2 corrected,45tests+39parentchecks+5F2casespass; default-home hook installed and registered after explicit user first-use consent, 5/5 actual callback probes pass(E086). Existing long-lived gateways/profile overrides not verified. T051offline120pass does notacceptactualexport: QA-PROVIDER-CLI-02 obsolete exportsubcommand confirmed; runtimeisolation unproven. T057127tests pass but parentpolicy-before-fetchstillfails(5/6probespass); no livefetch/importacceptance. QA-DATA-01bindingfix retained after24tests, no signature refactor required. E081edge-storageinterpretationincorrect; recount/report using directedpattern/countDISTINCTr mandatory before scientific use.

18/10 continuation E087/E088: T049 request boundary reproduced independently: source_scope discarded/currentdistrict mandatory; AI059 scoped implementation plan prepared, not dispatched. T060 engine/tool fix now independently reverified actualHTTP4/4 car/foot bothdirections after fresh processownership/hashpreflight. Planner travel-mode propagation stillopen; not fullintegration. CR057 native child currently supervises narrow social orchestration gate correction; RS058 memory/harness research and DOC056 report refresh parallel with disjoint paths. Wait release/independentQA before acceptance.

18/10 E089 supersedes social pending-gate wording above: CR057 terminal/released; narrow reuse orchestration fix accepted after141childindependent socialtests, root6/6probes and152acquisitionregressions. T057/T058 remain IN_PROGRESS for actualcapture/socket/T050. RS058 research proposal accepted after parent review, now4comparators includingMastra, runtimeP2stilldeferred. DOC056 finaleditorial awaitsrelease. Currentconsolidatedhandoff HANDOFF_CODEX_CURRENT_2026-10-18.md; nofullgoalacceptance.

EXP078current: contract14/14+freeze11/11pass, remainingprovider/intervention/nativeexport/lifecycle+testfixtures in R2handle87500. No primaryH2/H3yet; preservephase3/E2/adversarial/H1pending/phase5scope.

**Critical remaining core integration22:04:** CORE079prepared-plan.md connects existingworkingmemory to typeditineraryHTTP; current/chatdoesnotreturnplanning, current/generate_itinerarydoesnotreadworkinghistory. CodexEXP078assumptiondisproved; no nativeH3executionuntilappbridgeQA+pre-runamend/collectoradapt/newfreeze. Notphase5newmemory.

**Currentwriter22:12:** CORE079handle37775/sessionses_eb070065affezEgIMtel3NtxT4 đangnối existingmemoryvàtypedHTTPplan,45readonlybindingschecked. R2terminal/partial44QA+12pass4fail; khôngrestartR2haychạyscore/chatthiếuplan. Xemcheckpoint 2026-10-18-core079-memory-bridge-active.md.

**Latest22:41:** CORE079offlineaccepted15/10/357pass+47protected;37775terminal0/officialidle, no currentwriter. Next boundednativepilot per CORE079/parent-native-pilot-plan.json, thenH3amend/collectoradapt/4testcauses/newfreeze→phase3. Native/primaryresults notyetverified. Checkpoint 2026-10-18-core079-offline-accepted-native-pilot-next.md.

**Latest CORE079/EXP080:** Pilot85489 terminalexit1: disabled bypass/typed route passed,1/3cells; short-term prep503/unavailable then stop,2missing,3API/3knownCLIattempts. Cleanup19601/2freshclosed/sourcehashesmatch; no quota/auth diagnosis or active-memory native acceptance. Exact-once permission consumed, no rerun. Protocolv5 prep/chat→score/generate_itinerary amended before primary; old design/baseline preserved/fullfreezehold. EXP08037269/session ses_eb0336ac3ffe5n9qgmY4jvwdD2 implements fixed Codex plan offline only/1200s budget. Collector acceptance pending. Checkpoint 2026-10-18-core079-partial-native-exp080-active.md; report360static/93refs. Remaining nativeactive-memory/collectorQA/fullfreeze→H2/H3/E2/system/adversarial→phase4, fullSG/AC intact.

**19/10 current:** EXP080 source accepted offline:11root/22focused/6export/11freeze/20evaluator pass,46bindings/3AST unchanged;candidateunfrozen. Exactsessioninactive/currentserver10672/old28328absent;no historicalstop-time claim. Agentreport/logmissing disclosed. CORE081 remaining-memory batch preparedmax4API/2fakecases/0realcalls/no newpermission. Freshengineportsdown; CORE082Hermes65000/session20261019_140404_45e62d,budget600s restoring verifiedcachedexistingengines only,no download/import/rebuild/graphwrites/modelAPI. Nativeactive-memory/fullfreeze stillgatephase3; checkpoint2026-10-19-exp080-offline-accepted.md/report364static95refs. FullSG/AC/H1/phase5scope unchanged.

## QA-SPATIAL-PERF-097 — prefilter5km chậm hơn trong cohort đã chốt
- Priority:P1, Status:OBSERVED/OPEN, Parent:SG08/SG13/AC04/AC07.
- TIM097n5/arm:median117,6202→150,1539s (+27,66%); fullacceptedcount7091961match. SharedhostRAM97%/no isolation; nguyên nhân chưa xác định.
- Không claim prefilter luôn nhanh; không đổi query/threshold hoặc rerun cohort để cải thiện kết quả. Khảo sát instrumentation/queryplan trên process/DB riêng sau phép đo, giữ baseline/query/source/proof versions và không gọi PROFILEhits là scalarfunctioncalls.

## Current UI delivery tasks — Codex20/10

| ID | Title | Parent / origin | Priority | Status | Dependencies | Description / acceptance | Evidence | Blocker |
|---|---|---|---|---|---|---|---|---|
| UI127 | Chatbot + HCMC3D | demo/user20Oct | P0 | accepted bounded | existing native APIs | Chat first, real coordinates/red pins/safe cards; backend unchanged | UI-127/parent-ui-static-review.json | worker final report absent; Codex QA used |
| UI129 | Typed single-flight | UI127/independent QA | P0 | done | UI127 | Block duplicate POST during source/mode switch;18 race assertions pass | UI-127/parent-busy-race-final.json; UI-129/parent-idle.json | none in tested scope |
| B131 | Live two-button journey | demo/user priority | P0 | PARTIAL terminal | UI127/129/native stack | Chat+typed+source/route/times+two markers passed; click not observed | BROWSER-131/independent-live-review.json | pin/popup observation timeout, cause unknown |
| B133 | Pin interaction isolation | B131/Codex QA | P0 | done, fixture only | B131 terminal | Actual browser click pin/card, no extra model POST | BROWSER-133/result.json; pin-card.png | does not replace live-click evidence |
| DOC132 | Current report + checkpoint | phase4/user checkpoint | P1 | delivered | bounded receipts | Concise VI report distinguishes live/fixture/historical outcomes | DOC-132/applied.json; checkpoints/2026-10-20-ui-demo-live-partial.md | originalgoal not certified complete |

## UI fixes — current bounded delivery

| ID | Title | Parent / origin | Priority | Status | Dependencies | Description / acceptance | Evidence | Blocker |
|---|---|---|---|---|---|---|---|---|
| UI135 | Preserve/fit map pins | demo/B134QA | P0 | accepted bounded | UI129 | Keep MapLibre classes and fit above overlay | UI-135/parent-source-scope.json; BROWSER-136/result.json | no full live rerun |
| UI137 | Readable mobile POI card | demo/B136visualQA | P0 | accepted bounded | UI135 | Inline card <=620px, desktop popup, full facts/close visible | UI-137/parent-source-scope.json; BROWSER-138/result.json | six fixture layouts, not universal/live proof |
| DOC139 | Report/current checkpoint sync | phase4/user checkpoint | P1 | delivered | UI137/B138 | Preserve historical PARTIAL; distinguish fixture/live | DOC-139/applied.json; checkpoints/2026-10-20-ui-pin-mobile-fixed.md | fullgoal incomplete |

## DOC147 — công việc mới đã kiểm

| ID | Title | Parent goal | Origin | Priority | Status | Dependencies | Description | Acceptance | Evidence | Blocker |
|---|---|---|---|---|---|---|---|---|---|---|
| AUD140 | 31SG/AC và delta live | master | Codex audit | P1 | VERIFIED | master+LIVE143 | Đối chiếu nguyên văn, giữ gaps | 31mục và delta có giới hạn | AUD-140/current-gap-map.json; live143-requirement-delta.json | không phải toàn master hoàn tất |
| REF141 | Nguồn nền tảng/L07 | thesis | Codex audit | P1 | VERIFIED | nguồn official/cache | Audit metadata/phương pháp, giữ nguồn inaccessible | Không claim toàn PDF đọc mới | REF-141/l07-methodology-review.json; docs/research/FOUNDATION_CITATION_AUDIT_2026-10-20_VI.md | full bibliography/thesis còn thiếu |
| REF142 | 136claim Markdown | thesis | parallel audit | P1 | VERIFIED | 12Markdown/receipts | Lập locator/status/omission | 189metadata checks;13cụm cần đồng bộ | REF-142/parent-review.json; manuscript-claim-audit.json | chưa semantic QA toàn claim/DOCX/PDF |
| LIVE143 | Demo API/JS thật | demo | user one-shot | P0 | VERIFIED | UI137/native | Chat→lịch→ghim/chọn POI | 31checks;không full-card visual proof | LIVE-143/result.json; independent-result-review.json | một hành trình, không toàn validity |
| B144 | Tái hiện popup bị che | demo | LIVE143 image review | P0 | VERIFIED | same POI pair | Giữ testfailure để chứng minh lỗi | camera settled/fullcard oracle fails | BROWSER-144/result.json | fixture không live |
| UI145 | Sửa popup layer | demo | B144 | P0 | VERIFIED | Go coding/B146 | Một CSSrule, JSidentical | B146 fullcard paint/readability pass | UI-145/parent-source-scope.json; BROWSER-146/independent-result-review.json | fixture visual riêng |
| DOC147 | Báo cáo phase4/checkpoint | four phases | Codex final editorial | P1 | VERIFIED | bounded evidence | Đồng bộ trạng thái/giới hạn | JSON/HTML/refs/JS match; độc lập QA | DOC-147/applied.json; checkpoints/2026-10-20-live143-and-thesis-audit.md | wholegoal vẫn IN_PROGRESS |

## DEP148/149 — tiếp tục SG16/T016

| ID | Title | Parent goal | Origin | Priority | Status | Dependencies | Description | Acceptance | Evidence | Blocker |
|---|---|---|---|---|---|---|---|---|---|---|
| DEP148 | Compose readiness gap review | SG16/T016 | current-state audit | P1 | VERIFIED | tracked definitions | Compare approved Jev/Go target with integration | source-backed9groups; no runtime proof | DEP-148/parent-findings.json; independent-gap-review.json | Compose remains unverified |
| DEP149 | Build-context secret exclusions | SG16/T016 | DEP148 risk | P0 before build | READY | new scoped host permission | OpenCode modifies only .dockerignore + return | fake sensitive paths excluded; source/templates eligible | DEP-149/brief.md | host permission pending; NOT DISPATCHED |

## REF150 — binary content validation

- ID: REF150
- Title: Read-only Word/PDF actual-content audit
- Parent Goal: SG18/AC09/AC10
- Origin: REF142 binary coverage gap
- Priority: P1
- Status: VERIFIED (bounded audit, not final thesis)
- Dependencies: current binary artifacts/REF142
- Description: Open current Word/PDF, compare text/images/assembly inputs and locate obsolete claims.
- Acceptance Criteria: Actual binary hashes stable, paragraph/page locators, dated findings, no manuscript writing or full-layout claim.
- Evidence: REF-150/parent-review.json; BINARY_AUDIT_VI.md; checkpoints/2026-10-20-binary-thesis-audit-ref150.md
- Blocker: Writing choice and full manuscript/source/format finalization remain; DEP149 separate permission pending.

## CHAT153 — user deferred chatbot orchestration

- ID: CHAT153
- Title: Chatbot tự nhận yêu cầu lập lịch, hỏi thông tin còn thiếu rồi gọi planner
- Parent Goal: Core assistant UX
- Origin: User20Oct chọn làm1/2/4 trước, giữ3backlog
- Priority: P1, deferred by user
- Status: DISCOVERED
- Dependencies: DEMO152 accepted; user chọn mở item3
- Description: Tách ý định tìm kiếm/gợi ý/lập lịch và nối chat→typedplanner sau xác nhận đủ tham số.
- Acceptance Criteria: Hội thoại tạo lịch có kiểm chứng mà không bắt buộc nút riêng, hỏi lại thay vì đoán, giữ scope/memory/mode.
- Evidence: user instruction; DEMO-152/brief.md explicit exclusion
- Blocker: Không triển khai trong gói1/2/4.
