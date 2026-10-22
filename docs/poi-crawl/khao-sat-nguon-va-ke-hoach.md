# Khảo sát nguồn và kế hoạch cào POI du lịch

Người viết: trợ lý phân tích. Ngày: 2026-10-04.
Phạm vi: khảo sát bằng thử nghiệm thật, không phải phỏng đoán. Mọi kết luận dưới đây đều có lệnh và kết quả kèm theo.
Trạng thái: **chờ chủ dự án duyệt**, chưa viết mã cào.

---

## 1. Câu hỏi cần trả lời

Anh muốn đi theo đường: tìm bài tổng hợp (TikTok, bài viết, sheet chia sẻ, list Google Maps) → tự phân loại địa điểm theo bộ nhãn do mình quy định → dùng Tavily, Serp Google Maps, Firecrawl cào dữ liệu thô của từng địa điểm → làm sạch và nạp vào hệ thống.

Khảo sát này trả lời ba câu: (a) mỗi loại nguồn thực tế đọc được đến đâu, (b) dữ liệu thô thu được có khớp với cái mà `POI_service` đòi hỏi không, (c) cần thêm gì trước khi viết mã.

---

## 2. Thử cào thủ công: kết quả thật

Cách thử: dùng công cụ đọc trang và Chrome chạy riêng (headless, không đụng phiên Chrome đang mở của anh). Không tải tệp nào về máy, chỉ đọc nội dung.

| Nguồn | Cách thử | Kết quả | Kết luận |
|---|---|---|---|
| Bài viết tổng hợp (vinwonders, reviewamthuc) | đọc trang | Lấy được đầy đủ: tên quán, địa chỉ, giờ mở cửa, giá tham khảo, điểm Google Maps. Bài "Top 15 quán hủ tiếu" cho 10 địa điểm có cấu trúc rất đều | **Dùng được ngay** |
| Google Sheet công khai | đọc qua đường xuất CSV | `docs.google.com/spreadsheets/d/<id>/export?format=csv` trả về CSV thật, có dòng tiêu đề | **Dùng được ngay** |
| TikTok | đọc tĩnh | Trả về chuỗi "Please wait..." (tường chặn bot) | Không đọc được bằng cách thường |
| TikTok | Chrome riêng | Lấy được caption và khối dữ liệu `__UNIVERSAL_DATA_FOR_REHYDRATION__`. Caption ví dụ: "Tổng hợp 4 quán nên ăn trên đường Hai Bà Trưng quận 1" | **Đọc được phần mô tả, nhưng danh sách quán nằm trong video, không có trong caption** |
| Threads (nơi phát tán sheet) | Chrome riêng | DOM chỉ 49 KB, không có bài viết nào; chỉ có metadata trang | Cần phiên đăng nhập hoặc API chính thức |
| Facebook | Chrome riêng | Chỉ đọc được metadata của trang (tên trang, số người theo dõi). Nội dung bài viết không có | Cần phiên đăng nhập |
| Google Maps (trang địa điểm) | Chrome riêng | HTML gốc **có** khối `APP_INITIALIZATION_STATE` chứa dữ liệu, ví dụ: `[[[31348.69,106.68605439999999,10.842931199999999],...` nhưng phần thân là mảng lồng nhau đã mã hoá, chưa lấy ra thẳng được tên, địa chỉ, số sao, giờ mở cửa | Đọc được nhưng phải giải mã; đây đúng là việc mà SerpApi Google Maps làm sẵn |
| Tìm kiếm | công cụ tìm kiếm mặc định | Chạy ở chế độ không khoá, thỉnh thoảng bị chặn 403 | Cần khoá để ổn định |

Hai phát hiện ngoài dự kiến, đáng chú ý:

1. **Trào lưu sheet ẩm thực là thật và có bài báo lớn viết về nó.** Tuổi Trẻ đưa tin về sheet "Food Tour SG" của tài khoản Threads `tipslife_byvulpinn`, hơn 400 địa điểm, có tên đường, khu vực, phân loại món ăn, giờ mở cửa, giá tham khảo; và sheet thứ hai của tài khoản `nhuquynh_d` phân loại theo quận kèm menu. Nghĩa là nguồn anh muốn cào đã tồn tại ở dạng có cấu trúc — chỉ là nó nằm trên Threads chứ không nằm trên web mở.
2. **Dữ liệu đúng như cái hệ thống cần.** Bài reviewamthuc cho sẵn tên + địa chỉ + giờ + giá + điểm Google Maps: gần như toàn bộ trường mô tả của `POI`. Cái còn thiếu là **toạ độ và quận** — mà `POI` bắt buộc phải có. Nên bước định vị là bắt buộc, không phải tuỳ chọn.

