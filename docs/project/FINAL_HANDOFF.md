**Codex21/10 — PLAY156:** Call graph đã thêm Phát/Tạm dừng/Tiếp bước/Chạy lại,1x/2x cho4chức năng. Từng bước có giải thích, chiều trả kết quả; số cạnh là mã tra cứu. Nội dung/sequence do Codex cha soạn, graph và12popup giữ nguyên.20nhóm NodeDOM vàsyntax đạt; khôngclaimbrowservisual/geometry mới. Tải lại file/tab để xem. Checkpoint: `checkpoints/2026-10-21-callgraph-playback.md`; demo/BAT/engine không đổi.

**Codex 21/10 — START154 / GRAPH155:** Demo đang chạy tại http://127.0.0.1:19102/travel; engine6367POI/3678397NEAR_BY và car/foot đã khôi phục bằng quyền mới. Có START_DEMO.bat (tự bật engine khi cả hai tắt từ cache cũ đã chuẩn bị; dùng lại stack khỏe) và call graph offline12module/7layer/19quan hệ, lọc+popup input/output. Nội dung do Codex cha viết, renderer không quyết định facts. Checkpoint hiện tại: `checkpoints/2026-10-21-demo-start-and-callgraph.md`. CHAT153 vẫn backlog; không mở H1/writing/Finalizing/DEP149. Các thông báo bên dưới là lịch sử.

**DEMO152 mới nhất — đã làm1/2/4 theo user:** chat vẫn gửi được khi tạo lịch (cùngphiên xửlýlầnlượt), cóHủy chờ; chọnnhiều/toàn26vùng nguồn; vẽrouteGraphHopper thật. Mục3 ởCHAT153backlog. Demo đãrestart, giữchạy19101/19102. QA/limits: `checkpoints/2026-10-20-demo152-items-1-2-4.md`; khôngnhậntoàngoalcomplete hoặc phépDEP149.

**Trạng thái điều phối mới nhất: chờ quyền/quyết định, đang chốt BLOCKED goal.** DEP149 chưa dispatch; câu hỏi host vẫn pending. Các QA độc lập đã trả, không có worker thuộc gói đang chạy để poll. Xem `checkpoints/2026-10-20-awaiting-owner-decisions.md` và `handoffs/DEP-149/blocked-audit.json`. Mục tiêu đầy đủ chưa hoàn tất; không phải pause theo yêu cầu user.

**REF150 mới nhất:** `checkpoints/2026-10-20-binary-thesis-audit-ref150.md`: đã audit actualWord/PDF có giới hạn, bản gốc giữ nguyên; DEP149 vẫn chưa dispatch/chờ quyền host. Writing/H1/Finalizing chưa mở.

**Checkpoint mới DEP148:** `checkpoints/2026-10-20-compose-readiness-dep148.md`. DEP149 brief chốt, CHƯA dispatch/chờ quyền host mới; không dùng lại quyền cũ. Demo/báo cáo phase4 và H1/writing/Finalizing boundaries giữ nguyên.

**Hiện tại — Codex20/10, DOC147 / phase4:** LIVE143 đã chạy đúng một lần được user duyệt, terminal0:31 kiểm tra luồng chat → lịch → hai ghim/chọn đúng POI;4Go/4CLI+1Jev. Ảnh live còn popup bị che; UI145 chỉ sửa CSS, JS giữ nguyên; B146 kiểm riêng đúng cặp POI nguồn trong fixture, toàn thẻ hiển thị rõ, không bị che; chưa kiểm hành động nút đóng. Không gọi lại model hoặc hồi tố ảnh live. Báo cáo phase4 đã giao, chờ user chọn H1 hoặc viết tiếp; mục tiêu tổng thể IN_PROGRESS. H1=0participants; Compose còn thiếu; crawler/grow-with-user thuộc Finalizing. AUD140/REF141/REF142 đã có gap map và audit Markdown, không sửa chương/DOCX/PDF. Không worker model/browser nào của gói còn chạy; quyền LIVE143 một lần đã dùng. Checkpoint: `checkpoints/2026-10-20-live143-and-thesis-audit.md`. Các thông báo phía dưới là lịch sử, không phải task đang chạy.

