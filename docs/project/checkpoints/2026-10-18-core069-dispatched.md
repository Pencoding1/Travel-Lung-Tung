# Checkpoint — CORE069 đang thực thi

Codex chủ trì kế hoạch, QA và nghiệm thu.18/10/2026. Scope S1–S6 đã được người dùng duyệt; phase5 Finalizing nhận mọi cơ chế mới.

- DATA068 đã release và được Codex nhận: checkpoint `2026-10-18-data068-full-import-accepted.md`. Handles62783/74743 đều terminal0; không poll/restart. Full graph6367POI/14Category/3678397NEAR_BY; Memgraph ownedPID9534/start6363950,3072MiB, data giữ nguyên sau restart.
- **CORE069 active handle50380**, exactsession **ses_eb201dea0ffe88oB4UGIXhOmrr**, executor OpenCode model **aibox/ds/deepseek-flash** (V4.1 theo user). Đã thấy step_start/text/read từ session này; chưa có acceptance.
- Codex plan chốt trước dispatch: `handoffs/CORE-069/brief.md`. Cwd `E:/Project/TVLT_2026/docs/project/handoffs/CORE-069`; executive `E:/Agent_Artifact/TVLT_2026/2026-10-18/core-flow-integration/events.log`.
- Mục tiêu: luồng nguồn OSM được chọn → nhu cầu → Jev/chat hoặc itinerary → đề xuất → routing car/foot → kết quả. Sửa typed chat context/source gates, catalog/UI tiếngViệt tối thiểu và native services; bounded provider-title/log fixes. Exact allowedpaths/tests/budget/live limits xem brief, không mở rộng.
- Một source writer; **không sửa đồng thời source CORE069**, không restart import/engine hoặc gọi model chồng lên gói. Poll50380 khi cần; observation timeout không phải terminal. Dừng đúng approval/auth/policy denial, không bypass/globalconfig/key read.
- Native2.0.32 không hỗ trợ --dir; dùng workdir thực và foreground CLI. Không tuyên bố detached callback/backgroundrunner đã hoạt động. Giữ handle/session/evidence cho phiên sau.

## QA sau khi executor release

1. Đọc status/report/result và diff so với CORE-069/before cùng source manifest. Kiểm scope/guard và actual run provenance trước acceptance.
2. Kiểm typed source/mode và current request ưu tiên hơn model/profile/history. Đặc biệt mixed-source details/nearby hoặc source switch không được lọt vào model/memory.
3. Kiểm actual connector + MCP SSE HTTP + full graph + GraphHopper; phân biệt controlled-model và realAIbox/Jev. Không chấp nhận shim/fake làm actual proof. Kiểm title auxiliary usage và honest unknowns.
4. Root chạy focused independent QA/counterexamples cần thiết; không rerun toàn repo sau thay đổi nhỏ. UI static không thay browser/render proof.
5. Sau gate lưu checkpoint và đồng bộ report/backlog. Chỉ mở phase3 sau S1–S6 freeze, không crawler/grow-with-user/H1/thesis sớm.

Report hiện tại `docs/reports/2026-10-18/index.html` đã đồng bộ DATA068;252staticchecks/79refs +75consistency +5phase/data checks đạt. Các assertions phase1/pending-data/120-provider cũ đã được wrapper root điều chỉnh theo phase2/S2/CLI067 chứng minh, không đổi evidence/test lịch sử. Không có browser/renderproof mới.
