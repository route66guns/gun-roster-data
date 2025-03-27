
# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

import time
import urllib.request
from urllib.parse import urlparse
import os
import requests
import io
from PIL import Image
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
                pattern = r'(\d+\.\d+\.\d+\.\d+)'  # ✅ fixed raw string
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
                    images = self.driver.find_elements(By.CSS_SELECTOR, "img.n3VNCb")
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

    def save_images(self, image_urls, keep_filenames):
        print("[INFO] Saving images...")
        for indx, image_url in enumerate(image_urls):
            try:
                print("[INFO] Image url:", image_url)
                search_string = ''.join(e for e in self.search_key if e.isalnum())
                image = requests.get(image_url, timeout=5)
                if image.status_code == 200:
                    with Image.open(io.BytesIO(image.content)) as img:
                        try:
                            if keep_filenames:
                                o = urlparse(image_url)
                                name = os.path.splitext(os.path.basename(o.path))[0]
                                filename = f"{name}.{img.format.lower()}"
                            else:
                                filename = f"{search_string}{indx}.{img.format.lower()}"
                            image_path = os.path.join(self.image_path, filename)
                            print(f"[INFO] Image saved at: {image_path}")
                            img.save(image_path)
                        except OSError:
                            rgb_im = img.convert('RGB')
                            rgb_im.save(image_path)

                        resolution = img.size
                        if resolution and (resolution[0] < self.min_resolution[0] or resolution[1] < self.min_resolution[1] or
                                           resolution[0] > self.max_resolution[0] or resolution[1] > self.max_resolution[1]):
                            img.close()
                            os.remove(image_path)
                        img.close()
            except Exception as e:
                print("[ERROR] Download failed:", e)
        print("[INFO] Downloads completed.")
