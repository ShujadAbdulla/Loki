"""WhatsApp Web scraper — Phase 1, read-only."""

from __future__ import annotations

import os
import time
from pathlib import Path

PROFILE_DIR = str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PersonalAgent" / "whatsapp_profile")


class WhatsAppAdapter:
    def __init__(self, config, audit):
        self._config = config
        self._audit = audit
        self._driver = None

    def _get_driver(self):
        if self._driver:
            return self._driver
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        opts = Options()
        opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=opts)
        return self._driver

    def open_and_wait_for_qr(self) -> bool:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            driver = self._get_driver()
            driver.get("https://web.whatsapp.com")
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-list"]'))
            )
            self._audit.log("whatsapp_connected", {}, category="TEAMS")
            return True
        except Exception as e:
            self._audit.log("whatsapp_error", {"error": str(e)}, category="ERROR")
            return False

    @property
    def connected(self) -> bool:
        try:
            return self._driver is not None and "web.whatsapp.com" in self._driver.current_url
        except Exception:
            return False

    def read_messages(self, contact_name: str, n: int = 20) -> list[dict]:
        try:
            from selenium.webdriver.common.by import By
            driver = self._get_driver()
            search = driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list-search"]')
            search.clear()
            search.send_keys(contact_name)
            time.sleep(2)
            results = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cell-frame-container"]')
            if not results:
                return []
            results[0].click()
            time.sleep(2)
            msgs = driver.find_elements(By.CSS_SELECTOR, '[data-testid="msg-container"]')
            messages = []
            for msg in msgs[-n:]:
                try:
                    text = msg.find_element(By.CSS_SELECTOR, '[data-testid="msg-text"]').text
                    messages.append({"text": text, "contact": contact_name})
                except Exception:
                    pass
            self._audit.log("whatsapp_read", {"contact": contact_name, "count": len(messages)}, category="TEAMS")
            return messages
        except Exception as e:
            self._audit.log("whatsapp_error", {"error": str(e)}, category="ERROR")
            return []

    def close(self):
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