**Cập nhật Codex20/10 — sửa xong ghim và card mobile:** UI135/137 dùng OpenCode Go, đều terminal0/interrupt0/wait0. BROWSER138 đạt6/6 bố trí desktop/mobile với HTML/catalog/POI fixture, toàn thẻ đọc được;0 native API/model/Jev. 8Nodegroups/18race đạt;163backendpins nguyên. Mã cuối355c713b…; B131live cũ vẫn PARTIAL, chưa chạy lại trên mã cuối. Xem `checkpoints/2026-10-20-ui-pin-mobile-fixed.md`; report DOC139. Không worker/browser QA còn chạy.

# Travel AI — trạng thái Codex ngày 20/10/2026

**Ưu tiên: demo trọn luồng bằng chatbot.** Chưa bắt đầu H1, viết luận văn hoặc Finalizing phase.

- Giao diện mới đã có hội thoại, thiết lập chuyến đi, bản đồ TP.HCM với nhà 3D và ghim đỏ. Bấm ghim/thẻ chọn cùng địa điểm. Không vẽ tuyến giả khi backend chưa trả hình học đường đi.
- OpenCode UI127 (AI-box V4.1) và bản sửa nhỏ UI129 (Go V4.1) đều đã dừng, có interrupt/wait receipt; không khởi chạy lại. Báo cáo cuối của worker UI127 chưa được giao, nên nghiệm thu dựa trên mã và QA Codex.
- QA: 8 nhóm Node, 11 kiểm tra catalog/static và 18 kiểm tra race độc lập đạt. Chrome headless BROWSER130 xác nhận 123 polygon tòa nhà thực sự được render, desktop/mobile không tràn ngang. Đây là trình duyệt thử riêng, không phải tab cá nhân của người dùng.
- BROWSER131 đã kết thúc PARTIAL: chat + typed thật đạt, hai ghim đúng tọa độ; click/popup timeout. Dùng 4 Go/4 CLI + 1 Jev. Handle55754 terminal1; không poll/rerun. BROWSER133 kiểm click/card bằng fixture riêng đạt, 0 model/Jev; handle41926 terminal0. Các browser QA đã đóng.
- Backend giữ graph 6.367 POI; SYS119 B2 riêng đã đạt 8 kiểm tra nguồn và tuyến hai điểm đầy đủ. GRAPH115 đạt 7/7 ca lifecycle trên 4 POI thử/engine thật, không chứng nhận toàn graph hoặc concurrency.
- H2 giữ 119 quan sát + 1 gap; H3 giữ 1/15 ô có lịch; TIM097 đủ 30 lượt nhưng 5 km chậm hơn 27,66%. Không chạy lại để lấp ô hoặc suy hiệu quả memory.

Checkpoint: `checkpoints/2026-10-20-ui-demo-live-partial.md`. Bằng chứng UI: `handoffs/UI-127`, `UI-129`, `BROWSER-130`; preflight/live riêng: `BROWSER-131`. Báo cáo tương tác: `docs/reports/2026-10-18/index.html` (đã đồng bộ DOC132).

Codex lập kế hoạch, QA và nghiệm thu; OpenCode triển khai mã. Không đọc raw env/auth, không vượt guard, không dùng lại quyền one-shot đã hết. Crawler và grow-with-user mới thuộc Finalizing phase. Mục tiêu tổng thể vẫn IN_PROGRESS.

Các worker và trạng thái pending trong phần lịch sử dưới đây không phải tiến trình hiện tại.


---

# Lịch sử — Travel AI handoff16/10, không phải final delivery

> Superseded historical handoff. For continuation, use [NEXT_SESSION_HANDOFF.md](NEXT_SESSION_HANDOFF.md) and its latest dated checkpoints. Updated 2026-10-16: the primary file now has 6,368 features / 6,367 frozen prepared candidates; 169 primary/acquisition checks pass, general registry revisions remain partial; a 33-page working manuscript has passed all-page layout review; the authorized DeepSeek V4 Flash alias has produced a synthetic engineering pair. No final scientific or deployment completion claim. The earlier statements below about missing primary data, pending native math and active old workers are historical. Also, OC027's out-of-scope `uv run` recreated the original `.venv`; do not rely on the older retained-environment statement below.