---

## 3. Không có khoá cho Tavily, SerpApi, Firecrawl

Đã kiểm: không có biến môi trường nào cho `TAVILY_API_KEY`, `SERPAPI_API_KEY`, `FIRECRAWL_API_KEY`, `GOOGLE_MAPS_API_KEY`. Cấu hình Hermes cũng không khai. Trong repo cũng không có dấu vết nào của ba dịch vụ này (ngoài một dòng nhắc tới google_maps trong prompt của ai_service).

Hệ quả cụ thể: Tavily và Firecrawl **không thay thế được** bước đọc bài tổng hợp (việc đó đang làm được bằng công cụ đọc sẵn có), nhưng cần cho hai việc khác: tìm bài theo chủ đề ở quy mô lớn, và vượt tường chặn của các trang khó. Còn SerpApi Google Maps là mảnh **không có gì bù được** trong kế hoạch, vì nó trả về thẳng tên, địa chỉ, toạ độ, số sao, giờ mở cửa, nhóm của Google — đúng những trường `POI` bắt buộc mà không phải tự giải mã khối mã hoá.

---

## 4. Bộ phân loại đề xuất

Tệp đầy đủ: `docs/poi-crawl/phan-loai-dia-diem.json` (đọc trực tiếp được, và cũng dùng được để tạo nút `Category`/`Tag` trong đồ thị).

Ba tầng, mỗi tầng có lý do tồn tại riêng:

- **Nhãn chính** (chọn đúng một): 11 nhãn, gồm `quan_an`, `an_vat`, `cafe`, `trang_mieng`, `nha_hang`, `bar`, `tham_quan`, `vui_choi`, `mua_sam`, `luu_tru`, `khac`. Tầng này tồn tại vì `POI.id` được sinh từ nhãn chính, và AI agent tra cứu theo id nhãn nên nhãn sai thì id sai và agent không tìm thấy.
- **Nhãn phụ** (nhiều nhãn, danh sách đóng): món ăn, hình thức, thời điểm, đối tượng, không gian. Tầng này tồn tại vì nó là thứ dùng để lọc theo sở thích, và vì `Tag` trong hệ thống chỉ có id và tên nên phải là danh sách đóng chứ không phải văn bản tự do.
- **Hình dạng** (`diem` hoặc `khu`): tách riêng khỏi nhãn vì dữ liệu thật có cả "hẻm 76 Hai Bà Trưng", "phố ẩm thực Vĩnh Khánh", "chợ đêm Tân Định" — những chỗ không có một địa chỉ duy nhất. Nếu nhét chúng vào cùng một khuôn với một quán thì lịch trình sẽ tính sai: đến một con hẻm thì không phải ghé 30 phút rồi đi.

Điểm đáng lưu ý: `khac` (Chưa Rõ) là nhãn có chủ đích, không phải nhãn rác. Nó tồn tại để chặn việc đoán bừa, và để mọi bản ghi thiếu bằng chứng vẫn được giữ lại và đưa vào danh sách chờ kiểm thay vì bị bỏ.

---

## 5. Luồng đề xuất và điểm nối vào mã hiện có

Luồng sáu bước:

1. **Tìm bài** — theo chủ đề và địa bàn, thu về danh sách URL ứng viên (bài blog tổng hợp, sheet công khai, bài mạng xã hội).
2. **Trích danh sách địa điểm** — từ mỗi bài rút ra các địa điểm thô: tên, địa chỉ nếu có, đoạn mô tả, và nguồn.
3. **Phân loại** — gán nhãn chính, nhãn phụ, hình dạng theo bộ ở mục 4. Bước này chạy **trước** khi cào chi tiết, đúng như anh muốn.
4. **Định vị và làm giàu** — tra Google Maps cho từng địa điểm để lấy toạ độ, quận, thành phố, giờ mở cửa, số sao, nhóm của Google. Đây là bước bắt buộc vì `POI` đòi `longitude`, `latitude`, `district`, `city`.
5. **Làm sạch và gộp trùng** — chuẩn hoá tên, cắt các tiền tố quảng cáo, gộp bản ghi trùng theo tên và khoảng cách toạ độ.
6. **Nạp** — tạo `Category`/`Tag` trong đồ thị trước, rồi nạp POI qua API.

