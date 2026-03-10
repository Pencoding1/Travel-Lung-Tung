window.addEventListener('beforeunload', function (e) {
    // Chặn hành vi chuyển hướng hoặc tải lại trang
    e.preventDefault();
    console.log("Đã chặn một nỗ lực chuyển hướng trang!");
});