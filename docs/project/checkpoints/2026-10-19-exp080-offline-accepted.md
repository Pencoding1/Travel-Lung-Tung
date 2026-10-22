# Checkpoint — Codex: collector H3 đã được nhận offline

Cập nhật 19/10/2026. Goal ACTIVE/INCOMPLETE. Đây là tiến bộ thực tế: collector đã sửa đúng endpoint và qua QA độc lập; chưa có thí nghiệm chính mới.

## Mã đã nghiệm thu

Receipt: `../handoffs/EXP-080/parent-final-acceptance.json`, decision `ACCEPTED_OFFLINE_TYPED_COLLECTOR_CODE_NOT_NATIVE_OR_FREEZE`.

- `/chat` chuẩn bị hội thoại; `/generate_itinerary` trả lịch để scoring. Cùng owner/session/source trong mỗi cell, cùng body typed giữa các điều kiện.
- Nguồn phải khớp cả `grounding.source_scope` và `planning.request_constraints.source_scope`. Chỉ lấy selected IDs/giờ thật từ repaired schedule; không thay bằng prose hoặc retrieval evidence IDs.
- Lỗi input/source/lifecycle/cleanup giữ partial;503 dừng, không retry hoặc suy quota/auth.15cell và missingness giữ rõ; failed prep/lifecycle giữ closed diagnostics, bỏ raw error bodies.
- Manifest path/hash đã sửa cùng tệp; baseline mới ghi mã CORE079 hiện tại, không sửa baseline cũ. Candidate vẫn `frozen:false`, `thesis_mode:false`.
- Codex chạy **11 ca độc lập,22 focused,6 export giả lập,11 chống sửa freeze,20 hồi quy evaluator** đều đạt.46 readonly bindings và3 hàm validator AST giữ nguyên; hash agent báo khớp tệp thật. Lần setup đầu thiếu thư mục cha `qa-work` gây fixture errors, đã giữ log và sửa thư mục; không sửa assertion để qua test.
- RunnerSHA `771cac38d9a8e56822cb0322eaeadec0d6bc41f4ed71886bcbc42aecf3403d66`. MainSHA vẫn `a47411d178f9d37ce3c014b7e62f54b705a85ffbb298a28ca79d363bb8c39221`.

## Không còn writer EXP080 hiện hành

Client37269 exit0 đã ghi trước. Sau đêm, server hiệnPID10672; exactsession `ses_eb0336ac3ffe5n9qgmY4jvwdD2` inactive, officialwait0, oldserverPID28328 không còn. Không đủ bằng chứng xác định thời điểm dừng trên server cũ, không gọi đây là same-server historical idle. Không restart/interrupt phiên khác. Xem `parent-worker-final.json`, `parent-server-transition.json`.

Agent thiếu `report-vi.md` và `executor-tests.txt`; không bịa hai tệp đó hoặc nguồn tác giả. Có executor-result.json và toàn bộ QA thực chạy của Codex; parent-final-review-vi.md là review do Codex viết. Nhận mã offline, chưa gọi toàn bộ bàn giao đầy đủ.

## Gate còn lại và bước kế

1. CORE079 native vẫn **1/3**: disabled bypass/typed car route đạt; short-term prep503, hai cell chưa hoàn tất.3request/3knownCLIattempts, cleanup nguồn/cổng đã kiểm. Exact-once permission đã dùng; không chạy lại script cũ. Không H2/H3 primary hoặc fullfreeze.
2. CORE081 đã chuẩn bị **batch kỹ thuật mới cho short-term/two-tier**, tối đa4request, không thay kết quả thất bại cũ. Script `handoffs/CORE-081/parent_native_remaining.py` SHA `2d913771fa116ced7ab32bc1fd82739504840627922c7c314db153592b613d74`.2ca fake-only kiểm tra điều phối đạt;0model/0native thật. **Chưa được chạy, chưa xin/có quyền mới**, không tự dùng quyền CORE079. Mọi thay đổi script sau hash này phải được review lại trước quyền cụ thể.
3. Fresh TCP ngày19/10:17687/18989/19601/19602 đều không lắng nghe. **CORE082 Hermes đã dispatch**, handle65000/session20261019_140404_45e62d,budget600s từdispatch-prepared.json; planprepared-plan.md doCodex viết,preflightapprovalsmart/singlequerydeny/YOLOabsent/hooksourcesmatch. Chỉ khôi phục existing native engines từ cache và dữ liệu đang có. Không download/install/import/rebuild/reset/kill-by-port hoặc thay guard. Script startMemgraph có prepare/fetch nếu cache thiếu: phải kiểm cache/hash trước, dừng nếu thiếu. GH phải có existing graph cache, đúng JAR/PBF; không rebuild/import. Thu kết quả đúnghandle và kiểm chứng độc lập,không khởi chạy trùng.
4. Sau native active-memory proof và fullfreeze mới phase3 H2/H3/E2/system/3adversarialfamilies → phase4 report và chờ user H1/thesis choice. H1 chưa có người thật;phase5Finalizing toàncrawler/social/travelagency/grow-with-user/harness.

Giữ fullSG01–SG19/AC01–AC12. Codex lập kế hoạch/QA/nghiệm thu; OpenCode/Hermes làm theo /plan cố định. No raw.env/config/auth/env enumeration/private incident excerpt; safeprobeabsolute chỉpresence/type/length. NoALL/wildcards/globalguardchanges/reset/clean/commit/push; guarddeny dừng action, khôngrephrase/executorswap. Lưu checkpoint sau mốc lớn.
