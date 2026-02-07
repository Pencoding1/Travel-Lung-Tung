import requests

def is_dynamic_site(url: str) -> bool:
    html = requests.get(url, timeout=10).text.lower()

    js_signals = [
        "react", "vue", "angular",
        "__next", "nuxt",
        "window.__",
        "fetch("
    ]

    return any(sig in html for sig in js_signals)
