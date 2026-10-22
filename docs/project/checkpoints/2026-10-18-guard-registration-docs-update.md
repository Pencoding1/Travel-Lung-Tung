# Checkpoint Codex — đăng ký guardrail và cập nhật báo cáo

Chủ trì: Codex. Goal vẫn ACTIVE/INCOMPLETE. Turn trước chỉ giải thích trạng thái (no progress); turn này PROGRESS: xác minh runtime, đăng ký hook sau xác nhận trực tiếp của người dùng, kiểm thử callback thật và giao DOC056 song song.

## Guardrail T062

Hai script đã được cài tại `C:/Users/duyan/AppData/Local/hermes/agent-hooks/secret_guardrails/`. Receipt `E:/Agent_Artifact/TVLT_2026/2026-10-18/secret-guardrails/installation.json` xác nhận thêm pre-tool hook trước domain guard, giữ nguyên domain guard và các cấu hình khác.

Python hệ thống thiếu ruamel; thử launcher run-module/runpy bị lỗi argv, không phải policy denial. Runtime được xác định bằng official `--print-runtime-command`, sau đó dùng đúng Python Hermes + hermes_bootstrap để chạy script QA. Không tải/cài dependency, không đọc credential.

TTY55072 hiện đúng prompt first-use cho hook đã duyệt. Codex dừng, hỏi người dùng; người dùng trả lời “Cho phép đăng ký hook này”. Sau đó gửi y vào chính handle55072, terminal exit0. Không autoaccept/bypass hoặc sửa trực tiếp consent store.

`docs/project/handoffs/HM-055/parent-registration-proof.json`: registered=true, autoaccept_used=false, 5/5 production callback probes pass: dump môi trường và đọc .env bị chặn; file thường và helper absolute đã duyệt được phép; helper relative bị chặn. Payload là synthetic, callback chạy guard thật; không thực thi lệnh dump/read trong payload.

Chỉ nghiệm thu đăng ký hook ở default Hermes home và callback trên. Không tuyên bố gateway cũ đã reload, mọi profile được bảo vệ, hoặc script là OS sandbox. Hai script vẫn là defense in depth theo threat model đã ghi.

## Công việc song song và tiếp nối

Native `/root/interactive_docs_update` được người dùng yêu cầu. Codex plan tại `handoffs/DOC-056/brief.md`; child giám sát một Hermes file-only, provider aibox/model ds/deepseek-flash, session20261018_090835_429bfd, handle45287 theo child báo. Child đang sở hữu report HTML/JSON/modules và generator OC047; root không ghi các file đó trong lúc child làm. Giữ architecture hashes; chỉ static QA, không browser/server workaround. Parent đã gửi trạng thái guard cuối cùng cho child.

Remaining P0 không đổi: T051 export command sai và isolation chưa chứng minh; T057 collect_profile gọi fetcher trước gate reuse; T049 AI/planner source-scope còn thiếu. Kế tiếp là Codex plan sửa hai lỗi tái hiện được, giao executor coding, rồi QA độc lập; chưa chạy thí nghiệm primary/H1 hoặc viết luận án tiếp. Các số 6367 là candidates, không phải graph import đã commit. E085 sửa nhầm stored relationships với undirected traversal rows.

## Người dùng yêu cầu nối tiếp cả ba hướng

Codex xác nhận đã chậm nối tiếp các gói sau first-pass delivery, không gọi chúng là chưa từng được giao. Đã đọc lại HANDOFF_TO_CODEX_0608 và REVIEW_PACKET, giữ các sửa đổi/giới hạn QA hiện tại.

- `/root/social_poi_resume`: spawned theo Codex /plan `handoffs/CR-057/brief.md`. Chỉ runner orchestration reuse gate + focused tests/own report; Hermes thực thi. Không live fetch/import. Root nghiệm thu lại6probes + social suite.
- `/root/agent_memory_resume`: spawned theo `handoffs/RS-058/brief.md`. Đọc RS049, cập nhật ảnh hưởng của sửa memory, đối chiếu Hermes/Letta/LangGraph và thêm1harness bằng nguồn chính chủ; Hermes soạn báo cáo. P2 không coding trong bốn phase.
- `/root/interactive_docs_update`: đã chạy DOC056, giữ toàn quyền report HTML/JSON/generator đến release. Sơ đồ đã nhúng từ OC048, không tạo lại vô cớ. Child đã nhận guard registration5/5 mới.

Đây là ba native sub-agent được người dùng yêu cầu rõ, không phải ba chat mới. Chưa coi spawn là hoàn thành; session/task receipts chỉ là dispatch evidence. Không có writer overlap. Root tiếp tục kiểm chứng, sửa kết luận và lưu checkpoint sau release.
