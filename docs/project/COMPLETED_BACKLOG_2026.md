# Bản Backlog Tổng Hợp Những Hạng Mục Đã Thực Hiện, Khắc Phục & Hoàn Thiện (`TVLT_2026`)

> **Ngày cập nhật:** 07/11/2026
> **Nhánh kiểm chứng (Git Branch):** `bugs_and_modules`
> **Tổng số bài kiểm thử tự động (Automated Tests):** **2.142 / 2.142 PASSED (0 Failed)**
> **Trạng thái dữ liệu đồ thị (Memgraph):** Đã nạp thành công **6.367 / 6.367 POI** từ `data/primary_20261016/graph_ready_v2/prepared_pois.jsonl` (`hcm_primary_geojson`, 26 vùng nguồn `source_areas`).

---

## 1. Tổng Quan Tiến Độ Theo Các Giai Đoạn (Phases 1 – 4 + Data Ingestion)

| Giai đoạn | Mức ưu tiên | Trọng tâm thực hiện | Trạng thái | Kiểm chứng |
| :--- | :---: | :--- | :---: | :--- |
| **Phase 1** | **P0** | Khôi phục các module cốt lõi bị thiếu (`aibox_provider.py`, `chat_mvp.py`), đồng bộ MCP contract, hoàn thiện `MemgraphUserBehaviorRepository` và JEV Intent Router. | **DONE (100%)** | `164/164` tests pass |
| **Phase 2** | **P1** | Mở rộng định tuyến đa phương thức (`car`, `foot`), bảo mật JWT & ẩn thông tin nhạy cảm trong log/HTTP error, lưu trữ lịch trình bền vững (`MANAGE_SAVED`), nâng cấp giao diện `travel.html` (`B5`, `B6`, `B7`, `F-BOOKING`). | **DONE (100%)** | `690/690` tests pass + `verify_phase2.py` |
| **Phase 3** | **P2** | Bảo mật `crawler_service` bằng `CRAWLER_API_KEY` (`hmac.compare_digest`, fail-closed `503`), mở rộng 5 hồ sơ Wikivoyage đa thành phố Việt Nam (`Đà Nẵng`, `Hội An`, `Huế`, `Đà Lạt`, `Hà Nội`), cập nhật `.env.example` & `RUNBOOK.md`. | **DONE (100%)** | `40/40` tests pass + `verify_phase3.py` |
| **Phase 4** | **P2 / Ops** | Sửa lỗi race condition thread trên Windows (`test_capacity.py`), fallback `.venv` cho `native_runtime`, thêm profile `bike` vào GraphHopper 11, đóng gói Docker cho `crawler_service`, tạo CLI `multi_city_ingest.py`, sửa healthcheck `memgraph` trong `docker-compose.yaml`. | **DONE (100%)** | Toàn bộ `2.142/2.142` tests pass + `verify_phase4.py` |
| **Data Ingestion** | **P0 / Live** | Nạp dữ liệu chuẩn hóa `data/primary_20261016/graph_ready_v2/prepared_pois.jsonl` (6.367 POI) vào `memgraph-db` qua `scripts/load_primary_snapshot.py` và kiểm chứng toàn bộ hệ thống live. | **DONE (100%)** | `6.367` POI active, `/catalog/snapshots` & `/catalog/source_areas` `200 OK` |

---

## 2. Chi Tiết Các Hạng Mục Đã Tạo Mới, Sửa Lỗi & Nâng Cấp

### 2.1. Phase 1 (P0) — Khôi Phục Module Cốt Lõi & Đồng Bộ Hợp Đồng Giao Tiếp

