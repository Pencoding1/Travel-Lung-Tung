async () => {
    const wait = (ms) => new Promise(r => setTimeout(r, ms));
    // 1. DỌN DẸP: Đóng các Popup quảng cáo/khuyến mãi thường thấy trên Vietravel
    const closeSelectors = [
        '.modal-header .close', '[aria-label="Close"]',
        '.btn-close-ads', '.close-popup', '.ad-close'
    ];
    closeSelectors.forEach(sel => {
        const btn = document.querySelector(sel);
        if (btn) {
            console.log("Đang đóng popup/quảng cáo...");
            btn.click();
        }
    });
    await wait(500);

    // 2. CUỘN TRANG (SMOOTH SCROLL): Kích hoạt Lazy Load tour và ảnh
    console.log("Đang cuộn trang để nạp dữ liệu ẩn...");
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
            console.log(` Force render: ${sel}`);
            area.scrollIntoView();
            await wait(400);
        }
    }

    // 5. XỬ LÝ ẢNH: HOVER VÀ TRÍCH XUẤT CAPTION (MỚI BỔ SUNG)
    console.log(" Đang xử lý Caption ảnh (Hover & Extract)...");
    const images = document.querySelectorAll('article img, .node-article img, .slider img, .view-content img, figure img');

    for (let img of images) {
        try {
            // a. Cuộn tới ảnh để kích hoạt sự kiện chuột
            img.scrollIntoView({ behavior: "instant", block: "center" });
            await wait(100);

            // b. Giả lập Hover (cho Vietnam Tourism)
            img.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
            img.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
            await wait(150); // Chờ hiệu ứng hover hiện chữ

            // c. Lấy nội dung mô tả
            let captionText = img.getAttribute('alt') || img.getAttribute('title');

            // Tìm caption bên ngoài (nếu web dùng thẻ figcaption hoặc div caption)
            const container = img.closest('figure, .media-item');
            if (container) {
                const visibleCaption = container.querySelector('figcaption, .caption');
                if (visibleCaption && visibleCaption.innerText.trim().length > 0) {
                    captionText = visibleCaption.innerText.trim();
                }
            }

            // d. Chèn Caption vào DOM (nếu chưa có)
            if (captionText && captionText.length > 5) {
                const nextSibling = img.nextElementSibling;
                // Chỉ chèn nếu chưa có thẻ caption
                if (!nextSibling || (nextSibling.tagName !== 'FIGCAPTION' && !nextSibling.classList.contains('injected-caption'))) {
                    const captionEl = document.createElement('p');
                    captionEl.className = 'injected-caption'; // Đánh dấu để không chèn lặp
                    captionEl.innerHTML = `<strong>📷: ${captionText}</strong>`;
                    captionEl.style.cssText = "font-size: 14px; color: #555; font-style: italic; margin-top: 5px; border-left: 3px solid #ccc; padding-left: 8px;";

                    if(img.parentNode) {
                        img.parentNode.insertBefore(captionEl, img.nextSibling);
                    }
                }
            }
        } catch (e) {
            console.log("Lỗi xử lý ảnh:", e);
        }
    }

    // 6. Xử lý ảnh rác - CHỈ GIỮ LẠI ẢNH TOUR
            const shouldRemove = (img) => {
    const src = (img.src || "").toLowerCase();
    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    const parent = img.parentElement;
    const alt = (img.getAttribute('alt') || "").toLowerCase();
    const className = (img.className || "").toLowerCase();
    const parentClass = (parent?.className || "").toLowerCase();

    // 1. SVG / vector / icon nền tảng
            if (
                src.includes(".svg") ||
                src.includes("svg+xml") ||
                src.includes("data:image/svg")
            ) return true;
            
            // 2. Icon / badge / label UI của Traveloka
            if (
                src.includes("imageresource") ||
                src.includes("icon") ||
                src.includes("logo") ||
                src.includes("badge") ||
                src.includes("sprite")
            ) {
                // Chỉ xóa nếu là ảnh nhỏ (icon/logo)
                if ((w > 0 && w < 150) || (h > 0 && h < 150)) {
                    return true;
                }
            }
            
            // 3. Ảnh UI rất nhỏ (rating, logo, tiện ích, button icon)
            if (
                (w > 0 && w < 150) &&
                (h > 0 && h < 150)
            ) return true;
            
            // 4. Ảnh trong các phần tử không phải nội dung tour
            if (parent) {
                // Loại bỏ ảnh trong header, footer, nav, sidebar
                if (
                    parent.closest('header, footer, nav, aside, .header, .footer, .nav, .sidebar') ||
                    parent.closest('[data-testid*="header"], [data-testid*="footer"], [data-testid*="nav"]') ||
                    parent.closest('.tv-header, .tv-footer, .breadcrumbs')
                ) return true;
                
                // Loại bỏ ảnh trong các phần quảng cáo, sponsor
                if (
                    parent.closest('.ad, .advertisement, .sponsor, .promo, .promoBanner, .partner-payment-section') ||
                    parent.closest('[class*="ad"], [class*="sponsor"], [class*="promo"], [id*="ad"]') ||
                    className.includes('ad') || className.includes('sponsor') || className.includes('promo') ||
                    parentClass.includes('ad') || parentClass.includes('sponsor') || parentClass.includes('promo')
                ) return true;
                
                // Loại bỏ ảnh trong các phần download app, newsletter
                if (
                    parent.closest('.download-app-section, .newsletter, .app-download') ||
                    parentClass.includes('download') || parentClass.includes('newsletter')
                ) return true;
            }
            
            // 5. Ảnh có alt text chứa từ khóa không mong muốn
            if (alt) {
                const unwantedKeywords = ['icon', 'logo', 'badge', 'button', 'arrow', 'chevron', 'close', 'menu', 'sponsor', 'ad', 'quảng cáo'];
                if (unwantedKeywords.some(keyword => alt.includes(keyword))) {
                    // Chỉ xóa nếu là ảnh nhỏ
                    if ((w > 0 && w < 200) || (h > 0 && h < 200)) {
                        return true;
                    }
                }
            }
            
            // 6. Ảnh trong các phần tử có class/id đặc biệt của Traveloka (UI elements)
            if (
                className.includes('icon') ||
                className.includes('logo') ||
                className.includes('badge') ||
                className.includes('rating-icon') ||
                className.includes('star-icon') ||
                img.closest('[class*="icon"], [class*="logo"], [class*="badge"]')
            ) {
                // Chỉ xóa nếu là ảnh nhỏ
                if ((w > 0 && w < 200) || (h > 0 && h < 200)) {
                    return true;
                }
            }
            
            // 7. Ảnh có URL chứa các pattern không mong muốn
            const unwantedUrlPatterns = [
                '/icon/', '/logo/', '/badge/', '/sprite/', '/button/', '/arrow/',
                'icon.', 'logo.', 'badge.', 'sprite.', 'button.', 'arrow.',
                'imageresource', 'static/traveloka', 'assets/icons', 'assets/logos'
            ];
            if (unwantedUrlPatterns.some(pattern => src.includes(pattern))) {
                // Chỉ xóa nếu là ảnh nhỏ
                if ((w > 0 && w < 200) || (h > 0 && h < 200)) {
                    return true;
                }
            }
            
            return false;
            }

            const allImages = document.querySelectorAll('img');
            let count = 0;
            allImages.forEach(img => {
                if (shouldRemove(img)) {
                    img.remove(); // Xóa khỏi DOM ngay lập tức
                    count++;
                }
            });

            console.log(`✅ Đã xóa ${count} ảnh rác (icon, logo, quảng cáo, sponsor).`);

            document.querySelectorAll('svg').forEach(el => el.remove());
            // 7. Loại bỏ Footer:
        (function removeFooterByText() {
            const FOOTER_KEYWORDS = [
                "tổng quan",
                "lựa chọn dịch vụ",
                "về traveloka",
                "sản phẩm",
                "khác"
            ];

            const bodyChildren = Array.from(document.body.children);

            let footerStartIndex = -1;

            for (let i = 0; i < bodyChildren.length; i++) {
                const el = bodyChildren[i];
                const text = (el.innerText || "").toLowerCase();

                if (FOOTER_KEYWORDS.some(k => text.includes(k))) {
                    footerStartIndex = i;
                    break;
                }
            }

            if (footerStartIndex !== -1) {
                for (let i = footerStartIndex; i < bodyChildren.length; i++) {
                    bodyChildren[i].remove();
                }
            }
        })
};