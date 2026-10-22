# Bốn giai đoạn chính và Finalizing phase

Cập nhật: 18/10/2026. Chỉ đạo mới của người dùng thay thế cách triển khai dàn trải trước đây.

**Amendment mới nhất đã duyệt:** user duyệtS1–S6, ưu tiên luồng **nhận thông tin người dùng → recommending → routing → kết quả dùng được**, rồi thí nghiệm/báo cáo. **Phase5 là “Finalizing phase” tích hợp toàn bộ cơ chế mới**, gồm grow-with-user, crawlerlegacy/travelagency/socialweb và mở rộng đã chốt khác. Không chờ chúng để qua phase2/3. Xem PHASE2_SCOPE_FOR_APPROVAL_VI.md; mọi note cũ đặt crawlP0/P1 làm gatephase2 đã bị thay thế.

## Phân công

- Codex: lập kế hoạch, xác định yêu cầu theo đề cương, thiết kế tình huống QA, đọc mã, kiểm chứng độc lập và duyệt kết quả.
- OpenCode: thực hiện mã, hiện thực kiểm thử theo tiêu chí Codex và tạo báo cáo tương tác bằng kỹ năng đã cài. Khi cần AI-box, dùng `aibox/ds/deepseek-flash`, DeepSeek V4.1 Flash theo xác nhận của người dùng; chọn Go cho việc đơn giản theo quy tắc chi phí bên dưới. Không dùng tuyến ghi rõ V4.0.
- Mỗi thời điểm tập trung một gói việc có ranh giới rõ. Không mở thêm nhánh không cần cho đề cương. Ghi checkpoint sau mỗi mốc lớn.

### Quy tắc `/plan` của Codex — bổ sung theo người dùng

`/plan` áp dụng cho **Codex**: trước mọi bàn giao, Codex phải lập và chốt kế hoạch gồm mục tiêu, phạm vi tệp, thứ tự thực hiện, tình huống QA và điều kiện nhận. OpenCode nhận kế hoạch đã chốt để thực hiện mã; không tự lập kế hoạch thay Codex, không tự đổi phạm vi hay tiêu chí. Không giao agent một yêu cầu mở kiểu “hãy tự lên kế hoạch và làm”. Không đồng nhất việc viết chữ `/plan` trong brief với bật chế độ kỹ thuật. Trong phiên hiện tại, chế độ nền tảng do hệ thống điều khiển; Codex vẫn phải thực hiện bước lập kế hoạch trước khi giao việc, không tuyên bố đã chuyển mode nếu không có xác nhận. OC047 đã được giao bằng brief/kế hoạch Codex viết trước chỉ đạo bổ sung; không khởi chạy lại gây phí.

### Chọn model theo chi phí — chỉ đạo bổ sung của người dùng

- AI-box cung cấp DeepSeek mới, mạnh hơn và có tính phí: dành cho phân tích/lập trình khó, thiết kế quan trọng hoặc lỗi phức tạp. Tuyến hiện dùng là `aibox/ds/deepseek-flash` (V4.1 theo người dùng).
- OpenCode Go là tuyến DeepSeek thấp hơn, miễn phí theo người dùng: ưu tiên việc đơn giản, lặp lại, chỉnh trình bày hoặc tạo bản nháp khi có thể đáp ứng chất lượng. Phải xác định đúng alias và khả dụng; từng có lỗi hết hạn mức, không giả định lần gọi tiếp theo sẽ thành công.
- Chạy kiểm thử xác định trực tiếp, không gọi model chỉ để chạy lệnh. Gom việc liên quan thành một brief rõ, không gọi nhiều model để tạo lại cùng báo cáo. Không tự chuyển từ Go sang tuyến tính phí cho việc không cần thiết.
- Không dùng tuyến ghi rõ V4.0; chỉ đạo này vẫn giữ nguyên. Không đổi model giữa phiên đang chạy hoặc đổi cấu hình toàn cục. OC047 đã được giao AI-box trước chỉ đạo chi phí; giữ phiên đó, không gọi lại.

## 1. Kiểm chứng — findings đã chốt, QA tiếp tục từng bản sửa

Rà soát những mô-đun đã xây dựng, chấp nhận hoặc trả lại các bản giao OC040/042/043/045/046, lập bảng QA theo yêu cầu và kiểm tra luồng thật khi có điều kiện. Phân biệt mã đã có, kiểm thử giả lập, kiểm thử động cơ thật và tích hợp toàn hệ thống.

Đầu ra: danh sách lỗi có bằng chứng và mức ưu tiên; báo cáo tương tác tiếng Việt cho từng mô-đun, tổng quan kiến trúc và tiến độ. Không chờ hết QA mới cho người dùng xem trạng thái hiện tại.

Điều kiện chuyển: mọi mô-đun quan trọng đã được rà soát; lỗi và giới hạn đã xác định; phạm vi sửa cần thiết theo đề cương được chốt. Không coi phát hiện lỗi là lý do thêm tính năng ngoài phạm vi.

## 2. Hoàn thiện mã theo đề cương — trọng tâm hiện tại

**Phạm vi nguồn do người dùng xác nhận18/10:** hệ thống chính dùng POI OSM; crawler legacy Traveloka/Vietravel vẫn hoãn vì không khả thi mở rộng. Không mở lại legacy hoặc dùng việc thiếu nguồn đó để chặn phase2/thí nghiệm. Gói crawl xã hội/web P0/P1 được yêu cầu sau này là phạm vi riêng; không gộp thành legacy đã phục hồi hoặc claim dữ liệu mạng xã hội khi mới có capture web. File primary chưa có OSM ID/URL; không tự tạo lineage OSM.

