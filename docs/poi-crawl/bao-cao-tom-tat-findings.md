# Báo cáo tóm tắt findings: kế hoạch tìm kiếm và cào dữ liệu tăng cường từ mạng xã hội

**Đề tài:** Travel Lung Tung (TVLT_2026) — bổ sung dữ liệu điểm đến (POI) bằng dữ liệu cào từ mạng xã hội và nguồn công khai.
**Người thực hiện:** trợ lý phân tích. **Thời gian:** 2026-10-04 → 2026-10-05.
**Bản mã đo:** `1d18ac3` (local bằng `origin/main`, đã kiểm hai chiều: lệch `0 0`).
**Trạng thái:** báo cáo kết quả khảo sát, **chưa viết mã cào**, chờ chủ dự án duyệt.

**Nguyên tắc của báo cáo:** mọi kết luận dưới đây đều từ thử nghiệm thật, không phải phỏng đoán. Chỗ nào chưa kiểm thì ghi rõ là chưa kiểm.

**Tài liệu gốc kèm theo:**

- `docs/poi-crawl/khao-sat-nguon-va-ke-hoach.md` — khảo sát nguồn, kế hoạch 6 giai đoạn.
- `docs/poi-crawl/tiktok-trich-xuat.md` — chi tiết đường TikTok, đã kiểm chứng.
- `docs/poi-crawl/phan-loai-dia-diem.json` — bộ phân loại đề xuất.

---

## 1. Bối cảnh: ba ràng buộc của hệ thống quyết định toàn bộ kế hoạch

Khảo sát bắt đầu từ việc đọc lược đồ dữ liệu của hệ thống, và ba ràng buộc dưới đây chi phối mọi lựa chọn về sau:

1. **`POI` bắt buộc có `longitude`, `latitude`; nếu có `address` thì `district` và `city` là bắt buộc** (`POI_service/app/core/domain/graph_entities.py:154-171`). Nghĩa là mọi địa điểm cào về đều phải được định vị trước khi nạp. Đây là điểm nghẽn thật của kế hoạch, không phải bước cào.
2. **Nhãn phân loại quyết định mã định danh.** `POI.id` sinh theo mẫu `<nhãn_chính>_<tỉnh>_<quận>_<đường>_<ngày>_<uuid8>`, lấy từ `poi_categories[0]` (`graph_entities.py:181-220`). Nhãn sai thì id sai.
3. **Không được bịa nhãn.** Chính sách trong `ai_service/prompt.json` ghi rõ agent không được tự nghĩ ra category id. Vì vậy bộ nhãn phải **được tạo trong đồ thị trước** khi nạp POI, nếu không bản ghi sẽ rơi vào tiền tố `UNCATEGORIZED`.

Hệ quả trực tiếp: kế hoạch không thể chỉ là "cào về rồi lưu"; bắt buộc phải có bước định vị và bước tạo nhãn nằm trước bước nạp.

---

## 2. Kết quả khảo sát từng loại nguồn

Chín loại nguồn/đường đã thử thật. Cách thử: dùng công cụ đọc trang và Chrome chạy riêng (headless, không đụng phiên Chrome đang mở của chủ dự án).

| Nguồn | Kết quả thử | Kết luận |
|---|---|---|
| Bài viết tổng hợp (vinwonders, reviewamthuc, bestprice) | Đọc được đầy đủ: tên, địa chỉ, giờ mở cửa, giá, điểm Google Maps. Một bài cho 10 địa điểm có cấu trúc đều | **Dùng được ngay** |
| Google Sheet công khai | `docs.google.com/spreadsheets/d/<id>/export?format=csv` trả về CSV thật, có dòng tiêu đề | **Dùng được ngay** |
| TikTok — caption | oEmbed công khai, không cần khoá: `tiktok.com/oembed?url=<video>` trả về caption, tác giả | Dùng được, nhưng caption **không chứa danh sách quán** |
| TikTok — trang video | Khối JSON gốc phơi **phụ đề tự sinh, có track tiếng Việt** (`Source:"ASR"`, `vie-VN`). Đọc thẳng ra WebVTT | **Phát hiện quan trọng nhất — xem mục 3** |
| Threads | DOM chỉ 49 KB, không có bài viết nào, chỉ có metadata trang | Cần đăng nhập hoặc API chính thức |
| Facebook / Instagram | Chỉ đọc được metadata trang; nội dung bài viết không có | Cần đăng nhập |
| Google Maps — trang địa điểm | HTML gốc **có** khối `APP_INITIALIZATION_STATE` chứa dữ liệu, nhưng thân là mảng lồng nhau đã mã hoá | Đọc được nhưng phải giải mã; cần công cụ chuyên |
| Google Maps — link danh sách chia sẻ | **Chưa thử được** — không có mẫu thật | Cần 3 link mẫu từ chủ dự án |
| Tìm kiếm mặc định | Chạy chế độ không khoá, đã gặp lỗi 403 vài lần | Cần khoá để ổn định |

