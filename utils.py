import datetime
import email.utils
import json
import os
import re
import threading
import time
from collections import defaultdict

from googleapiclient.discovery import build

CACHE_FILE = "email_cache.json"

# Global Sync State
# Tracks the progress of the background sync operation.
SYNC_STATE = {
    "is_running": False,
    "total_to_scan": 0,
    "scanned_count": 0,
    "status": "Idle",
    "errors": [],
}


def get_gmail_service(credentials):
    """Builds and returns the Gmail API service.

    Args:
        credentials (google.oauth2.credentials.Credentials): valid user credentials.

    Returns:
        googleapiclient.discovery.Resource: The authenticated Gmail API service resource.
    """
    return build("gmail", "v1", credentials=credentials)


def parse_sender_email(from_header):
    """Extracts the email address from a 'From' header string.

    Args:
        from_header (str): The value of the From header, e.g., "Name <email@example.com>".

    Returns:
        str: The extracted email address (e.g., "email@example.com") or the original string if no brackets found.
    """
    # Example: "Google <no-reply@accounts.google.com>" -> "no-reply@accounts.google.com"
    match = re.search(r"<(.+?)>", from_header)
    if match:
        return match.group(1)
    return from_header


class BackgroundSyncer(threading.Thread):
    """Background thread for syncing Gmail messages to a local cache.

    This class handles listing messages from Gmail, batch fetching their metadata
    (including labels), and storing them in a local JSON cache. It supports
    pausing/stopping via a threading Event and updates a global state variable.
    """

    def __init__(self, credentials, max_results=50000):
        """Initializes the BackgroundSyncer.

        Args:
            credentials (google.oauth2.credentials.Credentials): Auth credentials.
            max_results (int): Maximum number of emails to scan. Defaults to 50000.
        """
        super().__init__()
        self.credentials = credentials
        self.max_results = max_results
        self.output_cache = load_cache()
        self._stop_event = threading.Event()

    def stop(self):
        """Signals the thread to stop execution."""
        self._stop_event.set()

    def run(self):
        """Executes the sync process."""
        global SYNC_STATE
        SYNC_STATE["is_running"] = True
        SYNC_STATE["status"] = "Starting sync..."
        SYNC_STATE["scanned_count"] = 0
        SYNC_STATE["total_to_scan"] = 0
        SYNC_STATE["errors"] = []

        try:
            service = get_gmail_service(self.credentials)

            # --- PHASE 1: List Messages ---
            # We fetch a list of message IDs first. This is a cheaper operation.
            messages = []
            page_token = None
            fetched_count = 0

            SYNC_STATE["status"] = "Listing messages..."

            while not self._stop_event.is_set():
                # Fetch headers only first to get IDs
                kwargs = {
                    "userId": "me",
                    "maxResults": min(500, self.max_results - fetched_count),
                    "includeSpamTrash": False,
                }
                if page_token:
                    kwargs["pageToken"] = page_token

                results = service.users().messages().list(**kwargs).execute()
                batch_msgs = results.get("messages", [])
                messages.extend(batch_msgs)
                fetched_count += len(batch_msgs)

                SYNC_STATE["total_to_scan"] = fetched_count

                page_token = results.get("nextPageToken")
                if not page_token or fetched_count >= self.max_results:
                    break

                # Rate limit for listing
                time.sleep(0.1)

            if self._stop_event.is_set():
                SYNC_STATE["status"] = "Stopped by user"
                return

            # --- PHASE 2: Identify Missing Cache Entries ---
            missing_ids = [
                msg["id"] for msg in messages if msg["id"] not in self.output_cache
            ]
            SYNC_STATE["status"] = (
                f"Found {len(messages)} messages. Fetching details for {len(missing_ids)} new items..."
            )

            # --- PHASE 3: Batch Fetch Details ---
            if missing_ids:
                new_items = {}

                def batch_callback(request_id, response, exception):
                    """Callback for Google API batch request."""
                    if exception:
                        # Log error but don't stop everything
                        return

                    headers = response["payload"].get("headers", [])
                    header_dict = {h["name"]: h["value"] for h in headers}

                    from_header = header_dict.get("From", "Unknown")
                    sender_email = parse_sender_email(from_header)
                    # Simple name parse
                    if "<" in from_header:
                        sender_name = from_header.split("<")[0].strip().strip('"')
                    else:
                        sender_name = sender_email

                    new_items[response["id"]] = {
                        "email": sender_email,
                        "name": sender_name,
                        "last_date": int(response["internalDate"]),
                        "labels": response.get("labelIds", []),  # Capture labels
                    }

                BATCH_SIZE = 100
                for i in range(0, len(missing_ids), BATCH_SIZE):
                    if self._stop_event.is_set():
                        break

                    batch = service.new_batch_http_request(callback=batch_callback)
                    chunk_ids = missing_ids[i : i + BATCH_SIZE]

                    for mid in chunk_ids:
                        # Format 'full' is required to get labelIds
                        batch.add(
                            service.users()
                            .messages()
                            .get(
                                userId="me",
                                id=mid,
                                format="full",
                                metadataHeaders=["From", "Date"],
                            )
                        )

                    try:
                        batch.execute()
                        # Update progress
                        SYNC_STATE["scanned_count"] += len(chunk_ids)
                        SYNC_STATE["status"] = (
                            f"Fetching details... {SYNC_STATE['scanned_count']}/{len(missing_ids)}"
                        )

                        # Intermediate save every 5 batches (500 emails)
                        if i % 500 == 0:
                            self.output_cache.update(new_items)
                            save_cache(self.output_cache)
                            new_items = {}  # clear temp buffer

                        # RATE LIMIT: Sleep between batches to avoid 429 errors
                        time.sleep(0.5)

                    except Exception as e:
                        SYNC_STATE["errors"].append(str(e))
                        time.sleep(2)  # Backoff on error

                # Final save of any remaining items
                self.output_cache.update(new_items)
                save_cache(self.output_cache)

            SYNC_STATE["status"] = "Complete"

        except Exception as e:
            SYNC_STATE["status"] = f"Error: {str(e)}"
            import traceback

            traceback.print_exc()
        finally:
            SYNC_STATE["is_running"] = False


