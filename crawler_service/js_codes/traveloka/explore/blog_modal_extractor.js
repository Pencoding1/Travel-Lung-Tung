try {
        // TỐI ƯU 1: Thu hẹp vùng quét. 
        // Cố gắng tìm vùng chứa bài viết chính, nếu không có mới fall back về document
        const mainContainer = document.querySelector('article, main, .blog-content, .r-161024n') || document;
        
        // TỐI ƯU 2: Bỏ Array.from() để tiết kiệm RAM, duyệt trực tiếp trên NodeList
        const elements = mainContainer.querySelectorAll('h1, h2, h3, p, div[dir="auto"], img, div[role="heading"], li');
        
        let locations = [];
        let currentLocation = null;
        let shortDesc = "";
        let state = 'WAITING_FOR_H1'; 

        // TỐI ƯU 3: Khai báo Regex 1 lần duy nhất bên ngoài vòng lặp
        const regexTitleClean = /^[\d\.\/\-]+\s*/;
        const regexLineClean = /^[-•]\s*/;
        const regexRating = /\d\.\d\/10/;

        for (let i = 0; i < elements.length; i++) {
            let el = elements[i];
            if (state === 'DONE') break;

            let tagName = el.tagName.toUpperCase();

            // Xử lý Hình ảnh (Giữ nguyên logic)
            if (tagName === 'IMG') {
                if (state === 'PARSING_LOCATIONS' && currentLocation) {
                    let src = el.src || "";
                    if (src && !src.includes('svg') && !src.includes('icon') && el.alt) {
                        if (!currentLocation.image_url) {
                            currentLocation.image_url = src;
                            currentLocation.image_description = el.alt;
                        }
                    }
                }
                continue;
            }

            // TỐI ƯU 4: Dùng textContent để kiểm tra logic (Siêu nhanh vì không tính toán CSS)
            let rawText = el.textContent || ""; 
            let trimmedText = rawText.trim();
            if (!trimmedText) continue;
            
            let lowerText = trimmedText.toLowerCase();

            // BỎ QUA RÁC
            if (trimmedText.includes("VND | VI") || trimmedText.includes("Khuyến mãi") || trimmedText.includes("Đặt Ngay") || trimmedText.includes("Xem giá") || trimmedText.includes("Tiết kiệm")) continue;
            if (trimmedText.includes(" | Ảnh:") || lowerText.includes("nguồn:")) continue; 

            // ĐỢI H1
            if (state === 'WAITING_FOR_H1') {
                if (tagName === 'H1') state = 'PARSING_SHORT_DESC';
                continue;
            }

            // NHẬN DIỆN TIÊU ĐỀ
            let isHeading = (tagName === 'H2' || tagName === 'H3' || (tagName === 'DIV' && el.getAttribute('role') === 'heading' && el.getAttribute('aria-level') >= '2'));
            
            if (isHeading) {
                if (lowerText.includes("lời kết") || lowerText.includes("gợi ý") || lowerText.includes("tìm chỗ ở") || lowerText.includes("bài viết được đề xuất") || lowerText.includes("các chuyến bay nổi bật") || lowerText.includes("khám phá")) {
                    state = 'DONE';
                    break;
                }

                if (currentLocation) {
                    // TỐI ƯU 5: Dùng Spread Operator clone object nhanh hơn Object.assign
                    locations.push({...currentLocation});
                }
                
                // Khi lấy dữ liệu THẬT ĐỂ LƯU mới gọi innerText (Hạn chế tối đa số lần gọi)
                let actualText = el.innerText ? el.innerText.trim() : trimmedText;

                currentLocation = {
                    location_title: actualText.replace(regexTitleClean, '').trim(),
                    address: "",
                    ticket_price: "",
                    operating_hours: "",
                    content: "",
                    image_url: "",
                    image_description: ""
                };
                state = 'PARSING_LOCATIONS';
                continue;
            }

            // Lấy text thật có xuống dòng
            let actualText = el.innerText ? el.innerText.trim() : trimmedText;

            // LẤY MÔ TẢ NGẮN
            if (state === 'PARSING_SHORT_DESC') {
                if (actualText.length > 40 && !lowerText.includes("đọc trong khoảng") && !lowerText.includes("traveloka vn")) {
                    if (!shortDesc.includes(actualText)) {
                        shortDesc += actualText + "\n";
                    }
                }
            } 
            // LẤY THÔNG TIN ĐỊA ĐIỂM
            else if (state === 'PARSING_LOCATIONS' && currentLocation) {
                let lines = actualText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                
                for (let j = 0; j < lines.length; j++) {
                    let cleanLine = lines[j].replace(regexLineClean, ''); 
                    let lowerLine = cleanLine.toLowerCase();

                    if (lowerLine.startsWith("địa chỉ") || lowerLine.startsWith("vị trí")) {
                        let parts = cleanLine.split(':');
                        currentLocation.address = parts.length > 1 ? parts.slice(1).join(':').trim() : cleanLine;
                    } 
                    else if (lowerLine.startsWith("giá vé") || lowerLine.startsWith("mức giá") || lowerLine.startsWith("chi phí")) {
                        let parts = cleanLine.split(':');
                        let val = parts.length > 1 ? parts.slice(1).join(':').trim() : cleanLine;
                        currentLocation.ticket_price += (currentLocation.ticket_price ? " | " : "") + val;
                    } 
                    else if (lowerLine.startsWith("thời gian") || lowerLine.startsWith("giờ mở cửa") || lowerLine.startsWith("mở cửa") || lowerLine.startsWith("giờ hoạt động")) {
                        let parts = cleanLine.split(':');
                        currentLocation.operating_hours = parts.length > 1 ? parts.slice(1).join(':').trim() : cleanLine;
                    } 
                    else if (cleanLine.length > 20 && !cleanLine.includes("VND") && !regexRating.test(cleanLine)) {
                        if (!cleanLine.includes("@Shutterstock") && !cleanLine.includes("@Google Maps") && !cleanLine.includes(" | Ảnh:")) {
                            if (!currentLocation.content.includes(cleanLine)) { 
                                currentLocation.content += cleanLine + "\n";
                            }
                        }
                    }
                }
            }
        }

        if (currentLocation && state !== 'DONE') {
            locations.push({...currentLocation});
        }

        locations = locations.filter(loc => loc.address !== "" || loc.operating_hours !== "" || (loc.content && loc.content.length > 80));

        const injectedDiv = document.createElement('div');
        injectedDiv.id = 'injected_blog_data';
        injectedDiv.style.display = 'none';
        injectedDiv.innerText = JSON.stringify({
            short_description: shortDesc.trim(),
            locations: locations
        });
        document.body.appendChild(injectedDiv);

    } catch (error) {
        console.error("Custom JS Extractor Error:", error);
    }