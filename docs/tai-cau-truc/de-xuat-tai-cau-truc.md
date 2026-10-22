# Đề xuất tái cấu trúc Travel Lung Tung

Ngày: 2026-10-05. Bản mã đo: `1d18ac3` (local bằng `origin/main`, đã kiểm lại hai chiều).
Trạng thái: **bản đề xuất để anh duyệt**, chưa sửa một dòng mã nào.

Tài liệu này gồm bốn phần theo đúng bốn việc anh nêu: ranh giới giữa các gói, phân tầng nghiệp vụ và hạ tầng, module cào dữ liệu định kỳ và năng lực tìm kiếm cho agent, và bộ khung chạy agent (harness). Phần TikTok đã trả lời riêng ở `khao-sat-nguon-va-ke-hoach.md`, mục 10.

---

## 1. Số đo hiện trạng

Toàn bộ số dưới đây do tôi đếm trực tiếp trên mã, không lấy từ ghi chú cũ.

| Gói | Số tệp mã | Tổng dòng | Ghi chú đo được |
|---|---|---|---|
| `POI_service` | 30 | 3411 | Hạ tầng chiếm 1181 dòng (riêng `memgraph.py` 997), miền chỉ 333 dòng |
| `crawler_service` | 17 | 1513 | Bộ cào + tiền xử lý + khuôn trích xuất |
| `ai_service` | 3 | 535 | `main.py` một mình 518 dòng |
| `backend_service` | 13 | 439 | Tệp endpoint chính **0 dòng**, không có `main.py` |
| `shared_lib` | 5 | 60 | Chỉ có 5 tệp, tổng 60 dòng |

Bốn phép đo nói lên vấn đề rõ hơn mọi mô tả:

1. **`shared_lib` gần như không tồn tại.** 60 dòng, và cả dự án **dùng đúng một lần** (`POI_service/.../memgraph.py` nhập `travel_shared.exceptions`). Thư viện dùng chung đã được tạo ra nhưng không ai dùng.
2. **Mã bị sao chép thay vì chia sẻ.** `enum.py` của `POI_service` và của `backend_service` **giống nhau 100%** (42 dòng, so từng dòng: 0 khác biệt). Có **12 tên lớp trùng** giữa hai gói, gồm cả `BaseRepository`, `BaseFirebaseRepository`, `FireStoreConnector`.
3. **Hai lớp cùng tên mang hai nghĩa khác nhau.** `POI_service/app/core/domain/graph_entities.py` có `POI`, `Category`, `Tag`, `Address`, `Product`, `ContactInfo` với nghĩa "nút trong đồ thị không gian". `backend_service/app/core/domain/POI.py` cũng có đúng những tên đó, nhưng nghĩa là "một bản ghi tài liệu", và chính mã cũng ghi rõ: *"Except the faq, all attributes are doc's id in vector database"*. Người đọc mã không thể biết cái nào là cái nào nếu chỉ nhìn tên lớp.
4. **Không có nơi nào sở hữu nội dung để tìm kiếm.** Giao diện `IDocumentRepository` được **khai báo một chỗ nhưng được tham chiếu ở 6 tệp** (`dependencies/services.py`, `api/mcp/tools.py`, `endpoint_poi_router.py`, `core/services/management.py`, `core/services/poi_service.py`) — và **không có lớp nào hiện thực nó**. Lớp `Description` (gồm `review_id`, `summary_id`, `seo_doc_id`, `faq`) được định nghĩa ở hai nơi và **không được tạo ra ở bất kỳ đâu**.

Một điều tôi phải nói thẳng để anh không hiểu sai hiện trạng: **số vi phạm nhập chéo giữa các gói chỉ có một**. Vấn đề không phải là các gói nhập lẫn nhau, mà là **các gói cùng tồn tại song song với những bản sao của nhau**. Đây là điểm khác biệt quan trọng, vì cách chữa của hai bệnh này hoàn toàn khác nhau: bệnh nhập chéo chữa bằng luật phụ thuộc, còn bệnh sao chép thì luật phụ thuộc không chữa được gì.

---

## 2. Vì sao khó bảo trì: bốn nguyên nhân

**2.1. Ranh giới đang chia theo công nghệ, không chia theo miền nghiệp vụ.** Mỗi gói đều có `api/`, `core/domain/`, `core/infrastructure/`. Cách chia này trả lời câu hỏi "tệp này thuộc loại gì" chứ không trả lời câu hỏi "thay đổi này thuộc về ai". Hệ quả cụ thể: nghiệp vụ lịch trình nằm rải ở `POI_service` (định tuyến), `backend_service` (lưu lịch trình), và `ai_service` (sinh lịch trình), nên một thay đổi về lịch trình phải sửa ở ba gói. Đó chính là cảm giác "khó bảo trì hơn dự kiến" mà anh mô tả.

