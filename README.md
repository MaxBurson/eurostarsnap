# Eurostar SNAP Scraper

Monitors Eurostar SNAP for available tickets between London and Amsterdam, sends WhatsApp notifications via CallMeBot.

## Setup

### 1. Get CallMeBot API Key
1. Add `+34 644 71 81 99` to your WhatsApp contacts
2. Send `I allow callmebot to send me messages` to that number
3. Save the API key you receive

### 2. Configure GitHub Secrets
Add these secrets to your GitHub repo (Settings → Secrets → Actions):
- `CALLMEBOT_PHONE`: Your phone number with country code (e.g., `447123456789`)
- `CALLMEBOT_APIKEY`: The API key from CallMeBot

### 3. Enable GitHub Actions
The scraper runs automatically every 10 minutes via GitHub Actions.

## Local Development

```bash
pip install -r requirements.txt
export CALLMEBOT_PHONE="your_phone"
export CALLMEBOT_APIKEY="your_apikey"
python scraper.py
```

## Routes Monitored
- London St Pancras → Amsterdam Centraal
- Amsterdam Centraal → London St Pancras
