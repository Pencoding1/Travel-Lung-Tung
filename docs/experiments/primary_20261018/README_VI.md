# EXP076 — Bộ đầu vào thí nghiệm sơ cấp (UNFROZEN)

Trạng thái: **candidate chưa đóng băng, chưa được nghiệm thu**. Không phải nghiên cứu đã chấp nhận,
không có kết quả mô hình hay kết luận khoa học. Codex vẫn là bên duyệt độc lập.

## Tệp
- `build_inputs.py` — bộ sinh offline, tất định, chỉ đọc thiết kế/nguồn/tuyến đã cố định.
- `candidate_manifest.json` — 20 kịch bản H2 P01–P20 (`frozen=false`, `thesis_mode=false`,
  `review.decision=pending_codex_review`).
- `source_binding.json` — bind hash thiết kế (kể cả correction-1/2), payload, raw, builder,
  route snapshot, lineage từng POI và số tuyến từng ca.
- `h3_profile_candidates.json` — năm profile tổng hợp M1–M5, ba điều kiện, request chung;
  `frozen=false`, không phải người tham gia hay kết quả H3.

## Quy tắc đã áp dụng
- 20 ca đúng thiết kế Codex; không đổi selection/window/budget/pace/minimum/meal.
- POI bind đúng ID, namespace, input hash, nhãn nguồn Quan 1, category, toạ độ, raw hours,
  lineage hash. Mọi `cost` là `null`; giá không có trong nguồn, không suy ra 0.
- `opening_windows` chiếu chuỗi giờ nguồn qua `parse_operation_time` lên ngày authored
  (+07:00). `24/7` = 00:00 hôm nay đến 00:00 hôm sau. Giờ thiếu/không hỗ trợ = rỗng (unknown).
- `visit_minutes`, ngày, khung ngày, `max_stops`, `minimum_stops`, meal window, budget là
  giả định/ yêu cầu authored, không phải sự thật về địa điểm.
- `route_edges` chỉ gồm cặp có hướng thực tế thành công cho đúng mode và ID đã chọn;
  giữ `adapter_*`, `raw_*` và provenance chứa hash snapshot + hash response. Không suy
  tuyến ngược, không self-edge, không tuyến bịa.
- Đa ngày theo production: POI cuối ngày trước là origin ngày sau; ngày rỗng giữ origin;
  travel inbound được tính sau giờ bắt đầu ngày mới. Không giả định khách sạn/ lưu trú.
- Mọi input giữ `source_scope` và `source_evidence` đóng theo từng POI.

## Giới hạn
- Giá, freshness, license, source URL, rating đều thiếu; budget không xác định được hiệu ứng.
- Pool 8 POI có giờ hỗ trợ + 1 POI thiếu giờ là purposive, không đại diện 6367 records.
- P20 (pool rỗng) là stress test authored, không phải bằng chứng nguồn không có POI.
- 5 profile × 4 variant, 10 ca mỗi mức biên; không full factorial, không suy luận nhân quả
  cho mode/pace/budget. Giờ chỉ là chiếu chuỗi nguồn, không xác minh venue hiện tại.

## Chạy lại
```
python docs/experiments/primary_20261018/build_inputs.py
```
Không có network/model/engine call. Chạy hai lần phải giống hệt từng byte.
