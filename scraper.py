#!/usr/bin/env python3
"""
Eurostar SNAP Scraper
Monitors for available tickets between London and Amsterdam.
Sends WhatsApp notifications via CallMeBot when tickets are found.
"""

import os
import re
import requests
import urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
SNAP_URL = "https://snap.eurostar.com/uk-en"
ROUTES = [
    {"from": "London", "to": "Amsterdam"},
    {"from": "Amsterdam", "to": "London"},
]

# CallMeBot settings from environment
CALLMEBOT_PHONE = os.environ.get("CALLMEBOT_PHONE", "")
CALLMEBOT_APIKEY = os.environ.get("CALLMEBOT_APIKEY", "")


def send_whatsapp(message: str) -> bool:
    """Send WhatsApp message via CallMeBot API."""
    if not CALLMEBOT_PHONE or not CALLMEBOT_APIKEY:
        print("CallMeBot credentials not configured. Message:")
        print(message)
        return False

    encoded_message = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={CALLMEBOT_PHONE}&text={encoded_message}&apikey={CALLMEBOT_APIKEY}"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            print(f"WhatsApp message sent successfully")
            return True
        else:
            print(f"Failed to send WhatsApp: {response.status_code} - {response.text}")
            return False
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
                    
                    # Look for route selection or available dates on the page
                    # The SNAP site typically shows a calendar or list of available dates
                    
                    # Try to find and click on origin selector
                    origin_selector = page.locator(f"text={route['from']}").first
                    if origin_selector.count() > 0:
                        origin_selector.click()
                        page.wait_for_timeout(1000)
                    
                    # Try to find destination
                    dest_selector = page.locator(f"text={route['to']}").first
                    if dest_selector.count() > 0:
                        dest_selector.click()
                        page.wait_for_timeout(1000)
                    
                    # Look for available dates - these are typically highlighted or clickable
                    # Common patterns: calendar cells, date buttons, availability indicators
                    available_elements = page.locator(
                        "[class*='available'], [class*='selectable'], "
                        "[data-available='true'], .calendar-day:not(.disabled), "
                        "[class*='date']:not([class*='unavailable']):not([class*='disabled'])"
                    )
                    
                    # Also check for any text indicating availability
                    page_content = page.content()
                    
                    # Look for date patterns in the page
                    date_pattern = r'\b(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*(\d{4})?\b'
                    dates_found = re.findall(date_pattern, page_content, re.IGNORECASE)
                    
                    # Check for "no availability" messages
                    no_availability_patterns = [
                        "no tickets available",
                        "sold out",
                        "no availability",
                        "no snap tickets",
                        "check back later"
                    ]
                    
                    page_text = page.inner_text("body").lower()
                    has_no_availability = any(pattern in page_text for pattern in no_availability_patterns)
                    
                    if has_no_availability:
                        print(f"  No availability found for {route['from']} → {route['to']}")
                    elif available_elements.count() > 0 or dates_found:
                        # Found potential availability
                        availability_info = {
                            "route": f"{route['from']} → {route['to']}",
                            "element_count": available_elements.count(),
                            "dates_found": dates_found[:5] if dates_found else []
                        }
                        results["available"].append(availability_info)
                        print(f"  FOUND AVAILABILITY: {availability_info}")
                    else:
                        print(f"  Could not determine availability for {route['from']} → {route['to']}")
                        
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
