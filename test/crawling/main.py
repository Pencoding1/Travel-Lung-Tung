
import os
import dotenv
from pipelines.crawling.Crawling import ManualCrawler

dotenv.load_dotenv()

if __name__ == "__main__":
    print("\n" + "="*60)
    print(" ĐANG CHẠY TEST TRỰC TIẾP TẠI FILE CRAWLING.PY")
    print("="*60)
    
    # Khởi tạo
    crawler = ManualCrawler()
    target = "https://travel.com.vn/du-lich-ho-chi-minh.aspx"
    
    # Test Crawl
    print(f"📡 Crawl: {target}")
    crawler.crawl(target) # Sẽ gọi logic _fetch_markdown bên trong
    
    # Lấy dữ liệu raw
    raw_md = crawler.crawled_contents.get(target)
    
    if raw_md:
        # Test Parse
        print("🧠 Parse & Download ảnh...")
        data = crawler.parse(raw_md)
        
        print("\n" + "="*60)
        print(f"📊 KẾT QUẢ: {len(data)} TOUR")
        print("="*60)
        
        for idx, t in enumerate(data, 1):
            print(f"Tour #{idx}: {t.title}")
            print(f" - Giá: {t.metadata.get('price', 'N/A')}")
            if t.images:
                print(f" - Ảnh: ✅ Đã có Base64 (Len: {len(t.images[0])})")
            else:
                print(" - Ảnh: ⚠️ Không có")
            print("-" * 30)
    else:
        print("❌ Không có dữ liệu để parse.")