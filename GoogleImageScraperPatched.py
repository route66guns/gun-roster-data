
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
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
        image_path = os.path.join(image_path, search_key)
        if not isinstance(number_of_images, int):
            print("[Error] Number of images must be integer value.")
            return
        if not os.path.exists(image_path):
            print("[INFO] Image path not found. Creating a new folder.")
            os.makedirs(image_path)
        if not os.path.isfile(webdriver_path):
            exit("[ERR] chromedriver not found at path: " + webdriver_path)

        for _ in range(1):
            try:
                options = Options()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Chrome(webdriver_path, options=options)
                self.driver.set_window_size(1400, 1050)
                self.driver.get("https://www.google.com")
                try:
                    WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.ID, "W0wltc"))).click()
                except Exception:
                    pass
            except Exception as e:
                pattern = r'(\d+\.\d+\.\d+\.\d+)'
                version = list(set(re.findall(pattern, str(e))))[0]
                exit("[ERR] Please update the chromedriver.exe to match Chrome version.")

        self.search_key = search_key
        self.number_of_images = number_of_images
        self.webdriver_path = webdriver_path
        self.image_path = image_path
        self.url = f"https://www.google.com/search?q={search_key}&source=lnms&tbm=isch"
        self.headless = headless
        self.min_resolution = min_resolution
        self.max_resolution = max_resolution
        self.max_missed = max_missed

    def find_image_urls(self):
        print("[INFO] Gathering image links")
        self.driver.get(self.url)
        image_urls = []
        count = 0
        missed_count = 0
        time.sleep(3)

        while self.number_of_images > count and missed_count < self.max_missed:
            thumbnails = self.driver.find_elements(By.CSS_SELECTOR, "img.Q4LuWd")
            for img in thumbnails[count:]:
                try:
                    img.click()
                    time.sleep(1)
                    class_names = ["n3VNCb", "iPVvYb", "r48jcc", "pT0Scc", "H8Rx8c"]
                    all_found = [self.driver.find_elements(By.CLASS_NAME, class_name) for class_name in class_names if self.driver.find_elements(By.CLASS_NAME, class_name)]
                    if not all_found:
                        print(f"[WARN] No matching image elements found for: {self.search_key}")
                        return []
                    images = all_found[0]
                    for image in images:
                        src_link = image.get_attribute("src")
                        if src_link and "http" in src_link and not "encrypted" in src_link:
                            print(f"[INFO] {self.search_key} \t #{count} \t {src_link}")
                            image_urls.append(src_link)
                            count += 1
                            break
                except Exception:
                    missed_count += 1
                if count >= self.number_of_images:
                    break

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        self.driver.quit()
        print("[INFO] Google search ended")
        return image_urls
