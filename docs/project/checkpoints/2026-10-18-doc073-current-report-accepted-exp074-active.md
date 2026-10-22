# Checkpoint — interactive docs hiện tại đã nghiệm thu tĩnh

**Chủ trì: Codex, 18/10/2026.** Mục tiêu tổng thể còn active/incomplete. Lần goal trước có tiến triển thực: chạy S5 native một lần, tìm/sửa oracle và lưu kiểm tra giờ nguồn; không chỉ nhắc trạng thái.

## Đã chốt
- DOC073 OpenCode AI-box, session ses_eb14e4c27ffePW6pvoq7Kp83FW, handle56650. Artifact + executor static checks đã có; Codex dùng official interrupt/resume=false, wait204, active target=false; client1 do interrupt. Source writer đã nhả, không khởi chạy lại.
- Codex chỉnh câu chữ/giới hạn cuối, kiểm độc lập325static/73localrefs đạt;9node/8edge đúng source topology; showcase9/9,0errors/warnings. Deliver lại độc lập cho HTML trùng bytes. Biên nhận `handoffs/DOC-073/parent-final-acceptance.json`.
- Report `docs/reports/2026-10-18/index.html`; diagram architecture.html/spec architecture.json. Chỉ nghiệm thu tĩnh/deterministic, không browser/perceptual. Google Fonts tùy chọn còn trong template; Viewer UI/html-lang English; nội dung Việt. Giữ bằng chứng browser cũ như lịch sử.
- QA ban đầu của Codex có2giả định sai: application/json bị gom vàoJS, và nghĩ mọi tài nguyên font nhúng offline. Giữ kết quả ban đầu, sửa cách phân loại và công bố font dependency; không sửa HTML trusted hoặc giả browserpass.

## Đang làm / quyền chạy
- **EXP074 handle49550/session ses_eb140c55affeVPcaDwcaicoVsg**: collector hiện có dùng providerV2 đã nhận, projection arrival/departure/initial-vs-repaired, đúng identity/usage/ledger/primary-vs-synthetic. Fixed brief trước dispatch. Chỉ benchmarks/live_model + relatedtests/ownartifacts; production provider READONLY,0actualmodelcalls. Không ghi report/DOC073. Cần kiểm exact process/session hiện tại trước followup, không restart vì timeout.
- **MEM072R1 chưa chạy**: original once-only approval đã dùng. Original native3authpass/createassertfail/0model/cleanupstopped.5offlineSQLitechecks xác định oracle expected_version0 sai khi tạo absentprofile. Revisedscript SHA474ca0c4ea7ff53e883d7d8372d30dc46b38f7693a43b879c5f049275c1590f2 chờ NEW explicitapproval; không chạy bằng executor khác hoặc đổi tên.
- Dữ liệu primary:428/6367hoursstrings parseable, nhãnQuan1 có92; chỉ cú pháp nguồn, không verifiedfreshness. Có receipt/script ở EXP074; chưa freeze20scenario hoặc routecase.

## Tiếp theo
1. S5 chỉ chạy bản sửa một lần nếu có câu trả lời cho phép rõ; kiểm kết quả/cleanup, không tự retry.
2. Chờ EXP074 release/idle; Codex review logic, dùng fixture độc lập parent_projection_fixture.py và regression liên quan. Không dùng fake tests làm scientific evidence; không chạy legacyV1 trênCLI2.0.32.
3. Chốt source/model/settings/cases/route/feasibility/code/data freeze, sau đó phase3 H2/H3/adversarial/system. Không chạy lại acceptedfullgraph/provider/foot/car chỉ để nhắc lại.
4. Phase4 báo cáo/chờ người dùng chọnH1/viếtthesis. Phase5Finalizing giữ toàn bộ crawler/growwithuser/mới. Không đánh dấu fullgoalcomplete.