**2.2. "Dùng chung" bị thay bằng "sao chép".** Vì `shared_lib` không ai dùng, mỗi gói tự định nghĩa lại mô hình. Sửa một chỗ không lan sang chỗ kia, và hai bản sẽ trôi khỏi nhau theo thời gian. Bằng chứng đã có sẵn: `enum.py` giống nhau hôm nay, nhưng `POI.py` của backend đã khác `graph_entities.py` tới 224 dòng.

**2.3. Hạ tầng lấn át nghiệp vụ, và logic điều phối nằm sai chỗ.** Trong `POI_service`, hạ tầng 1181 dòng gấp 3,5 lần miền (333 dòng). Logic điều phối không nằm ở tầng dịch vụ mà nằm trong tầng giao tiếp: `api/mcp/tools.py` tự tải 200 bản ghi rồi tự lọc trong bộ nhớ, và `api/rest/v1/endpoint_ingestion.py` tự quyết định chạy canary rồi mới đẩy nền. Những quyết định đó là nghiệp vụ, không phải giao tiếp, nên không kiểm thử được nếu không dựng cả máy chủ.

**2.4. Không có tầng nào chịu trách nhiệm về "nội dung".** Đây là nguyên nhân trực tiếp làm việc số 3 của anh (tìm kiếm cho agent) bế tắc: muốn tìm kiếm bằng chữ thì phải có chữ để tìm, mà trong hệ thống hiện không có bên nào sản sinh ra chữ đó. `IDocumentRepository` treo ở giữa, `Description` không ai tạo.

---

## 3. Cấu trúc đích đề xuất

### 3.1. Giữ nguyên số dịch vụ, làm rõ ranh giới theo miền

Đề xuất **không tăng số dịch vụ**. Lý do rất cụ thể: bệnh hiện tại là sao chép mô hình, mà tách thêm một dịch vụ thì mô hình lại được sao chép thêm một lần nữa — chi phí vận hành tăng trong khi ranh giới vẫn mờ. Việc cần làm trước là **một mô hình miền dùng chung, một chiều phụ thuộc rõ ràng**, chỉ khi đó mới bàn tới tách dịch vụ.

Năm miền, đặt tên theo việc chứ không theo công nghệ:

| Miền | Chịu trách nhiệm | Hiện đang nằm ở đâu |
|---|---|---|
| `shared` | Mô hình miền dùng chung (POI, Category, Tag, Address, Product, ContactInfo, các enum) và tiện ích chung | `shared_lib` (60 dòng, chưa dùng) + các bản sao trong từng gói |
| `poi` | Đồ thị điểm đến: đọc, ghi, phân loại, quan hệ không gian | `POI_service` (trừ phần định tuyến) |
| `itinerary` | Lịch trình và định tuyến theo lịch trình | Rải ở `POI_service`, `backend_service`, `ai_service` |
| `ingestion` | Cào, làm sạch, định vị, phân loại, nạp vào hệ thống | `crawler_service` + phần canary trong `POI_service` |
| `agent` | Bộ khung chạy agent và các công cụ nó dùng | `ai_service` + `api/mcp` |

Về `backend_service`: đo được là tệp endpoint chính **0 dòng**, không có `main.py`, tổng 439 dòng nhưng chủ yếu là mô hình sao chép. Hai lựa chọn, tôi nêu cả hai kèm hệ quả:

- **Gộp vào miền `itinerary` trong `POI_service`** (tôi nghiêng về cách này): giảm từ 5 gói xuống 4, xoá được 12 lớp trùng, và xoá luôn cái tên `POI` mang hai nghĩa. Hệ quả nếu không làm: hai mô hình `POI` tiếp tục trôi xa nhau, mỗi lần sửa phải sửa hai chỗ và không có phép kiểm nào bắt được lệch.
- **Giữ lại và làm cho nó thật sự chạy** (thêm `main.py`, viết endpoint, thêm vào compose): giữ được ý định tách dịch vụ ban đầu, nhưng phải chấp nhận chi phí đồng bộ hai mô hình, và phải nói rõ nó khác `POI_service` ở điểm nào.

### 3.2. Ba tầng trong mỗi miền, phụ thuộc một chiều

