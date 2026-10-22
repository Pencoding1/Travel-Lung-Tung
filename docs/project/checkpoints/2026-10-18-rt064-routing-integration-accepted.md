# Checkpoint — car/foot đã đi xuyên planner, 18/10/2026

Chủ trì **Codex trong chat này**, sở hữu /plan, test và nghiệm thu. OpenCode `aibox/ds/deepseek-flash` thực hiện RT064 theo brief; session `ses_eb2873846fferZUXD3ioCRlwx0`, initial86936/R129806 đều terminal0. Không còn writer RT064, không restart các handle này. Goal ACTIVE/INCOMPLETE.

## Đã nghiệm thu có giới hạn

- Request nhận đúng `car` hoặc `foot`, mặc định car để tương thích; ghi rõ lựa chọn explicit/default. Sai kiểu/giá trị trả422 trước MCP/model. Không suy mode từ mô tả hay model.
- Mode được truyền vào MCP, route edge, scenario và response constraints; source scope giữ nguyên. Profile trả về không khớp bị từ chối, không fallbackcar; thiếu echo không bị gọi là xác nhận profile từ provider.
- Codex tái hiện14 yêu cầu chưa đạt trên snapshot trước sửa. Sau lần đầu:233planner+162grounding và15ASGIđạt nhưng probe bổ sung phát hiện phản chiếu profile vào lỗi. Same-sessionR1 sửa detail hằng và thêm1test. Root cuối:234planner +15contractprobe đạt;15ASGI trướcR1 đã kiểm được số phút car2/foot17 và invalid0downstream. Grounding162 đạt ở bản đầu, R1 chỉ thay detail lỗi profile/test/report, không sửa grounding/main/payload.
- Hai canary thật chạy **tuần tự** sau terminal: request→AI/planner→MCP đăng ký thật in-process→Memgraph transaction thật→GraphHopper HTTP thật. Car2chiều200, foot2chiều200 và `ch.disable=true`; lịch sau sửa giữ source selection. Model sinh nội dung được kiểm soát, không model thật/H2.
- Fresh process ownership/hash preflight đạt cho mỗi canary. Đồ thị trước/sau/final đều0nodes/0relationships; frozenprimaryhashkhôngđổi, không import bền vững.
- Cặp POI thật chỉ khoảng20m: rawcar1s/foot14s cùng làm tròn1phút. Không suy thành đo chất lượng tuyến toàn thành phố hoặc performance.

Nguồn chứng minh: handoffs/RT-064/parent-final-review.json, parent-source-audit.json, parent-contract-before-r1.json, parent-contract-after.json, parent-http-mode-results.json, parent-real-mode-{car,foot}.json. Before source snapshots giữ nguyên. Pytest gộp thư mục có lỗi collection do trùng basename; chạy riêng đạt, không sửa/xóa tests/cache để giấu lỗi. Probe sandbox đầu bị chủ động cancel rồi host run được duyệt thông thường; không policy-denial bypass.

Giới hạn workflow: executor đã viết2script QAgiả dưới Temp/opencode ngoài exactallowed_writes; report đã đính chính. Không coi terminal0 là toàn phiên tuân thủ. Không có bằng chứng secretread/network từ các script đó. AIofflinevenv MCP2.3.0 lệchlock; canary engine dùng MCP1.26.0 thực tế, không tự cài/migrate.

## Việc tiếp theo — phải tiếp tục

1. **T051**: kiểm effective agent/policy của CLI engine trước model. Root vừa đối chiếu tài liệu V2: có agent API theo Location; xem CLI-060/root-v2-research-followup.md. Đây mới là hướng khảo sát, chưa runtime proof. Lập brief trước khi giao coding; không gọi model thật/default hoặc đọc auth/config/env/history để dò server. Không chấp nhận generated config thay proof engine.
2. **T050/T049**: native source lineage consumer và nhập snapshot6367candidate, review category/admin/entity, source selection phía client, kiểm fullsnapshot/deployed HTTP. Canary2POI không thay gate này.
3. Cấu hình Jev runtime/policy có chủ đích và QA service đầy đủ, dùng thông tin TOKEN đã có qua loader; không rawread/in/copy.env. Pilot Jev30câu đã xong, không tuning lại holdout.
4. Sau các gate mới freeze/run20pairedH2 và5x3H3/đối kháng. Chưa H1 participants; chờ user sauphase4 mới H1/viếtluậnán. AgentMemoryP2 sau4phase, không làm trước.
5. Giữ checkpoint sau mốc lớn, cập nhật báo cáo tương tác tiếng Việt ngắn gọn. Không tuyên bố hoàn thành toàn goal; không reset/clean/commit/push. Các nhánh crawl/memory/docs trước đã bàn giao, không spawn lại để lặp báo cáo.

Báo cáo phase2/car-foot đã đồng bộ canonicalJSON/HTML9module/generator; root234staticchecks/70refs+75consistency và phase/mode semanticchecks đạt, node--check đạt. Không render/browser proof mới. Report architecture bytes snapshot trướcAI063 vẫn giữ và ghi caveat. Event timing/write-path audit: parent-execution-audit.json.
