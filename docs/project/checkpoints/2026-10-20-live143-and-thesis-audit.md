# Checkpoint Codex — luồng demo thật và audit luận văn

20/10/2026. Turn trước là PROGRESS: ba lỗi UI đã sửa và có sáu ca browser
fixture. Turn này tiếp tục demo thật và audit, không thu hẹp mục tiêu gốc.

## Demo đã kiểm đến đâu

User đã duyệt LIVE143 đúng một lần sau preflight. Handle84302 kết thúc0:
chat qua Jev/Go → tạo lịch hai POI → ghim đúng tọa độ → click mở đúng tên POI →
chọn thẻ lịch trình đúng ID.31kiểm tra đạt, hai POST,4Go/4CLI attempt và1Jev;
không retry/AI-box fallback. Source scope Quan1,car,same anonymous session,
memorytrue được giữ;163public backend pins và UI355c không đổi trong lần chạy.
Browser thử riêng đã đóng; không nhận là userIAB/H1 hoặc mọi input đều hợp lệ.

Review ảnh độc lập phát hiện popup bị bảng lịch trình che;31check trên không
chứng minh toàn thẻ đọc được. B144 dùng đúng cặp ID/tọa độ/thuộc tính POI nguồn
trong HTML fixture, chờ camera ổn định, xác nhận card vẫn bị che. Giữ failure.

UI145 giao OpenCode Go thêm đúng `.maplibregl-popup { z-index: 5; }`. JavaScript
byte-identical với bản đã chạy LIVE143. B146 lặp đúng ca fixture B144: toàn card,
địa chỉ/giờ/nút đóng hiển thị rõ và vượt paint hit-test phía trên bảng; chưa kiểm hành động đóng; parent và reviewer đã
xem ảnh. Một fixture POST,0native API/model/Jev. Không hồi tố ảnh LIVE143 thành
full-card proof và không gọi model lại chỉ cho một thay đổi CSS.

Mã cuối HTML SHA256:
`5bf75d2a0078292c80290ef28f6adab593fc4b4e13c946c8a9e4a1b7d21c83c8`.
Luồng API/JS có bằng chứng live; phần sửa lớp hiển thị có QA riêng trên cặp POI
nguồn. Giá/giờ theo dữ liệu chưa đủ xác nhận feasibility toàn cục. Không có
polyline backend nên không vẽ đường nối giả thành đường đi thực tế.

## Audit đã giao

- AUD140 đối chiếu31SG/AC nguyên văn với master; SG14/AC08 đã chạy ba family
  và giữ failures, không đặt gate mọi ca phải đạt. Delta LIVE143 nhận core
  end-to-end có giới hạn; Compose vẫn chưa kiểm thật. Public hosting không
  được tự thêm thành gate nếu master không yêu cầu.
- REF141 kiểm nhóm nguồn nền tảng/kỹ thuật, tìm URL F05 cũ404 và làm rõ F10
  là Playwright. F04 gặp429/403, đã dừng; không bypass hoặc tải qua proxy.
- Tìm được L07PDF lưu sẵn,27trang/25.291.544byte, hash58ac8466…; đọc/render
  các trang1/10/14 xác nhận phương pháp/giới hạn. Không tải mới; không nhận là
  đã đọc lại toàn27trang hoặc xác minh byte với bản publisher hiện nay.
- REF142 rà12Markdown/666dòng,136nhận định.13cụm không còn đúng nếu trình
  bày là trạng thái hiện tại; đây không phải cáo buộc sai tại ngày viết cũ.
  Parent189kiểm tra hash/vị trí/phạm vi đạt, ghi caveat các phần vẫn đúng.
  DOCX/PDF chưa audit nội dung; không sửa các chương hay viết luận văn mới.

Report hiện tại: `docs/reports/2026-10-18/index.html`, cập nhật DOC147,
giai đoạn4 báo cáo/chờ user quyết định. Bản thảo và các benchmark frozen giữ
nguyên; SG17/18/19 không được nhận hoàn tất từ một report hoặc số test xanh.

## Tiếp tục và giới hạn

1. User đã ưu tiên demo; giao diện tại http://127.0.0.1:19102/travel cần refresh
   để nhận CSS mới nếu service còn chạy. Không khẳng định uptime tương lai.
2. H1 hiện0participants; chờ user chọn H1 hoặc viết tiếp luận văn. Chưa tự tuyển
   người, tạo câu trả lời giả, sửa/assemble manuscript hay mở Finalizing.
3. SG16 còn reproducible Compose validation; native demo không tự chứng minh
   Compose. Physical engine calls, đầy đủ provenance/license/freshness và
   toàn bộ claim-to-final-DOCX/PDF vẫn chưa đủ bằng chứng.
4. Crawler/travel-agency/social acquisition hai họ nguồn, grow-with-user/new
   harness vẫn Phase5Finalizing, không biến thành gate chặn core thí nghiệm.
5. Không rerun LIVE143 hoặc dùng lại quyền one-shot. H2=119provenance+1gap,
   H3=1/15, TIM0975km chậm27,66%, SYS1018supported/1inconclusive đều giữ;
   SYS119B2 và LIVE143 là các receipt riêng, không gộp thành kết quả cũ đẹp hơn.

Hermes prepare.lock deny vẫn dừng. Probe sandbox health Permission13/Win10013
không được retry bằng executor khác; LIVE143 có quyền mới riêng đã dùng hết.
Không đọc rawenv/config/auth hoặc token đã retired. Codex sở hữu plan/QA/final
prose, OpenCode coding; mọi handoff mới phải có brief chốt và một writer.

## Trạng thái tiến trình

LIVE14384302exit0/browserclosed. B14439245exit1/browserclosed. UI145 SID
`ses_ea68da3e9ffeAcImRx47DmJmjT`,handle56575exit0,interrupt0/wait0,return có.
B14666972exit0/browserclosed. Không model/browser worker nào trong gói còn chạy.

Evidence: AUD-140/current-gap-map.json và live143-requirement-delta.json;
REF-141/{foundation-sources.json,technical-sources.json,l07-methodology-review.json};
REF-142/{manuscript-claim-audit.json,parent-review.json}; LIVE-143/{result.json,
journal.jsonl,authorization.json,independent-result-review.json}; UI-145/
parent-source-scope.json; BROWSER-146/independent-result-review.json.

Mục tiêu tổng thể vẫn IN_PROGRESS;31mục summary và các receipt này không thay
completion audit từng nhiệm vụ/đầu ra của toàn bộ master.