```
domain/       <- không nhập gì từ hạ tầng; chỉ pydantic và thư viện chuẩn
application/  <- dịch vụ và điều phối; chỉ nhập từ domain; định nghĩa "cổng ra"
adapters/     <- fastapi, mcp, driver cơ sở dữ liệu, http; nhập từ application
```

Điểm mấu chốt không phải là ba cái tên thư mục, mà là **luật phụ thuộc một chiều có máy kiểm**. Tôi đã viết sẵn script đếm vi phạm (chính là script dùng để đo ở mục 1), nên việc còn lại là đưa nó thành cổng kiểm tự động. Hệ quả nếu không có cổng này: ba tầng chỉ là quy ước trên giấy, vài tuần sau lại lẫn lộn như cũ.

Kèm theo một việc nhỏ nhưng quan trọng: **đưa logic điều phối ra khỏi tầng giao tiếp**. Cụ thể là chuyển phần "tải 200 bản ghi rồi lọc trong bộ nhớ" từ `api/mcp/tools.py` và phần "canary rồi đẩy nền" từ `api/rest/v1/endpoint_ingestion.py` xuống tầng `application`. Lý do: đây là những quyết định nghiệp vụ, phải kiểm thử được mà không cần dựng máy chủ.

### 3.3. Đặt tên lại để hai khái niệm POI không còn trùng tên

Đây là thay đổi rẻ nhất mà có tác dụng lớn nhất. Cần hai cái tên khác nhau cho hai thứ khác nhau:

- `POI` — nút trong đồ thị không gian, dùng cho tra cứu và định tuyến.
- `POIProfile` (hoặc `POIDocument`) — bản ghi nội dung dùng cho tìm kiếm, gồm tóm tắt, bài viết, câu hỏi thường gặp, đánh giá.

Hệ quả nếu không đổi tên: mọi người đọc mã tiếp tục phải mở hai tệp để biết `POI` đang nói về cái gì, và mọi cuộc trao đổi trong nhóm đều phải kèm câu hỏi "POI nào".

---

## 4. Module cào dữ liệu định kỳ hằng đêm

Hiện trạng đo được: **không có một dòng nào về lịch chạy trong toàn dự án** (không cron, không scheduler, không Celery, không DAG), và `docker-compose.yaml` có 7 dịch vụ cùng các volume nhưng không có thành phần định kỳ. Nghĩa là module này làm mới hoàn toàn, không phải sửa cái đang có — đây là tin tốt, vì thiết kế được ngay từ đầu thay vì chắp vá.

Nguyên tắc thiết kế, kèm lý do:

1. **Không ghi thẳng vào cơ sở dữ liệu.** Tiến trình đêm phải đi qua đúng đường nạp hiện có (`POST /ingestion/batch`, canary 10 bản ghi rồi lô 500). Lý do: ghi thẳng sẽ bỏ qua toàn bộ kiểm tra miền, và tạo ra đường ghi thứ ba trong khi hệ thống đã có hai đường ghi đang lệch nhau.
2. **Có vùng đệm trung gian trước khi nạp.** Dữ liệu cào về phải nằm ở đâu đó kèm dấu vết nguồn (đường dẫn bài, thời điểm đọc) trước khi thành POI. Lý do: nếu không thì không thể trả lời "bản ghi này ở đâu ra" và không thể chạy lại khi lô đêm hỏng.
3. **Chạy lại được, không sinh trùng.** Cần một khoá tự nhiên ổn định cho mỗi địa điểm (nguồn + tên đã chuẩn hoá + toạ độ làm tròn) để chạy hai đêm liên tiếp không tạo hai bản ghi cho cùng một quán. Lý do: đây là chế độ hỏng chắc chắn xảy ra, không phải giả định.
4. **Có báo cáo mỗi đêm.** Cuối lượt chạy phải ghi ra: số bài đã đọc, số địa điểm trích được, số định vị được, số bị loại và vì sao, số trùng đã gộp. Không có báo cáo thì không biết đêm nào hỏng.
5. **Chỉ chạy một lượt tại một thời điểm.** Lượt trước chưa xong thì lượt sau phải chờ, không chồng lên nhau.

Về công cụ đặt lịch: ba lựa chọn, theo thứ tự từ rẻ tới đắt — (a) cron của hệ điều hành gọi một lệnh, (b) một tiến trình chạy nền có sẵn thư viện lịch, (c) một hệ thống xếp hàng đầy đủ. Tôi đề xuất **(a) hoặc (b)**, vì khối lượng mỗi đêm nhỏ và chưa có nhu cầu chạy song song; chọn (c) bây giờ là thêm hạ tầng chưa dùng tới. Việc chọn (a) hay (b) cần anh quyết vì nó phụ thuộc cách anh triển khai.