Codex lập từng gói sửa và ca kiểm thử; OpenCode triển khai. Ưu tiên nhập POI đầy đủ, giữ phạm vi dữ liệu do người dùng chọn xuyên suốt AI/planner, kết nối tuyến đường và tích hợp dịch vụ. Codex kiểm chứng lại trước khi nhận. Chỉ sửa những phần cần cho mục tiêu luận văn và thí nghiệm.

**Thay đổi phạm vi:** không dùng Ollama/local LLM để phân loại ý định; dùng Jev của TypeSafe. AI063 đã triển khai và qua QA offline cùng pilot API thật 30 câu tổng hợp; xem checkpoint 2026-10-18-jev-live-pilot-accepted.md. Còn cấu hình runtime có chủ đích và kiểm định tích hợp; pilot không thay thí nghiệm chính. Jev chỉ phân loại/định tuyến; không thay model sinh câu trả lời/lập lịch. Không âm thầm fallback về Ollama.

Điều kiện chuyển: phiên bản mã/dữ liệu/cấu hình được đóng băng; các luồng và ràng buộc thiết yếu chạy được; không còn lỗi chặn thí nghiệm. Các phụ thuộc chưa có phải ghi rõ, không giả lập thành kết quả thật.

## 3. Chạy thí nghiệm

Chạy bộ thí nghiệm đã đăng ký: 20 cặp tình huống H2, năm hồ sơ nhân tạo × ba điều kiện bộ nhớ, các nhóm đối kháng và kiểm tra hệ thống. Lưu đầu vào, phiên bản, model, cấu hình, lỗi, độ trễ và chi phí có phạm vi đo rõ. Hồ sơ nhân tạo không phải người tham gia H1. Không thực hiện H1 ở giai đoạn này.

Điều kiện chuyển: dữ liệu thí nghiệm và phân tích có thể tái lập; báo cáo đầy đủ thất bại và giới hạn; không dùng kết quả giả lập làm bằng chứng khoa học.

## 4. Báo cáo và chờ người dùng quyết định

Giao báo cáo tương tác tiếng Việt ngắn gọn: kiến trúc, chức năng từng mô-đun, kết quả QA, kết quả thí nghiệm và phần còn thiếu. Không tự bắt đầu H1 hoặc tiếp tục viết luận văn. Người dùng sẽ quyết định tiến hành H1 hay viết tiếp luận văn.

## Quy cách báo cáo

Màn hình đầu chỉ gồm bốn giai đoạn, số liệu thiết yếu và sơ đồ dễ hiểu. Nhấn vào mô-đun để xem: làm gì, đã làm gì, kiểm chứng đến đâu, còn thiếu gì. Bằng chứng mã/kiểm thử để trong phần mở rộng. Không hiển thị phần trăm hoàn thành không có cơ sở. Dùng nhãn rõ: **đã kiểm chứng**, **chờ QA**, **chưa hoàn tất**.

## P2 sau bốn giai đoạn — Agent Memory theo khách hàng

User đã đổiphase5 thành Finalizing phase chung: memorygrow-with-user và crawler đều thuộcphase5, sau4phase chính và kế hoạch triển khai được chốt; không mở implementation trongphase2.

Chỉ đạo bổ sung 18/10/2026: nghiên cứu Hermes và2–3 harness khác, đề xuất dùng harness/component hay tự xây lớp điều phối/memory để giữ preference và cải thiện theo khách hàng. Một sub-agent có thể nghiên cứu song song theo brief RS049; **triển khai/migration/integration chỉ sau khi hoàn tất bốn giai đoạn**, không cần chờ viết luận án và không tự khởi động H1. Không biến nghiên cứu P2 thành nhánh sửa mã hay điều kiện chặn bốn phase. Tôn trọng nền tảng memory hiện có và planner/validator, tenant, source scope.


## Bổ sung nguồn POI xã hội/web — ưu tiên người dùng18/10/2026

Gói OC050 do Codex lập kế hoạch, sub-agent thứ ba và cuối cùng giám sát OpenCode triển khai: **P0** quy trình ingest và nguồn fetch nhanh có tên + địa chỉ + mô tả/review; **P1** crawler HTTP nguồn dễ/web tĩnh chạy được; **P2** nguồn động/chống bot khó chỉ nghiên cứu/backlog. Đây là phạm vi bổ sung được yêu cầu rõ, không tự mở thêm nhánh. Mã mới vẫn phải qua gate phase1/2 trước đóng băng phase3. Dữ liệu mới tách primary; không nhập graph thật trong gói này. Xem T057–T059 và handoffs/OC-050/brief.md.


18/10 execution amendment (historical snapshot, superseded for current phase):
Hermes-first routing/localdomain/guard rules remain in EXECUTOR_POLICY.md;
OC050interrupted/unaccepted and phase1current described that earlier checkpoint.
Current20/10 scope is phase3 outcomes/systemverification then phase4report;
all crawler/newharness integration is Finalizing phase per user's later approval.
New20/10 coordination instruction requires proactive parallel subagents for
independent tasks, with one writer per file and Codex-authored plans.
