# TikTok: lấy dữ liệu video và trích xuất thông tin

Ngày: 2026-10-05. Trạng thái: **đã kiểm chứng thật, chờ anh duyệt trước khi viết mã vào dự án**.
Ghi chú: tài liệu này thay thế kết luận ở mục 10 của `khao-sat-nguon-va-ke-hoach.md`. Kết luận cũ ("TikTok kém hiệu quả nhất") nay **sai** và đã được sửa.

---

## 1. Kết quả then chốt: TikTok tự sinh phụ đề, và ta đọc được

TikTok chạy sẵn phần chuyển tiếng nói thành văn bản cho video, và **phụ đề đó nằm ngay trong trang video**, không cần tải video, không cần khoá API, không cần tự chạy nhận dạng giọng nói.

Đường đi đã kiểm chứng:

```
1. Mở trang video bằng trình duyệt thật
2. Đọc khối JSON gốc:  <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">
   đường dẫn: __DEFAULT_SCOPE__ → webapp.video-detail → itemInfo → itemStruct → video → subtitleInfos
3. Trong danh sách đó chọn track có Source = "ASR" và LanguageCodeName = "vie-VN"
4. Đọc thẳng URL đó → nhận về tệp WebVTT có mốc thời gian
```

Kết quả thật khi làm việc này với video `@tebefood/video/7493546709595720967`:

- Danh sách track: `eng-US` (Source `MT`, tức bản dịch máy) và **`vie-VN` (Source `ASR`, version `1:whisper_lid`, 5.419 byte)**. Tức TikTok dùng chính Whisper để nhận dạng tiếng Việt, và ta đọc được đúng bản gốc tiếng Việt chứ không phải bản dịch.
- Khối `claInfo` xác nhận: `hasOriginalAudio: true`, `enableAutoCaption: true`, `originalLanguageInfo.language = "vie-VN"`.
- Nội dung tệp phụ đề lấy được (trích nguyên văn, giữ cả lỗi nhận dạng):

```
00:00:00.080 --> 00:00:01.520
top 4 quán mọi người nên thử
00:00:01.560 --> 00:00:02.960
trên con đường Hai Bà Trưng Quận một
00:00:09.481 --> 00:00:12.041
đầu tiên không thể không nhắc đến bắn giò Hai Bà Trưng
00:00:16.241 --> 00:00:17.921
ở đây có 4 loại chính là bắn giò ...
00:00:24.760 --> 00:00:27.080
nếu ăn liền tại chỗ là bánh giò nóng hổi luôn một phần
00:00:27.160 --> 00:00:29.800
chỉ có 25 Xu siêu bình dân và topping đầy đặn
00:00:39.440 --> 00:00:41.320
tiếp đến là bánh mì hơn 75 của cụ lý
```

Đọc phần này ra được đúng thứ cần: danh sách quán, địa bàn (Hai Bà Trưng, Quận 1), giá (25 nghìn), và cả mô tả món. Đây là dữ liệu mà caption không hề có: caption chỉ là một câu mô tả chủ đề.

**Đo độ phủ trên 3 video của 3 tài khoản khác nhau: 3/3 đều có track `vie-VN` nguồn ASR.** Ba mẫu là quá ít để kết luận, nhưng đủ để coi đây là đường chính và phải đo tiếp trên 30–50 video trước khi cam kết.

---

## 2. Ba chi tiết kỹ thuật bắt buộc phải biết khi viết mã

Ba cái này nếu không biết trước thì sẽ mất thời gian gỡ:

1. **URL phụ đề có hạn dùng.** Trường `UrlExpire` là mốc thời gian hết hạn, và URL chỉ sống khoảng một ngày. Nghĩa là phải đọc URL rồi lấy nội dung ngay trong cùng một lượt, không lưu lại để dùng hôm sau.
2. **Tiêu đề kiểu nội dung trả về sai.** Máy chủ trả `Content-Type: video/mp4` nhưng phần thân đúng là văn bản `WEBVTT`. Nếu viết mã kiểm tra kiểu nội dung rồi bỏ qua khi thấy `video/mp4` thì sẽ bỏ mất chính dữ liệu cần lấy. Cách đúng: cứ đọc phần thân và kiểm tra nó bắt đầu bằng `WEBVTT`.
3. **Cần gửi kèm `Referer: https://www.tiktok.com/`.** Không có thì thường bị từ chối.

Bằng chứng cho cả ba điểm nằm ở lần đọc thật trong phiên này: lần gọi trả về `mã trả về: 200 | kiểu nội dung: video/mp4 | độ dài nội dung: 4648` và phần thân mở đầu bằng `WEBVTT`.

---

## 3. Các dịch vụ cào TikTok đang bán gì, giá bao nhiêu

Đã tra, số dưới đây là giá niêm yết trên trang nhà cung cấp, chưa kiểm bằng cách trả tiền thật:

**Cào dữ liệu video và tài khoản (metadata, lượt thích, bình luận):**

