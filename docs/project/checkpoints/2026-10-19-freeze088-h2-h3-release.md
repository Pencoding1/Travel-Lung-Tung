# Checkpoint FREEZE088 — Codex, 19/10/2026

**Đã chốt bản mã/dữ liệu/cấu hình H2/H3 trước khi chạy. Chưa chạy thí nghiệm chính.**

Authority: `docs/project/handoffs/FREEZE-088/parent-final-acceptance.json`, decision
`ACCEPTED_H2_H3_PRE_RUN_FREEZE_NOT_EXECUTION_OR_RESULTS`.

## Đã hoàn tất

- 122 tệp công khai được hash riêng; toàn bộ 67 pins của CORE087 vẫn khớp.
- Ghi Git HEAD và hash dirty diff chỉ cho danh sách public đã duyệt. Patch nằm trong RAM, không in/lưu. Các tệp untracked/ignored được hash riêng; không claim toàn bộ worktree sạch hay đã commit.
- Khóa 34 distribution theo metadata và 52 quan hệ phụ thuộc mặc định đang áp dụng; không thiếu/xung đột. Fallback chỉ tenacity9.1.4 theo launcher đã duyệt. Python/base executable/CLI có mã băm, OS/CPU/RAM đã ghi.
- H2 giữ nguyên 20 đầu vào đã nghiệm thu/hash631d6fdc…; 20 cặp prompt dùng cùng facts, khác instruction theo thiết kế. Dry-run tạo đủ120 lượt (20×2×3), không resolver/provider/model. Timeout120s, một attempt, tối đa120 yêu cầu sinh model.
- H3 giữ nguyên candidate cũ chưa frozen; tạo manifest execution riêng. Collector/source gates chấp nhận manifest mới; 9 mutation bị chặn. Giữ `thesis_mode=false` theo gate dành cho hồ sơ nhân tạo; không sửa collector để đổi nhãn này.
- H3: 5profile×3điều kiện=15cell; tối đa33 local model-generating API requests,165 known CLI attempts,33Jev; timeoutCLI30s/HTTP210s; không retry/best-of/paid fallback. Nguồn1483POI, typed itinerary và lifecycle giữ nguyên thiết kế trước kết quả.
- 181 điều kiện nghiệm thu nguồn/runtime/đầu vào/manifest đạt. Không đổi production code, dữ liệu gốc, protocol, kết quả cũ hoặc guard.

## Artifact mới

- `docs/project/handoffs/FREEZE-088/freeze-bundle.json`: release và hash của các artifact.
- `public-inventory.json`, `runtime-dependency-lock.json`, `study-controls.frozen.json`.
- `offline-preparation-results.json`, `qa-work/h2-dry-plan/manifest.json`.
- `docs/experiments/primary_20261018/h2_execution.freeze088.v1.json`.
- `docs/experiments/primary_20261018/h3_execution.freeze088.v1.json`.
- `execution-commands.json`: exact argv chuẩn bị cho phase3; **executed=false/authorized=false**.

Không chạy lại `accept_study_freeze.py` hoặc các builder để ghi đè release. Nếu nguồn thay đổi, ghi nhận drift và lập release mới có lý do; không sửa manifest cũ để khớp kết quả.

## Demo người dùng đang mở

Theo yêu cầu “mở giao diện cho tôi”, Codex đã bật native MCP19101/AI19102, alias `opencode-go/deepseek-v4.1-flash`. Launcher trả `started`, hai health200, run `core069-eea009702056`, MCP PID31284, AI PID35196 tại08:27UTC. Đây là snapshot lúc bật, không bằng chứng process còn sống mọi thời điểm.

Browser tab5 hiển thị Travel Lung Tung, vùng nguồn6367bản ghi/Quan1 có1483bản ghi, biểu mẫu và hai nút; chưa gửi model qua thao tác của Codex. Chỉ xác nhận trang/catalog hiển thị; chưa browser end-to-end có model, chưa visual/perceptual QA toàn diện. Không kết luận modelcall của người dùng bằng0.

Giữ app để người dùng trải nghiệm. Không stop/restart app, sửa source/config hoặc chạy scientific collection cạnh tranh cùng provider/engines khi demo đang được sử dụng. Quyền mở UI không phải quyền chạy primary experiments hay tái dùng các pilot một lần.

## Bước tiếp theo bắt buộc

1. **Đã đồng bộ** dashboard tiếng Việt/bảng S6/SG/AC:382staticchecks/104refs đạt; phase3 ở trạng thái chuẩn bị, chưa có kết quả. Không mở thêm smoke loop.
2. Trước thực thi, chạy lại `FREEZE-088/verify_release.py` chỉ đọc (sau editorial đã exit0:122public/34package/14bundleartifact không drift), rồi kiểm catalog/engine readiness, output mới trống; ghi actual start/end timestamp. Metadata version lock không chứng minh byte của tất cả package hoặc optional integrations.
3. Khi demo kết thúc, xem exact `execution-commands.json`, chuẩn bị gói phase3 và xin quyền mới chính xác nếu phần chạy chạm scope guard đã chặn trước đây. Mọi quyền CORE079/083/085/087 đều đã dùng; không suy rộng sang primary.
4. Chạy H2/H3 có kiểm soát, lưu tất cả failures/missing/usage giới hạn đo; không chỉnh tiêu chí sau kết quả, retry để lấy kết quả đẹp hoặc paid fallback.
5. Chuẩn bị/chạy E2 trên engine thật (1/3/5km;1warm-up+5reps), kiểm hệ thống và đủ3nhóm đối kháng theo protocol. Những batch này cần pre-run control riêng; release H2/H3 không tự chứng nhận chúng đã chuẩn bị hoặc đã chạy.
6. Phase4 báo cáo tương tác kết quả. H1 hiện0người; chỉ làm H1/viết luận án sau lựa chọn của user. Phase5 Finalizing giữ crawler/travelagency/social/grow-with-user/harness và cơ chế mới; không kéo lại phase2.

## Giới hạn phải giữ nguyên

Giá chưa biết; giờ nguồn không xác minh tươi; không hứa mọi lịch khả thi. Alias model có evidence, upstream weights/quantization/effective default sampling không quan sát được. H2 seed đầu vào không phải seed model. H3 identity/SQLite thử nghiệm không phải IdP triển khai thật; 5 hồ sơ nhân tạo không phải người tham gia H1 hoặc mẫu để suy p-value dân số. Không có primary observations hoặc kết luận giả thuyết tại mốc này.

Hai lỗi preparation của Codex được ghi trong acceptance: mock tên resolver không tồn tại; sau đó RAM-only H3 promotion đặt nhầm thesis_mode=true bị gate từ chối. Đã sửa script QA theo đúng contract; không chỉnh collector hoặc ghi đè input/dry plan để che lỗi. Không có model call trong FREEZE088.

Goal vẫn active/incomplete. Không báo hoàn tất SG01–SG19/AC01–AC12 chỉ vì chốt release.
