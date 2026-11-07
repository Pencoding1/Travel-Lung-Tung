"""Codex-authored observable acceptance cases; not fixture/model simulations."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rows=[]
def add(id,message,expected,preconditions=None):
 rows.append({'id':id,'message':message,'preconditions':preconditions or [],'expected':expected,'execution':'REAL_HTTP_AND_BROWSER_WHEN_REQUIRED','status':'NOT_RUN'})
add('I11-01','Quán này mở cửa lúc nào?',['CHITCHAT/LOOKUP','resolve current POI','retrieve actual hours or disclose unknown'],['one identified real POI in context'])
add('I11-02','Gợi ý quán cà phê yên tĩnh trong vùng đã chọn.',['CHITCHAT/RECOMMEND','source scope preserved','recommend only retrieved POIs','quietness unknown disclosed if unsupported'])
add('I11-03','Từ điểm A đến điểm B đi bộ thế nào?',['CHITCHAT/ROUTE','real foot routing for identified IDs','no straight-line fallback'],['two real POIs A/B'])
add('I11-04','Lên lịch ngày 07/11/2026 cho hai người thích bảo tàng, ngân sách 2 triệu.',['PLAN/CREATE','prefill supplied data','no planning handoff before user confirmation'])
add('I11-05','Bỏ bảo tàng khỏi lịch này, thêm quán cà phê.',['PLAN/MODIFY','resolve owned current plan','preserve other constraints','recompute route and independently validate'],['owned current plan with museum'])
add('I11-06','Sửa lịch đó đi.',['PLAN/MODIFY','NEEDS_CLARIFICATION for ambiguous plan','no handler side effect'],['two plans in context'])
add('I11-07','Lưu lịch này lại.',['MANAGE_SAVED/SAVE','require authenticated owner','persist confirmed current payload without regenerating'],['authenticated user','current plan'])
add('I11-08','Cho tôi xem các lịch đã lưu.',['MANAGE_SAVED/LIST','real bounded owner-only results'],['authenticated user with saved plans'])
add('I11-09','Mở lịch đã lưu A.',['MANAGE_SAVED/OPEN','load exact owner record','do not recompute itinerary'],['owned saved record A'])
add('I11-10','Xóa lịch đã lưu A.',['MANAGE_SAVED/DELETE','delete only exact authorized target','auditable action'],['owned saved record A dedicated to acceptance'])
add('I11-11','Mở lịch B của người khác.',['no unauthorized record disclosure','dispatch denied','no owner override from text'],['caller identity A','saved record B owned by another acceptance identity'])
add('I11-12','Bạn đang nhớ sở thích gì của tôi?',['MANAGE_MEMORY/VIEW_PROFILE','only caller profile','anonymous cannot retrieve durable profile'])
add('I11-13','Cập nhật sở thích của tôi: thích bảo tàng.',['MANAGE_MEMORY/UPDATE_PROFILE','authenticated owner','preserve other valid preferences','real version conflict handled'],['legitimate acceptance identity'])
add('I11-14','Xóa hồ sơ sở thích của tôi.',['MANAGE_MEMORY/DELETE_PROFILE','only caller profile removed','session history not implicitly removed'],['dedicated acceptance profile'])
add('I11-15','Xóa ngữ cảnh cuộc trò chuyện này.',['MANAGE_MEMORY/CLEAR_SESSION','only current namespace cleared','durable profile unchanged'],['two separate acceptance sessions'])
add('I11-16','Tìm quán yên tĩnh rồi đặt bàn luôn… mà thôi, chỉ gợi ý trước.',['RECOMMEND remains active','BOOKING request CANCELLED','no booking handler call'])
add('I11-17','Đặt bàn nhà hàng X và tạo lịch hai ngày luôn.',['atomic requests BOOKING and PLAN','MULTIPLE_ACTIONS','ask priority','no feature side effects before clarification'])
add('I11-18','Quán này còn bàn không? Nếu còn thì giữ bàn cho bốn người.',['BOOKING primary','question retained as context','no invented availability','ask target if unspecified'])
add('I11-19','Đặt bàn ở quán đó.',['BOOKING','NEEDS_CLARIFICATION if entity ambiguous','no handler side effect'],['two restaurants in context'])
add('I11-20','Đặt bàn tại quán A.',['query correct service type and source','show Book Ngay for actual service','click transfers selected service to booking screen','external command fake clearly labeled'],['actual known service A','browser interaction'])
add('I11-21','Bỏ bảo tàng, thêm cà phê gần khách sạn tôi đang ở.',['separate remove/add claims','unknown hotel stays unresolved','no invented coordinates or entity','ask necessary clarification'])
add('I11-22','Không dùng sở thích cũ, lần này chỉ đi bảo tàng trong vùng B.',['current constraints override stored preferences','scope B authoritative','no reuse of old-scope evidence'],['profile and prior scope A'])
add('I11-23','Xin chào!',['CHITCHAT social greeting','no forced POI retrieval','no booking/planning/saved/memory side effect'])
add('I11-24','Xóa lịch A rồi thôi đừng xóa nữa, mở nó cho tôi xem.',['DELETE request CANCELLED','OPEN selected','record preserved','request-level cancellation does not cancel OPEN'],['owned acceptance saved record A'])
payload={'contract':'FT-CHAT-MVP-001 v1.1','source':'docs/contracts/CHAT_INTENT_AMENDMENT_2026-10-28.md','kind':'APPROVED_BEHAVIOR_ACCEPTANCE_SPEC_NOT_TEST_RESULT','rules':['No mock/unit substitutions for live acceptance','No real booking','No primary writes','Legitimate dedicated test identities and isolated writable storage required for positive mutations','FAIL/BLOCKED/NOT_RUN distinct','Do not change old frozen tests/expected'],'cases':rows}
dest=ROOT/'tests/behavior_specs/chat_v1_1_cases.json';dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Created',len(rows),'acceptance cases; NOT_RUN.')
if len({r['id'] for r in rows})!=len(rows):raise RuntimeError('Duplicate case IDs')
