#!/usr/bin/env python3
"""
Eurostar SNAP Scraper
Monitors for available tickets between London and Amsterdam.
Sends Telegram notifications when availability changes.
"""

import os
import re
import json
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# State file to track previous results
STATE_FILE = "previous_state.json"

# Configuration
SNAP_URL = "https://snap.eurostar.com/uk-en"
# Direct search URLs with pre-selected routes
# Station codes: London=7015400, Amsterdam=8400058, Paris Gare du Nord=8727100
ROUTES = [
    {
        "from": "London", 
        "to": "Amsterdam",
        "url": "https://snap.eurostar.com/uk-en?origin=7015400&destination=8400058"  # London St Pancras to Amsterdam
    },
    {
        "from": "Amsterdam", 
        "to": "London",
        "url": "https://snap.eurostar.com/uk-en?origin=8400058&destination=7015400"  # Amsterdam to London St Pancras
    },
    {
        "from": "London", 
        "to": "Paris",
        "url": "https://snap.eurostar.com/uk-en?origin=7015400&destination=8727100"  # London St Pancras to Paris Gare du Nord
    },
    {
        "from": "Paris", 
        "to": "London",
        "url": "https://snap.eurostar.com/uk-en?origin=8727100&destination=7015400"  # Paris Gare du Nord to London St Pancras
    },
]

# Telegram settings from environment
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(message: str) -> bool:
    """Send Telegram message via Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured. Message:")
        print(message)
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data)
        result = response.json()
        
        if result.get("ok"):
            print(f"Telegram message sent successfully. Message ID: {result['result']['message_id']}")
            return True
        else:
            print(f"Telegram API error: {result}")
            return False
    except Exception as e:
        print(f"Error sending Telegram: {e}")
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
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
                        page.wait_for_timeout(2000)
                        
                        # Take screenshot of calendar
                        page.screenshot(path=f"calendar_{origin.lower()}_{destination.lower()}.png")
                        print("Calendar opened, extracting dates...")
                        
                        # Get the calendar HTML to understand structure
                        calendar_html = page.content()
                        
                        # Look for day cells/buttons - try multiple approaches
                        # Approach 1: Look for elements that are just numbers
                        day_elements = page.locator("button, td, div").all()
                        
                        checked_count = 0
                        for elem in day_elements:
                            try:
                                text = elem.inner_text().strip()
                                # Check if it's a day number (1-31)
                                if text.isdigit() and 1 <= int(text) <= 31:
                                    checked_count += 1
                                    # Get element info for debugging
                                    classes = elem.get_attribute("class") or ""
                                    aria_disabled = elem.get_attribute("aria-disabled")
                                    is_disabled = False
                                    try:
                                        is_disabled = elem.is_disabled()
                                    except:
                                        pass
                                    
                                    # Log first few for debugging
                                    if checked_count <= 5:
                                        print(f"  Day {text}: classes='{classes[:50]}', disabled={is_disabled}, aria-disabled={aria_disabled}")
                                    
                                    # Check if this date is available (not grey/disabled)
                                    is_grey = (
                                        is_disabled or
                                        "disabled" in classes.lower() or
                                        "unavailable" in classes.lower() or
                                        aria_disabled == "true"
                                    )
                                    
                                    if not is_grey:
                                        available_dates.append(int(text))
                            except:
                                pass
                        
                        print(f"Checked {checked_count} day elements")
                        
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


def load_previous_state() -> dict:
    """Load the previous state from file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Could not load previous state: {e}")
    return {}


def save_current_state(state: dict):
    """Save the current state to file."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"State saved to {STATE_FILE}")
    except Exception as e:
        print(f"Could not save state: {e}")


def results_to_state(results: dict) -> dict:
    """Convert scrape results to a comparable state dict."""
    state = {}
    
    # Store available routes with their dates
    for avail in results.get("available", []):
        route = avail["route"]
        dates = avail.get("dates", [])
        state[route] = {"status": "available", "dates": sorted(dates)}
    
    # Store sold out routes
    for route in results.get("sold_out", []):
        state[route] = {"status": "sold_out", "dates": []}
    
    return state


def compare_states(previous: dict, current: dict) -> tuple[bool, str]:
    """Compare previous and current states. Returns (has_changed, change_description)."""
    if not previous:
        # First run - no previous state
        return True, "first_run"
    
    if previous == current:
        return False, "no_change"
    
    # Build description of changes
    changes = []
    all_routes = set(previous.keys()) | set(current.keys())
    
    for route in all_routes:
        prev_data = previous.get(route, {"status": "unknown", "dates": []})
        curr_data = current.get(route, {"status": "unknown", "dates": []})
        
        prev_status = prev_data.get("status", "unknown")
        curr_status = curr_data.get("status", "unknown")
        prev_dates = set(prev_data.get("dates", []))
        curr_dates = set(curr_data.get("dates", []))
        
        if prev_status != curr_status:
            if curr_status == "available":
                changes.append(f"🎉 {route}: Now AVAILABLE!")
            elif curr_status == "sold_out":
                changes.append(f"😢 {route}: Now SOLD OUT")
        elif prev_dates != curr_dates:
            new_dates = curr_dates - prev_dates
            removed_dates = prev_dates - curr_dates
            if new_dates:
                changes.append(f"➕ {route}: New dates: {', '.join(sorted(new_dates))}")
            if removed_dates:
                changes.append(f"➖ {route}: Dates gone: {', '.join(sorted(removed_dates))}")
    
    return True, "\n".join(changes)


def main():
    print("=" * 50)
    print("Eurostar SNAP Availability Checker")
    print("=" * 50)
    
    # Load previous state
    previous_state = load_previous_state()
    print(f"Previous state: {previous_state}")
    
    # Scrape current availability
    results = scrape_snap_availability()
    
    # Convert to comparable state
    current_state = results_to_state(results)
    print(f"Current state: {current_state}")
    
    # Compare states
    has_changed, change_description = compare_states(previous_state, current_state)
    print(f"Has changed: {has_changed}")
    print(f"Change description: {change_description}")
    
    # Save current state for next run
    save_current_state(current_state)
    
    # Only send message if state has changed
    if has_changed:
        if change_description == "first_run":
            message = "🚄 EUROSTAR SNAP - Initial Status\n"
            message += "=" * 25 + "\n\n"
        else:
            message = "🚨 EUROSTAR SNAP - CHANGE DETECTED!\n"
            message += "=" * 25 + "\n\n"
            message += f"{change_description}\n\n"
        
        # Current status
        message += "📊 Current Status:\n"
        
        if results["available"]:
            for avail in results["available"]:
                message += f"\n✅ {avail['route']}"
                if avail.get("dates"):
                    dates_str = ", ".join(avail["dates"][:10])
                    message += f"\n   Dates: {dates_str}"
        
        if results["sold_out"]:
            for route in results["sold_out"]:
                message += f"\n❌ {route}: SOLD OUT"
        
        if not results["available"] and not results["sold_out"]:
            message += "\n⚠️ Could not determine availability"
        
        message += f"\n\n🔗 {SNAP_URL}"
        
        print("\n" + "=" * 50)
        print("SENDING NOTIFICATION - State changed!")
        print(message)
        print("=" * 50)
        
        send_telegram(message)
    else:
        print("\n" + "=" * 50)
        print("No change detected - NOT sending notification")
        print("=" * 50)
    
    return has_changed


if __name__ == "__main__":
    main()