**Phát hiện ngoài dự kiến:** trào lưu "sheet ẩm thực" trên Threads là thật và đã được báo lớn đưa tin (Tuổi Trẻ). Ví dụ được nêu tên: sheet "Food Tour SG" của tài khoản `tipslife_byvulpinn` với hơn 400 địa điểm, có tên đường, khu vực, phân loại món, giờ mở cửa, giá tham khảo; và sheet của tài khoản `nhuquynh_d` phân loại theo quận kèm menu. Nghĩa là nguồn dữ liệu mục tiêu **đã tồn tại ở dạng có cấu trúc**, chỉ là nằm trên nền tảng cần đăng nhập.

---

## 3. Ba phát hiện chính

### 3.1. TikTok không cần API, không cần tải video — TikTok tự sinh phụ đề tiếng Việt

Đây là phát hiện quan trọng nhất và nó lật ngược kết luận ban đầu của chính báo cáo này.

TikTok chạy sẵn phần chuyển tiếng nói thành văn bản cho video (dùng chính Whisper, `version: "1:whisper_lid"`) và **phơi kết quả trong khối JSON gốc của trang**. Đường đi đã kiểm chứng:

```
1. Mở trang video bằng trình duyệt thật
2. Bóc khối <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">
   đường dẫn: __DEFAULT_SCOPE__ → webapp.video-detail → itemInfo → itemStruct → video → subtitleInfos
3. Chọn track có Source = "ASR" và LanguageCodeName = "vie-VN"
   (bỏ track Source = "MT" — đó là bản dịch máy, tên riêng bị dịch chứ không phải chép lại)
4. Đọc URL đó → nhận về tệp WebVTT có mốc thời gian
```

Kết quả thật, trích nguyên văn từ phụ đề của video `@tebefood/video/7493546709595720967`:

```
top 4 quán mọi người nên thử / trên con đường Hai Bà Trưng Quận một
đầu tiên không thể không nhắc đến bắn giò Hai Bà Trưng
chỉ có 25 Xu siêu bình dân và topping đầy đặn
tiếp đến là bánh mì hơn 75 của cụ lý
```

Ra đúng thứ cần: tên quán, khu vực, món, giá — những thứ caption hoàn toàn không có.

**Đo độ phủ:** 3/3 video của 3 tài khoản khác nhau đều có track `vie-VN` nguồn ASR.

**Ba cái bẫy kỹ thuật phải biết trước:**

1. **Máy chủ trả sai kiểu nội dung** — báo `Content-Type: video/mp4` nhưng phần thân là văn bản `WEBVTT`. Kiểm theo kiểu nội dung là mất dữ liệu.
2. **URL có hạn dùng** — `UrlExpire` sống khoảng một ngày; phải đọc trang và lấy phụ đề trong cùng một lượt.
3. **Phải gửi kèm `Referer: https://www.tiktok.com/`**, không thì bị từ chối.

**Hệ quả cho kế hoạch:** TikTok từ chỗ bị xếp là "nguồn kém hiệu quả nhất" trở thành một trong những nguồn tốt nhất — không cần khoá, không cần tải video, không cần mua dịch vụ. (Kết luận cũ đã được sửa tại mục 10.5 của `khao-sat-nguon-va-ke-hoach.md`.)

### 3.2. Nhà cung cấp trả tiền: cần cho ba việc khác, không cần cho đường chính

Đã tra giá niêm yết (chưa trả tiền thật để kiểm):

- **Cào video/tài khoản:** Apify `clockworks/tiktok-scraper` từ **1,70 USD/1.000 kết quả**; Apify `best-tiktok-scraper` **1,88 USD/1.000**; Bright Data từ **2,50 USD/1.000 bản ghi**, có **5.000 tín dụng miễn phí mỗi tháng**; Data365 **300–850 EUR/tháng**.
- **Cào phụ đề:** Apify từ **0,04 USD** đến **1,00 USD/1.000**.
- **Hiểu nội dung video (cả hình lẫn tiếng):** TwelveLabs **0,042 USD/phút**, miễn phí 600 phút.

Các nguồn đều xác nhận: **TikTok không có API chính thức nào trả về phụ đề**, và phần lớn dịch vụ bên thứ ba cũng chỉ lấy đúng cái mà ta đã lấy được miễn phí — khác ở chỗ làm được quy mô lớn, có proxy trải rộng.

**Về API chính thức của TikTok:** ba nhóm đều không dùng được — Research API chỉ nhận tổ chức nghiên cứu phi lợi nhuận và chỉ mở cho Mỹ/châu Âu/Canada/Brazil; Display API chỉ đọc dữ liệu của chính người đã cấp quyền; Content Posting API để đăng bài.

