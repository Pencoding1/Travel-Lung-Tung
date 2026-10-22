# Checkpoint EXP089 — Codex, 20/10/2026

**Bộ thu E2 chỉ đọc đã được nhận offline. Chưa chạy phép đo Memgraph thật.**

Authority: `docs/project/handoffs/EXP-089/parent-final-acceptance.json`, decision `ACCEPTED_OFFLINE_READ_ONLY_E2_COLLECTOR_NOT_LIVE_E2`.

Báo cáo tương tác đã đồng bộ:384staticchecks/105source references đạt, không có visual/browser QA mới. Checkpoint và10artifact công khai đã mirror tại `E:/Agent_Artifact/TVLT_2026/2026-10-20/codex-exp089-checkpoint/`.

## Đã làm

- OpenCode `aibox/ds/deepseek-flash` triển khai đúng kế hoạch Codex: package mới `benchmarks/spatial_live/`, test mới `tests/spatial_live/test_runner.py`. Không đổi production source, dữ liệu/protocol hoặc bản H2/H3.
- Lấy đầy đủ6367POI từ inputhash37340a80…; kế hoạch có20.266.161cặp không thứ tự,50batch128anchors, bán kính1/3/5km. Dữ liệu nguồn giữ nguyên, không coi nhãn vùng là ranh giới hành chính hiện nay.
- So tập cặp thật trong RAM từng batch; giữ FN/FP/hash/missing, không dùng count bằng nhau để kết luận tập bằng nhau.
- Timing dùng truy vấn **count-only**:1warm-up+5measured mỗi nhánh/bán kính, tổng36ô (30đo/6warm-up). Cùng point.distance/prefilter đã pin; chưa có thời gian đo thật.
- Lỗi xác thực/quyền có mã nhận diện được sẽ chặn toàn bộ truy vấn phụ thuộc còn lại; lỗi metadata không hỗ trợ được ghi là gap. Không đoán từ thông điệp lỗi tự do hoặc in thông tin nhạy cảm.
- Codex chạy lại toàn bộ54ca hiện tại và11ca độc lập dùng fake fixture trước sửa: **65passed/2,04s**.137điều kiện source/input/binding đạt; sohash4file với báo cáo executor.
- `FREEZE-088/verify_release.py` vẫn exit0:122public files/34packages/14bundleartifacts không đổi. H2/H3 release giữ nguyên; không tạo primary outcome.

## Hai lỗi đã phát hiện và sửa, không xóa bằng chứng cũ

Ban đầu31test pass nhưng không phát hiện timing chuyển toàn bộpair rows về máy; và authdeny tại indexmetadata vẫn bị nuốt thành gap rồi chạy45query giả lập tiếp. Codex tái hiện trong `parent-initial-findings.json`, giao R1 đúng hai lỗi. Timingcount và terminaldeny đã có QA độc lập; không làm nhẹ tiêu chí để nhận.

## Worker đã dừng

Original handle84950 không còn tại lần kiểm20/10; exact-sessionwait exit0/emptybody, không khẳng định naturalCLIexit cũ. Session được tái dùng có chủ đích: `ses_eacae6e2affeXnpm1rScJpQfKD`.

R1handle50476 đã bị parent interrupt theo budget300s; API trảinterrupted=true, exact-sessionwait exit0/emptybody, shellclientexit1. Có result.json/report-vi.md/tests.txt và mã/test; sourcehashes khớp. Không active-list, không claim continuity của toàn bộ server hoặc tự nhiên kết thúc đầy đủ. **Không restart/retry worker này chỉ vì clientexit1**; Codex đã nhận code bằng QA độc lập.

Executive:
`E:/Agent_Artifact/TVLT_2026/2026-10-20/spatial-collector-exp089-r1/`.
Brief gốc ở ngày19; checkpoint Codex mirror riêng ngày20.

## Còn thiếu trước E2 thật

1. Chốt manifest E2 riêng: input/query/source/runtime/hardware, engine metadata, exact output/commands/budgets. Candidate hiệnfrozen=false; không dùng acceptedoffline để tự mở --execute.
2. Trước batch dài, quyết định/bổ sung cơ chế lưu tiến độ bền hoặc supervisor có phạm vi rõ: code hiện ghi output khi hoàn tất/lỗi được xử lý, không phải journal từng batch chống processloss. Không phục dựng đoạn mất thành đã đo.
3. Budget3600s hiện kiểm giữa query; query đang chạy có timeout120s và có thể kéo wallclock quá mốc3600. Không gọi đây là hard process deadline.
4. Khi được chạy, giữ đủ36ô/mọi missing/failure, không retry lấy kết quả đẹp. Chỉ báo logical candidate/input reduction; không suy ra physical distance evaluation count hoặc tốc độ tốt hơn trước khi đo.
5. Read-only query không chứng minh orientation/duplicate/staleedges/rebuild khi POI di chuyển. DATA068 là evidence riêng; các mutationfixture còn lại chỉ trên DB dùng một lần được duyệt, không sửa graphprimary.

## Đường tiếp theo của toàn dự án

- H2/H3 pre-run release FREEZE088 đã chốt; exactcommands có trong `execution-commands.json`, chưa thực thi/chưa tự suy quyền từ pilot một lần.
- Demo UI đã mở theo yêu cầu19/10. Trạng thái mở là snapshot cũ; chưa kiểm lại runtime ngày20. Không tự stop/restart hoặc giả định người dùng đã kết thúc; tránh collection cạnh tranh khi demo còn dùng.
- Sau kiểm điều kiện/quyền thực thi khi cần, chạy H2/H3 có kiểm soát; song song về kế hoạch vẫn giữ E2/system/3nhóm đối kháng đủscope, không thay bằng fake tests.
- Phase4 báo cáo tiếng Việt; H1 hiện0người, chờ user chọn H1 hoặc viết luận án. Crawler/social/travelagency/grow-with-user/harness mới giữ phase5 Finalizing. Goal vẫn active/incomplete, chưa đạt toànSG01–SG19/AC01–AC12.