- Apify, `clockworks/tiktok-scraper`: từ **1,70 USD / 1.000 kết quả**.
- Apify, `scrape-creators/best-tiktok-scraper`: **1,88 USD / 1.000 kết quả**.
- Bright Data, kho dữ liệu TikTok: từ **2,50 USD / 1.000 bản ghi**, có **5.000 tín dụng miễn phí mỗi tháng**; kho TikTok của họ có hơn 307 triệu bản ghi dựng sẵn.
- Data365: **300 EUR/tháng** gói cơ bản (một mạng xã hội, 500 nghìn tín dụng), **850 EUR/tháng** gói chuẩn (ba mạng xã hội, 1 triệu tín dụng).

**Cào phụ đề hoặc văn bản nói:**

- Apify, `automation-lab/tiktok-transcript-scraper`: từ **0,04 USD / 1.000** (rẻ bất thường, nên kiểm chất lượng trước khi tin).
- Apify, `maximedupre/tiktok-transcript-scraper`: từ **0,90 USD / 1.000 phụ đề**.
- Apify, `scrape-creators/best-tiktok-transcripts-scraper`: **1,00 USD / 1.000 video**.
- Apify, `scrape-creators/best-tiktok-transcripts-scraper`: có bản trả về WebVTT kèm mốc thời gian.

**Hiểu nội dung video (không chỉ đọc lời nói):**

- TwelveLabs: **0,042 USD/phút** cho việc lập chỉ mục video, cộng phí hạ tầng; **miễn phí 600 phút** ở gói dùng thử. Mô hình này phân tích cả hình lẫn tiếng, tức đọc được cả chữ hiện trên màn hình.

**Sự thật quan trọng mà các nguồn đều xác nhận:** TikTok **không có API chính thức nào trả về phụ đề**. Các dịch vụ trên đều là bên thứ ba, và phần lớn trong số họ cũng chỉ lấy đúng cái mà ta vừa lấy được miễn phí — khác nhau ở chỗ họ làm ở quy mô lớn, có proxy trải rộng, và có sẵn cơ chế vượt chặn.

**Kết luận về nhà cung cấp:** không cần mua gì cho đường chính, vì đường chính đã lấy được phụ đề tiếng Việt miễn phí. Nhà cung cấp chỉ cần cho ba việc khác: (a) lấy **bình luận** (bình luận tải qua API có chữ ký, không nằm trong trang), (b) chạy ở **quy mô lớn** khi bị chặn, (c) video **không có phụ đề tự sinh**.

---

## 4. Phương pháp trích xuất thông tin từ video, xếp theo thứ tự nên làm

**Cách 1 — Đọc phụ đề tự sinh rồi cho mô hình ngôn ngữ trích xuất (đã kiểm chứng, làm trước tiên).**
Lấy WebVTT như mục 1, đưa toàn bộ văn bản kèm mốc thời gian cho mô hình, yêu cầu trả về danh sách địa điểm dạng có cấu trúc: tên, món, giá, khu vực, mốc thời gian trong video. Chi phí gần bằng không, và vì có mốc thời gian nên sau này đối chiếu lại được với đúng đoạn video.

**Cách 2 — Kết hợp caption và bình luận.**
Bình luận là nguồn chữa lỗi rất tốt: người xem thường hỏi "cho xin địa chỉ" và chủ kênh trả lời, hoặc người khác đính chính tên quán. Cái này phải mua dịch vụ vì bình luận không nằm trong trang.

**Cách 3 — Đọc chữ hiện trên màn hình bằng cắt khung hình rồi nhận dạng.**
Nhiều video giới thiệu quán có chèn sẵn tên quán và địa chỉ dưới dạng chữ trên hình — đây là nguồn chính xác hơn lời nói, vì không qua nhận dạng giọng nói. Cách làm: dùng `ffmpeg` (máy anh **đã có**, bản 9.0.1) cắt khung hình mỗi 1–2 giây hoặc cắt theo các mốc thời gian lấy từ phụ đề, rồi đọc chữ trên khung hình đó. Cách này cần có tệp video, nên vướng luật cứng và cần anh quyết (xem mục 6).

**Cách 4 — Tự chạy nhận dạng giọng nói (chỉ khi không có phụ đề).**
Đây là phương án dự phòng cuối. Máy anh hiện **không có** thư viện nhận dạng nào (`faster_whisper`, `whisper`, `torch`, `cv2` đều không có; `tesseract` cũng không có). Có ba đường: cài mô hình chạy tại máy, thuê dịch vụ nhận dạng, hoặc dùng dịch vụ hiểu video như TwelveLabs. Lưu ý: làm cách này là tự nhận dạng lại đúng việc mà TikTok đã làm sẵn ở cách 1, nên chỉ dùng khi video thật sự không có phụ đề.

**Cách 5 — Tải video về để lưu trữ.**
Máy anh không có `yt-dlp`, và luật cứng của anh cấm tôi tải tệp về máy. Tôi không khuyến nghị: cách 1 cho ra đúng thứ cần mà không phải tải 40 MB mỗi video.

---

## 5. Kiểm soát chất lượng: chỗ này bắt buộc phải làm, không phải tuỳ chọn

