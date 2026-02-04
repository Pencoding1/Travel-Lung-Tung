    // 1. DỌN DẸP: Đóng các Popup quảng cáo/khuyến mãi thường thấy trên Vietravel
    const closeSelectors = [
        '.modal-header .close', '[aria-label="Close"]',
        '.btn-close-ads', '.close-popup', '.ad-close'
    ];
    closeSelectors.forEach(sel => {
        const btn = document.querySelector(sel);
        if (btn) {
            console.log("🧹 Đang đóng popup/quảng cáo...");
            btn.click();
        }
    });
    await wait(500);

    // 2. CUỘN TRANG (SMOOTH SCROLL): Kích hoạt Lazy Load tour và ảnh
    console.log("📜 Đang cuộn trang để nạp dữ liệu ẩn...");
    let totalHeight = 0;
    let distance = 400; // Tăng tốc độ cuộn một chút
    const maxScroll = 6000; // Giới hạn cuộn để tránh vòng lặp vô tận trên trang quá dài

    while (totalHeight < document.body.scrollHeight && totalHeight < maxScroll) {
        window.scrollBy(0, distance);
        totalHeight += distance;
        await wait(150); // Chờ một chút để nội dung kịp render
    }

    // Quay lại giữa trang để các thành phần sticky không che khuất nội dung khi click
    window.scrollTo(0, 1000);
    await wait(100);

    // 3. CLICK MỞ RỘNG: Xử lý nút "Xem thêm" và loại bỏ icon/logo rác
    const keywords = ["đọc thêm", "xem thêm", "hiển thị thêm", "read more", "chi tiết", "xem lịch trình đầy đủ"];
    const candidates = document.querySelectorAll(
        'div[role="button"], div[tabindex="0"], button, span, [data-testid="button_expandArticle"], .btn-show-more'
    );

    let clicked = 0;
    for (let el of candidates) {
        try {
            let text = (el.innerText || el.textContent || "").toLowerCase().trim();
            let isSpecialId = el.getAttribute('data-testid') === 'button_expandArticle';

            if (isSpecialId || (keywords.some(k => text.includes(k)) && text.length < 50)) {
                if (el.offsetParent === null) continue; // Bỏ qua nếu nút đang ẩn

                console.log(`🖱️ Click mở rộng: ${text.substring(0, 20)}...`);
                el.scrollIntoView({ behavior: "instant", block: "center" });
                await wait(300);
                el.click();
                clicked++;
                await wait(600);
            }
        } catch (e) {}
    }

    // 4. FORCE RENDER: Đảm bảo các khu vực quan trọng hiện text
    const contentAreas = [
        '[data-testid="ctr_tourItinerary"]',
        '#itinerary-section',
        '.tour-introduction',
        '.tour-itinerary'
    ];

    for (let sel of contentAreas) {
        const area = document.querySelector(sel);
        if (area) {
            console.log(`🔄 Force render: ${sel}`);
            area.scrollIntoView();
            await wait(400);
        }
    }

    // 5. LOẠI BỎ RÁC: Xóa Icon và Logo khỏi DOM để Markdown sạch hơn
    const garbage = document.querySelectorAll('svg, i[class*="icon"], .logo, .social-share, .footer-ads');
    garbage.forEach(el => el.remove());

    console.log(`✅ Hoàn tất! Đã click ${clicked} mục.`);
    return clicked;
})();