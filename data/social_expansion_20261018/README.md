# data/social_expansion_20261018

Dữ liệu của OC-050, tách tuyệt đối real/synthetic. Không có file nào là dữ liệu
đã ingest vào graph.

## `real/`

- `raw/node_137__c17af074fcbb.html`: raw capture thật của
  `https://vietnam.travel/node/137` (HTTP 200, 51051 bytes, sha256
  `c17af074fcbbb501939e95fa8fbc1e972ce4b1920e1d9a2840023b4bb11c733b`).
- `policy/`: robots.txt và terms-conditions capture thật (xem `report.json`).
- `exploratory/vietnam_travel_hcmc10_vi.html`: capture thật của bài 10 điểm HCMC;
  **không dùng** vì layout không có anchor ổn định cho từng POI.
- `export.json`: 7 record chuẩn hoá (name/address/description/anchor), synthetic=false.
- `acquisition_manifest.json`, `mapping.json`: mapping **chưa được review** (entities rỗng).
- `acquisition_out/`: kết quả quality gate thật: 7 candidates, **accepted 0**, 7 quarantine.
- `ingestion_plan/`: payload rỗng, `imported=0`.
- `report.json`, `capture_index.json`: evidence và index offline đã xác minh hash.

Reuse status của nguồn: **not_permitted**. Terms yêu cầu văn bản cho phép trước khi
dùng/copy/lưu. Vì vậy mọi record thật bị quarantine; không tuyên bố đây là dữ liệu
dùng được cho sản phẩm.

## `synthetic/`

Fixture **100% synthetic**, reviewer `"synthetic-test-reviewer"`, không phải người thật:

- 3 record: 1 đủ điều kiện (có toạ độ fixture + reviewed fixture), 1 thiếu toạ độ,
  1 thiếu name.
- `raw/page.html`: raw capture **synthetic** (91 bytes, sha256
  `f46c9c4a03a167b42087b6e7575bc3a6070f9adb92f694b4a74aa86494a952ab`), được
  `field_evidence` tham chiếu để kiểm tra roundtrip.
- `acquisition_out/`: 1 accepted, 2 quarantine; lần chạy lại 3 duplicate.
- `ingestion_plan/`: 1 payload, evidence sidecar; `imported=0`.

Không trộn file synthetic vào `real/`; state scope của pipeline cũng tách
`::synthetic` và `::real`.
