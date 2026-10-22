# Checkpoint — CORE069 ownership correction R2

Codex chủ trì plan/QA/acceptance,18/10/2026. Goal ACTIVE/INCOMPLETE. Không nhận CORE069 hoặc phase2 theo unitpass.

## Dừng worker đúng cách

- R1CLIhandle52111 **terminal1** sauCtrl+C, nhưngofficialAPI còn thấytargetactive. Điều này xác nhậnCLIexit **không phải** workerstopproof.
- Rootđốichiếu ownsessionID qua normalCLIapi, dùngschema [OpenCodeV2](https://dev.opencode.ai/v2/openapi.json) đểtìm đúng `session.interrupt`/`experimental.session.wait`/`session.active`, không đọcglobalcredentials. Guessed `/abort` và`/status` không có trongschema; attempts trước thấtbại vàkhôngđược dùnglàmproof.
- **parent-r1-official-interrupt.json:** cùngserverPID28328/version2.0.32, ownsessionactive trước, interruptresume=false trảinterruptedtrue, waitidleexit0, targetabsent sau. **Worker confirmedinactive trước R2**. Sanitizedownsessionexport còn cóidlemessage, khôngrawtranscriptđược lưu/in.

## Lỗi mới đã chứng minh

- `parent-ownership-gap.json` actualhelper +hermeticmetadata: freshforeignlistener đượcadopt vàbịcleanupnhắm signal; `pid_termination_simulation_count=3`. **Không actualOSsignal/socket/model/envoperation** trongprobe. ProofbindhelperSHA854107c5520397a0ac390fce65eb227f901dadcf9e86215113c52183cfd78049.
- R1thêm `_adopt_listener` vìWindowsvenvpythonredirector. Thờigian/porttừngtrống/alive khôngchứngminhchild, barePIDcleanupcũngkhôngchốngPIDreuse. Khôngapprove lifecycleđó.
- Rootread-onlyruntimeflags: Pythonisolated0/ignoreenvironment0; khôngđổilỗi chointerpreterisolation.
- `parent-r2-runtime-readiness.json`: actualbasePython **C:/Python314/python.exe**,3.14.0/SHA467014615a5255aca450ae88100dd2caf887da87657f00e3c2171ec44a685aec; primaryMCPvenvsitepath đãghi.

## Native tiến trình và diagnostic đã quan sát

- R1đãstartactualservices: MCP20960/launcher17624/19101, AI33912/launcher25904/19102; statefile hiệncó. RootCIMmetadata exactPIDs kiểm parent/image/commandtail đềutrue; actualcreationbinding vẫnphải freshverify trước stop. **Rootkhônggọiunsafehelpercleanup hoặcsignal**.
- `parent-r1-ai-log-counts.json`:1POSTgenerate_itineraryHTTP200,0TypesafeHTTPevents trênownAIlogs. Không cóbody/providermetadata đủ đểgọi thànhcông hoặcchấm thínghiệm. Khôngdeclare0appcalls nữa; reserveprior≤1mainattempt theoactualsingle-generationpath/defaultCLIattempt1. Rawownsessionexport chỉ xửlýtrongRAM bằngwhitelistprojection; khôngrawtranscript/keyđược lưu/in.
- NativefakeR1 có1mainproviderHTTP/0auxobserved,16checks báo true;90/272/159/403/47suites báo đạt. Root8launcher+6errorboundary đạt trênhashriêng; fullASGI/currentfinalsource/native gates vẫnpending.

## R2 đang chạy

- **Handle12839 ACTIVE**, exactsession **ses_eb201dea0ffe88oB4UGIXhOmrr**, model **aibox/ds/deepseek-flash**. Newplan `handoffs/CORE-069/revision-2.md` được Codex chốt trướcdispatch, khôngexecutor replan. Log `E:/Agent_Artifact/TVLT_2026/2026-10-18/core-flow-integration/events-r2.log`.
- Mộtwriter chohelper/settings/README/targettests; main/planner/provider/memoryread-only. Giữbefore-r2sourcebaseline vàlegacyidentitymetadata. **Khôngpoll/restart50380 hoặc52111**; cả2CLIterminal, sessionđãofficialidle trướcR2.
- Chọn directbaseinterpreter +fixedbootstrap/primaryMCP1.26paths để PIDlistenerđúngPopen, khôngadopt. Ownership/cleanup cầnPID+creation+image/argv/portbinding, PIDreuse/foreign/missingproof=>0signals. Reconcileold2services bằngfreshproof, khôngblindkill.
- Wireprocess-onlysettings thật trướcglobaldbsettingsinit; defaultlegacygiữ nguyên. Nativehelperconfiglocal17687+blankuser/password, nosecretfilecopy/noshim.
- BudgetR2bổsung2itinerarycar/foot+1generictypedfootchat đểbùprioruncertifiedrequest; max7additionalmainattempts+priorreserve1≤8 dướicap12, CLIattempt1explicit. Ghiledgertrướcrequest, actualresponse/model/usage/route/source, failures khôngbỏ. Không gọi “3requesttổng”; prior1requestvẫngiữ.

## QA sau R2

Officialworkeridle/release +actualownedchildreconciliation; sourcehashes, rootASGI8groups vàguard8/error6cầnrechecknếubytesđổi, newownershipnegativecases bắt buộc. Actualproductionconnector/SSE/HTTP/UI/source/route/modelproof, process-onlywiring/S5profile-auth/H3-readiness. Khôngmodel/thesisprimarytrials trướcS1–S6freeze; crawler/grow-with-userphase5Finalizing. Rootreportinteractive vẫnpendingcoreflow, chưangụytrangHTTP200làendtoendpass.