| Mã hạng mục | Vấn đề / Yêu cầu ban đầu | Giải pháp đã thực hiện | Tệp tin liên quan |
| :--- | :--- | :--- | :--- |
| **P1-01** | `scripts/aibox_adapter.py` gọi import `ai_service.domains.providers.aibox_provider` nhưng module này chưa tồn tại trên đĩa. | Tạo mới `aibox_provider.py` cài đặt đầy đủ `AiboxOpenAICompatibleAdapter`, `ProviderConfigError`, `ProviderTransportError`, `load_aibox_Env_config`, kiểm tra SSRF/allowlist domain, và cập nhật `scripts/aibox_adapter.py`, `config.py`, `__init__.py`. | `ai_service/domains/providers/aibox_provider.py`, `ai_service/domains/providers/config.py`, `ai_service/domains/providers/__init__.py`, `scripts/aibox_adapter.py` |
| **P1-02** | Các bộ test `tests/chat_mvp/*` và `tests/behavior_specs/test_chat_v1_1_contracts.py` yêu cầu `ai_service.domains.chat_mvp` nhưng module này bị thiếu. | Xây dựng `ai_service/domains/chat_mvp.py` cung cấp deterministic state machine cho toàn bộ 24 kịch bản `TVLT-CHAT-v1.1` (`CHITCHAT`, `PLAN`, `MANAGE_SAVED`, `MANAGE_MEMORY`, `BOOKING`, `OUT_OF_DOMAIN`), chống prompt-injection và kiểm soát provenance nghiêm ngặt. | `ai_service/domains/chat_mvp.py` |
| **P1-03** | Tham số phân trang `offset` trong MCP tool `explore_pois` chưa đồng bộ với mô tả tool và câu truy vấn Cypher. | Cập nhật `tool_description.py` và `ai_service/domains/chat_agent.py` để truyền và mô tả chính xác tham số `offset` trong `explore_pois`. | `POI_service/app/api/mcp/tool_description.py`, `ai_service/domains/chat_agent.py` |
| **P1-04** | `MemgraphUserBehaviorRepository` trong `memgraph.py` ném `IntentedNotImplementedException` cho các hàm CRUD và hành vi người dùng. | Cài đặt đầy đủ `create`, `get_by_id`, `get_all`, `update`, `delete` và `log_interaction` bằng Cypher параметризованный (parameterized) trên Memgraph. | `POI_service/app/core/infrastructure/db/repositories/memgraph.py` |
| **P1-05** | `JEVIntentRouter` chỉ nhận diện tập từ khóa hẹp và chưa được gắn vào luồng tiền xử lý của `/chat`. | Mở rộng bộ từ điển đa nhóm ý định tiếng Việt (có dấu & không dấu) trong `jev_intent.py` và tích hợp `JEVIntentRouter` vào `ai_service/main.py` với cơ chế fallback an toàn. | `ai_service/domains/jev_intent.py`, `ai_service/main.py` |

---

### 2.2. Phase 2 (P1) — Định Tuyến Đa Phương Thức, Bảo Mật, Lưu Trữ Lịch Trình & Giao Diện

| Mã hạng mục | Vấn đề / Yêu cầu ban đầu | Giải pháp đã thực hiện | Tệp tin liên quan |
| :--- | :--- | :--- | :--- |
| **P2-01** | GraphHopper chỉ có cấu hình `car`, thiếu cấu hình `foot` trong `config.yml` và `docker-compose`. | Bổ sung profile `foot` (`custom_model_files: [foot.json]`, CH `foot`) và encoded values tương ứng vào `graphhopper/data/config.yml`; đồng bộ `GRAPHHOPPER_PROFILES=car,foot` trong `docker-compose.yaml` và `docker-compose.integration.yaml`. | `graphhopper/data/config.yml`, `docker-compose.yaml`, `docker-compose.integration.yaml` |
| **P2-02** | Rò rỉ chuỗi lỗi hệ thống hoặc cấu hình nhạy cảm trong exception handler và thiếu kiểm tra độ dài tối thiểu của `JWT_SECRET`. | Chuẩn hóa xác thực `JWT_SECRET` (tối thiểu 32 ký tự cho môi trường production) trong `auth.py`; làm sạch (sanitize) toàn bộ phản hồi lỗi HTTP `500`/`502`/`503` và log trong `POI_service`, `ai_service`, `backend_service`. | `POI_service/app/core/security/auth.py`, `POI_service/app/main.py`, `ai_service/main.py`, `backend_service/app/main.py` |
| **P2-03** | Thiếu cơ chế lưu trữ lịch trình bền vững (`MANAGE_SAVED`) qua REST API. | Cài đặt `SavedDraftStore` (lưu trữ JSON bền vững theo `user_id`, cô lập dữ liệu giữa các người dùng) và các endpoint `GET/POST/DELETE /saved/itineraries` trong `ai_service/main.py`. | `ai_service/main.py`, `ai_service/domains/chat_mvp.py` |
| **P2-04** | Giao diện `travel.html` cần bổ sung công cụ quản lý lịch trình đã lưu, quản lý bộ nhớ cá nhân, tạo lịch trình mới và hộp thoại đặt chỗ (`F-BOOKING`). | Cài đặt đầy đủ các tính năng `B5` (Lịch trình đã lưu), `B6` (Hồ sơ & Bộ nhớ), `B7` (Phiên mới) và Modal `F-BOOKING` trong `ai_service/static/travel.html` mà vẫn bảo toàn 100% các bài test DOM/Playwright hiện hữu. | `ai_service/static/travel.html` |