---

## 5. Năng lực tìm kiếm cho agent

Đây là phần phải nói rõ thứ tự, vì thứ tự sai thì mọi thứ phía sau đều vô nghĩa.

**Bước 1 (bắt buộc, làm trước tiên): có nội dung để tìm.** Hiện `IDocumentRepository` được khai báo mà không ai hiện thực, và `Description` không được tạo ở đâu. **Không có bước này thì chọn công cụ tìm kiếm nào cũng cho ra kết quả rỗng.** Việc cần làm: hiện thực giao diện đó, và bắt đường cào sản sinh ra nội dung (tóm tắt, mô tả, câu hỏi thường gặp) cho mỗi POI.

**Bước 2: chọn công cụ tìm kiếm.** Ba lựa chọn, kèm điều kiện chọn:

- **Chỉ mục toàn văn trong Memgraph** (rẻ nhất, dữ liệu đã nằm ở đó, không thêm hạ tầng). Đo được hiện trạng: trong mã truy vấn đồ thị **không có chỉ mục toàn văn, không có vector, không có `CREATE INDEX`** — chỉ có so khớp `CONTAINS` và `toLower`. Đây là điểm xuất phát rẻ nhất.
- **Cơ sở dữ liệu quan hệ với chỉ mục toàn văn và tìm gần đúng** (mạnh hơn cho tìm theo tên có dấu, viết sai chính tả; đổi lại thêm một hệ thống phải vận hành).
- **Tìm kiếm theo vector** (đắt nhất: cần sinh vector, cần kho vector, cần đo chất lượng).

Đề xuất: **làm (a) trước**, và chỉ chuyển sang (b) hoặc (c) khi có số đo cho thấy (a) không đủ. Lý do: người dùng hỏi "quán hủ tiếu ở Quận 3" là bài toán khớp chữ và lọc theo thuộc tính, chưa cần tới ngữ nghĩa.

**Bước 3: sửa lại công cụ tra cứu của agent.** `explore_pois` hiện nhận đủ tham số (thành phố, quận, đường, nhãn, từ khoá sản phẩm) nhưng bên trong là **một chuỗi ưu tiên**: hễ có địa lý thì từ khoá bị bỏ qua hoàn toàn, và kết quả sau đó được **lọc trong bộ nhớ trên 200 bản ghi vừa tải về**. Nghĩa là câu hỏi "quán hủ tiếu ở Quận 3" hôm nay trả về mọi quán ở Quận 3, không lọc theo "hủ tiếu". Cần đổi thành lọc tổ hợp ở tầng truy vấn.

---

## 6. Bộ khung chạy agent (harness)

Hiện trạng: `ai_service/main.py` một tệp 518 dòng chứa tất cả — `get_gemini_headers`, `analyze_intent`, `execute_agent_loop`, `generate_itinerary_endpoint`, `execute_chitchat`, `chat_endpoint`. Tệp `domains/prompts.py` là tệp rỗng 0 dòng. Trong toàn dự án **không có một phép kiểm thử nào**.

Vì sao harness là điểm sáng mà lại phải sửa: nó là thành phần duy nhất mà chất lượng phụ thuộc vào **hành vi của mô hình**, không phụ thuộc vào mã. Muốn cải tiến nó thì bắt buộc phải đo được, mà hiện tại không có phép đo nào. Không đo thì mọi thay đổi câu lệnh (prompt) chỉ là phỏng đoán.

Đề xuất chia thành năm phần theo việc, và thêm hai thứ đang thiếu:

- **Năm phần:** cổng tiếp nhận yêu cầu; phân tích ý định; vòng lặp gọi công cụ; sinh lịch trình; trả lời thường. Lý do tách: bốn trong năm phần này tiến hoá độc lập, gộp chung một tệp thì sửa phần nào cũng phải đọc cả 518 dòng.
- **Thiếu thứ nhất — hợp đồng công cụ:** mỗi công cụ cần mô tả rõ ràng cho mô hình, kiểm tra tham số trước khi chạy, và câu trả lời lỗi viết cho mô hình đọc. Lý do: hiện `explore_pois` trả về chuỗi lỗi chung chung, mô hình không biết phải sửa tham số nào.
- **Thiếu thứ hai — bộ đo:** một bộ câu hỏi cố định kèm kỳ vọng về công cụ phải gọi, chạy lại sau mỗi thay đổi, và ghi vết từng lượt (gọi công cụ nào, tham số gì, mất bao lâu). Số cần đo: tỉ lệ gọi đúng công cụ, tỉ lệ tham số hợp lệ, tỉ lệ trả lời có căn cứ.

