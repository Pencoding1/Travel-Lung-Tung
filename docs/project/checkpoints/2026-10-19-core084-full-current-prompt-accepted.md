# Checkpoint CORE084 — Codex, 19/10/2026

**Đã sửa và nghiệm thu offline lỗi cắt prompt hiện tại khi bật memory. Goal tổng ACTIVE/INCOMPLETE; phase2 chưa hoàn tất.**

## Công việc đã hoàn thành

Codex tái hiện lỗi qua10 trường hợp bằng AST hàm synthesis thật và memory.compose thật, không import main/đọc env/gọi model: memory bật cắt prompt hiện tại ở8.000ký tự, memory tắt giữ nguyên. Schema/facts/profile ở cuối có thể biến mất. Đây là lỗi mã và sai khác điều kiện thật; chưa chứng minh prompt lịch sử CORE081 đã bị cắt.

Sau kế hoạch /plan được Codex viết, OpenCode aibox/ds/deepseek-flash sửa duy nhất nhánh current của _synthesis_messages và thêm2 kiểm thử. Synthesis dùng mega_prompt gốc đầy đủ; system/history vẫn compose/lọc như cũ. Không đổi memory.compose hoặc caps, validator/schema/nguồn/provider/planner; không thêm retry/fallback.

Codex chạy độc lập32ca (5ca mới,15rootQA cũ,12focused), tất cả đạt;10case AST đều giữ toàn bộ current.57binding công khai giữ hash;130node AST top-level khác của main giữ nguyên. Ca ASGI prompt>16.000ký tự xác nhận current/schema/history/profile tới provider giả. Không có application modelcall trong gói này. Actor báo thêm32regression; Codex không gọi đó là đã tự chạy lại.

Nguồn nhận mới: main.py SHA d866c52f477b3c32f9ebfd1919e04d31f0a2d6e2b042465c80b1a914f8c10b0d; test SHA ce3a81bff42db6df3c592a813c0d7229e1063cdd26b21d61d1ff02cd794d0451. Authority: handoffs/CORE-084/parent-final-acceptance.json.

## Giới hạn vận hành và bằng chứng

OpenCode handle8645 exit0, session ses_eacedead3ffef7g2M0W4vIu207. Exact-session wait CLI exit0/bodyempty; parser initially expected JSON and failed after command success, then fixed without rerun. Auto-review rejected an earlier combined script because active-list could expose other sessions; it never executed. Safer exact-session wait removed enumeration. No active-list/server continuity claim; do not retry rejected enumeration.

Brief ban đầu nhầm cho executor ghi events.log trong khi Tee của parent sở hữu. Actor thử ghi timeline không có bằng chứng trước giờ dispatch, gặp file-lock error rồi thử shell; Codex dừng và yêu cầu sửa báo cáo. Không dùng timeline đó, không gọi file-lock là guard denial. Sự cố và lỗi parent phân quyền log được ghi trong acceptance; final prose/acceptance dựa QA độc lập. Future brief: events.log chỉ parent ghi; executor chỉ result/report/tests.

CORE083/081 giữ nguyên: engine đã khôi phục;2API/4CLI, short-term marker tới model nhưng output thiếu stops,0/2cell; two-tier chưa gọi, QAstack dọn. Không đổi thất bại thành thành công, không tuyên bố sửa đúng nguyên nhân lịch sử. Quyền chạy một lần CORE083 đã dùng, không rerun.

## Việc tiếp theo cần hoàn thành

1. Chuẩn bị **một** gói native memory theo hash nhận mới; old CORE079/CORE083 pins vẫn là lịch sử và không được sửa để chạy lại script cũ. Kiểm source freeze/budget/cleanup bằng offline QA trước mọi lần gọi model.
2. Xác minh short-term/two-tier trên native stack, giữ source1483/owner/session/schema/credential boundaries và toàn bộ thất bại. Xin quyền chính xác mới nếu gói chạm phạm vi từng bị chặn; không dùng lại exact-once cũ. Không chạy thử nhiều lần chỉ để lấy output thành công.
3. Fullfreeze sau gate phase2, rồi phase3 H2/H3/E2/system/adversarial theo giao thức. Bằng chứng giả lập không thay native hoặc khoa học; model nondelivery phải ở mẫu số.
4. Phase4 báo cáo và người dùng chọn H1 hoặc luận án.0người tham gia, chưa tự tuyển/viết luận án. Crawler/social/travelagency/grow-with-user/harness mới ởphase5 Finalizing.

Codex lập kế hoạch/QA/nghiệm thu; OpenCode code theo brief, Hermes OS/evidence trong phạm vi guard. Giữ no secrets/rawenv/config/auth/history/ALL/globalguard edits/reset/clean/commit/push. Tiếp đầy đủ SG01–SG19/AC01–AC12, checkpoint sau mốc lớn.
