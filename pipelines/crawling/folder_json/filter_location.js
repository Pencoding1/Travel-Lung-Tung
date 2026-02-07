async () => {
    const wait = (ms) => new Promise(r => setTimeout(r, ms));

    async function selectAndApplyLocation(locationName) {
        console.log(`\n📍 Bắt đầu quy trình chọn: ${locationName}`);

        const dropdownInputs = document.querySelectorAll('.select-container__button input[placeholder="Tìm kiếm..."]');

        const triggerInput = dropdownInputs[1];

        if (triggerInput) {
            console.log("1. Click mở Dropdown...");
            triggerInput.click();
            await wait(1000); // Chờ 1s cho list sổ xuống
        } else {
            console.error("❌ Không tìm thấy ô chọn điểm khởi hành!");
            return;
        }

        const listItems = document.querySelectorAll('li.select-container__list--item');
        let targetItem = null;

        for (let item of listItems) {
            if (item.textContent.trim() === locationName) {
                targetItem = item;
                break;
            }
        }

        if (targetItem) {
            console.log(`2. Đã tìm thấy "${locationName}". Click chọn...`);
            targetItem.click();
            await wait(500); // Chờ UI cập nhật lựa chọn
        } else {
            console.error(`❌ Không tìm thấy địa điểm: ${locationName} trong danh sách!`);
        }

        const buttons = document.querySelectorAll('button.btn.btn-primary');
        let applyBtn = null;

        for (let btn of buttons) {
            if (btn.textContent.trim() === "Áp dụng") {
                applyBtn = btn;
                break;
            }
        }

        if (applyBtn) {
            console.log("3. Click nút 'Áp dụng'.");
            applyBtn.click();
            console.log("⏳ Đang chờ tải dữ liệu mới...");
            await wait(3000);
        } else {
            console.error("❌ Không tìm thấy nút Áp dụng!");
        }
    }

    await selectAndApplyLocation("TP. Hồ Chí Minh");
    await selectAndApplyLocation("Hà Nội");

    console.log("\n✅ Đã hoàn tất toàn bộ kịch bản lọc!");
};