from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import requests
import io
from PIL import Image
from urllib.parse import urlparse
import re

class GoogleImageScraper():
    def __init__(self, webdriver_path, image_path, search_key="cat", number_of_images=1, headless=True, min_resolution=(0, 0), max_resolution=(1920, 1080), max_missed=10):
        print("[DEBUG] Using patched GoogleImageScraper.")
        image_path = os.path.join(image_path, search_key)
        if not isinstance(number_of_images, int):
            print("[Error] Number of images must be integer value.")
            return
        if not os.path.exists(image_path):
            print("[INFO] Image path not found. Creating a new folder.")
            os.makedirs(image_path)

        options = Options()
        if headless:
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
        
        service = Service(webdriver_path)
        self.driver = webdriver.Chrome(service=service, options=options)

        self.search_key = search_key
        self.number_of_images = number_of_images
        self.image_path = image_path
        self.url = f"https://www.google.com/search?q={search_key}&tbm=isch"
        self.min_resolution = min_resolution
        self.max_resolution = max_resolution
        self.max_missed = max_missed

    def find_image_urls(self):
        print(f"[INFO] Searching Google for: {self.search_key}")
        self.driver.get(self.url)
        image_urls = []
        count = 0
        missed_count = 0

        thumbnails = self.driver.find_elements(By.CSS_SELECTOR, "img.Q4LuWd")
        for thumbnail in thumbnails:
            try:
                thumbnail.click()
                time.sleep(1)
            except Exception:
                continue

            images = self.driver.find_elements(By.CSS_SELECTOR, "img.n3VNCb")
            all_found = [img.get_attribute("src") for img in images if img.get_attribute("src") and "http" in img.get_attribute("src")]
            if not all_found:
                print(f"[WARN] No matching image elements found for: {self.search_key}")
                missed_count += 1
                if missed_count > self.max_missed:
                    break
                continue

            image_urls.append(all_found[0])
            print(f"[INFO] Found image URL: {all_found[0]}")
            count += 1
            if count >= self.number_of_images:
                break

        self.driver.quit()
        return image_urls