Vì vậy nhà cung cấp chỉ cần thiết cho: **(a) bình luận** (bình luận tải qua API có chữ ký, không nằm trong trang), **(b) chạy quy mô lớn khi bị chặn**, **(c) video không có phụ đề tự sinh**.

### 3.3. Bộ phân loại: phải chốt trước khi cào, và phải đủ ba tầng

Đề xuất tại `phan-loai-dia-diem.json`, cấu trúc ba tầng, mỗi tầng có lý do tồn tại riêng:

- **Nhãn chính (11, chọn một):** `quan_an`, `an_vat`, `cafe`, `trang_mieng`, `nha_hang`, `bar`, `tham_quan`, `vui_choi`, `mua_sam`, `luu_tru`, `khac`. Tầng này tồn tại vì nó quyết định mã định danh POI và là thứ AI agent dùng để tra cứu.
- **Nhãn phụ (23, danh sách đóng, tối đa 5 mỗi chỗ):** món ăn, hình thức, thời điểm, đối tượng, không gian. Tồn tại vì `Tag` trong hệ thống chỉ có id và tên nên phải là danh sách đóng, không thể là văn bản tự do.
- **Hình dạng (`diem` / `khu`):** tách khỏi nhãn, vì dữ liệu thật có "hẻm 76 Hai Bà Trưng", "phố ẩm thực Vĩnh Khánh", "chợ đêm Tân Định" — những chỗ không có một địa chỉ duy nhất. Nếu xử lý như một quán thì lịch trình sẽ tính sai thời lượng.

Nhãn `khac` (Chưa Rõ) là nhãn có chủ đích: nó tồn tại để chặn việc đoán bừa, mọi bản ghi thiếu bằng chứng vẫn được giữ lại và đưa vào danh sách chờ kiểm thay vì bị bỏ.

---

## 4. Luồng đề xuất và điểm nối vào mã hiện có

Sáu bước, thứ tự không thể đảo:

1. **Tìm bài** theo chủ đề và địa bàn → danh sách URL ứng viên.
2. **Trích danh sách địa điểm thô** từ mỗi bài (tên, địa chỉ nếu có, mô tả, nguồn).
3. **Phân loại** theo bộ nhãn ở mục 3.3 — bước này chạy **trước** khi cào chi tiết.
4. **Định vị và làm giàu** qua Google Maps (toạ độ, quận, thành phố, giờ mở cửa, số sao). Bắt buộc, vì `POI` đòi bốn trường này.
5. **Làm sạch, gộp trùng** (theo tên và khoảng cách toạ độ).
6. **Nạp** — tạo `Category`/`Tag` trong đồ thị trước, rồi nạp qua API hiện có.

Điểm nối với mã đang có (đã đọc để xác nhận):

- Bộ cào hiện tại dùng `crawl4ai`, lớp cơ sở `BaseDetailCrawler` tại `crawler_service/app/pipelines/crawling/base/detail_crawler.py`, với hai hàm bắt buộc phải viết: `get_hook()` và `crawl_with_schema()`. Thêm nguồn mới là thêm lớp con theo đúng khuôn này, không dựng bộ cào song song.
- Phân nhánh theo `crawl_type` (`hotel`, `activities`, `destination`, `destinations`, `explore`), khuôn trích xuất nạp từ `crawl_schemas/css/traveloka/<loại>/`.
- API nạp: `POST /ingestion/batch` nhận mảng dict, tự kiểm kiểu theo `POI`, chạy 10 bản ghi đầu như lô canary đồng bộ rồi đẩy phần còn lại vào nền theo lô 500, tiến độ báo qua `GET /ingestion/stream/{job_id}`; canary hỏng trả 422 và không nạp gì.

---

## 5. Kiểm soát chất lượng: chỗ bắt buộc phải làm

**Phụ đề tự sinh sai tên riêng tiếng Việt rất nhiều.** Bằng chứng ngay trong mẫu ở mục 3.1: "bánh giò" bị nhận thành "bắn giò". Vì vậy:

1. Mỗi tên trích ra **phải định vị lại qua Google Maps**, dùng quận làm ngữ cảnh; chỉ nhận khi tìm được địa điểm khớp và đúng quận.
2. **Lưu bằng chứng cho từng địa điểm**: đoạn phụ đề gốc, mốc thời gian, đường dẫn video. Không có bằng chứng thì không kiểm tra lại được lỗi.
3. **Không tin giá và giờ mở cửa từ lời nói** — lấy từ Google Maps, dùng lời nói làm tham khảo.
4. **Số cần đo ở đợt thử đầu:** tỉ lệ video có track tiếng Việt; số địa điểm nói ra so với số định vị được; tỉ lệ tên sai do nhận dạng; tỉ lệ trùng với dữ liệu đã có.

