from flask import Flask
import requests
import json
from rich import print
from rich.progress import track
from rich.spinner import Spinner
from rich.console import Console
from datetime import datetime, timedelta
import threading
import time
import warnings
import logging
from requests.exceptions import RequestException
import os
from dotenv import load_dotenv 

# Load environment variables from .env file
load_dotenv()

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module='flask')

app = Flask(__name__)

current_zone_name_global = "Initializing..."
next_zone_name_global = "Initializing..."

@app.route('/')
def home():
    global current_zone_name_global
    global next_zone_name_global
    return f"""
    <html>
        <head>
            <link href="https://fonts.googleapis.com/css2?family=Inter&display=swap" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Inter', sans-serif;
                    font-size: 1.5rem;
                    text-transform: uppercase;
                    color: #000000;
                }}
                .current-zone {{
                    text-transform: uppercase;
                }}
            </style>
        </head>
        <body>
            <span class="current-zone"><strong>Current Zone:</strong></span> {current_zone_name_global}
            <br>
            <span class="current-zone"><strong>Next Zone:</strong></span> {next_zone_name_global}
        </body>
    </html>
    """

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
    
    except RequestException:
        print("[red]Error fetching terror zone data.[/red]")
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
                    print(f"[red]Failed to send message to Discord. Response: {response.content.decode()}[/red]")
            return success_all
                
    except RequestException as e:
        print(f"[red]Failed to send message to Discord. Error: {e}[/red]")
        return False

def save_last_data(data):
    try:
        with open("history.json", "w") as file:
            json.dump(data, file)
    except IOError:
        print("[red]Error saving last data to history.json.[/red]")

def load_last_data():
    try:
        with open("history.json", "r") as file:
            return tuple(json.load(file))
    except (FileNotFoundError, ValueError, IOError):
        print("[red]Error loading last data from history.json.[/red]")
        return None

def main_loop():
    next_data, current_data = fetch_terror_zone_data()
    print(f"[bold gold1]Fetching Terror Zone data[/bold gold1]")

    save_last_data(next_data + current_data)
    print(f"[bold spring_green1]Save the fetched data to history.json[/bold spring_green1]")

    (next_zone_name, next_image_url, next_status, next_timestamp), (current_zone_name, current_image_url, current_status, current_timestamp) = next_data, current_data
    print(f"[bold cornflower_blue]Current Terror Zone:[/bold cornflower_blue] {current_zone_name}\n[bold red3]Next Terror Zone:[/bold red3] {next_zone_name}\n")

    global current_zone_name_global
    current_zone_name_global = current_zone_name

    global next_zone_name_global
    next_zone_name_global = next_zone_name

    send_to_discord(
        (current_zone_name, current_image_url, current_status, current_timestamp),
        (next_zone_name, next_image_url, next_status, next_timestamp),
        webhook_url=debug_webhook_url
    )

    last_saved_data = load_last_data()
    already_sent = False

    while True:
        current_time = datetime.now()
        if 0 <= current_time.minute < 5 and not already_sent:
            print("[blue_violet]Top of the hour detected! Waiting for a few minutes before checking for updated data...[/blue_violet]")
            
            time.sleep(180)
            
            retries = 0
            max_retries = 5

            next_data, current_data = fetch_terror_zone_data()

            while retries < max_retries and (next_data + current_data) == last_saved_data:
                time.sleep(60)
                next_data, current_data = fetch_terror_zone_data()
                retries += 1
                print("[gold1]Data matches history. Retrying...[/gold1]")

            if (next_data + current_data) != last_saved_data:
                success = send_to_discord(current_data, next_data)
                if success:
                    print(f"[medium_spring_green]Successfully sent updated data to Discord at {current_time.strftime('%I:%M %p %d-%m-%Y')}[/medium_spring_green]")
                    save_last_data(next_data + current_data)
                    already_sent = True
                else:
                    print("[red]Failed to send message to Discord.[/red]")
            else:
                print("[red]Maximum retries reached. Data still matches history.[/red]")

        else:
            already_sent = False
            next_hour = current_time.replace(minute=0, second=0) + timedelta(hours=1)
            seconds_until_next_hour = int((next_hour - current_time).total_seconds())
            
            console = Console()
            with console.status("[bold grey58]Waiting for the top of the hour...[/bold grey58]", spinner="dots"):
                time.sleep(seconds_until_next_hour)

thread = threading.Thread(target=main_loop)
thread.start()

if __name__ == "__main__":
  print("[grey54]Starting the Flask server...[/grey54]")
  app.run(host='0.0.0.0', port=6060)