Quan hệ giữa phần này và phần 5 rất chặt: bộ đo sẽ chỉ ra ngay là agent gọi `explore_pois` với từ khoá rồi nhận kết quả không lọc — đó là loại lỗi mà đọc mã rất khó thấy nhưng chạy bộ đo thì thấy sau một lần.

---

## 7. Lộ trình đề xuất, có cổng dừng

**GĐ1 — Chốt ranh giới, chưa sửa mã.** Anh quyết bốn việc ở mục 8. Ra: tài liệu này được duyệt. Cổng: anh xác nhận.

**GĐ2 — Một mô hình miền dùng chung.** Chuyển mô hình vào `shared_lib`, đổi tên hai khái niệm POI, xoá bản sao. Đây là việc rẻ nhất và mở đường cho mọi việc sau. Cổng: script kiểm trùng lặp báo 0; số tệp bị ảnh hưởng nằm trong dự kiến.

**GĐ3 — Cổng kiểm phân tầng + gom logic điều phối về tầng dịch vụ.** Cổng: cổng kiểm chạy sạch, và không vỡ hành vi hiện có (kiểm bằng cách gọi lại các điểm truy cập API).

**GĐ4 — Nội dung và tìm kiếm.** Hiện thực phần đọc tài liệu, cho đường cào sản sinh nội dung, dựng chỉ mục toàn văn, sửa công cụ tra cứu của agent. Cổng: một bộ câu hỏi thật chạy qua agent và trả về kết quả có lọc đúng theo từ khoá.

**GĐ5 — Cào định kỳ + bộ đo harness.** Cổng: chạy hai đêm liên tiếp không sinh bản ghi trùng; bộ đo cho ra số đầu tiên.

Việc **không nên làm**, kèm lý do: viết lại từ đầu (mã không hỏng, chỉ lệch tổ chức); tách thêm microservice trước khi có mô hình dùng chung (sẽ nhân bản bản sao); đổi cơ sở dữ liệu (không có bằng chứng nào cho thấy Memgraph là nút cổ chai); thêm kho vector trước khi có nội dung (sẽ dựng kho chứa rỗng).

---

## 8. Việc cần anh quyết

1. **`backend_service`**: gộp vào miền `itinerary` (tôi đề xuất), hay giữ lại và làm cho nó chạy thật?
2. **`shared_lib`**: đồng ý biến nó thành mô hình miền dùng chung thật (khoảng 300 dòng được chuyển vào), hay muốn giữ cách mỗi gói tự định nghĩa?
3. **Công cụ tìm kiếm**: bắt đầu bằng chỉ mục toàn văn trong Memgraph (tôi đề xuất), hay đã có ý định dùng kho vector từ đầu?
4. **Đặt lịch cào đêm**: cron hệ điều hành hay tiến trình chạy nền có thư viện lịch? Việc này phụ thuộc cách anh triển khai máy chủ.
5. **Bộ đo harness**: anh có bộ câu hỏi nào đang dùng để thử bằng tay không? Nếu có thì tôi dùng chính nó làm nền, không tự nghĩ ra bộ mới.

---

## 9. Kết luận

Cảm nhận của anh là đúng, nhưng nguyên nhân hơi khác dự đoán. Không phải các gói đang nhập lẫn nhau — chỉ có một chỗ như vậy. Vấn đề là các gói **song song tồn tại với những bản sao của nhau**: `shared_lib` 60 dòng gần như không được dùng, hai tệp `enum.py` giống nhau 100%, 12 tên lớp trùng, và hai khái niệm `POI` khác nghĩa nhưng cùng tên. Vì vậy cách chữa hiệu quả nhất không phải là tách thêm dịch vụ hay đổi cơ sở dữ liệu, mà là **một mô hình miền dùng chung, đặt tên lại cho rõ, và một cổng kiểm phụ thuộc chạy tự động** — việc rẻ nhất, mở đường cho tất cả các việc còn lại.

Hai việc số 3 và số 4 của anh hoá ra lại móc vào cùng một chỗ: muốn agent tìm kiếm được thì phải có nội dung, mà nội dung thì chưa có bên nào sản sinh. Nên thứ tự đúng là: sửa ranh giới mô hình trước, rồi mới làm nội dung và tìm kiếm, rồi mới tới cào định kỳ và bộ đo. Làm ngược lại thì mỗi bước sau đều phải xây trên một nền còn đang đổi tên.