---

### 2.3. Phase 3 (P2) — Bảo Mật Crawler, Hồ Sơ Đa Thành Phố & Tài Liệu Vận Hành

| Mã hạng mục | Vấn đề / Yêu cầu ban đầu | Giải pháp đã thực hiện | Tệp tin liên quan |
| :--- | :--- | :--- | :--- |
| **P3-01** | `crawler_service` dùng khóa mặc định `"secret_crawl_key_2025"` và so sánh chuỗi `!=` dễ bị timing attack; `main.py` chưa có global exception handler an toàn. | Nâng cấp `crawler_service/app/core/security.py` sử dụng `CRAWLER_API_KEY` từ biến môi trường, áp dụng `hmac.compare_digest`, cơ chế fail-closed (`503` khi chưa cấu hình khóa, `403` khi sai khóa) và thêm global exception handler không rò rỉ traceback vào `crawler_service/app/main.py`. | `crawler_service/app/core/security.py`, `crawler_service/app/main.py`, `tests/crawler_service/test_security.py` |
| **P3-02** | Hệ thống thu thập dữ liệu xã hội (`social_ingest`) chỉ có hồ sơ TP.HCM (`wikivoyage_en_hcmc`). | Bổ sung 5 hồ sơ Wikivoyage đa thành phố Việt Nam (`wikivoyage_en_danang`, `wikivoyage_en_hoian`, `wikivoyage_en_hue`, `wikivoyage_en_dalat`, `wikivoyage_en_hanoi`) với bounding box tọa độ chính xác trong `profiles.py` và bộ test kiểm chứng. | `crawler_service/app/social_ingest/profiles.py`, `tests/social_poi_ingest/test_wikivoyage_profile.py` |
| **P3-03** | `.env.example` và `docs/deployment/RUNBOOK.md` thiếu hướng dẫn cấu hình các biến môi trường mới (`AIBOX_*`, `CRAWLER_API_KEY`, `SAVED_ITINERARY_STORAGE_PATH`). | Cập nhật `.env.example` và viết mới mục 10 trong `docs/deployment/RUNBOOK.md` hướng dẫn chi tiết cách vận hành, kiểm tra sức khỏe và xử lý sự cố. | `.env.example`, `docs/deployment/RUNBOOK.md` |

---

### 2.4. Phase 4 (Hoàn Thiện Triệt Để) — Sửa Lỗi Môi Trường Windows, Thêm `bike`, Dockerize Crawler & Nạp Dữ Liệu Đồ Thị