Updated 2026-10-15. The completion gate has NOT passed. This document supports continuation and review; it is not a final delivery claim.

## Source of truth

Read MASTER_GOAL.md and EXECUTION_PROTOCOL.md for the complete SG01–19/AC01–12 scope. Read ACCEPTANCE_TRACKER.md for requirement status, PROGRESS.md for current ownership and process handles, INDEPENDENT_QA.md for rejection/acceptance evidence, and BACKLOG.md for remaining work. Source code and executed output take precedence over executor completion labels.

The user's original working tree already had deleted Architecture_Note.md and TODO.md and untracked docs. Those changes were preserved. No git commit, original graph migration or historical data overwrite has been performed. The original broken .venv was retained; isolated validation environments were created alongside it.

## Verified changes

- POI identity is stable through validation; coordinates are finite and within range.
- Spatial candidate filtering handles latitude, poles, dateline and cross-district endpoint order. Live Cypher and stale-edge lifecycle remain separate gates.
- Ingestion uses fresh transactions on retry, complete record accounting and retained SSE event history. HTTP/SSE tests used fake databases; event history remains process-local.
- AI grounding binds returned POI identity to requested identity and uses structured administrative context. Unsupported factual fields remain unknown or are reconstructed from evidence.
- Actual MCP tools expose administrative/category evidence, conjunctive search and complete ordered route inputs. Registration and payload contracts were tested in process; no real graph or route call was made.
- POI graph-only startup no longer requires Firebase. Optional Firebase is explicitly enabled; startup/cleanup paths were tested with injected connectors.
- Compose configuration had JWT wiring and secret literal removal repaired. The historical token still requires owner rotation; no token is reproduced here.

Counts and exact commands: EVIDENCE_REGISTER.md. Counts overlap and must not be added together or treated as scientific sample sizes.

## Current unfinished implementation

Memory corrections and namespace integration independently passed190 combined AI tests. Deployment, startup, graph lifecycle and regression checks passed291tests, with46 updater/ingestion checks in a separate environment; counts overlap. OC-016 integrates the planner into the actual itinerary endpoint; OC-017 integrates spatial rebuild into mutations and exposes terminal outcomes; OC-018 builds the offline experiment evaluator. Current handles and one-writer ownership are in PROGRESS.md. Poll existing handles, never restart based only on observation timeout.

After those submissions: independently check repairs, integrate the deterministic planner into the actual itinerary endpoint, test the real upstream/downstream payloads, reconcile runtime dependency locks, and execute an isolated deployed workflow when the engine is available. A pure planner module alone does not satisfy end-to-end itinerary completion.

## Actual data and research

`data/expansion_20261015` contains two Wikidata entity exports and a derived sample of30 OSM nodes from the pre-existing local PBF. The first acquisition pass produced32 candidates, all requiring review and none accepted. The second pass recognized32 duplicates while retaining32 quarantined entries. Original PBF and Wikidata hashes were preserved. The PBF header gives a snapshot timestamp of2026-03-17; its download time remains unknown. Source expansion is separate from the original approximately200-POI thesis scope.

The12-work literature matrix and related-work synthesis are available under docs/research and docs/thesis. Four experiment protocols and a real-human study protocol are prepared. Synthetic spatial/planning checks and five profile fixtures are engineering evidence only. There are no real participant responses, matched model comparison results or reproduced historical headline metrics.

Chapters1–5 are working Markdown drafts. The user confirmed the original proposal is lost and authorized reconstruction from legacy documents. LEGACY_RECONSTRUCTION.md records provenance and four newly worded RQs; CHAPTER_2_FOUNDATIONS_RECONSTRUCTED.md replaces missing theory sections using verified primary sources. The old18-reference list is not fabricated. No original-file response is pending. The working set is not a finished60–70-page thesis and has not been assembled/rendered as a final document.

## Reproduce isolated checks

Run each suite from the repository root using its matching environment. Concurrent source owners must finish before rerunning their suites.

