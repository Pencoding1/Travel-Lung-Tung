"""Codex-authored content assembly; no product changes or secret inputs."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
items = []

def add(id, group, title, status, text, source, choices=None):
    items.append(dict(id=id, group=group, title=title, status=status,
                      behavior=text, source=source, choices=choices or []))

review = (ROOT / 'docs/contracts/APPROVAL_REVIEW_2026-10-27.md').read_text(encoding='utf-8')
for line in review.splitlines():
    if line.startswith('| F-'):
        cells = [x.strip() for x in line.strip('|').split('|')]
        add(cells[0], 'Chức năng', cells[0], 'APPROVED', cells[1].removeprefix('APPROVED: '), 'docs/contracts/APPROVAL_REVIEW_2026-10-27.md')

chat = (ROOT / 'docs/contracts/F-CHAT_MVP_CONTRACT.md').read_text(encoding='utf-8')
add('F-CHAT', 'Chức năng', 'F-CHAT — Agent Chat MVP', 'APPROVED', chat, 'docs/contracts/F-CHAT_MVP_CONTRACT.md')
booking = (ROOT / 'docs/contracts/F-BOOKING_MVP_CONTRACT.md').read_text(encoding='utf-8')
add('F-BOOKING', 'Chức năng', 'F-BOOKING — query dịch vụ → Book Ngay → screen booking', 'APPROVED', booking, 'docs/contracts/F-BOOKING_MVP_CONTRACT.md')
add('F-UI', 'Chức năng', 'F-UI — thiết kế OTA', 'HOLD', 'Chủ dự án chưa thấy UI hiện tại giống app OTA; sẽ quyết định thiết kế cuối cùng sau. Tạm hold phần chốt UI. Được sử dụng bản draft để demo chức năng. Không coi UI draft là thiết kế cuối cùng đã duyệt. Luồng Book Ngay → screen booking vẫn thuộc F-BOOKING đã duyệt.', 'Quyết định chủ dự án trong chat ngày 27/10/2026')

# Every Chat clause remains individually reviewable, without requiring reapproval.
for match in re.finditer(r'\*\*(B[1-7]) — ([^*]+)\*\*\s*([\s\S]*?)(?=\n\*\*B[1-7]|\n### |\Z)', chat):
    add('CHAT-' + match[1], 'Chi tiết Chat', match[1] + ' — ' + match[2], 'APPROVED', match[3].strip(), 'docs/contracts/F-CHAT_MVP_CONTRACT.md')
add('CHAT-G', 'Chi tiết Chat', 'G — ràng buộc chung', 'APPROVED', 'Không tự Booking/Planning khi người dùng mới hỏi thông tin. Không tạo dữ liệu thực tế không có căn cứ.', 'docs/contracts/F-CHAT_MVP_CONTRACT.md §6')
add('CHAT-RULES', 'Chi tiết Chat', 'Các quy tắc bổ sung đã chốt', 'APPROVED', 'Đủ thông tin = sở thích/nhu cầu + ngày khởi hành/sử dụng + ngân sách; khu vực và số người có thể null. Thiếu thì ≥3 phương án. Mỗi cặp phương án khác ≥2 chiều trong khu vực, nhịp, ngân sách, loại trải nghiệm và tập POI khác nhau. Ngày tương đối được quy đổi có date_text/date_source, theo timezone Việt Nam và clock tiêm cho test. Một hành động cùng câu hỏi: hành động thắng; thiếu đối tượng thì hỏi; hai hành động ngang hàng chưa rõ ưu tiên thì hỏi thứ tự. Tên field quan sát cụ thể vẫn là thiết kế kỹ thuật, không tự coi là schema frozen.', 'docs/contracts/F-CHAT_MVP_TEST_PLAN.md §2.2–2.5')
add('TEST-GATE', 'Quyết định đã chốt', 'TA-CHAT-001 — kiến trúc và cổng nghiệm thu', 'APPROVED', 'ĐÃ DUYỆT ngày 28/10/2026 qua biên nhận receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb, chỉ mục TEST-GATE, không có ghi chú sửa đổi.\n\n20 test đặc tả cho agent lập trình đọc + 100 test QA giữ riêng để kiểm các tình huống khác, tránh chỉ làm đúng những test đã biết. Nghiệm thu: cả hai bộ đạt, kiểm tĩnh sạch và mỗi họ D1–D10 có bằng chứng cố ý phá hành vi làm test đỏ rồi hoàn nguyên. Không sửa kỳ vọng để lấy xanh; thay behavior phải có change request.\n\nBooking theo contract đã duyệt: Book Ngay chuyển screen, lệnh đặt ra ngoài là fake. Đây là kiểm offline, không chứng minh model/booking thật. Baseline ngày 22/10 giữ nguyên: T1 20 fail; T2 96 fail/4 pass; chưa chạy lại trong lượt áp dụng biên nhận. Không cần duyệt lại.', 'docs/contracts/F-CHAT_MVP_TEST_ARCHITECTURE.md; review-20261027/receipts/receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb.json')
add('SEC-SCOPE', 'Quyết định đã chốt', 'Hoàn thiện xử lý lỗi và đăng nhập ngay trong MVP', 'APPROVED', 'ĐÃ CHỐT ngày 28/10/2026: sửa trực tiếp trong MVP hiện tại, không tách thành một gói phải làm trước MVP hoặc để backlog riêng.\n\n1. Khi có lỗi, trả thông báo dễ hiểu; không hiển thị chi tiết mã và dấu vết lỗi nội bộ cho người dùng.\n2. Dịch vụ POI chỉ chấp nhận token đăng nhập có thời hạn sử dụng và xác định được người dùng, thống nhất với AI/backend.\n3. Chỉ cho phép những địa chỉ giao diện được chỉ định gọi API có đăng nhập.\n\nTrước khi sửa, kiểm tra các giao diện và token đang dùng để tránh làm hỏng luồng hiện tại; danh sách địa chỉ cụ thể sẽ được xác định từ các giao diện đang được sử dụng. Không bao gồm đưa hệ thống lên Internet.\n\nĐây là phương án đã được chủ dự án chốt trong chat, chưa phải kết quả sửa mã hoặc kiểm thử. Không cần duyệt lại nếu không có thay đổi.', 'Quyết định trực tiếp của chủ dự án trong chat ngày 28/10/2026; APPROVAL_REVIEW_2026-10-27.md')
add('CATALOG', 'Phạm vi và quy trình', 'Danh mục 11 chức năng', 'APPROVED', 'Giữ 10 chức năng: F-CHAT, F-PLAN, F-LOOKUP, F-MEMORY, F-SAVED, F-INGEST, F-ACQUIRE, F-SCOPE, F-UI, F-OPS; thêm F-BOOKING để định nghĩa riêng. Duyệt danh mục không tự duyệt implementation.', 'Quyết định chủ dự án trong chat ngày 27/10/2026')
add('WORKFLOW', 'Phạm vi và quy trình', 'Duyệt behavior trước triển khai', 'APPROVED', 'Rà soát và duyệt từng chức năng toàn hệ thống trước triển khai. F-UI cuối cùng được HOLD theo chỉ đạo sau, có thể demo bằng draft. Chưa triển khai mã sản phẩm trong đợt rà soát này. Phê duyệt behavior không đồng nghĩa đã kiểm chứng chạy thật.', 'docs/contracts/APPROVAL_REVIEW_2026-10-27.md')
add('BOUNDARIES', 'Phạm vi và quy trình', 'Các giới hạn giữ nguyên', 'APPROVED', 'Chưa đặt chỗ thật. Crawler mở rộng và grow-with-user theo Finalizing; duyệt contract F-ACQUIRE không mở phase này. H1, viết luận văn, public deployment không được mở bởi form duyệt behavior. Giữ dữ liệu/thí nghiệm primary đã đóng băng và thay đổi không liên quan của người dùng.', 'docs/project/FOUR_PHASE_PLAN.md; APPROVAL_REVIEW_2026-10-27.md')

assert len({x['id'] for x in items}) == len(items)
assert sum(x['group'] == 'Chức năng' for x in items) == 11
data = dict(schema_version=1, id='TVLT-BEHAVIOR-REVIEW-20261028-v3', title='TVLT — Duyệt behavior toàn hệ thống', date='2026-10-28', reference='School News Monitoring: selected_ids, confirm_existing/amend/keep_deferred, comment, snapshot-bound immutable receipt; original HTML unavailable in current reference docs.', notice='Snapshot v3 ngày 28/10: đã áp dụng biên nhận duyệt TEST-GATE vào tài liệu, giữ nguyên các quyết định khác và UI HOLD. Không còn câu hỏi PENDING trong danh sách này; không đồng nghĩa mã đã đạt kiểm thử. Nháp snapshot cũ vẫn được giữ trong trình duyệt nhưng không tự chuyển sang nội dung mới.', items=items)
(OUT / 'content.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Wrote {len(items)} review items; 11 functions; {sum(x["status"] == "PENDING" for x in items)} pending decision(s).')
