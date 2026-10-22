# Checkpoint Codex — TIM097 đang đo timing

20/10/2026. Lượt trước là tiến triển: TIM096 đã nhận offline137ca riêng,273preservation. Lượt này đã chốt release và khởi chạy một cohort mới đúng mục tiêu E2, không chạy lại correctness hoặc điền ô cũ.

- Release `handoffs/TIM-097/release.json`,26publicpins, manifest `e2-timing-execution.frozen.json`; kiểm độc lập50điều kiện/6negativegates đạt. Một handshake+SHOWVERSION chỉ đọc: engine sẵn sàng3.13.2. Runtime/input/query/proof/source/hostconditions đều pin. Chưa có kết quả timing được nghiệm thu ở thời điểm dispatch.
- **Unified exec handle95078** đang được theo dõi; không launch/resume lại. Command/moduleflags đóng băng, đường dẫn Windows/backslash trong release và literalforwardslash của PowerShell được lưu riêng ở primary-dispatch.json; so path bằng canonical, flags bằng literal. Sourcekhôngđổi.
- Output mới `docs/experiments/primary_20261018/runs/e2-tim097-timing/result.json`.36cell=6warmup+30measured,1/3/5km,n5/arm; worker/supervisor7200s+cleanup<=10s. Querymax120s,0model/Jev/writes,oneattempt/no retry/recovery/fallback. Nếu lỗi/quyền/timeout thì giữ bằng chứng và cellmissing, không sửa tiêu chí.
- Proof staticE2093 dùng đúng archives; fresh fullPOIprojection trước timing. Countmismatch phải dừng phần sau. Reusedcorrectness không phải rawset comparison mới/snapshotisolated proof; metricengine khácPython6371,physicalenginecount còn thiếu. Version hiện tại không hồi tố buildE2093.
- Quan sát journal bằng `handoffs/TIM-097/parent_progress.py`; đây là completedprefix không chứng minh processalive. Kiểm liveness bằng đúnghandle95078. Khi terminal lưu exactexit/supervisor/childcleanup, verify pins và coverage; không chạy verifier prelaunch sau khioutputđãtạo.
- Không thực hiện enginebenchmark/systemwrites/recovery cạnh tranh trong phép đo. Sau cohort: instrumentation engine thực/disposableDBsemantics/system/ba nhóm đối kháng theo scope. H2/H3/E2093 bất biến. Phase4report rồi chờ user chọnH1/writing; phase5extensions hoãn.

Không mark goalcomplete/blocked. Nếu phiên bị cắt, tiếp tục quan sát đúnghandle; observationtimeout không phải terminal. Handle bị missing cần đối chiếu supervisor/journal/output đúng task, không suy từ lock hoặc restart.

Quan sát08:05:08UTC: đúnghandle95078 vẫnrunning; journalprefixverified có1warmupbaseline1km thành công,0measured/0failed; projectionpassed,finalresultchưacó. Đây không phải nghiệm thu terminal. QA báo cáo421checks/122source-reference đạt; khôngbrowserproofmới.

Bổ sung08:09:55UTC: handle95078 được poll và vẫnrunning; journal4/36cell=2warmup+2measuredsuccess,0failed. Đã cập nhật6dòngSG/4dòngAC trước đó còn trạng thái H2/H3chưa chạy. Post-terminal reviewer parent_review_primary.py đã viết/parse, chỉ được chạy sau primary-terminal.json; chưa chạy/không giả kết quả. ENGINE_INSTRUMENTATION_NOTES_VI.md phân biệt PROFILEoperatorpulls với scalarfunctioncalls và chốt hướng khảo sát process dùng riêng sau timing; GitHubsource cachemiss không là sourceverification. Không có enginequery/cài công cụ từ nghiên cứu này.

Mốc08:22:19UTC: vòng quan sát6lần trên đúnghandle95078 xác nhận vẫnrunning;13/36cell=3warmup+10measuredsuccess,0failed. Nhóm1km đủ5measured/arm và2warmup; tất cả12cell accepted_pairs=740159. Lưu milestone-1km-observed.json với seq16/bodyhash làm mốc prefix bất biến, không pin hash toàn journal đang append. Chưa kết luận so sánh hoặc nghiệm thu terminal;3km warmupbaseline đãpass. Tiếp chỉ pollhandle95078/đọcprefix; không rerun verifier prelaunch, không launch/resume mới.

Mốc08:39:17UTC: vòng quan sát đúnghandle95078 xác nhận vẫnrunning;24/36cell=4warmup+20measuredsuccess,0failed. Nhóm3km đủ5measured/arm và2warmup; tất cả12cell accepted_pairs=3678397. milestone-3km-observed.json giữ seq/bodyhash prefix;26publicpins không đổi. Còn nhóm5km; chưa nghiệm thu terminal/toàncohort, không retry/resume.