```powershell
.\.venv-validation\Scripts\python.exe -m pytest tests/acquisition -q --basetemp .qa-tmp-acquisition-review
.\.venv-mcp-validation\Scripts\python.exe -m pytest tests/startup tests/mcp_contracts tests/audit tests/domain_identity tests/spatial -q -o faulthandler_timeout=30 --basetemp .qa-tmp-poi-review
.\.venv-ai-validation\Scripts\python.exe -m pytest tests/ai_grounding tests/ai_chat_memory -q -o faulthandler_timeout=30 --basetemp .qa-tmp-ai-review
.\.venv-validation\Scripts\python.exe -m pytest tests/planning -q --basetemp .qa-tmp-planning-review
.\.venv-validation\Scripts\python.exe -m pytest tests/deployment -q --basetemp .qa-tmp-deployment-review
```

These commands are reproducibility instructions, not a claim that every current suite passes after active edits. The last accepted and rejected runs are recorded in INDEPENDENT_QA.md. Some in-process async tests stalled under the restricted shell and completed under approved normal execution with fake collaborators; interrupted runs were not counted as passing.

## External gates and remaining evidence

1. Docker Linux engine: missing named pipe on the latest check, despite the user's reset/restart. No additional blind reset. No containers built or started.
2. Original graph snapshot/category inventory: not recovered and not verified. Real-data acceptance and graph writes need an inspectable catalog and snapshot-safe isolated test target.
3. Configured model access: no real Gemini completions have been executed. Never substitute mocked success for model quality or usage measurements.
4. Human study: actual voluntary participants, consent and execution required. No simulated responses can satisfy H1.
5. Thesis reconstruction: authorized and drafted; integration, reference normalization and final rendering remain. Lost original wording is disclosed, no longer a prerequisite to further writing.

Completion requires the full requirement-by-requirement audit in ACCEPTANCE_TRACKER.md, actual deployed evidence where required, consistent thesis tables/references/figures, and final document rendering. A blocked item stays explicitly blocked; the overall goal remains active while independent work is available.

## 2026-10-18 window (Hermes acting as Codex, 02:33–06:08)

What changed and is measured (full detail: `E:/Agent_Artifact/TVLT_2026/2026-10-18/HANDOFF_TO_CODEX_0608.md`; register entries E076–E082):

- T061: source-result date serialization fixed at the service boundary with a distinct `serialization_failed` code; the real-graph canary passes 7/7 stages with a clean rollback (in-process FastMCP + Memgraph only, no HTTP transport, no Docker).
- QA-DATA-01: the "real snapshot" hole was proven by execution and closed with `real_binding_mismatch` before any file read; the reviewed real path still validates 6367 records.
- T051: `--pure` is capability-negotiated and the native-binary resolution for the `@opencode/cli/bin` npm layout was fixed, so the CLI transport can start; no live model call was made.
- T060: routing sends `ch.disable` for profiles without a built CH (measured: car 200, foot 400, foot+ch.disable 200); no straight-line fallback.
- T057: fetch bounded before read, real DNS pinning with proxies disabled, license gate before any request; entity identity namespaced by canonical page URL; enrichment requires name+address+finite coordinates and no longer echoes transport text. Social suite 56→127 (including a new Wikivoyage CC BY-SA adapter), acquisition 140→152.
- Two real memory defects found and fixed: the ReAct result dropped `turn_messages` (history lost after turn 1, measured 120/120 prompts) and a valid profile block was truncated through its closing tag and safety sentence. `ai_chat_memory` 102→110.
- Experiment 2 measured on the frozen snapshot: 20,266,161 pairs, 0 prefilter false negatives at 1/3/5 km, candidate work cut 95.5%/78.5%/59.3%.
- HM-053 guard scripts root-QA'd (40 tests, 19 execution payloads); the hook is **not** installed.

Still blocked, unchanged: full 6367 import and graph edge counts, source scope in the AI planner (T049 proposal only), Docker end-to-end and durability, and the H1 human study (external dependency). Experiment 3/4 harnesses run offline with fake models and are labelled `fixture_only`; they are not scientific results.
