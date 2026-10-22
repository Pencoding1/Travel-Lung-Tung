# Checkpoint Codex — crawler sang phase5, scopephase2 chờ duyệt

18/10/2026, thay đổi do người dùng trực tiếp yêu cầu. **Checkpoint này supersede mọi note cũ rằng crawlP0/P1 là gatephase2.**

1. Toàn bộ crawlerlegacy/travelagency/socialweb T057–T059 chuyển **phase5 finalize**. Chốt kế hoạch nguồn travelagency vàmxh trước khi triển khai lại. Giữ artifact/code đã có, không xóa hoặc gọi đó là đã hoàn thành. Không đợi crawler để qua phase2/3.
2. Core dùng OSM POIs hiện có.6368raw/6367preparedcandidates, chưa fullgraphacceptance; giữ unknownupstreamIDs, khôngbịa lineage. Không tìm thêm nguồn/enrichmenttrảphí trongphase2.
3. Codex đã lập **PHASE2_SCOPE_FOR_APPROVAL_VI.md** với6scope: S1AI/Jev/CLI; S2OSM→graph; S3dịchvụHTTP/client hiệncó; S4planner/car-foot/ràngbuộc; S5memoryhiệncó choH3; S6QA/freeze/report. Đây là danh sách đề xuất để user duyệt, **chưa mở gói implementation mới**.
4. Scope ngoàiphase2: primaryH2/H3/đốikháng ởphase3; report/userchoiceởphase4; crawlerởphase5; growwithuserimplementationP2sau4phase; H1/thesis theo userchoice. KhôngDockerrepair/harnessmigration/UIredesign hoặcnguồn mới tự phát.
5. **CLI067R1 đã được cấp quyền trước khi chốt danh sách** vẫn đang chạy handle **7747**, same session **ses_eb264bdc8ffeBEy4NnUOEb7hs0**, modelaibox/ds/deepseek-flash. Khôngrestart/racesource. Initial20173terminal1/root180providerpass/4counterexamplefails, nativeQAclearcarrierkhôngđượcnhận. Đọc checkpointcli067-independent-review-r1 vàrevision-1.md. Root có thể hoàn thành QA bản sửa này; khôngmở tiếpS2/S3/... trước userduyệt scope.

MASTER_GOAL/FOUR_PHASE_PLAN/BACKLOG/DECISION_LOGD012 đã cập nhật. GoalACTIVE/INCOMPLETE, khôngpause/completegiả. Handoff phải giữ mới nhất; thông tinhistoricalbêndưới đượcđọc theo supersessionnày.
