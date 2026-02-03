(async function() {
    console.log("⚡ Bắt đầu xử lý mở rộng nội dung...");
    const wait = (ms) => new Promise(r => setTimeout(r, ms));

    // 1. Cuộn trang để load toàn bộ DOM (quan trọng cho Traveloka)
    const totalHeight = document.body.scrollHeight;
    for (let i = 0; i < totalHeight; i += 600) {
        window.scrollTo(0, i);
        await wait(100);
    }
    window.scrollTo(0, document.body.scrollHeight / 3); // Quay lại vị trí giữa trang
    await wait(1000);

    // 2. Click các nút mở rộng
    const keywords = ["đọc thêm", "xem thêm", "hiển thị thêm", "read more", "chi tiết", "xem lịch trình đầy đủ"];
    // Tìm rộng hơn để không bỏ sót
    const candidates = document.querySelectorAll('div[dir="auto"], div[role="button"], div[tabindex="0"], span, [data-testid="button_expandArticle"]');

    let clicked = 0;
    for (let el of candidates) {
        try {
            let text = (el.innerText || el.textContent || "").toLowerCase().trim();
            // Kiểm tra nút đặc biệt (theo ID bạn cung cấp) hoặc theo từ khóa
            let isSpecialId = el.getAttribute('data-testid') === 'button_expandArticle';

            if (isSpecialId || (keywords.some(k => text.includes(k)) && text.length < 50)) {
                // Kiểm tra hiển thị
                if (el.offsetParent === null) continue;

                console.log(`🖱️ Click vào: ${text.substring(0, 20)}...`);
                el.scrollIntoView({behavior: "auto", block: "center"});
                await wait(300);
                el.click();
                clicked++;
                await wait(500); // Chờ nội dung bung ra
            }
        } catch (e) {}
    }

    // 3. FORCE RENDER: Cuộn qua lại khu vực lịch trình để ép hiển thị text
    const itinerary = document.querySelector('[data-testid="ctr_tourItinerary"]') || document.querySelector('#itinerary-section');
    if (itinerary) {
        console.log("🔄 Force render lịch trình...");
        itinerary.scrollIntoView();
        await wait(500);
    }
    return clicked;
})();