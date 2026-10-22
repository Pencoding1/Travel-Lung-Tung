# Checkpoint — kiểm tra độc lập hai ranh giới R1

Codex18/10/2026. Goal ACTIVE/INCOMPLETE; CORE069 chưa nghiệm thu toàn gói.

## Bằng chứng đã chạy

- `CORE-069/parent_guard_qa.py` → **8/8case đạt,0spawnattempt**. Actualchild_environment với explicitsyntheticbase; blockedhostenvstub, không đọc env thật, không spawn/model. Nonempty/emptycarriers giữ byteexact, override bị từ chối. Sourcehelper ổn định trongprobe, SHA256 **1cbd35de298365ebb596473c023300ff42b15246a0b375cd5a39cf929f2712b4** tại lần kiểm. Nếuhelperđổi sauđó, rootphải kiểm lại thay vì dùng receipt cũ.
- `parent_error_payload_qa.py` → **6/6case đạt**, actualpurefunction `_tool_failure_payload`; tùyýcode/detail, scopeflag giả/unknowncode, knowncodekhôngflag, protocolfault và oversizedcode không echo opaquevalue. Có hash3sourcefiles/trước-sau ổn định trong `parent-error-payload-results.json`. Đây là boundaryproof, **chưa thay fullASGI/history regression sau finalrelease**.
- InitialrootASGI7/8failure giữ nguyên; parent_context_qa hiện kiểm opaquevalue ởcảcode/detail. Probechỉrunhostapproved sauR1release vì Windowsrestrictedsandbox từngkẹt asyncio.socketpair. Không coiđó làappbug/guarddenial.

## Executor R1 hiện tại

- **Livehandle52111**, samecapturedsession `ses_eb201dea0ffe88oB4UGIXhOmrr`; modelaibox/ds/deepseek-flash. Không restart hoặc sourcewritechồng. Original50380CLIterminal1; worker/serverabort chưa có độc lậpreceipt, không suy từCtrl+C. Hiện chỉ theo dõi R1stream/handle, không mở session khác.
- Streamreportedsuites90pass,272pass,159pass,403pass,47pass sauca89pass/1fail trướcđó; chưa cộng thànhunique total hoặc gọirootverified trước khi mapcommands/assertions. Testfailuremode-historyđã có lần90pass sau sửa; giữ kết quả thấtbại lịch sử.
- Nativefakeartifact: actualinstalledCLI, oneactualrun/export, **1providerHTTPrequest chính/0auxobserved**,16checks báo true. Đã đọc sourceprobe: taskfakeprovider/dummykey, ambientguardrefusal giữ, không xóa carriers. Không paidmodel/pluginisolation/totalbilling claim; rootindependentnative rerun cânnhắc saurelease, không chạyrootartifactchồngoutputexecutor.
- Nativelaunch đang xử lý import **travel_shared**; có unitpass không thay actualconnector/SSE/HTTP/client proof. Tại lầnkiểm defaultcorestatefilechưa có, không lấyđó làm chứng minhkhôngcóchild/orphan. Sauterminal phảireconcile ownedPID/start/ports/cleanup từ actualmetadata.

## Những điểm phải chốt khi QA bản cuối

1. So sourcehash/securityreceipts với finalbytes; rerun targetnếunguồnđổi, rồi chạy fullparentASGI8groups với fakecollaborators và focusedrelevantregressions cần thiết.
2. **Settings wiring:** source review hiện có `MemgraphDB.from_process_env`, nhưng `db_settings=MemgraphDB()` vẫn là default vàlauncher trướcđó chỉ fixedhost/port. Cần chứng minh native chọn đúngprocess-onlyconfig đãyêu cầu; mộtclassmethod test riêng không chứng minhproductionconnector đã dùng nó. Khôngshims/configdefault/globalenv/key inspection.
3. Actualproductionconnector +MCP SSE/HTTP +full6367graph +GraphHopper car/foot vàactualmodel/Jev diagnostics theo caps brief. Kiểm typedmode trongprompt/request vàactualroute, sourceID từngstop, unknownprice/hours, modelrequested/observed/usage/errors. Không dùngfakecase thayactualAPI.
4. Existingmemory/profile/JWT/isolation/H3-readiness vẫn cần gate phù hợp; genericUIanonymouskhông tự chứng minh durableprofile/backendauth flow. Không thêmgrow-with-user.
5. Code/data/config/scenarios chưafreeze; primaryH2/H3 chưachạy. SauS1–S6đủ, cậpnhậtarchitecture/report/thửnghiệm theoPHASE3_READINESS_AFTER_DATA068.md; collectorCLI V1 cũ không được chạyblind. Crawler/grow-with-user/nguồnmới giữphase5Finalizing; H1/thesischờuserchoicephase4.
