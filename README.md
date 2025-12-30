# Eurostar SNAP Scraper

Monitors Eurostar SNAP for available tickets between London and Amsterdam, sends WhatsApp notifications via Twilio.

## Setup

### 1. Set up Twilio WhatsApp Sandbox
1. Create a Twilio account at https://www.twilio.com/try-twilio
2. Go to Console → Messaging → Try it out → Send a WhatsApp message
3. Send the join code from your phone to the sandbox number

### 2. Configure GitHub Secrets
Add these secrets to your GitHub repo (Settings → Secrets and variables → Actions → Repository secrets):
- `TWILIO_ACCOUNT_SID`: Your Twilio Account SID
- `TWILIO_AUTH_TOKEN`: Your Twilio Auth Token
- `TWILIO_WHATSAPP_FROM`: Sandbox number (e.g., `+14155238886`)
- `YOUR_PHONE_NUMBER`: Your WhatsApp number (e.g., `+447123456789`)
- `TELEGRAM_BOT_TOKEN`: Your Telegram Bot Token
- `TELEGRAM_CHAT_ID`: Your Telegram Group Chat ID

### 3. Enable GitHub Actions
The scraper runs automatically every 10 minutes via GitHub Actions.

## Local Development

```bash
pip install -r requirements.txt
playwright install chromium
export TWILIO_ACCOUNT_SID="your_sid"
export TWILIO_AUTH_TOKEN="your_token"
export TWILIO_WHATSAPP_FROM="+14155238886"
export YOUR_PHONE_NUMBER="+447123456789"
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_group_chat_id"
python scraper.py
```

## Routes Monitored
- London St Pancras → Amsterdam Centraal
- Amsterdam Centraal → London St Pancras
- London St Pancras → Paris Gare du Nord
- Paris Gare du Nord → London St Pancras
