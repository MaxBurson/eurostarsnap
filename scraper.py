#!/usr/bin/env python3
"""
Eurostar SNAP Scraper
Monitors for available tickets between London and Amsterdam.
Sends WhatsApp notifications via Twilio when tickets are found.
"""

import os
import re
from twilio.rest import Client
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
SNAP_URL = "https://snap.eurostar.com/uk-en"
ROUTES = [
    {"from": "London", "to": "Amsterdam"},
    {"from": "Amsterdam", "to": "London"},
]

# Twilio settings from environment
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Sandbox number
YOUR_PHONE_NUMBER = os.environ.get("YOUR_PHONE_NUMBER", "")


def send_whatsapp(message: str) -> bool:
    """Send WhatsApp message via Twilio API."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not YOUR_PHONE_NUMBER:
        print("Twilio credentials not configured. Message:")
        print(message)
        return False

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Ensure phone numbers have whatsapp: prefix
        to_number = YOUR_PHONE_NUMBER if YOUR_PHONE_NUMBER.startswith("whatsapp:") else f"whatsapp:{YOUR_PHONE_NUMBER}"
        from_number = TWILIO_WHATSAPP_FROM if TWILIO_WHATSAPP_FROM.startswith("whatsapp:") else f"whatsapp:{TWILIO_WHATSAPP_FROM}"
        
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        print(f"WhatsApp message sent successfully. SID: {msg.sid}")
        return True
    except Exception as e:
        print(f"Error sending WhatsApp: {e}")
        return False


def scrape_snap_availability() -> dict:
    """
    Scrape Eurostar SNAP website for available dates.
    Returns dict with route info and available dates.
    """
    results = {"available": [], "errors": []}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print(f"Loading SNAP page: {SNAP_URL}")
            page.goto(SNAP_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for the page to fully load
            page.wait_for_timeout(3000)
            
            # Accept cookies if present
            try:
                cookie_btn = page.locator("button:has-text('Accept'), #onetrust-accept-btn-handler")
                if cookie_btn.count() > 0:
                    cookie_btn.first.click()
                    page.wait_for_timeout(1000)
            except:
                pass
            
            # Get page text for analysis
            page_text = page.inner_text("body").lower()
            print(f"Page text sample: {page_text[:1000]}...")
            
            # Check for "sold out" / "no availability" messages
            sold_out_patterns = [
                "sold out",
                "currently sold out", 
                "no tickets available",
                "no availability",
                "no snap tickets",
                "check back later",
                "sorry this route is currently sold out"
            ]
            
            is_sold_out = any(pattern in page_text for pattern in sold_out_patterns)
            
            # Check if London-Amsterdam route is mentioned/available
            has_london = "london" in page_text
            has_amsterdam = "amsterdam" in page_text
            
            print(f"Has London: {has_london}, Has Amsterdam: {has_amsterdam}")
            print(f"Is sold out: {is_sold_out}")
            
            if is_sold_out:
                print("❌ Route is SOLD OUT - no availability")
            else:
                # Check for positive availability indicators
                availability_indicators = [
                    "select your outbound",
                    "select your return", 
                    "choose your train",
                    "book now",
                    "add to basket",
                    "from €",
                    "from £"
                ]
                
                has_availability = any(indicator in page_text for indicator in availability_indicators)
                
                if has_availability:
                    results["available"].append({
                        "route": "London ↔ Amsterdam",
                    })
                    print("✅ AVAILABILITY FOUND!")
                else:
                    print("⚠️ No clear availability indicators found (but not explicitly sold out)")
            
            # Take a screenshot for debugging
            page.screenshot(path="snap_screenshot.png")
            print("\nScreenshot saved to snap_screenshot.png")
            
        except PlaywrightTimeout as e:
            results["errors"].append(f"Page load timeout: {str(e)}")
            print(f"Timeout error: {e}")
        except Exception as e:
            results["errors"].append(f"Scraping error: {str(e)}")
            print(f"Error: {e}")
        finally:
            browser.close()
    
    return results


def main():
    print("=" * 50)
    print("Eurostar SNAP Availability Checker")
    print("=" * 50)
    
    results = scrape_snap_availability()
    
    if results["available"]:
        # Build notification message
        message = "🚄 EUROSTAR SNAP ALERT!\n\nAvailable tickets found:\n"
        for avail in results["available"]:
            message += f"\n• {avail['route']}"
            if avail.get("dates_found"):
                dates_str = ", ".join([f"{d[0]} {d[1]}" for d in avail["dates_found"][:3]])
                message += f"\n  Dates: {dates_str}"
        
        message += f"\n\n🔗 Book now: {SNAP_URL}"
        
        print("\n" + "=" * 50)
        print("AVAILABILITY FOUND!")
        print(message)
        print("=" * 50)
        
        send_whatsapp(message)
    else:
        print("\n" + "=" * 50)
        print("No availability found at this time.")
        print("=" * 50)
    
    if results["errors"]:
        print("\nErrors encountered:")
        for error in results["errors"]:
            print(f"  - {error}")
    
    return len(results["available"]) > 0


if __name__ == "__main__":
    main()
