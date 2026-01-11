# Stallarr

This Python script acts as a specialized watchdog for Lidarr. It monitors the download queue for stalled downloads, removes them, and attempts to find a replacement. It also periodically scans the "Wanted" list to trigger searches on slskd for missing albums.

## Features

* **Stall Detection:** Identifies downloads in the Lidarr queue that have stalled, failed, or have a "warning" status.
* **Ratio Protection:** Only acts on downloads for whitelisted clients. It **ignores** downloads from other clients to prevent accidental hit-and-runs on private trackers.
* **Blocklist Management:** Automatically clears the blocklist for a specific album if all available releases have been blocked, allowing a fresh attempt.
* **Wanted Scanner:** Periodically checks Lidarr's "Wanted" list and searches slskd for albums that haven't been searched for recently.
* **Working Time:** Only runs during specified hours (2am to 7am by default)

## Prerequisites

* **Python 3.x**
* **Lidarr:** Installed and running.
* **Requests Library:** `pip install requests`

## Configuration

Open the script and edit the variables at the top of the file.
