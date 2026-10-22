# Checkpoint EXP086 — Codex, 19/10/2026

**Đã nhận offline bản sửa thu bằng chứng lỗi và binding sau CORE084. Chưa native two-tier, chưa fullfreeze hoặc primary. Goal tổng ACTIVE/INCOMPLETE.**

## Đã hoàn thành

Theo /plan do Codex chốt trước, OpenCode `aibox/ds/deepseek-flash` sửa đúng4tệp: collector H3, focused tests, README và candidate unfrozen. Mã giữ riêng lỗi nghiệp vụ top-level và lỗi từng provider call; giữ các receipt thất bại không có sessionID; lọc error_code qua enum đóng trước ledger/observation/projection.90mã bổ sung có provenance từ nguồn công khai, tổng enum110mã; giá trị lạ thành unknown, nonstring không stringify. Không suy quota/auth.

Codex tạo baseline mới EXP086 trước dispatch, giữ46đường dẫn readonly của EXP080, chỉ hash main.py đổi theo bản sửa CORE084 đã nhận. Baseline cũ nguyên SHAfe40e5cc…; mớiSHA4c76c6733f3c4687dcf263032660df3dde39f50e7ab6d9256cfe735e4e748a6d. Candidate được dựng lại bằng builder, bind path/hash/code/dependency thật; frozen=false,thesis_mode=false,review=pending. Ba hàm gate AST và fatal classification giữ nguyên, không bỏ hoặc nới gate.

## QA độc lập của Codex

-34ca đạt:28focused gồm22ca cũ+6ca bổ sung, cùng6ca Codex dùng fake seam trước chỉnh sửa. Không cộng actor31ca lần khác thành tổng khác.
-11ca chống sửa manifest đạt; kiểm alias/ports/source/profile/conditions/caps/hash/unfrozen trước backend.
-46readonly binding khớp;3gateAST không đổi;30hàm/helper/test AST có sẵn giữ nguyên. FakeBackend chỉ thêm cờ mặc định không kích hoạt và2nhánh inject mới; phần mã cũ giữ nguyên, các phương thức khác AST không đổi. Root QA dùng snapshot fixture cũ độc lập.
- HTTP200 prep model_unavailable và3receipts(2ok/1failed) giữ top-code/per-callcode riêng,3attempt,0typed/15missing, cleanup. Typed plan_invalid giữ nondelivery/15mẫu số. Chuỗi lỗi giống khóa nhưng không trùng fixture sentinel không xuất hiện trong tệp lưu.
-0application model/native/actual HTTP calls trong gói. Actor báo thêm3chat-boundaryca trong31-run; Codex không tự gọi đó là đã chạy lại.

## Source nhận mới

Authority: `handoffs/EXP-086/parent-final-acceptance.json`.

- benchmarks/memory_live/runner.py SHA592186070450f9767e943bda9f8a7f0a3df6f5e72e6d54bc2966b178a8704e78
- tests/memory_live/test_runner.py SHAd6ac080fe1e306f2bf8cb1019f356792538c3306de00067988002b0de69b75c8
- benchmarks/memory_live/README.md SHA8fee765d17818face9fba6347ee1edd4e4f620e8a3b4a875898f19f6d71d1765
- candidate SHA4e1e3d5341be87d16ff41a0d60e5ffa02e314abe73026dd27efb3dc380da1a72
- main.py vẫn là CORE084 SHAd866c52f…; không sửa service/provider/helper/projection/evaluator/frozen input.

## Worker, corrections và giới hạn

Handle44746 client terminal0, session ses_eacd9f900ffeUbZW5dQH71Jf6L. Artifact đã giao; parent dùng interrupt resume=false được interrupted:true, exact-session wait0 gần ngân sách600s; không lấy danh sách phiên khác hoặc chứng nhận server continuity/natural final-text completion. Không restart.

Codex policy ban đầu bỏ TIME_ORDER_INVALID ở dòng112 do extraction dừng111; sửa89→90trước nghiệm thu, giữ nguyên before-snapshots/baseline. Source checker ban đầu gọi nhầm execute thay vì _execute và đòi toàn fixture AST bất biến; sau đọc diff, kiểm chính xác phần mở rộng mặc định không kích hoạt và giữ toàn assertion cũ. Inline shell diff helper exit1/không diagnostic; chuyển sang saved QA script để tránh quoting, không có denial được báo. Các correction nằm trong acceptance, không gán cho production failure.

Actor lần chạy focused trước chỉnh sửa có10fail/12pass do baseline cũ lệch main; đã ghi trong tests.txt. Sau sửa28focused đạt. Hai thư mục pytest đầu dưới task E trước khi làm rõ temporary scope; các lần sau chuyển workspace qa-work/executor-tests. Không có source/secret/globalguard edit ngoài4file khai báo. events.log thuộc parent, executor không ghi vào log.

**CORE085 cũ vẫn partial:** short-term native2điểm/car1,645km đạt; two-tier prep stage3failed/chưa typed;3API/7attempts,nguyên nhânunknown do mã lỗi không được giữ. Bản sửa EXP086 không khôi phục hay diễn giải lại nguyên nhân đó. Quyền exact-once CORE085/CORE083/CORE079/MEM072 đã dùng hết; không rerun.

## Bước tiếp theo — một gói, không lặp lại short-term

1. Chuẩn bị chỉ phần **two-tier native còn thiếu**: tối đa2request API (1prep/1typed), source accepted CORE084+EXP086, closed enum/receipt đầy đủ, schema/fullprofile/history/fixturecredential proof trước khi kết luận. Không chạy lại short-term hoặc đổi timeout/provider/guard để lấy kết quả đẹp; không tự dùng quyền cũ. QA harness offline trước, xin quyền chính xác mới nếu chạm phạm vi deny trước.
2. Nếu provider thất bại, lưu mã thật và phân loại nguyên nhân từ bằng chứng; không suy quota/auth, không thử live vô hạn. Giữ planned denominator/nondelivery. Còn việc độc lập thì tiếp tục; chỉ blocked toàn goal khi thực sự hết khả năng tiến triển theo quy tắc3turn.
3. Chốt full code/data/config/runtime freeze theo S1–S6 và protocol sau gate native, rồi phase3 H2/H3/E2/system/adversarial. Chưa primary observation/H3 effects/pvalues/token savings. H2inputs20tìnhhuống vẫn nguyên.
4. Phase4 báo cáo và chờ người dùng chọn H1 hoặc luận án;0người tham gia H1. Crawler/social/travelagency/grow-with-user/harness mới ởphase5 Finalizing; không đưa lại phase2.

Codex lập kế hoạch/QA/nghiệm thu/final prose, OpenCode code theo brief; Hermes OS/evidence trong guard. Artifacts E:/Agent_Artifact/TVLT_2026/2026-10-19/closed-evidence-exp086 và bản checkpoint Codex. Không raw env/config/auth/unrelatedhistory/privateincidentexcerpt/ALL/globalguardchanges/reset/clean/commit/push. Đọc actual files/receipts trước rely; checkpoint sau task/phase quan trọng; tiếp toàn SG01–SG19/AC01–AC12.
