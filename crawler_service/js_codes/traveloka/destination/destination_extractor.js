return new Promise(async (resolve) => {
        const wait = (ms) => new Promise(res => setTimeout(res, ms));
        let extractedData = {
            destination_info: {}, 
            articles_carousel: [], 
            transportation_guide: { methods: [] },
            practical_tips: [], 
            activities_carousel: [], 
            hotels_carousel: []
        };

        // --- MODULE 0: HÀM QUÉT CAROUSEL TỐI ƯU ---
        async function getCarousel(keywords, requirePrice, requireRating) {
            try {
                let targetWidget = null;
                let finalTitle = keywords[0];

                // TỐI ƯU 1: Dùng textContent thay vì innerText để TÌM KIẾM (Nhanh gấp 10 lần)
                let widgets = Array.from(document.querySelectorAll('[data-testid="merch-section"], #merchandising > div, .r-pw2am6'));
                for (let w of widgets) {
                    let text = (w.textContent || "").toLowerCase();
                    if (keywords.some(kw => text.includes(kw.toLowerCase()))) {
                        targetWidget = w;
                        let h = w.querySelector('h2, h3, h4, h5, [role="heading"]');
                        if (h) finalTitle = h.textContent.trim();
                        break;
                    }
                }

                if (!targetWidget) {
                    let headings = Array.from(document.querySelectorAll('h2, h3, h4, h5, [role="heading"], div[dir="auto"], span'));
                    let targetH = headings.find(h => {
                        let t = (h.textContent || "").trim().toLowerCase();
                        return t.length > 0 && t.length < 100 && keywords.some(kw => t.includes(kw.toLowerCase()));
                    });
                    if (targetH) {
                        let curr = targetH;
                        for(let i=0; i<15; i++) { 
                            if(curr.parentElement) curr = curr.parentElement;
                            if(curr.querySelectorAll('a[href]').length >= 3) break;
                        }
                        targetWidget = curr;
                        finalTitle = targetH.textContent.trim();
                    }
                }

                if (!targetWidget) return null;

                let results = [];
                let hasNext = true;
                let maxClicks = 8; 

                while (hasNext && maxClicks > 0) {
                    let cards = Array.from(targetWidget.querySelectorAll('a[href]'));
                    for (let card of cards) {
                        let img = card.querySelector('img');
                        if (!img) continue; 
                        
                        let titleEl = card.querySelector('h2, h3, h4, h5, h6, [role="heading"]');
                        let title = titleEl ? titleEl.textContent.trim() : "";
                        
                        // Ở phần trích xuất chi tiết, vẫn dùng innerText để lấy \n
                        let textLines = (card.innerText || "").split('\n').map(t => t.trim()).filter(t => t !== "");
                        
                        if (!title && textLines.length > 0) {
                            let candidates = textLines.filter(t => !t.includes('Tiết kiệm') && !t.includes('VND') && !t.includes('₫') && !t.includes('/10'));
                            if (candidates.length > 0) title = candidates[0];
                        }
                        if (!title) continue;
                        
                        let imgUrl = img.src || img.getAttribute('srcset') || "";
                        if (imgUrl.includes(' ')) imgUrl = imgUrl.split(' ')[0]; 
                        let itemUrl = card.href || card.getAttribute('href') || "";
                        
                        let itemData = { title: title, image_url: imgUrl, url: itemUrl };
                        
                        if (requirePrice) {
                            let prices = textLines.filter(t => (t.includes('VND') || t.includes('₫')) && /\d/.test(t));
                            if (prices.length > 0) itemData.price = prices[prices.length - 1]; 
                        }
                        if (requireRating) {
                            let rates = textLines.filter(t => t.includes('/10') || /^[0-9]\.[0-9]$/.test(t));
                            if (rates.length > 0) itemData.rating = rates[0];
                        }
                        if (!results.find(i => i.title === title)) results.push(itemData);
                    }
                    
                    let nextBtn = Array.from(targetWidget.querySelectorAll('div[role="button"]')).find(b => b.querySelector('polyline[points="6 3 11 8 6 13"]'));
                    if (nextBtn) {
                        let opacity = window.getComputedStyle(nextBtn).opacity;
                        let parentHidden = nextBtn.closest('div[style*="opacity: 0"]');
                        if (opacity !== "0" && !parentHidden && maxClicks > 1) {
                            nextBtn.click(); 
                            // TỐI ƯU 2: Giảm thời gian chờ slide từ 800ms xuống 250ms (Đủ để render DOM mới)
                            await wait(250); 
                        } else { hasNext = false; }
                    } else { hasNext = false; }
                    maxClicks--;
                }
                return { section_title: finalTitle, items: results };
            } catch (e) { return null; }
        }

        try {
            // --- MODULE 1: THÔNG TIN ĐIỂM ĐẾN ---
            try {
                let titleEl = document.querySelector('h1[aria-level="1"]');
                extractedData.destination_info.title = titleEl ? titleEl.textContent.trim() : "";
                
                let seeMoreBtn = document.querySelector('div[aria-label="See More"], div[aria-label="Xem thêm"], div[aria-label="See Less"]');
                if (seeMoreBtn && (seeMoreBtn.getAttribute('aria-label') === 'See More' || seeMoreBtn.getAttribute('aria-label') === 'Xem thêm')) {
                    seeMoreBtn.click(); 
                    await wait(200); // TỐI ƯU: 700ms -> 200ms
                }
                let descContainer = titleEl ? (titleEl.closest('.r-161024n') || titleEl.parentElement.parentElement) : document;
                let pTags = descContainer.querySelectorAll('p');
                extractedData.destination_info.short_description = Array.from(pTags).map(p => p.textContent.trim()).join('\n');
            } catch(e) {}

            // TỐI ƯU 3: CHẠY SONG SONG (PARALLEL) CÁC CAROUSEL THAY VÌ TUẦN TỰ
            const [c1, c2, c3] = await Promise.all([
                getCarousel(['Bài viết cảm hứng', 'cảm hứng'], false, false),
                getCarousel(['Hoạt động thú vị', 'Trải nghiệm', 'Tham quan'], true, false),
                getCarousel(['Chỗ ở', 'Khách sạn'], true, true)
            ]);

            if(c1) extractedData.articles_carousel.push(c1);
            if(c2) extractedData.activities_carousel.push(c2);
            if(c3) extractedData.hotels_carousel.push(c3);

            // --- MODULE 2: MẸO DI CHUYỂN ---
            try {
                const normalize = txt => (txt || "").toLowerCase().trim();

                // TỐI ƯU DÙNG textContent để rà soát danh sách nhanh hơn
                const guideTitle = Array.from(
                    document.querySelectorAll('h2, h3, h4, div[role="heading"], span')
                ).find(el => {
                    const t = normalize(el.textContent);
                    return (t === "mẹo du lịch" || t.includes("mẹo du lịch khi đến") || t.includes("travel tips"));
                });

                if (guideTitle) {
                    extractedData.transportation_guide.main_title = guideTitle.textContent.trim();
                    let section = guideTitle;

                    for (let i = 0; i < 10 && section?.parentElement; i++) {
                        section = section.parentElement;
                        if (section.querySelectorAll('div[tabindex="0"]').length >= 2) break;
                    }

                    if (section) {
                        const tabs = Array.from(section.querySelectorAll('div[tabindex="0"]'))
                        .filter(el => {
                            const txt = (el.textContent || "").trim();
                            return txt.length > 0 && txt.length < 35 && !txt.includes('?');
                        }).slice(0, 8);

                        for (const tab of tabs) {
                            const keyword = tab.textContent.trim();
                            if (!keyword) continue;

                            tab.click();
                            // TỐI ƯU: Đợi cứng 300ms thay vì dùng vòng lặp interval tốn tài nguyên
                            await wait(300);

                            let longestP = "";
                            Array.from(section.querySelectorAll('p, div[dir="auto"], span')).forEach(node => {
                                if (!node.offsetParent) return; 
                                if (node.closest('div[tabindex="0"]')) return;
                                const txt = node.textContent.trim();
                                if (txt.length > longestP.length && txt.length > 20 && txt !== keyword && !txt.includes("Mẹo du lịch")) {
                                    longestP = txt;
                                }
                            });

                            if (longestP.length > 0) {
                                extractedData.transportation_guide.methods.push({ keyword, content: longestP });
                            }
                        }
                    }
                }
            } catch (e) { console.error("Lỗi Module 2:", e); }

            // --- MODULE 3: MẸO THIẾT THỰC (FAQ) ---
            try {
                let targetContainer = null;
                let popupOpened = false;

                let allTextDivs = Array.from(document.querySelectorAll('div[dir="auto"], span'));
                let targetTextDiv = allTextDivs.find(el => {
                    let txt = (el.textContent || "").toLowerCase().trim();
                    return txt.includes("see all practical tips") || txt.includes("xem tất cả mẹo");
                });

                let seeAllBtn = null;
                if (targetTextDiv && targetTextDiv.parentElement) {
                    let overlayBtn = targetTextDiv.parentElement.querySelector('div[tabindex="0"]');
                    seeAllBtn = overlayBtn ? overlayBtn : targetTextDiv.parentElement;
                }

                if (seeAllBtn) {
                    seeAllBtn.click();
                    popupOpened = true;
                    await wait(800); // TỐI ƯU: 2000ms là quá thừa, 800ms đủ cho popup bật lên
                    
                    let dialogs = document.querySelectorAll('div[role="dialog"]');
                    if (dialogs.length > 0) targetContainer = dialogs[dialogs.length - 1]; 
                }

                if (!popupOpened) {
                    let tipsHeader = Array.from(document.querySelectorAll('h2, h3, h4, div[role="heading"], div[dir="auto"], span')).find(h => {
                        let t = (h.textContent || "").toLowerCase().trim();
                        return t === "mẹo thiết thực" || t.includes("mẹo thiết thực khi") || t.includes("practical tips");
                    });

                    if (tipsHeader) {
                        targetContainer = tipsHeader;
                        for(let i=0; i<15; i++) {
                            if(targetContainer.parentElement) targetContainer = targetContainer.parentElement;
                            if (targetContainer.textContent.includes('?')) break;
                        }
                    }
                }

                if (targetContainer) {
                    let faqs = Array.from(targetContainer.querySelectorAll('div[tabindex="0"]')).filter(el => {
                        return (el.textContent || "").includes('?');
                    }).slice(0, 20);

                    for(let faq of faqs) {
                        let question = faq.textContent.trim().split('\n').filter(t => t.includes('?'))[0] || faq.textContent.trim();
                        if (!question || !question.includes('?')) continue; 
                        
                        try { faq.click(); } catch(err) {} 
                        await wait(100); // TỐI ƯU: Phản hồi accordion của React rất nhanh, 100ms là đủ
                        
                        let answer = "";
                        let answerContainer = faq.nextElementSibling;
                        
                        if (answerContainer) {
                            answer = (answerContainer.textContent || answerContainer.innerText || "").trim();
                        } 

                        if (answer.length < 5 && faq.parentElement) {
                            let parentText = faq.parentElement.textContent;
                            if (parentText.includes(question)) {
                                answer = parentText.replace(question, "").trim();
                            }
                        }

                        if (answer.toLowerCase().includes("mẹo thiết thực khi") || answer === question) {
                            answer = "";
                        }

                        if(question && answer.length > 5) {
                            extractedData.practical_tips.push({ question: question, answer: answer });
                        }
                    }
                }

            } catch(e) { console.error("Lỗi Module 3:", e); }

        } catch (e) {
            extractedData.fatal_error = e.toString();
        }

        try {
            const injectedDiv = document.createElement('div');
            injectedDiv.id = 'injected_destination_data';
            injectedDiv.style.display = 'none';
            injectedDiv.innerText = JSON.stringify(extractedData);
            document.body.appendChild(injectedDiv);
        } catch(e) {}
        
        resolve(extractedData);
    });