Điểm nối với mã đang có (đã đọc để xác nhận, không suy đoán):

- Bộ cào hiện tại dùng thư viện `crawl4ai`, lớp cơ sở `BaseDetailCrawler` ở `crawler_service/app/pipelines/crawling/base/detail_crawler.py` với hai hàm phải viết: `get_hook()` và `crawl_with_schema()`. Thêm nguồn mới nghĩa là thêm một lớp con theo đúng khuôn này, không phải dựng bộ cào song song.
- Bộ cào phân nhánh theo `crawl_type` (`hotel`, `activities`, `destination`, `destinations`, `explore`), nạp khuôn trích xuất từ `crawl_schemas/css/traveloka/<loại>/`. Nguồn mới nên đi cùng cơ chế này để không phá luồng `discover` hiện có.
- API nạp: `POST /ingestion/batch` nhận một mảng dict, tự kiểm tra kiểu theo `POI`, chạy 10 bản ghi đầu như lô canary đồng bộ rồi mới đẩy phần còn lại vào nền theo lô 500, tiến độ báo qua `GET /ingestion/stream/{job_id}`. Canary hỏng thì trả 422 và không nạp gì.
- Trường bắt buộc của một POI: `name`, `longitude`, `latitude`; nếu có `address` thì `district` và `city` bắt buộc; `poi_categories[0]` quyết định tiền tố id.
- Cảnh báo đã kiểm chứng trong mã: nhãn chính không tồn tại trước khi nạp thì POI rơi vào tiền tố `UNCATEGORIZED`. Vì vậy bước tạo nhãn phải chạy trước bước nạp, và có phép đếm kiểm chứng bằng 0.

---

## 6. Việc phải quyết trước khi viết mã

1. **Bộ nhãn**: duyệt 11 nhãn chính, hay cắt bớt? Tôi đề xuất giữ đủ vì mỗi nhãn ứng với một hành vi lịch trình khác nhau.
2. **Hình dạng khu/phố/chợ**: giữ như thuộc tính `hinh_dang` (đề xuất), hay muốn tách thành một nhãn chính riêng?
3. **Đơn vị ngân sách**: mã đang so `daily_budget < 50` và `<= 150` (`graph_entities.py:71-79`). Đây là đơn vị gì — nghìn đồng, hay đô? Dữ liệu cào về là VNĐ, nên nếu đơn vị là đô thì phải có quy đổi, không thì mọi quán bình dân sẽ bị xếp nhầm thành cao cấp.
4. **Khoá API**: có mua khoá SerpApi (Google Maps) không? Đây là khoá duy nhất mà tôi thấy khó thay thế. Firecrawl và Tavily là tiện, chưa phải bắt buộc cho đợt đầu.
5. **Phiên đăng nhập**: Threads, Facebook, Instagram đều cần đăng nhập. Anh có cho phép dùng phiên Chrome thật của anh để đọc công khai không? Việc này nghĩa là tự động hoá trên tài khoản của anh, có rủi ro khoá tài khoản, nên tôi không tự làm.
6. **Ba link mẫu thật**: ba link kiểu list Google Maps đã chia sẻ (danh sách điểm đã lưu). Đây là loại duy nhất tôi chưa thử được vì không có mẫu thật.
7. **Phạm vi và khối lượng đợt đầu**: chỉ TP.HCM, và khoảng bao nhiêu POI (ví dụ 300–500) để tôi đặt cổng đo?

---

## 7. Kế hoạch theo giai đoạn, có cổng dừng

**GĐ0 — Khảo sát và chốt phân loại** (đang ở đây). Ra: tệp này và `phan-loai-dia-diem.json`. Cổng: anh duyệt bộ nhãn và trả lời mục 6.

