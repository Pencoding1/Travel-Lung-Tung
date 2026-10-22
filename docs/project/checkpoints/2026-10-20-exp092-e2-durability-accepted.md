# Checkpoint Codex — EXP092, bộ thu E2 bền vững đã nhận offline

Ngày20/10/2026. Lượt goal trước là progress: H2 đã thực thi/phân tích; lượt này tiếp tục tiến tới E2, không đổi mục tiêu đầy đủ SG01–SG19/AC01–AC12.

## Kết quả đã kiểm

Codex lập kế hoạch/test/QA, OpenCode dùng `aibox/ds/deepseek-flash` (V4.1 theo người dùng) triển khai. Có journal append-only/hash-chain/fsync, từ chối tái dùng; reader báo tail chưa hoàn tất và từ chối hỏng bản ghi. Lưu từng correctness batch và timing cell đã xong; ghi đĩa ngoài khoảng đo latency của cell. JSON cuối ghi atomic. Query timeout giới hạn theo thời gian còn lại.

Supervisor chạy đúng một child Python, argv cố định/no shell, budget3600s kể cả thời gian tạo process; cleanup tối đa5s terminate+5s kill, chỉ child do task tạo. Lỗi wait/cleanup và ngắt bàn phím có xử lý/bằng chứng. Không chứng minh engine transaction đã hủy tức thì; fsync không bảo đảm mọi lỗi phần cứng. Unit đang chạy khi bị ngắt giữ unknown/missing; không resume hoặc tự tạo kết quả.

- QA đầu của Codex:88pass/3fail, giữ trong `EXP-092/parent-initial-findings.json`. Journal bỏ qua dòng trống, deadline cộng dư thời gian spawn, lỗi wait bỏ cleanup.
- R1 sửa đúng3lỗi; Codex chạy độc lập **99passed in8.49s,exit0**:54test cũ giữ nguyên+21test executor+11Codex EXP089+13Codex EXP092. Không cộng các lượt cũ thành tổng mới.
- **209kiểm tra nguồn/binding đạt**; chỉ8định nghĩa cũ của runner đổi theo scope, không xóa định nghĩa. Query text/hash, thuật toán production,36timingcells/6warmup/30measured,1/3/5km không đổi.
-124tệp public H2091,6tệp primary H3 và13tệp H2/analysis vẫn khớp hash. H2 vẫn120attempted/119provenance+1timeoutgap; H3 vẫn1/15partial.
- Dry-run thật đọc đủ6367POI/20.266.161cặp/50anchorbatches, candidate vẫn unfrozen/reviewpending. **0query engine,0application model experiment** trong gói này. Các fake/dummy subprocess test không phải kết quả khoa học E2.
- Script kiểm binding đầu của Codex hiểu sai key basename H3 thành path repo, dừng trước acceptance; đã sửa prefix H3 run, không sửa dữ liệu/tiêu chí.

## Worker và artifact

Session đúng task: `ses_ea88b6c61ffeudE41irWeeuIvW`. Initialhandle30053 và R1handle17880 đều terminal/clientexit0; exact-session official wait0/empty sau mỗi vòng. Không active-list, không claim server continuity/natural inner termination ngoài chứng cứ đó.

- Kế hoạch: `docs/project/handoffs/EXP-092/prepared-plan.md`, `prepared-plan-r1.md`.
- Nghiệm thu: `EXP-092/parent-final-acceptance.json`.
- Candidate: `EXP-092/full-primary-candidate-plan.json` (chưa freeze).
- Executive: `E:/Agent_Artifact/TVLT_2026/2026-10-20/e2-durability-exp092/`, `e2-durability-exp092-r1/`.
- Log của parent chỉ giữ loại event/sessionID, không raw command/text/diagnostic. Safety của mọi thao tác worker không được tự suy rộng thành audit raw trace; parent dựa trên mã, hash, report và QA độc lập.

## Phiên tiếp phải hoàn thành các phần còn lại

1. **Gói tiếp theo là E2 freeze và phép đo thật**, không tiếp tục vòng smoke/QA đã đạt. Đọc FOUR_PHASE_PLAN.md/EXECUTOR_POLICY.md và receipt này; chốt trước source/input/query/runtime/engine endpoint và chính xác argv/output mới. Giữ budget3600s+cleanup<=10s, một lượt/no retry/no resume.
2. Kiểm actual engine availability bằng thao tác chỉ đọc phù hợp. Không chạy lại script recovery hoặc quyền một lần đã dùng; không đọc routing config/WSL bằng quyền cũ. Nếu engine không sẵn sàng và recovery chạm guard, dừng đúng action và nêu bằng chứng.
3. Dùng supervisor đã nhận để đo E2: full6367POI,1/3/5km,50batch,6warmup+30measured. Phân tích accepted-set equality/FN/FP/candidate logical counts/latency bằng dữ liệu thật; nếu ngắt, dùng journal đã commit, không tự tạo unit missing hay claim toàn cohort thành công.
4. Giữ các ca storededge orientation/duplicate/movedPOI/transaction rebuild trong **DB dùng riêng**; không sửa primary đang có dữ liệu. Hoàn thành kiểm hệ thống và3nhóm đối kháng theo SG/AC, không dùng test giả thay bằng chứng thật.
5. H2/H3 cũ không retry/fill missing. Cohort mới cần prospective amendment/quyền phù hợp. Không đổi tiêu chí sau kết quả để nhận giả thuyết.
6. Cập nhật interactive report tiếng Việt và checkpoint sau mốc lớn. Phase4 mới chờ người dùng chọn H1 hoặc viết tiếp luận án; H1 hiện0người. Phase5 Finalizing vẫn giữ crawler/new grow-with-user/harness.

Goal vẫn active/incomplete. Mã collector được nhận offline không đồng nghĩa E2 đã được đo, toàn hệ đã hoàn tất hoặc luận văn đã có kết luận.

Report QA cuối:400kiểm tra tĩnh/112tham chiếu đạt trong EXP-092/parent-static-results.json; không có browser/perceptual QA mới.

