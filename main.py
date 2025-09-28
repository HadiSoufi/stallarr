import time
import requests
import json
import threading
from datetime import datetime, timezone, timedelta

LIDARR_URL = 'http://192.168.0.107:8686/'
LIDARR_API_KEY = "0bdd17ecea7844ce8eb0256f5cc9ae99"

REQUEST_TIMEOUT = 30

PAGE_SIZE = 100
SEARCH_THRESHOLD_HOURS = 2
search_threshold = timedelta(hours=SEARCH_THRESHOLD_HOURS)

LIDARR_API_URL = f"{LIDARR_URL}/api/v1/"
queue_url = LIDARR_API_URL + "queue"
command_url = LIDARR_API_URL + "command"
wanted_url = LIDARR_API_URL + "wanted/missing"

headers = {
    "X-Api-Key": LIDARR_API_KEY,
    "Content-Type": "application/json"
}

delete_params = {
    'blocklist': 'true',
    'removeFromClient': 'true'
}


# Reset the blocklist if every release is blocklisted
def clear_blocklist(album_id):
    try:
        params = {"albumId": album_id}
        releases = requests.get(f"{LIDARR_URL}release", headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        releases.raise_for_status()

        try:
            release_ids = {r['id'] for r in releases.json()}
        except requests.exceptions.JSONDecodeError:
            return False

        # Get all blocklisted releases for the album
        blocklist = requests.get(f"{LIDARR_URL}blocklist", headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        blocklist.raise_for_status()

        try:
            blocklist_records = blocklist.json().get('records', [])
        except requests.exceptions.JSONDecodeError:
            return False

        blocklist_ids = {b['releaseId'] for b in blocklist_records}

        if release_ids.issubset(blocklist_ids):
            print("Blocklist full; clearing blocklist.")
            blocklist_ids = [b['id'] for b in blocklist_records]
            requests.delete(f"{LIDARR_URL}blocklist/bulk", headers=headers,
                            json={"ids": blocklist_ids}).raise_for_status()
            return True

    except requests.exceptions.RequestException as e:
        print(f"API Error while checking blocklist: {e}")
        return False


# Sends a command to Lidarr to search for a specific album.
def search_album(album_id, title):
    if not album_id or not title:
        return False

    print("Beginning search for " + title + ". Ensuring that search queue is clear.")
    try:
        wait = True
        searching = True

        while wait:
            response = requests.get(command_url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            for command in response.json():
                # Check if a search for this album is already queued or running
                valid_search = (command.get('name') == 'AlbumSearch'
                                and command.get('status') in ['queued', 'started']
                                and 'body' in command
                                and 'albumIds' in command['body'])

                if valid_search:
                    if album_id in command['body']['albumIds']:
                        return False
                    else:
                        searching = True
                        break

            if searching:
                searching = False
                time.sleep(.1)
            else:
                wait = False

    except requests.exceptions.RequestException as e:
        print(f"  - Warning: Could not check for active searches due to an error: {e}")
        return False

    print("Search queue clear. Ensuring that blocklist isn't full.")
    clear_blocklist(album_id)

    try:
        print("Triggering album search.")
        payload = {
            "name": "AlbumSearch",
            "albumIds": [album_id]
        }
        response = requests.post(command_url, headers=headers, data=json.dumps(payload), timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        print()
        return True
    except requests.exceptions.RequestException as e:
        print(f"  - Failed to trigger a search for '{title}': {e}")
        return False


# Check for stalled downloads, remove and search for them
def check_stalled_downloads():
    print("Checking Lidarr for stalled downloads...")

    stalled_items = []

    try:
        response = requests.get(queue_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()

        for item in data.get('records', []):
            bad_download = item.get('trackedDownloadStatus') == 'warning'
            error = item.get('errorMessage') is not None
            stalled = item.get('timeleft') is None
            invalid = item.get('albumId') is None

            if bad_download or error or stalled or invalid:
                stalled_items.append(item)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching queue from Lidarr: {e}")
        return None

    if not stalled_items:
        print("No stalled downloads found.")
        return

    print(f"Found {len(stalled_items)} stalled item(s) to process.")

    for item in stalled_items:
        item_id = item.get('id')
        album_id = item.get('albumId')
        title = item.get('title')

        print(f"Found stalled item: '{title}'")

        try:
            delete_url = queue_url + f"/{item_id}"
            response = requests.delete(delete_url, headers=headers, params=delete_params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  - Failed to remove '{title}': {e}")

        search_album(album_id, title)
        print("-" * 20)
        time.sleep(1)

    print("Stall check finished.")


# Fetches the 'Wanted' list from Lidarr and searches for albums that haven't been searched for recently.
def check_and_search_wanted():
    print("Checking Lidarr for wanted albums...")

    now_utc = datetime.now(timezone.utc)
    page = 1
    total_records = 1  # Initialize to enter the loop
    albums = []

    while (page - 1) * PAGE_SIZE < total_records:
        try:
            params = {'page': page, 'pageSize': PAGE_SIZE}
            response = requests.get(wanted_url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            data = response.json()
            total_records = data.get('totalRecords', 0)
            albums += data.get('records', [])

            page += 1

        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Lidarr on page {page}: {e}")
            break
        except (ValueError, KeyError) as e:
            print(f"Error parsing data from Lidarr: {e}")
            break

    if not albums and page == 1:
        print("No items found on the wanted list.")
        return

    print(f"{len(albums)} items found on the wanted list.")
    searched = 0

    for album in albums:
        album_id = album.get('id')
        title = album.get('title')
        last_search_dt = datetime.fromisoformat(album.get('lastSearchTime'))

        # Check if the last search is older than our threshold
        if now_utc - last_search_dt > search_threshold:
            searched += search_album(album_id, title)
            time.sleep(1)

    print(f"Wanted queue processed. Searched for {searched} albums.")


def stall_thread():
    while True:
        check_stalled_downloads()
        print()
        time.sleep(60)


def wanted_thread():
    while True:
        check_and_search_wanted()
        print()
        time.sleep(60)


def main():
    if not LIDARR_API_KEY or LIDARR_API_KEY == "YOUR_API_KEY_HERE":
        print("Error: Please set your LIDARR_URL and LIDARR_API_KEY in the script.")
        return

    t1 = threading.Thread(target=stall_thread)
    t2 = threading.Thread(target=wanted_thread)

    t1.start()
    t2.start()


if __name__ == "__main__":
    main()
