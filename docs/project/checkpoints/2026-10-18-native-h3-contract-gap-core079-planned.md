# Checkpoint — Codex: phát hiện sai giả định H3, chặn chạy trước khi có dữ liệu

18/10/2026 khoảng22:04. Goal ACTIVE/INCOMPLETE. Lượt này PROGRESS: kiểm chứng Docker/catalog, đối chiếu đủ19SG, sửa tài liệu tiến độ lỗi thời, phát hiện hợp đồngAPI không hỗ trợ H3 đã định, giữ execution gate và lập kế hoạch nối đúng pipeline hiện có.

## Phát hiện trọng yếu phải đọc trước

EXP078/parent-native-api-contract-audit.json bind mainSHA b569918e…: /chat2022–2163 có workingmemory/ReAct/routing nhưng không trả planning.repaired_schedule hoặc gọi typedplanner; /generate_itinerary1851–1881 cùng _generate_itinerary_impl/_run_itinerary/_build_synthesis_prompt không đọc WORKING_MEMORY. Typedrepairedschedule chỉ xuất ở1648; synthesis hiện chỉ có usermega_prompt+longprofile, không shorthistory.

**Đây là sai giả định trong kế hoạch EXP078 do Codex lập.** Không lỗiđượcchứngminh của guard/provider/participant. CORE070chat và CORE071typed itinerary receipts vẫn đúng riêng phạm vi; chúng không chứng minh typedplan+workinghistory chung. Fakebackend tự có planning không là nativeproof. Không gọi model để tạo kết quả chắc chắn thiếuplan, không dùng retrievedIDs/prose để giảselectedIDs.

Giao thức EXPERIMENT_PROTOCOL.md đã thêm executionhold trước mọi primarycalls; bytes trướcnotice giữ ở EXP078/before-endpoint-gap-EXPERIMENT_PROTOCOL.md. Chưa studycode/configfreeze hoặc primaryH2/H3 outcomes. H3scoring chỉ được chạy sau: bridgeappcodeQA + sửa giao thức/endpoint/typedcontrols trướcprimary +adaptcollector/newsourcebaseline/fullfreeze.

## Worker và bước triển khai

EXP078R2handle87500/session ses_eb0856af5ffe9Rz795LwqyP47J vẫn đang hoàn thiện measurementboundaryoffline; không sửaapp/protectedcode hoặc tựđổiendpoint. Budget1200s từ EXP078/prepared-r2.json started_at_utc14:46:35.6544945Z, deadline22:06:35.654Asia/Saigon. Đãsteerđúngsession về contractgap; finalreportphải disclose. Pollđúnghandle, khôngrestarttrùng. Xác minh officialidle/clientterminal trước rootQA. Source chưa nhận.

CORE079/prepared-plan.md đã được Codex chốt, **PREPARED_NOT_DISPATCHED**, chỉ giao sauR2nhảnguồn: nối productionworkingmemory vào HTTP/generate_itinerary bằng session/auth/sourceboundary đang có; truyền context server-side tới synthesis của pipeline/planner/validator hiện có, memoryoffbypassboth, currenttypedconstraintswin, commitgroundedresult/failuresemantics/leaseisolation. Không cần schema mới vì ItineraryRequest đã có session_id. Khôngnewharness/autopreference/growwithuser/crawler. CasesA–F trongplan là acceptance nghĩa cốđịnh. Không thực hiện sourcechanges ngoài plan trước sourcehandoff.

## Những tiến bộ khác được kiểm chứng

- DockerEngine29.2.1/Linux/amd64 kết nối qua versionprobe readonly. T016 oldBLOCKEDDockerunavailable đã đổiIN_PROGRESS; build/Compose/fullworkflow vẫn thiếu, không làverifieddeployment.
- GET/healthz và/travel200. Catalog5s banđầutimeout; followup200/1snapshot5.608s. SourceareaAPI/MCP quét đủ6367records/0corrupt/no truncation, exactscope1483khớpH3; no modelcalls/graphwrites/browserproof.
- SG_REQUIREMENT_STATUS_2026-10-18.md đốichiếu đủ19SG của MASTER_GOAL,22evidencepaths cófile; đó không phải cert nội dung tấtcảrequirement. Originalscopegiữnguyên, scopephase5/H1writingphasesápdụng.
- CURRENT_PROGRESS_2026-10-18.md đã viết lại tiếngViệt từevidencecurrent; staleJevnotimplemented/fullimportmissing/Dockerunavailable/Geminidefault bảncũ archive. Mastergoal/backlog cậpnhật blockerđúng.
- Interactivedocs đã công bố endpointgap/CORE079plan, memorymodulependingintegration; QAstatic348checks/87refs đạt, diagramlogicaltopology giữnguyên, nobrowser/perceptualproof. Root reportQA receipts ở EXP078/parent-static-results.json.

## Bắt buộc tiếp tục toàn bộ scope

1. Finish/release R2 bounded; rootreview remainingidentity/intervention/lifecycle/tests vàprotectedfreezeAST. Passingofflinecollector vẫn không mở nativeH3gate vì contractgap.
2. Giao CORE079fixedplan choOpenCode đúng model AIbox ds/deepseek-flash; core memorybridge→QA→boundednewnativepilot theo policy. Không reuse MEM072script exact-once quyền đã dùng, không bypassguard bằng đổiexecutor.
3. AmendH3 trướcprimary: prep/chat và scoring/generate_itinerary cócommon typedbody/profileconditions/source/date/time/stoplimits/visitduration đượcchốt; modelgeneratingAPIcap33/stagesactualJevmeasured; lifecycle riêng. Adaptcollector/root-reviewedsourcebaseline, giữ olddesign/failures/frozenH2immutable; fullfreeze rồiphase3H2/H3/E2/system/adversarial.
4. Phase4báocáo, chờ userchọnH1 hoặcviếtthesis; H1chưa cóvolunteers. Phase5Finalizing toàncrawler/newharness/growwithuser. Không shrinkSG/AC hoặc tự viếtluậnán sớm.
5. Savecheckpoint sau criticalphase; safeprobe-only secretpresence/type/length, no raw.env/auth/config, noALL/wildcard/globalguardchanges, noreset/clean/commit/push, preserveuserchanges; reportbrowserrefusal khôngworkaround.