**GĐ1 — Chốt nguồn ưu tiên và dựng bộ trích danh sách.** Chọn hai loại nguồn làm trước (đề xuất: bài viết tổng hợp và sheet công khai, vì cả hai đã chứng minh đọc được). Ra: hàm trích danh sách địa điểm thô từ một URL, chạy được trên 10 bài. Cổng: đưa ra 50 bản ghi thô kèm nguồn để anh soi.

**GĐ2 — Định vị và làm giàu.** Nối Google Maps để lấy toạ độ, quận, thành phố, giờ, số sao. Ra: bản ghi đủ trường bắt buộc. Cổng: 100% bản ghi có toạ độ và quận hợp lệ, đo bằng script đếm.

**GĐ3 — Phân loại.** Áp bộ nhãn, chạy được cả bằng luật và bằng mô hình, mỗi bản ghi lưu lại lý do gán nhãn. Cổng: lấy mẫu 30 bản ghi, đo tỉ lệ gán đúng; dưới 80% thì chỉnh bộ nhãn chứ không nạp.

**GĐ4 — Làm sạch, gộp trùng, tạo nhãn trong đồ thị.** Cổng: số bản ghi trùng đã gộp, và số nút `Category`/`Tag` đã tạo khớp với bộ nhãn.

**GĐ5 — Nạp và kiểm chứng.** Nạp theo canary 10 rồi lô 500 qua API hiện có. Cổng: đếm số POI có tiền tố `UNCATEGORIZED` bằng 0; thử dựng một lịch trình trên dữ liệu mới; đối chiếu ngược 20 POI với nguồn gốc.

---

## 8. Rủi ro và giới hạn

- **Điều khoản nền tảng**: TikTok, Facebook, Instagram, Threads đều cấm thu thập dữ liệu tự động trong điều khoản. Đợt đầu nên bám vào nguồn công khai thật sự (bài viết, sheet được chia sẻ công khai) và coi phần mạng xã hội là việc riêng anh quyết.
- **Nội dung nằm trong video**: TikTok là video, danh sách quán nằm ở phần hình và tiếng. Hệ thống hiện không có công cụ chuyển tiếng nói thành văn bản, nên TikTok chỉ dùng được phần caption và phần bình luận. Muốn moi được nội dung video thì phải thêm một bước ngoài phạm vi này.
- **Sheet có thể bị khoá lại**: sheet chia sẻ công khai có thể đổi quyền bất kỳ lúc nào. Bản ghi phải lưu lại nguồn và thời điểm đọc để biết dữ liệu cũ.
- **Dữ liệu nguồn không đáng tin tuyệt đối**: các bài tổng hợp tự nhận "chỉ mang tính tham khảo", giá và giờ mở cửa có thể đã cũ. Vì vậy bước định vị qua Google Maps phải là nguồn chuẩn cho toạ độ, giờ, và trạng thái còn mở hay đã đóng.
- **Chưa có gì được chạy thật**: toàn bộ tài liệu này dựa trên đọc mã và đọc nguồn. Chưa dịch vụ nào được khởi động, chưa ghi vào cơ sở dữ liệu.

---

## 9. Kết luận

Hướng đi anh đề ra là làm được, nhưng thứ tự và điểm nghẽn khác với dự đoán ban đầu. Phần dễ nhất — đọc bài tổng hợp và đọc sheet — đã chứng minh chạy được ngay bằng công cụ sẵn có. Phần khó không nằm ở chỗ cào, mà ở ba chỗ: mạng xã hội cần phiên đăng nhập, nội dung TikTok nằm trong video nên chỉ moi được phần chữ, và toạ độ thì bắt buộc phải có nên bắt buộc phải có nguồn định vị chuẩn. Vì vậy đề nghị của tôi là đợt đầu bám vào hai nguồn công khai đã kiểm chứng, chốt bộ nhãn, và mua đúng một khoá là SerpApi cho Google Maps; phần mạng xã hội tách thành giai đoạn riêng sau khi có quyết định của anh về phiên đăng nhập.

---

## 10. TikTok: tải về được không, có API nào không

Câu hỏi đặt ra sau buổi khảo sát: có thể tải video về, hoặc có API nào cào dữ liệu TikTok không. Kết quả kiểm tra:

**10.1. Đường đọc không cần khoá — đã thử và chạy được.** TikTok có endpoint oEmbed công khai, trả về JSON không cần xác thực:

```
GET https://www.tiktok.com/oembed?url=<link video>
```

