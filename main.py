import requests
import json
import threading
import time
import logging
import os
from dotenv import load_dotenv  # Import the load_dotenv function
from requests.exceptions import RequestException
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Global variable to control the loop
stop_thread = False

def load_zone_mappings():
    with open("zones.json", "r") as file:
        return json.load(file)

zone_mapping = load_zone_mappings()

def load_webhook_urls():
    webhook_urls = []
    i = 1
    while True:
        webhook_url = os.getenv(f"WEBHOOK{i}")
        print(f"DEBUG: WEBHOOK{i} = {webhook_url}")  # Debugging line
        if webhook_url is None:
            break
        webhook_urls.append(webhook_url)
        i += 1
    logging.info(f"Loaded {len(webhook_urls)} webhook URLs from environment variables.")
    return webhook_urls

webhook_urls = load_webhook_urls()

def load_debug_webhook_url():
    return os.getenv("DEBUG_WEBHOOK")

debug_webhook_url = load_debug_webhook_url()

def fetch_terror_zone_data():
    url = 'https://www.d2emu.com/api/v1/tz'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        def get_zone_data_from_ids(ids_list):
            for zone_id in ids_list:
                zone_data = zone_mapping.get(zone_id)
                if zone_data:
                    return zone_data
            return {"location": f"Zone {ids_list[0]}"}

        current_zone_data = get_zone_data_from_ids(data['current'])
        next_zone_data = get_zone_data_from_ids(data['next'])

        zone_name_current = current_zone_data.get("location")
        image_url_current = current_zone_data.get("image", "")
        status_current = "Current"
        timestamp_current = datetime.now().strftime('%m/%d/%Y, %I:%M:%S %p')

        zone_name_next = next_zone_data.get("location")
        image_url_next = next_zone_data.get("image", "")
        status_next = "Next"
        timestamp_next = (datetime.now() + timedelta(minutes=data.get('duration', 0))).strftime('%m/%d/%Y, %I:%M:%S %p')

        return (zone_name_next, image_url_next, status_next, timestamp_next), (zone_name_current, image_url_current, status_current, timestamp_current)

    except RequestException as e:
        logging.error(f"Error fetching terror zone data: {e}")
        return None, None

def create_embed(zone_name, image_url, status, timestamp):
    if status == "Current":
        title = "Current Terror Zone"
    else:
        title = "Next Terror Zone"

    COLOR_CURRENT = 0x00FF00  # Green
    COLOR_NEXT = 0xFF0000  # Red
    color = COLOR_CURRENT if status == "Current" else COLOR_NEXT
    return {
        "title": title,
        "color": color,
        "image": {
            "url": image_url
        }
    }

def send_to_discord(current_data, next_data, webhook_url=None):
    current_embed = create_embed(*current_data)
    next_embed = create_embed(*next_data)
    footer_embed = {
        "description": "TZone-BOT v5.0 | Created by <@111629316164481024> | Data provided by d2emu.com",
        "color": 0xFFFFFF
    }
    payload = {"embeds": [current_embed, next_embed, footer_embed]}

    try:
        if webhook_url:
            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
        else:
            success_all = True
            for webhook_url in webhook_urls:
                response = requests.post(webhook_url, json=payload)
                response.raise_for_status()
                if response.status_code != 204:
                    success_all = False
                    logging.error(f"Failed to send message to Discord. Response: {response.content.decode()}")
            return success_all

    except RequestException as e:
        logging.error(f"Failed to send message to Discord. Error: {e}")
        return False

def save_last_data(data):
    try:
        with open("history.json", "w") as file:
            json.dump(data, file)
    except IOError as e:
        logging.error(f"Error saving last data to history.json: {e}")

def load_last_data():
    try:
        with open("history.json", "r") as file:
            return tuple(json.load(file))
    except (FileNotFoundError, ValueError, IOError) as e:
        logging.error(f"Error loading last data from history.json: {e}")
        return None

def main_loop():
    global stop_thread
    while not stop_thread:
        # Fetch Terror Zone data
        next_data, current_data = fetch_terror_zone_data()
        logging.info("Fetching Terror Zone data")

        # Save the fetched data to history.json
        save_last_data(next_data + current_data)
        logging.info("Save the fetched data to history.json")

        # Print to console
        (next_zone_name, next_image_url, next_status, next_timestamp), (current_zone_name, current_image_url, current_status, current_timestamp) = next_data, current_data
        logging.info(f"Current Terror Zone: {current_zone_name}, Next Terror Zone: {next_zone_name}")

        # Send the fetched data to debug webhook
        send_to_discord(
            (current_zone_name, current_image_url, current_status, current_timestamp),
            (next_zone_name, next_image_url, next_status, next_timestamp),
            webhook_url=debug_webhook_url
        )

        last_saved_data = load_last_data()
        already_sent = False
        current_time = datetime.now()
        next_hour = current_time.replace(minute=0, second=0) + timedelta(hours=1)
        seconds_until_next_hour = int((next_hour - current_time).total_seconds())
        time.sleep(seconds_until_next_hour)

    logging.info("Thread has been stopped.")

# Function to stop the loop
def stop():
    global stop_thread
    stop_thread = True

thread = threading.Thread(target=main_loop)
thread.start()