Phụ đề tự sinh **sai tên riêng tiếng Việt rất nhiều**. Bằng chứng ngay trong mẫu ở mục 1: "bánh giò" bị nhận thành "bắn giò", "bánh mì" thành "bắn mì" ở đoạn khác. Vì vậy:

1. **Mỗi tên trích ra phải được định vị lại qua Google Maps** trước khi thành điểm đến, dùng quận làm ngữ cảnh. Chỉ nhận khi tìm được địa điểm khớp và đúng quận.
2. **Lưu lại bằng chứng** cho từng địa điểm: đoạn phụ đề gốc, mốc thời gian, đường dẫn video. Không có bằng chứng thì không kiểm tra lại được lỗi.
3. **Không tin giá và giờ mở cửa từ lời nói**: người nói có thể nói sai hoặc video đã cũ. Giá và giờ lấy từ Google Maps, chỉ dùng lời nói làm thông tin tham khảo.
4. **Số cần đo sau đợt thử đầu:** tỉ lệ video có track tiếng Việt; số địa điểm nói ra so với số định vị được; tỉ lệ tên bị sai nhận dạng; tỉ lệ trùng với dữ liệu đã có.

---

## 6. Chi phí, rủi ro, và giới hạn

**Chi phí đường chính:** gần bằng không về tiền, nhưng tốn băng thông: mỗi video phải mở một trang khoảng 600 KB mới lấy được URL phụ đề, trong khi tệp phụ đề chỉ 4–12 KB. Nghĩa là phải mở trang rồi bỏ ngay, chỉ giữ lại tệp phụ đề và phần đã trích xuất. Với 1.000 video thì khoảng 600 MB trang phải đọc.

**Rủi ro bị chặn:** đọc ở quy mô lớn thì TikTok sẽ hạn chế. Cần giãn cách giữa các lần gọi, không chạy song song ồ ạt, và chỉ đọc những video thật sự cần.

**Rủi ro điều khoản:** phụ đề là do TikTok sinh ra và phơi trong trang, nên đọc nó là hành vi giống như đang xem trang. Nhưng đọc tự động với số lượng lớn thì đi ngược điều khoản sử dụng của nền tảng. Việc chấp nhận rủi ro này là quyết định của anh, không phải của tôi, nên tôi nêu rõ ở đây.

**Giới hạn của bằng chứng hiện có:** tôi mới đo 3 video (3/3 có phụ đề tiếng Việt). Chưa đo tỉ lệ địa điểm trích đúng vì chưa viết bước trích xuất. Chưa thử bình luận và chưa thử cắt khung hình.

---

## 7. Việc cần anh quyết

1. **Đi theo đường chính** (đọc phụ đề tự sinh + mô hình trích xuất) cho TikTok, hay vẫn muốn mua dịch vụ bên thứ ba? Tôi đề xuất đường chính, và chỉ mua khi cần bình luận hoặc chạy quy mô lớn.
2. **Đo trên 30 video** để chốt tỉ lệ phủ trước khi viết mã vào dự án? Việc này tôi làm được ngay, chỉ cần anh đồng ý cho tôi chạy trình duyệt đọc khoảng 30 trang.
3. **Bình luận**: có cần lấy không? Nếu cần thì phải chọn nhà cung cấp (Apify từ 1,70 USD/1.000, hoặc Bright Data có 5.000 tín dụng miễn phí mỗi tháng — nên thử gói miễn phí trước).
4. **Cắt khung hình đọc chữ trên màn hình**: có làm không? Nếu có thì cần thống nhất việc tải video, vì luật cứng đang cấm và tôi không tự vượt.

---

## 8. Kết luận

Câu trả lời cho câu hỏi của anh gọn hơn dự đoán: **không cần API TikTok, không cần tải video, không cần mua dịch vụ cào phụ đề.** TikTok tự sinh phụ đề tiếng Việt bằng chính Whisper và phơi nó trong trang video; ta đọc khối JSON của trang, lấy URL track `Source = ASR, LanguageCodeName = vie-VN`, rồi đọc tệp WebVTT. Tôi đã làm được việc này ba lần liên tiếp trên ba video khác nhau, và nội dung phụ đề có đúng thứ cần: tên quán, khu vực, món, giá.

Việc phải làm cho đúng không nằm ở chỗ lấy phụ đề, mà ở chỗ **chữa lỗi tên riêng**: phụ đề tự sinh viết "bánh giò" thành "bắn giò", nên mọi tên trích ra đều phải định vị lại qua Google Maps rồi mới được thành điểm đến. Nhà cung cấp trả tiền chỉ cần thiết cho ba việc khác: bình luận, chạy ở quy mô lớn khi bị chặn, và video không có phụ đề — nghĩa là đợt đầu không phải mua gì cả.

So với kết luận cũ của tôi ở tài liệu khảo sát (mục 10): tôi đã sai khi xếp TikTok vào nguồn kém hiệu quả nhất. Sai ở chỗ tôi chỉ kiểm phần caption rồi kết luận, chưa mở khối JSON gốc của trang. Đã sửa lại ở mục 10 của tài liệu đó.
