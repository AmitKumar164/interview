# linkedin_scrape.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import json

# --------------- CONFIG ---------------
PROFILE_URL = "https://www.linkedin.com/in/amit-kumar-a38728203/"  # change to your target
CHROMEDRIVER_PATH = "/usr/bin/chromedriver"  # or wherever your chromedriver lives
# --------------------------------------

options = Options()
options.add_argument("--start-maximized")
# you may add headless if you want, but many sites detect headless => better visible
# options.add_argument("--headless")

service = ChromeService(executable_path=CHROMEDRIVER_PATH)
driver = webdriver.Chrome(service=service, options=options)

try:
    driver.get(PROFILE_URL)
    time.sleep(5)  # wait for page load

    # Scroll to bottom to load dynamic content
    scroll_pause = 2
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    data = {}

    # Example: name
    h1 = soup.find("h1")
    if h1:
        data["name"] = h1.get_text(strip=True)

    # Example: headline / current role
    headline = soup.find("div", {"class": "text-body-medium"})
    if headline:
        data["headline"] = headline.get_text(strip=True)

    # Example: location (bottom of name or near top)
    location = soup.select_one("span.text-body-small")
    if location:
        data["location"] = location.get_text(strip=True)

    # Example: summary / about (if present)
    about = soup.find("section", {"class": "pv-about-section"})
    if about:
        data["about"] = about.get_text(strip=True)

    # Example: experience block — note: LinkedIn’s HTML changes often, verify in browser devtools
    exp_section = soup.find_all("div", {"class": "pv-entity__summary-info"})
    experiences = []
    for exp in exp_section:
        title_el = exp.find("h3")
        company_el = exp.find("p", {"class": "pv-entity__secondary-title"})
        date_el = exp.find("h4", {"class": "pv-entity__date-range"})
        experiences.append({
            "title": title_el.get_text(strip=True) if title_el else None,
            "company": company_el.get_text(strip=True) if company_el else None,
            "dates": date_el.get_text(strip=True) if date_el else None
        })
    if experiences:
        data["experience"] = experiences

    print(json.dumps(data, indent=2))

finally:
    driver.quit()
