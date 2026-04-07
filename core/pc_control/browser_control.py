from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus


class BrowserControl:
    def open_url(self, url: str) -> bool:
        return webbrowser.open(url)

    def search(self, query: str) -> bool:
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        return webbrowser.open(search_url)
