from playwright.async_api import async_playwright

async def discover_dynamic_urls(seed_url: str, domain: str) -> list[str]:
    urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(seed_url, timeout=30000)
        await page.wait_for_timeout(3000)

        anchors = await page.query_selector_all("a[href]")
        for a in anchors:
            href = await a.get_attribute("href")
            if href and domain in href:
                urls.add(href)

        await browser.close()

    return list(urls)
