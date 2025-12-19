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
# Direct search URLs with pre-selected routes
# Station codes: London=7015400, Amsterdam=8400058, Paris Gare du Nord=8727100
ROUTES = [
    {
        "from": "Paris", 
        "to": "Amsterdam",
        "url": "https://snap.eurostar.com/uk-en?origin=8727100&destination=8400058"  # Paris Gare du Nord to Amsterdam
    },
    {
        "from": "Amsterdam", 
        "to": "Paris",
        "url": "https://snap.eurostar.com/uk-en?origin=8400058&destination=8727100"  # Amsterdam to Paris Gare du Nord
    },
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
    results = {"available": [], "sold_out": [], "errors": []}
    
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
            
            # Check both routes: London→Amsterdam and Amsterdam→London
            for route in ROUTES:
                origin = route["from"]
                destination = route["to"]
                route_url = route["url"]
                
                print(f"\n{'='*40}")
                print(f"Checking route: {origin} → {destination}")
                print(f"URL: {route_url}")
                print(f"{'='*40}")
                
                # Load the route-specific URL directly
                page.goto(route_url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(3000)
                
                # Accept cookies if they appear again
                try:
                    cookie_btn = page.locator("button:has-text('Accept'), #onetrust-accept-btn-handler")
                    if cookie_btn.count() > 0:
                        cookie_btn.first.click()
                        page.wait_for_timeout(1000)
                except:
                    pass
                
                # Click the Search button
                print("Clicking Search button...")
                try:
                    search_btn = page.locator("button:has-text('Search')").first
                    search_btn.click(timeout=10000)
                    print("Search button clicked, waiting for results...")
                    page.wait_for_timeout(5000)
                except Exception as e:
                    print(f"Could not click search button: {e}")
                
                # Take screenshot
                screenshot_name = f"snap_{origin.lower()}_{destination.lower()}.png"
                page.screenshot(path=screenshot_name)
                print(f"Screenshot saved: {screenshot_name}")
                
                # Get page text AFTER search
                page_text = page.inner_text("body").lower()
                print(f"Page text sample: {page_text[:500]}...")
                
                # Simple check: if "sold out" appears, no availability. Otherwise, there IS availability!
                is_sold_out = "sold out" in page_text or "sorry this route" in page_text
                
                print(f"Contains 'sold out': {is_sold_out}")
                
                if is_sold_out:
                    print(f"❌ {origin} → {destination}: SOLD OUT")
                    results["sold_out"].append(f"{origin} → {destination}")
                else:
                    # Try to get available dates from the calendar
                    available_dates = []
                    try:
                        # Click on date field to open calendar
                        date_field = page.locator("[class*='date'], button:has-text('Dec'), button:has-text('Jan')").first
                        date_field.click(timeout=5000)
                        page.wait_for_timeout(1000)
                        
                        # Look for bold dates (available) in the calendar
                        # Bold dates typically have font-weight: bold or a specific class
                        bold_dates = page.locator("button[class*='bold'], [style*='font-weight: bold'], [style*='font-weight:bold'], [class*='available'], [class*='active']:not([class*='disabled'])")
                        
                        for i in range(bold_dates.count()):
                            try:
                                date_text = bold_dates.nth(i).inner_text()
                                if date_text.strip().isdigit():
                                    available_dates.append(date_text.strip())
                            except:
                                pass
                        
                        print(f"Found {len(available_dates)} available dates: {available_dates}")
                    except Exception as e:
                        print(f"Could not extract dates: {e}")
                    
                    print(f"✅ {origin} → {destination}: AVAILABILITY FOUND!")
                    results["available"].append({
                        "route": f"{origin} → {destination}",
                        "dates": available_dates if available_dates else ["dates available - check website"]
                    })
            
            # Save final screenshot
            page.screenshot(path="snap_screenshot.png")
            print("\nFinal screenshot saved to snap_screenshot.png")
            
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
    
    # Always send a message with the results (for testing)
    message = "Maxie, here's your SNAP update\n"
    message += "=" * 25 + "\n\n"
    
    # Report available routes
    if results["available"]:
        message += "✅ AVAILABLE:\n"
        for avail in results["available"]:
            message += f"\n• {avail['route']}"
            if avail.get("dates"):
                dates_str = ", ".join(avail["dates"][:10])  # Show up to 10 dates
                message += f"\n  Dates: {dates_str}"
        message += "\n\n"
    
    # Report sold out routes
    if results["sold_out"]:
        message += "❌ SOLD OUT:\n"
        for route in results["sold_out"]:
            message += f"• {route}\n"
        message += "\n"
    
    # If nothing found at all
    if not results["available"] and not results["sold_out"]:
        message += "⚠️ Could not determine availability\n\n"
    
    # Report errors if any
    if results["errors"]:
        message += "⚠️ Errors:\n"
        for error in results["errors"]:
            message += f"• {error}\n"
        message += "\n"
    
    message += f"🔗 {SNAP_URL}"
    
    print("\n" + "=" * 50)
    print("RESULTS:")
    print(message)
    print("=" * 50)
    
    # Always send WhatsApp for testing
    send_whatsapp(message)
    
    return len(results["available"]) > 0


if __name__ == "__main__":
    main()