def get_account_info(credentials):
    """Fetches high-level account statistics from the Gmail API.

    Args:
        credentials (google.oauth2.credentials.Credentials): Auth credentials.

    Returns:
        dict: A dictionary containing 'total_messages', 'email_address',
              'threads_total', and 'history_id'.
    """
    service = get_gmail_service(credentials)
    profile = service.users().getProfile(userId="me").execute()
    return {
        "total_messages": profile.get("messagesTotal"),
        "email_address": profile.get("emailAddress"),
        "threads_total": profile.get("threadsTotal"),
        "history_id": profile.get("historyId"),
    }


def load_cache():
    """Loads the email metadata cache from disk.

    Returns:
        dict: The cached email data (ID -> metadata), or an empty dict if invalid.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_cache(cache):
    """Saves the email metadata cache to disk.

    Args:
        cache (dict): The email metadata dictionary to save.
    """
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def fetch_email_stats(credentials, max_results=2000, query=None):
    """Aggregates email statistics from the local cache.

    Allows filtering by date ('before:YYYY-MM-DD') and category ('category:social').

    Args:
        credentials: (Unused, kept for interface compatibility)
        max_results (int): (Unused in local cache mode, kept for compatibility)
        query (str): Optional query string for filtering.

    Returns:
        dict: A dictionary with 'stats' (list of senders) and 'meta' (scan summary).
    """
    # Use local cache for speed
    cache = load_cache()

    if not cache:
        return {"stats": [], "meta": {"total_scanned": 0, "oldest_date": "N/A"}}

    # --- Aggregation Logic ---
    stats = defaultdict(lambda: {"count": 0, "ids": [], "name": "Unknown"})
    oldest_timestamp = float("inf")
    total_scanned = 0

    # Pre-process query for local filtering
    before_ts = None
    target_category = None

    if query:
        if "before:" in query:
            try:
                date_str = query.split("before:")[1].split(" ")[0]
                before_ts = (
                    time.mktime(
                        datetime.datetime.strptime(date_str, "%Y-%m-%d").timetuple()
                    )
                    * 1000
                )
            except:
                pass

        if "category:" in query:
            # Extract category (e.g. category:social)
            # Mappings for internal Gmail label IDs
            cat_arg = query.split("category:")[1].split(" ")[0].upper()
            if cat_arg in ["SOCIAL", "PROMOTIONS", "UPDATES", "FORUMS"]:
                target_category = f"CATEGORY_{cat_arg}"

    for mid, data in cache.items():
        # 1. Apply Date Filter
        if before_ts and data.get("last_date", 0) >= before_ts:
            continue

        # 2. Apply Category Filter
        if target_category:
            labels = data.get("labels", [])
            if target_category not in labels:
                continue

        total_scanned += 1

        # Track oldest email seen in this result set
        ts = data.get("last_date", 0)
        if ts < oldest_timestamp:
            oldest_timestamp = ts

        email = data.get("email", "Unknown")
        stats[email]["count"] += 1
        stats[email]["ids"].append(mid)
        stats[email]["name"] = data.get("name", email)
        stats[email]["last_date"] = max(stats[email].get("last_date", 0), ts)

    # Sort senders by count (descending)
    sorted_stats = sorted(
        [{"email": k, **v} for k, v in stats.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    # Format the oldest date for display
    oldest_date_str = "N/A"
    if oldest_timestamp != float("inf") and total_scanned > 0:
        dt = datetime.datetime.fromtimestamp(oldest_timestamp / 1000.0)
        oldest_date_str = dt.strftime("%Y-%m-%d")

    return {
        "stats": sorted_stats,
        "meta": {"total_scanned": total_scanned, "oldest_date": oldest_date_str},
    }


def delete_messages(credentials, message_ids):
    """Moves messages to Trash instead of permanently deleting them.

    Also updates the local cache to remove the trashed items, ensuring consistency.

    Args:
        credentials (google.oauth2.credentials.Credentials): Auth credentials.
        message_ids (list): List of message IDs to trash.

    Returns:
        int: The number of messages successfully moved to Trash.
    """
    service = get_gmail_service(credentials)
    if not message_ids:
        return 0

    # Batch modify (max 1000 per request)
    batch_size = 1000
    cleaned_ids = []

    for i in range(0, len(message_ids), batch_size):
        batch_ids = message_ids[i : i + batch_size]
        try:
            # Move to Trash using batchModify
            service.users().messages().batchModify(
                userId="me", body={"ids": batch_ids, "addLabelIds": ["TRASH"]}
            ).execute()
            cleaned_ids.extend(batch_ids)
        except Exception as e:
            print(f"Error trashing batch: {e}")

    # Update Cache: Remove only successfully trashed IDs
    if cleaned_ids:
        cache = load_cache()
        for mid in cleaned_ids:
            if mid in cache:
                del cache[mid]
        save_cache(cache)

    return len(cleaned_ids)


def clear_local_cache():
    """Removes the local JSON cache file."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    return True
