"""Deterministic extraction tests for JSON-LD, HTML profiles and CSV."""

from crawler_service.app.social_ingest.extract import (
    address_hints,
    extract_csv,
    extract_html_chapters,
    extract_jsonld,
    page_slug,
)

FROM = dict(
    page_url="https://example.test/pois",
    capture_sha256="a" * 64,
    capture_path="raw/page.html",
    fetched_at="2026-10-18T00:00:00Z",
)


def chapters_html() -> str:
    return """
    <html><body><main>
      <section class="ac-chapter" id="chapter-1">
        <div class="ac-chapter__row"><h2>Bảo tàng Chứng tích Chiến tranh</h2></div>
        <div class="ac-body"><p>Mô tả <strong>đậm</strong> với tiếng Việt.</p>
          <p><strong>Admission:</strong> 15,000 VND<br>
          <strong>Hours of Operation:</strong> 7:30 a.m. - 5 p.m.<br>
          <strong>Address:</strong> 28 Võ Văn Tần, Phường 6, Quận 3</p></div>
      </section>
      <section class="ac-chapter" id="chapter-2">
        <div class="ac-chapter__row"><h2>Notre Dame Cathedral</h2></div>
        <div class="ac-body"><p>Second block narrative.</p>
          <p><strong>Address:</strong> 1 Công Xã Paris, Bến Nghé, Quận 1</p></div>
      </section>
    </main></body></html>
    """


def test_html_chapters_keep_each_block_separate_and_unicode():
    result = extract_html_chapters(chapters_html(), page_slug="node/137", **FROM)
    assert len(result.records) == 2
    first, second = result.records
    assert first.name == "Bảo tàng Chứng tích Chiến tranh"
    assert "Quận 3" in first.address_raw
    assert "Quận 1" not in first.address_raw
    assert "Second block narrative" not in first.description
    assert second.name == "Notre Dame Cathedral"
    assert second.address_raw.startswith("1 Công Xã Paris")
    assert first.record_id == "node/137#chapter-1"
    assert second.record_id == "node/137#chapter-2"
    assert first.coordinates is None
    assert first.field_evidence and all(
        item["raw_sha256"] == "a" * 64 for item in first.field_evidence
    )


def test_html_missing_name_address_description_are_marked_not_invented():
    html = """
    <section class="ac-chapter" id="chapter-1"><h2>Only Name</h2>
      <div class="ac-body"><p>Narrative without address.</p></div></section>
    <section class="ac-chapter" id="chapter-2">
      <div class="ac-body"><p>Address: 5 Test Street, District 1</p></div></section>
    <section class="ac-chapter" id="chapter-3"><h2>No Body</h2></section>
    """
    result = extract_html_chapters(html, page_slug="p", **FROM)
    assert len(result.records) == 3
    assert result.records[0].name == "Only Name"
    assert result.records[0].address_raw is None
    assert "missing_address" in result.records[0].issues
    assert result.records[1].name is None
    assert "missing_name" in result.records[1].issues
    assert result.records[2].description is None
    assert "missing_description" in result.records[2].issues


def test_html_missing_stable_anchor_is_flagged():
    html = """
    <section class="ac-chapter"><h2>No Anchor</h2>
      <div class="ac-body"><p>Narrative.</p><p>Address: 1 A Street, District 1</p></div>
    </section>
    """
    result = extract_html_chapters(html, page_slug="p", **FROM)
    assert result.records[0].record_id is None
    assert "unstable_record_anchor" in result.records[0].issues


def test_jsonld_multi_poi_and_malformed_block_is_reported_not_fatal():
    html = """
    <script type="application/ld+json">{ this is not json }</script>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[
      {"@type":"Restaurant","@id":"https://example.test/r/1","name":"Quán Ăn",
       "description":"Mô tả ngon.","address":{"streetAddress":"1 Lê Lợi","addressLocality":"Quận 1"},
       "geo":{"latitude":10.77,"longitude":106.70},
       "review":{"reviewBody":"Rất đáng thử."}},
      {"@type":"TouristAttraction","name":"Không Địa Chỉ","description":"Mô tả."}
    ]}
    </script>
    """
    result = extract_jsonld(html, **FROM)
    assert len(result.records) == 2
    assert result.errors and "malformed_jsonld" in result.errors[0]["error"]
    first, second = result.records
    assert first.record_id == "https://example.test/r/1"
    assert first.coordinates == (10.77, 106.70)
    assert first.review_text == "Rất đáng thử."
    assert "Quận 1" in first.address_raw
    assert first.category_tags == ["schema:restaurant"]
    assert second.record_id is None
    assert second.address_raw is None


def test_jsonld_itemlist_yields_each_item():
    html = """
    <script type="application/ld+json">
    {"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","item":{"@type":"CafeOrCoffeeShop","@id":"https://e.test/c/1","name":"Cafe Một","address":"1 A, District 1","description":"d1"}},
      {"@type":"ListItem","item":{"@type":"LocalBusiness","@id":"https://e.test/c/2","name":"Cafe Hai","address":"2 B, District 3","description":"d2"}}
    ]}
    </script>
    """
    result = extract_jsonld(html, **FROM)
    assert [record.name for record in result.records] == ["Cafe Một", "Cafe Hai"]
    assert result.records[0].record_id == "https://e.test/c/1"


def test_csv_bom_quotes_newlines_and_unicode():
    payload = (
        "\ufeffid,name,address,description,review\n"
        'csv-1,"Quán Một, Sài Gòn","1 Lê Lợi, Quận 1","Dòng mô tả\ncó xuống dòng",\n'
        'csv-2,"Quán ""Hai""","2 Hai Bà Trưng, Quận 3","Mô tả 2","Nhận xét 2"\n'
    ).encode("utf-8")
    result = extract_csv(
        payload,
        page_url="https://example.test/pois.csv",
        capture_sha256="b" * 64,
        capture_path="raw/pois.csv",
        fetched_at="2026-10-18T00:00:00Z",
    )
    assert not result.errors
    assert len(result.records) == 2
    assert result.records[0].record_id == "csv-1"
    assert result.records[0].name == "Quán Một, Sài Gòn"
    assert "\n" in result.records[0].description or "xuống dòng" in result.records[0].description
    assert result.records[1].name == 'Quán "Hai"'
    assert result.records[1].review_text == "Nhận xét 2"


def test_csv_without_stable_id_flags_identity():
    payload = "name,address,description\nQuán,1 A, Mô tả\n".encode("utf-8")
    result = extract_csv(
        payload,
        page_url="https://example.test/pois.csv",
        capture_sha256="b" * 64,
        capture_path="raw/pois.csv",
        fetched_at="2026-10-18T00:00:00Z",
    )
    assert result.records[0].record_id is None
    assert "unstable_record_anchor" in result.records[0].issues


def test_address_hints_use_only_explicit_text():
    hints = address_hints("28 Vo Van Tan, District 3")
    assert hints["addr:full"] == "28 Vo Van Tan, District 3"
    assert hints["addr:district_raw"] == "District 3"
    assert "addr:city_raw" not in hints
    assert address_hints("1 A, Ho Chi Minh City")["addr:city_raw"] == "Ho Chi Minh City"


def test_page_slug_is_stable_and_not_name_based():
    assert page_slug("https://vietnam.travel/node/137") == "node/137"
