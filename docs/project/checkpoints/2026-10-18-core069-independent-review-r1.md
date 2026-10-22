# Checkpoint — CORE069 root QA và correction R1

Codex chủ trì /plan, kiểm chứng và nghiệm thu; OpenCode coding theo brief.18/10/2026. Goal ACTIVE/INCOMPLETE.

## Trạng thái thực

- OriginalCORE069 handle **50380 terminal1**, Codex chủ động interrupt trước observednative/modellaunch vì launcher OS-only allowlist làm rơi guard carriers. Không coi đây là executorcomplete, không poll/restart50380.
- **R1 handle52111 ACTIVE**, reuse exactsession **ses_eb201dea0ffe88oB4UGIXhOmrr**, exactmodel **aibox/ds/deepseek-flash**. Plan `handoffs/CORE-069/revision-1.md` đã chốt trước dispatch, đi kèm brief gốc. Log `E:/Agent_Artifact/TVLT_2026/2026-10-18/core-flow-integration/events-r1.log`.
- Một source writer. Đã giữ `before-r1/`, sourceSHAmanifest, initialcontext/guardfailures. Không sửa parent/beforefiles hoặc source chồng R1. Không chạy model chồng lên livecaps trong task.

## Bằng chứng mới

1. Root `parent_context_qa.py` đã chạy actualASGI/schema/history với fakeJev/model/MCP: **7/8 nhóm đạt**, không phải model/tool/network thật. Schema13checks, sourceoverride/mixedresults/details substitution/actualfoot afterwrongcar/foreignroute/sourcechange memory đềuđạt. **Opaque upstream error detail lọt vào model** ởlegacy path: regression reproduced, không chỉphỏngđoán từdiff. Rawfailure giữ `parent-context-results-before-r1.json`.
2. Actual `child_environment` + hermeticsyntheticmapping: **cả2guardcarriers bịdrop**, noPopen/noCLI/model. `parent-guard-carrier-gap.json`. Không biết/không cần biết actualhostcarrier values để nhận lỗi. Initialprobe có đọc originalcarrier nội bộ chỉ để restoration, không in; scopeclaim đã sửa và giữ `parent-guard-carrier-gap-initial.json`, cleanproof thay bằng moduledependencyfixture, không đọc hostenv.
3. Logmetadataaudit trướcinterrupt không tìm thấy native-start/applicationendpoint commands; defaultcorestatefile absent. Không suy rộng thành toànmáy không cóservicekhác. SourceUI/corehelper đãtạo nhưng chưa acceptance/nativeE2E.
4. RootASGI lầnđầu kẹt Windows sandbox ởasyncio.socketpair, đã interrupt97669terminal1; bounded20s diagnostic35694 shellterminal0/probeexit1 xácnhậnstack ởsocket.accept/_fallback_socketpair. Hostapprovedrun sauđó1.813s tạo actual7/8result. Không dùng timeout này làm appbug hoặc bypassguard.

## R1 bắt buộc

Giữ guardcarriers byteexact và chặn serviceoverrides trướcPopen; không clear/mask actualguard. Bỏarbitraryerror detail/codeecho, dùng allowlist/constantreason. Typedcar/foot cần per-requestmodelcontext rõ đểUIselection không bịmodeldefault/profilechekhuất. Saufocusedtests/nativefakegates mớiactualdiagnostics theooriginalcaps2itinerary+1chat/12generationattempts/Jev3; bảo toàn errors/identity/usageunknown và trướclaunch freshownedhealth. Hoànthành originalnativeconnector/HTTP/catalog/UIflow, không thu hẹp thànhunit-onlysuccess.

## Tiếp theo

Poll52111; sauterminal đọcreport/result/commands/diff vàactualstages, chạyrootQA độc lập +guardhermeticprobe và kiểmprofile/history/runtime. Khônglặp broadrepoaudit. SourceS2DATA068đãnhận, graph6367POI/3678397NEAR_BY/ownedPID9534 giữ nguyên; khôngreimport. Chỉfreezephase2 sauS1–S6 đủ; crawler/grow-with-userphase5Finalizing, H1/thesischờuserchoicephase4.

## Qualification và probe bổ sung trong lúc R1 chạy

- Terminal1 của50380 chứng minh **CLI command đã dừng**; không có independent session-server abort/status receipt. Không dùng Ctrl+C/CLIexit làm bằng chứng mọi server-side work đã hủy. R1 reuse đúngsession, chỉ theo dõi stream/handle52111 hiện tại; không mở phiên thứ ba. Timestamps file không đủ chứng minh worker sống/chết. Khi cần hủy tiếp, phải kiểm cơ chế abort/status chính thức và actual owned worker, không suy từ clientexit.
- `parent_guard_qa.py` đã chuẩn bị/syntaxchecked, CHƯA CHẠY trên finalR1. Nó dùng explicit syntheticbase + forbiddenhostenv/Popenstubs để kiểm8case preservation/override, không đọc hostguard. `parent_context_qa.py` tăng độ phủ caseopaqueerror: cảcode/detail chứa cùngcanary, phải khôngecho; initial7/8receipt giữ nguyên.
- Source reviewR1 thấy guardpreservation seam, constant-error mapping và per-requestmodecontext đã có. Executor có report63testpass trongstream nhưng chưa terminal/report/nativeproof; không acceptance. Focused regression đang tiếp tục.
