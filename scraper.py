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
            
            for route in ROUTES:
                try:
                    print(f"\nChecking route: {route['from']} → {route['to']}")
                    
                    # Select origin station
                    origin_input = page.locator("[data-testid='origin-input'], input[placeholder*='From'], input[aria-label*='From'], input[aria-label*='origin']").first
                    if origin_input.count() > 0:
                        origin_input.click()
                        page.wait_for_timeout(500)
                        origin_input.fill(route['from'])
                        page.wait_for_timeout(1000)
                        # Click on dropdown option
                        page.locator(f"text={route['from']}").first.click()
                        page.wait_for_timeout(500)
                    
                    # Select destination station
                    dest_input = page.locator("[data-testid='destination-input'], input[placeholder*='To'], input[aria-label*='To'], input[aria-label*='destination']").first
                    if dest_input.count() > 0:
                        dest_input.click()
                        page.wait_for_timeout(500)
                        dest_input.fill(route['to'])
                        page.wait_for_timeout(1000)
                        page.locator(f"text={route['to']}").first.click()
                        page.wait_for_timeout(500)
                    
                    # Click search button
                    search_btn = page.locator("button:has-text('Search'), button[type='submit']").first
                    if search_btn.count() > 0:
                        search_btn.click()
                        page.wait_for_timeout(3000)
                    
                    # Get page text for analysis
                    page_text = page.inner_text("body").lower()
                    print(f"  Page text sample: {page_text[:500]}...")
                    
                    # Check for "sold out" / "no availability" messages - this is the PRIMARY check
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
                    
                    if is_sold_out:
                        print(f"  ❌ SOLD OUT for {route['from']} → {route['to']}")
                        continue  # Skip to next route, don't report as available
                    
                    # Only check for availability if NOT sold out
                    # Look for actual bookable dates/times (train results)
                    has_train_results = any(indicator in page_text for indicator in [
                        "select",
                        "book now",
                        "available",
                        "€",
                        "£",
                        "departing",
                        "arriving"
                    ])
                    
                    if has_train_results:
                        availability_info = {
                            "route": f"{route['from']} → {route['to']}",
                        }
                        results["available"].append(availability_info)
                        print(f"  ✅ FOUND AVAILABILITY: {availability_info}")
                    else:
                        print(f"  ⚠️ Could not determine availability for {route['from']} → {route['to']}")
                        
                except Exception as e:
                    error_msg = f"Error checking {route['from']} → {route['to']}: {str(e)}"
                    results["errors"].append(error_msg)
                    print(f"  {error_msg}")
            
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
