const delay = ms => new Promise(res => setTimeout(res, ms));

const simulateClick = (element) => {
    if (element) {
        const event = new MouseEvent('click', {
            view: window,
            bubbles: true,
            cancelable: true
        });
        element.dispatchEvent(event);
    }
};

const extractModalData = () => {
    const modal = document.querySelector("div[data-testid='ctrTicketDetailsModal']");
    if (!modal) return null;

    // 1. Tạo bản sao để thao tác "phẫu thuật" an toàn trên DOM mà không làm hỏng UI web thật
    let clone = modal.cloneNode(true);

    // 2. Trích xuất Title và Links trước khi dọn dẹp
    const titleEl = clone.querySelector("h1");
    const title = titleEl ? titleEl.innerText.trim() : "Unknown Ticket";

    const linkEls = clone.querySelectorAll("a");
    const links = Array.from(linkEls).map(a => ({
        label: a.innerText.trim(),
        url: a.href
    })).filter(l => l.url && !l.url.startsWith('javascript:'));

    // 3. XÓA RÁC GIAO DIỆN (Garbage Collection)
    const garbageSelectors = [
        '[data-testid^="tabItemDetails-"]',      // Các nút Tab menu ngang (Tổng quan, Hiệu lực...)
        '[data-testid="lblItemPrice"]',          // Giá gốc
        '[data-testid="lblItemDiscountedPrice"]',// Giá đã giảm
        '[data-testid="btnCloseDetailsModal"]',  // Nút X đóng modal
        '[data-testid="btnReadMore"]',           // Nút Đọc thêm / Ẩn nội dung
        '.r-1vvnge1'                             // Huy hiệu giảm giá UI (-15%)
    ];
    
    garbageSelectors.forEach(selector => {
        clone.querySelectorAll(selector).forEach(el => el.remove());
    });

    // Xóa các phần tử chứa text rác cụ thể (Chọn vé, Được hoàn tiền)
    clone.querySelectorAll('div, span').forEach(el => {
        if (!el.innerText) return;
        const text = el.innerText.trim();
        if (text === 'Chọn vé' || text === 'Được hoàn tiền') {
            el.remove();
        }
    });

    // 4. CHUẨN HÓA CẤU TRÚC SANG SEMANTIC HTML
    // A. Chuyển các tiêu đề giả (div) thành thẻ <h3>
    const subHeadingKeywords = [
        "Giá đã bao gồm", "Giá không bao gồm", "Thông tin chung", 
        "Chính sách vào cửa", "Chính sách tái nhập cảnh", 
        "Chính sách đồ ăn & thức uống bên ngoài"
    ];
    clone.querySelectorAll('div').forEach(div => {
        // Chỉ xét các div không chứa HTML con phức tạp bên trong
        if (div.children.length === 0 && subHeadingKeywords.includes(div.innerText.trim())) {
            let h3 = document.createElement('h3');
            h3.innerText = div.innerText.trim();
            div.replaceWith(h3);
        }
    });

    // B. Phục hồi gạch đầu dòng (Lists) cho các dòng UI Flexbox
    clone.querySelectorAll('.r-18u37iz').forEach(row => {
        // Nếu row chứa icon bullet (img, svg, hoặc div vẽ chấm tròn r-z2wwpe)
        if (row.querySelector('img') || row.querySelector('svg') || row.querySelector('.r-z2wwpe')) {
            let textContent = row.innerText.trim();
            if (textContent && textContent.length > 0) {
                let li = document.createElement('li');
                li.innerText = textContent;
                row.replaceWith(li); // Thay thế cụm flexbox lằng nhằng bằng 1 thẻ <li> gọn gàng
            }
        }
    });

    return { 
        ticket_name: title, 
        clean_html: clone.innerHTML, // Trả về HTML đã dọn dẹp thay vì mảng text thô
        attached_links: links
    };
};

return await (async () => {
    let results = [];
    const detailBtns = document.querySelectorAll("div[data-testid='btnSeeItemDetails']");

    for (let i = 0; i < detailBtns.length; i++) {
        simulateClick(detailBtns[i]);
        await delay(2000); 

        const readMoreBtn = document.querySelector("div[data-testid='btnReadMore']");
        if (readMoreBtn) {
            simulateClick(readMoreBtn);
            await delay(1000); 
        }

        const data = extractModalData();
        if (data) results.push(data);

        const closeBtn = document.querySelector("div[data-testid='btnCloseDetailsModal']");
        if (closeBtn) simulateClick(closeBtn);

        await delay(1000); 
    }

    const injectedDiv = document.createElement('div');
    injectedDiv.id = 'injected_modal_data_from_js';
    injectedDiv.style.display = 'none';
    injectedDiv.innerText = JSON.stringify(results);
    document.body.appendChild(injectedDiv);

    return results;
})();