Kết quả thật khi gọi thử: `type=video`, `title` chính là caption ("Tổng hợp 4 quán nên ăn trên đường Hai Bà Trưng quận 1..."), `author_name`, `author_url`, kèm đoạn HTML nhúng. **Nhưng đó chỉ là phần chữ ở lớp ngoài:** caption chỉ nêu chủ đề, không có tên quán, không có địa chỉ.

> ⚠️ **Sửa lại ngày 05-10.** Câu trên chỉ đúng với phần caption. Trang video còn phơi một khối JSON gốc chứa **phụ đề tự sinh, có cả track tiếng Việt**, đọc thẳng ra văn bản được. Xem `tiktok-trich-xuat.md`. Kết luận ở mục 10.5 dưới đây cũng đã được sửa.

**10.2. API chính thức: không có đường nào cho dự án thương mại.** TikTok có ba nhóm API, và cả ba đều không dùng được cho việc này:

- **Research API** (đọc dữ liệu công khai về nội dung và tài khoản): chỉ nhận tổ chức nghiên cứu phi lợi nhuận, và theo điều khoản chỉ mở cho người ở Mỹ, châu Âu, Canada, Brazil. Một dự án sản phẩm ở Việt Nam không thuộc diện.
- **Display API**: yêu cầu người dùng tự đăng nhập và cấp quyền cho ứng dụng — chỉ đọc được dữ liệu của chính người đã cấp quyền, không đọc được bài của người khác.
- **Content Posting API**: để đăng bài lên TikTok, không phải để đọc.

**10.3. Bên thứ ba có thu phí — đọc được, kể cả phần chữ trong video.** Trong lúc tìm đã thấy các dịch vụ thương mại làm đúng việc này: SearchApi.io có engine `tiktok_video` trả về caption, lượt thích, bình luận; một nhóm dịch vụ Apify có sẵn scraper TikTok; và có dịch vụ chuyên trả về **metadata kèm transcript và comment** cho TikTok, Instagram, YouTube. Cần kiểm giá và điều khoản trước khi dùng.

**10.4. Tải video về rồi tự chuyển thành chữ.** Đây là đường tự chủ nhưng có hai chặn:

- Máy anh **không có `yt-dlp`** (đã kiểm). Và luật cứng ngày 18-09 của anh cấm tôi tải tệp về máy, nên tôi không được tự cài hay tự tải. Việc này phải anh duyệt bằng lời rồi ghi vào `cho_phep_tai.txt`.
- Kể cả tải được, muốn moi được tên quán thì phải có bước chuyển tiếng nói thành văn bản. Hermes có sẵn phần này nhưng đang cấu hình **tiếng Anh, model `base`** — dùng cho tiếng Việt sẽ phải đổi cấu hình và đo lại chất lượng, vì tên riêng quán ăn là chỗ dễ sai nhất khi chuyển tự động.

**10.5. Kết luận về TikTok (đã sửa ngày 05-10).** ⚠️ Bản đầu của mục này xếp TikTok vào nguồn **kém hiệu quả nhất** và đề nghị bỏ khỏi đợt đầu. **Kết luận đó sai**, vì tôi mới kiểm phần caption rồi kết luận mà chưa mở khối JSON gốc của trang.

Sự thật đã kiểm chứng: TikTok tự sinh phụ đề cho video (chạy chính Whisper, track `Source = ASR`, `LanguageCodeName = vie-VN`) và phơi nó trong khối JSON của trang. Đọc khối đó rồi đọc tệp WebVTT là ra **toàn bộ lời nói kèm mốc thời gian** — có tên quán, khu vực, món, giá. Đo trên 3 video của 3 tài khoản: 3/3 đều có track tiếng Việt.

Vì vậy TikTok **không còn là nguồn kém nhất mà là một trong những nguồn tốt nhất**: không cần khoá API, không cần tải video, không cần mua dịch vụ. Chi tiết phương pháp, chi phí, rủi ro và việc cần quyết: xem `tiktok-trich-xuat.md`.

Phần rủi ro vẫn giữ nguyên và cần anh quyết: đọc tự động ở quy mô lớn đi ngược điều khoản sử dụng của nền tảng, và việc chấp nhận rủi ro đó là quyết định của anh, không phải của tôi.
