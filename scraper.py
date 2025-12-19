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
                page.wait_for_timeout(2000)
                
                # Accept cookies if they appear again
                try:
                    cookie_btn = page.locator("button:has-text('Accept'), #onetrust-accept-btn-handler")
                    if cookie_btn.count() > 0:
                        cookie_btn.first.click()
                        page.wait_for_timeout(1000)
                except:
                    pass
                
                # Take initial screenshot
                page.screenshot(path=f"snap_{origin.lower()}_{destination.lower()}_initial.png")
                
                # Get page text to check for "sold out" message (appears immediately without clicking search)
                page_text = page.inner_text("body").lower()
                print(f"Page text sample: {page_text[:300]}...")
                
                # Check for the "Sorry this route is currently sold out" message
                route_sold_out = "sorry this route is currently sold out" in page_text
                
                print(f"Route sold out: {route_sold_out}")
                
                if route_sold_out:
                    print(f"❌ {origin} → {destination}: SOLD OUT")
                    results["sold_out"].append(f"{origin} → {destination}")
                else:
                    # Route has availability - click date button to open calendar and get available dates
                    available_dates = []
                    print("Opening calendar to extract available dates...")
                    
                    try:
                        # Click on the date button (shows something like "Sat 20 Dec")
                        date_btn = page.locator("button:has-text('Dec'), button:has-text('Jan')").first
                        date_btn.click(timeout=5000)
                        page.wait_for_timeout(1500)
                        
                        # Take screenshot of calendar
                        page.screenshot(path=f"calendar_{origin.lower()}_{destination.lower()}.png")
                        print("Calendar opened, extracting dates...")
                        
                        # Get all buttons in the calendar
                        all_buttons = page.locator("button").all()
                        
                        for btn in all_buttons:
                            try:
                                text = btn.inner_text().strip()
                                # Check if it's a day number (1-31)
                                if text.isdigit() and 1 <= int(text) <= 31:
                                    # Check if button is disabled (grey) or enabled (black/available)
                                    is_disabled = btn.is_disabled()
                                    classes = btn.get_attribute("class") or ""
                                    aria_disabled = btn.get_attribute("aria-disabled")
                                    
                                    is_grey = (
                                        is_disabled or
                                        "disabled" in classes.lower() or
                                        aria_disabled == "true"
                                    )
                                    
                                    if not is_grey:
                                        available_dates.append(int(text))
                            except:
                                pass
                        
                        # Remove duplicates and sort
                        available_dates = sorted(list(set(available_dates)))
                        # Convert back to strings
                        available_dates = [str(d) for d in available_dates]
                        
                    except Exception as e:
                        print(f"Could not extract dates from calendar: {e}")
                    
                    print(f"Found {len(available_dates)} available dates: {available_dates}")
                    print(f"✅ {origin} → {destination}: AVAILABILITY FOUND!")
                    
                    results["available"].append({
                        "route": f"{origin} → {destination}",
                        "dates": available_dates if available_dates else ["check website for dates"]
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
