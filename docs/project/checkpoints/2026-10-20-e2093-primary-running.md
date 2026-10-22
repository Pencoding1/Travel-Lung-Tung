# Codex checkpoint — E2093 đang đo E2 thật

20/10/2026. Sau EXP092offline99test/209binding, Codex đã chốt release E2 trước dữ liệu và khởi chạy **đúng một batch chỉ đọc** theo goal/phase3 được người dùng giao. Không model/Jev/graphwrite/recovery.

- **Unified exec handle83883** đã launch và trả trạng thái running. Kiểm đúng handle để biết còn chạy/terminal; journal hoặc lock không thay proof process còn sống. Không restart vì timeout quan sát.
- `docs/project/handoffs/E2-093/release.json` chứa exactargv/source/input/query/runtime/engineproof/limits; manifest `e2-execution.frozen.json` đã Codex duyệt trước phép đo. `parent_verify_release.py` đã đạt trước launch; không rerun nó sau launch để rồi hiểu nhầm outputexists là mất quyền.
- Output: `docs/experiments/primary_20261018/runs/e2-e2093-primary/result.json`, kèm `.journal.jsonl` và `.supervisor.json`.
-6367POI/20.266.161unorderedpairs/50anchorbatch,3radii,36timingcells=6warmup+30measured.3600s execution+<=10s cleanup,query<=120s/remaining. No retry/resume/fillmissing.
- Engine handshake thực tế ready, agent `Neo4j/v5.11.0 compatible graph database server - Memgraph`, Bolt5.2; đây không độc lập xác minh engine version3.13.2. Host16logicalCPU/~16GBRAM,92%RAM used lúc capture; shared desktop/no isolation,WSLmemorylimitunknown. Chỉ hardwaremetadata public, không đọc config.

Phiên tiếp phải poll handle83883, lưu terminal, kiểm journal chain/sourcebinding/cellcoverage/FNFP/equality/timing trước kết luận và checkpoint. Nếu bị ngắt chỉ unit đã commit là evidence; không tự tạo zeros/khôi phục rồi gọi lại cùng cohort. `parent_progress.py` đọc projection public đúng journal, không đo/modelcall, không proofliveness.

Các counts là logical candidates, chưa đo physical distance-function invocations; yêu cầu actual physical operations còn mở, không thu hẹp fullgoal. Storededge/move/rebuild dùng DB riêng. H2/H3 cũ bất biến; H1/viết luận án chờphase4choice; phase5extensions hoãn. Đọc prepared-plan.md và release limits để tiếp tục toàn bộ backlog sau E2.
