from flask import Flask
import requests
import json
from rich import print
from rich.progress import track
from datetime import datetime, timedelta
import threading
import time
import warnings
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module='flask')

app = Flask(__name__)

@app.route('/')
def home():
    return "Server is running."

def load_zone_mappings():
    with open("zones.json", "r") as file:
        return json.load(file)

zone_mapping = load_zone_mappings()

def load_webhook_urls():
    with open("webhooks.json", "r") as file:
        return [webhook["url"] for webhook in json.load(file)["webhooks"]]

webhook_urls = load_webhook_urls()

def load_debug_webhook_url():
    with open("webhooks.json", "r") as file:
        return json.load(file).get("debug_webhook")

debug_webhook_url = load_debug_webhook_url()

def fetch_terror_zone_data():
    url = 'https://www.d2emu.com/api/v1/tz'
    response = requests.get(url)
    if response.status_code == 200:
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
    else:
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
        "description": "TZone-BOT v5.0 | Created by <@111629316164481024> | Data provided by d2emu.com", # Please do not change this.
        "color": 0xFFFFFF
    }
    payload = {"embeds": [current_embed, next_embed, footer_embed]}
    if webhook_url:
        response = requests.post(webhook_url, json=payload)
        return response.status_code == 204
    else:
        success_all = True
        for webhook_url in webhook_urls:
            response = requests.post(webhook_url, json=payload)
            if response.status_code != 204:
                success_all = False
                print(f"[red]Failed to send message to Discord. Response: {response.content.decode()}[/red]")
        return success_all

def save_last_data(data):
    with open("history.json", "w") as file:
        json.dump(data, file)

def load_last_data():
    try:
        with open("history.json", "r") as file:
            return tuple(json.load(file))
    except (FileNotFoundError, ValueError):
        return None

def main_loop():
    (next_zone_name, next_image_url, next_status, next_timestamp), (current_zone_name, current_image_url, current_status, current_timestamp) = fetch_terror_zone_data()
    print(f"[bold green]Current Terror Zone:[/bold green] {current_zone_name}\n[bold red]Next Terror Zone:[/bold red] {next_zone_name}\n")

    send_to_discord(
        (current_zone_name, current_image_url, current_status, current_timestamp),
        (next_zone_name, next_image_url, next_status, next_timestamp),
        webhook_url=debug_webhook_url
    )

    last_hour_data = (next_zone_name, next_image_url, next_status, next_timestamp, current_zone_name, current_image_url, current_status, current_timestamp)
    last_saved_data = load_last_data()
    already_sent = False

    while True:
        current_time = datetime.now()
        if 0 <= current_time.minute < 5 and not already_sent:
            print("[cyan]Top of the hour detected! Checking for updated data...[/cyan]")
            already_sent = True
            
            retries = 0
            max_retries = 5

            while retries < max_retries:
                time.sleep(60)
                next_data, current_data = fetch_terror_zone_data()

                if last_hour_data != (next_data + current_data) and last_saved_data != (next_data + current_data):
                    break
                retries += 1
                print("[yellow]Data hasn't changed from the previous hour. Retrying...[/yellow]")

            if retries < max_retries:
                success = send_to_discord(current_data, next_data)
                if success:
                    print(f"[green]Successfully sent updated data to Discord at {current_time.strftime('%I:%M %p %d-%m-%Y')}[/green]")
                    last_hour_data = next_data + current_data
                    save_last_data(next_data + current_data)
                    time.sleep(120)
                else:
                    print("[red]Failed to send message to Discord.[/red]")
            else:
                print("[red]Maximum retries reached. Data hasn't changed from the previous hour.[/red]")
                already_sent = False

        elif current_time.minute >= 5:
            already_sent = False
            next_hour = current_time.replace(minute=0, second=0) + timedelta(hours=1)
            seconds_until_next_hour = int((next_hour - current_time).total_seconds())
            print(f"[cyan]Waiting for the top of the hour. Current time: {current_time.strftime('%I:%M %p %d-%m-%Y')}[/cyan]")
            for _ in track(range(seconds_until_next_hour), description="Time left until top of the hour"):
                time.sleep(1)

thread = threading.Thread(target=main_loop)
thread.start()

if __name__ == "__main__":
  print("[cyan]Starting the Flask server...[/cyan]")
  app.run(host='0.0.0.0', port=8080)