---

## 6. Rủi ro và giới hạn

- **Điều khoản nền tảng:** đọc ở quy mô lớn đi ngược điều khoản sử dụng của TikTok/Threads/Facebook/Instagram. Việc chấp nhận rủi ro này là quyết định của chủ dự án, không phải của trợ lý.
- **Bị chặn khi chạy lớn:** cần giãn cách giữa các lần gọi, không chạy song song ồ ạt.
- **Băng thông:** mỗi video phải mở một trang khoảng 600 KB để lấy được URL phụ đề chỉ 4–12 KB. Với 1.000 video là khoảng 600 MB trang phải đọc. Cách xử lý: mở trang, giữ lại phụ đề, bỏ ngay phần còn lại.
- **Dữ liệu nguồn có thể cũ:** các bài tổng hợp tự ghi "chỉ mang tính tham khảo"; giá và giờ mở cửa có thể đã thay đổi. Vì vậy Google Maps phải là nguồn chuẩn cho toạ độ, giờ, và trạng thái còn mở hay đã đóng.
- **Sheet công khai có thể bị khoá lại** bất kỳ lúc nào — phải lưu nguồn và thời điểm đọc.
- **Giới hạn của bằng chứng:** chưa chạy dịch vụ nào, chưa nối cơ sở dữ liệu, chưa ghi bản ghi nào. Độ phủ TikTok mới đo 3 video. Chưa viết bước trích xuất nên chưa có con số về tỉ lệ trích đúng. Chưa thử bình luận và chưa thử đọc chữ trên khung hình video.

---

## 7. Việc cần chủ dự án quyết

1. **Bộ nhãn:** duyệt 11 nhãn chính, hay cắt bớt? Khu/phố/chợ giữ là thuộc tính hình dạng (đề xuất) hay tách thành nhãn riêng?
2. **Khoá API:** có mua SerpApi cho Google Maps không? Đây là khoá duy nhất khó thay thế. Firecrawl và Tavily là tiện, chưa bắt buộc cho đợt đầu.
3. **Phiên đăng nhập** cho Threads/Facebook/Instagram: dùng phiên Chrome thật của chủ dự án hay không? Nếu không thì đợt đầu chỉ làm bài viết + sheet + TikTok (TikTok không cần đăng nhập).
4. **Đơn vị ngân sách:** mã đang so `daily_budget < 50` và `<= 150` (`graph_entities.py:71-79`) — đơn vị là nghìn đồng hay đô? Dữ liệu cào về là VNĐ; nếu đơn vị là đô mà không quy đổi thì mọi quán bình dân sẽ bị xếp nhầm thành cao cấp.
5. **Ba link danh sách Google Maps đã chia sẻ** làm mẫu thử — loại nguồn duy nhất chưa kiểm được. Kèm phạm vi địa bàn (chỉ TP.HCM?) và khối lượng đợt đầu (ví dụ 300–500 POI).
6. **Cho đo độ phủ TikTok trên 30 video** trước khi viết mã vào dự án.

---

## 8. Kết luận

Khảo sát cho ra một kết quả tốt hơn dự kiến ban đầu ở đúng chỗ khó nhất, và một kết quả xấu hơn ở chỗ tưởng là dễ.

**Tốt hơn:** TikTok — nguồn được cho là khó nhất — hoá ra lấy được dữ liệu mà không cần khoá, không cần tải video, không cần mua dịch vụ, vì chính TikTok đã chuyển lời nói thành phụ đề tiếng Việt và phơi nó trong trang. Đọc bài tổng hợp và đọc Google Sheet công khai cũng đã chứng minh chạy được ngay. Nghĩa là **đợt đầu không phải mua gì cả**.

**Xấu hơn:** hai nguồn dễ nhất về mặt kỹ thuật lại nằm sau tường đăng nhập (Threads — nơi phát tán chính các sheet ẩm thực — và Facebook/Instagram), và dữ liệu cào về **không tự đủ điều kiện để nạp**: hệ thống bắt buộc có toạ độ, quận, thành phố, nên bước định vị qua Google Maps là bắt buộc chứ không phải tuỳ chọn. Thêm nữa, phụ đề tự sinh viết sai tên riêng rất nhiều, nên bước chữa tên trước khi nạp cũng là bắt buộc.

Nói gọn: việc khó không nằm ở khâu cào dữ liệu, mà ở hai khâu nằm sau nó — **định vị** và **chữa tên**. Kế hoạch nên được đặt trọng tâm ở đó, và thứ tự đúng là chốt bộ nhãn, rồi định vị, rồi mới cào khối lượng lớn.