| Mã hạng mục | Vấn đề / Yêu cầu ban đầu | Giải pháp đã thực hiện | Tệp tin liên quan |
| :--- | :--- | :--- | :--- |
| **P4-01** | `test_capacity_rejects_and_releases_cleanly` trong `tests/ai_provider/test_capacity.py` bị lỗi race condition lập lịch thread trên Windows (`AssertionError: assert False`). | Thay lời gọi đồng bộ `first_started.wait()` làm nghẽn asyncio event loop bằng `await asyncio.to_thread(first_started.wait, 2.0)` để worker thread trong `asyncio.to_thread` được cấp phát CPU ngay lập tức. | `tests/ai_provider/test_capacity.py` |
| **P4-02** | `test_start_ rejects_when_validation_venv_is_missing` trong `tests/core_flow/test_native_helper.py` thất bại khi máy chỉ có `.venv` mà không có `.venv-mcp-validation`. | Cập nhật `scripts/native_runtime/core_service.py` tự động fallback sang `.venv` khi `.venv-mcp-validation` không tồn tại và cập nhật bài test kiểm chứng cả hai nhánh (fallback `.venv` và báo lỗi khi thiếu cả hai). | `scripts/native_runtime/core_service.py`, `tests/core_flow/test_native_helper.py` |
| **P4-03** | Bổ sung phương thức di chuyển bằng xe đạp (`bike`) vào cấu hình GraphHopper 11. | Thêm profile `bike` (`custom_model_files: [bike.json]`) và đầy đủ danh sách `graph.encoded_values` tương thích GraphHopper 11 (`road_environment, ferry_speed, max_speed, foot_road_access, sidewalk, bike_network, bike_road_access`) vào `graphhopper/data/config.yml`; bổ sung test `test_bike_without_built_ch_sends_ch_disable`. | `graphhopper/data/config.yml`, `tests/mcp_contracts/test_routing_profile_modes.py` |
| **P4-04** | Đóng gói Docker hoàn chỉnh cho `crawler_service` mà không phá vỡ hợp đồng 6-service của `docker-compose.yaml`. | Cập nhật `crawler_service/pyproject.toml`, `crawler_service/Dockerfile` và tạo file compose overlay `docker-compose.crawler.yaml`. | `crawler_service/pyproject.toml`, `crawler_service/Dockerfile`, `docker-compose.crawler.yaml` |
| **P4-05** | Tạo công cụ CLI vận hành pipeline thu thập dữ liệu đa thành phố. | Tạo `scripts/multi_city_ingest.py` hỗ trợ `--mode dry-run` (kiểm chứng offline 6 hồ sơ thành phố) và `--mode fetch` (thu thập dữ liệu thực tế từ Wikivoyage API có kiểm soát domain allowlist). | `scripts/multi_city_ingest.py` |
| **P4-06** | Container `memgraph-db` báo `unhealthy` do cờ `-e` không hợp lệ trong `mgconsole` của phiên bản Memgraph 3.1.1. | Sửa healthcheck của `memgraph` trong `docker-compose.yaml` thành `echo 'RETURN 1;' | mgconsole --host 127.0.0.1 --port 7687 ...` giúp cả 6 container đều đạt trạng thái `Up` / `healthy`. | `docker-compose.yaml` |
| **P4-07** | Nạp dữ liệu chuẩn hóa `data/primary_20261016/graph_ready_v2/prepared_pois.jsonl` vào đồ thị `memgraph-db` và kiểm chứng toàn hệ thống. | Xây dựng script `scripts/load_primary_snapshot.py` kiểm tra mã băm SHA-256 với `manifest.json`, xác thực schema `POI` cho toàn bộ **6.367 bản ghi**, nạp vào `memgraph-db` và xác nhận qua `/catalog/snapshots` (`valid_record_count: 6367`, `source_area_count: 26`, `excluded_corrupt_count: 0`). | `scripts/load_primary_snapshot.py` |

---

## 3. Kết Quả Kiểm Chứng Hệ Thống Sau Khi Nạp Dữ Liệu

1. **Kiểm tra trạng thái Container (`docker compose ps`):**
   - `memgraph-db`: `Up (healthy)` — cổng `127.0.0.1:7687`
   - `graphhopper`: `Up` — cổng `127.0.0.1:8989` (hỗ trợ `car`, `foot`, `bike`)
   - `tvlt_2026-poi_api-1`: `Up (healthy)` — cổng `127.0.0.1:8000`
   - `tvlt_2026-poi_mcp-1`: `Up (healthy)` — cổng `127.0.0.1:8001`
   - `travel_ai_hub`: `Up (healthy)` — cổng `127.0.0.1:8002`
   - `lab`: `Up` — cổng `127.0.0.1:3000`
2. **Kiểm tra Dữ liệu Đồ thị (`GET http://127.0.0.1:8002/catalog/snapshots`):**
   - `status`: `"ok"`
   - `dataset_namespace`: `"hcm_primary_geojson"`
   - `input_sha256`: `"713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c"`
   - `valid_record_count`: `6367`
   - `source_area_count`: `26`
   - `excluded_corrupt_count`: `0`
3. **Kiểm tra Toàn bộ Test Suite:**
   - **2.142 / 2.142 bài test tự động PASSED** (`0 failed`).
   - Toàn bộ hợp đồng đóng băng (`docs/contracts/frozen/TVLT-CHAT-v1.1-20261028/manifest.json`) và dữ liệu nguồn (`data/primary_20261016/`) được bảo toàn nguyên vẹn 100% mã băm SHA-256.
