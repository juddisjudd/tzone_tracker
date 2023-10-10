from flask import Flask
import requests
import json
from rich import print
from rich.progress import track
from datetime import datetime, timedelta
import threading
import time

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

def fetch_terror_zone_data():
  url = 'https://api.d2tz.info/terror_zone'
  response = requests.get(url)
  if response.status_code == 200:
    data = response.json().get('data', [])
    latest_zone = data[0]['zone']
    zone_name_latest = zone_mapping.get(latest_zone, f"Zone {latest_zone}")
    timestamp_latest = datetime.fromtimestamp(
        data[0]['time']).strftime('%m/%d/%Y, %I:%M:%S %p')
    status_latest = "Coming soon"

    current_zone = data[1]['zone']
    zone_name_current = zone_mapping.get(current_zone, f"Zone {current_zone}")
    timestamp_current = datetime.fromtimestamp(
        data[1]['time']).strftime('%m/%d/%Y, %I:%M:%S %p')
    status_current = "Now"

    return (zone_name_latest, status_latest,
            timestamp_latest), (zone_name_current, status_current,
                                timestamp_current)
  else:
    return None, None


def create_embed(zone_name, status, timestamp):
  if status == "Now":
    title = "Current Terror Zone"
  else:
    title = "Next Terror Zone"

  COLOR_NOW = 0x00FF00  # Green
  COLOR_COMING_SOON = 0xFF0000  # Red
  color = COLOR_NOW if status == "Now" else COLOR_COMING_SOON
  return {
      "title": title,
      "color": color,
      "image": {
          "url": zone_name  # Here, zone_name is the image URL
      }
  }

def send_to_discord(now_data, coming_soon_data):
  now_embed = create_embed(*now_data)
  coming_soon_embed = create_embed(*coming_soon_data)
  footer_embed = {
      "description": "TZone-BOT v4.0 | Created by <@111629316164481024> | Data provided by https://d2tz.info",
      "color": 0xFFFFFF  # White or another color of your choice
  }
  payload = {"embeds": [now_embed, coming_soon_embed, footer_embed]}
  success_all = True
  for webhook_url in webhook_urls:
    response = requests.post(webhook_url, json=payload)
    if response.status_code != 204:
      success_all = False
  return success_all

def main_loop():
    # Initialize previous_data with current data from API
    (latest_zone_name, latest_status, latest_timestamp), (current_zone_name, current_status, current_timestamp) = fetch_terror_zone_data()
    previous_data = (latest_zone_name, latest_status, latest_timestamp, current_zone_name, current_status, current_timestamp)
    
    while True:
        current_time = datetime.now()
        if 0 <= current_time.minute < 5:  # If it's between XX:00 to XX:05 for every hour
            (latest_zone_name, latest_status, latest_timestamp), (current_zone_name, current_status, current_timestamp) = fetch_terror_zone_data()
            current_data = (latest_zone_name, latest_status, latest_timestamp,
                            current_zone_name, current_status, current_timestamp)
            
            if previous_data != current_data:
                if all([current_zone_name, current_status, current_timestamp, latest_zone_name, latest_status, latest_timestamp]):
                    success = send_to_discord(
                        (current_zone_name, current_status, current_timestamp),
                        (latest_zone_name, latest_status, latest_timestamp)
                    )
                    if success:
                        print(f"[green]Successfully sent updated data to Discord at {current_time.strftime('%I:%M %p %d-%m-%Y')}[/green]")
                        previous_data = current_data
                    else:
                        print("[red]Failed to send message to Discord.[/red]")
                else:
                    print("[red]Failed to fetch data from the API.[/red]")
            time.sleep(30)  # Check every 30 seconds
        else:
            next_hour = current_time.replace(minute=0, second=0) + timedelta(hours=1)
            seconds_until_next_hour = int((next_hour - current_time).total_seconds())
            print(f"[cyan]Waiting for the top of the hour. Current time: {current_time.strftime('%I:%M %p %d-%m-%Y')}[/cyan]")
            for _ in track(range(seconds_until_next_hour), description="Time left until top of the hour"):
                time.sleep(1)

thread = threading.Thread(target=main_loop)
thread.start()

if __name__ == "__main__":
  app.run(host='0.0.0.0', port=8080)
