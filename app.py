"""
Gmail Cleanup Web Application.

This module provides the Flask application instance and the API endpoints
for the Gmail Cleanup tool. It handles authentication via Google OAuth2,
serves the frontend dashboard, and manages API requests for email statistics,
synchronization, and deletion.
"""

import os

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from utils import (
    SYNC_STATE,
    BackgroundSyncer,
    clear_local_cache,
    delete_messages,
    fetch_email_stats,
    get_account_info,
)

app = Flask(__name__)
# Secure session key (in production, strictly use a fixed secret from env vars)
app.secret_key = os.urandom(24)

# Allow HTTP for local development (OAuthlib security requirement)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = ["https://mail.google.com/"]
API_SERVICE_NAME = "gmail"
API_VERSION = "v1"

# Global reference to the current sync thread
current_syncer = None


def get_credentials():
    """Retrieves valid Google Cloud credentials from the session.

    Returns:
        google.oauth2.credentials.Credentials: Valid credentials object or None.
    """
    if "credentials" not in session:
        return None
    creds_data = session["credentials"]
    return Credentials(**creds_data)


@app.route("/")
def index():
    """Serves the main dashboard.

    Redirects to login if user is not authenticated.
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        return redirect(url_for("login"))

    return render_template("index.html")


@app.route("/login")
def login():
    """Serves the login page."""
    return render_template("login.html")


@app.route("/authorize")
def authorize():
    """Initiates the OAuth2 authorization flow.

    Redirects the user to Google's consent screen.
    """
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = url_for("callback", _external=True)
    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )
    session["state"] = state
    return redirect(authorization_url)


@app.route("/callback")
def callback():
    """Handles the OAuth2 callback from Google.

    Exchanges the authorization code for an access token and stores
    credentials in the session.
    """
    state = session["state"]
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
    )
    flow.redirect_uri = url_for("callback", _external=True)

    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)

    creds = flow.credentials

    # Store credentials in the session.
    # Note: In a production app, store tokens in a secure database.
    session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    """Clears the session and logs the user out."""
    session.clear()
    return redirect(url_for("login"))


# --- API Endpoints ---


@app.route("/api/stats")
def get_stats():
    """API endpoint to fetch aggregated email statistics.

    Query Parameters:
        max_results (int): Max emails to consider (legacy param).
        before (str): Date string (YYYY-MM-DD) to filter emails before.
        category (str): Category to filter (social, promotions, etc.).

    Returns:
        JSON: A dictionary containing 'stats' (list) and 'meta' (dict).
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # Get optional parameters
        max_results = request.args.get("max_results", 2000, type=int)
        before_date = request.args.get("before")  # YYYY-MM-DD
        category = request.args.get("category")

        query_parts = []
        if before_date:
            query_parts.append(f"before:{before_date}")
        if category and category != "all":
            query_parts.append(f"category:{category}")

        query = " ".join(query_parts) if query_parts else None

        print(f"Fetching stats with query: {query}")
        stats = fetch_email_stats(creds, max_results, query=query)
        print(f"Stats fetched: {len(stats['stats'])} items")
        return jsonify(stats)
    except Exception as e:
        import traceback

        traceback.print_exc()
        print("ERROR IN GET_STATS:")
        traceback.print_exc()
        print(f"Exception message: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
def delete_emails():
    """API endpoint to bulk delete (trash) emails.

    Expects a JSON body with a list of 'ids'.
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    ids = data.get("ids", [])

    if not ids:
        return jsonify({"deleted": 0})

    try:
        count = delete_messages(creds, ids)
        return jsonify({"deleted": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """API endpoint to clear the local email metadata cache."""
    try:
        clear_local_cache()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/account")
def account_info():
    """API endpoint to fetch high-level account information."""
    creds = get_credentials()
    if not creds:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        info = get_account_info(creds)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Sync Management Endpoints ---


@app.route("/api/sync/start", methods=["POST"])
def start_sync():
    """API endpoint to trigger the background sync process."""
    global current_syncer
    creds = get_credentials()
    if not creds:
        return jsonify({"error": "Unauthorized"}), 401

    if SYNC_STATE["is_running"]:
        return jsonify({"status": "Already running"})

    current_syncer = BackgroundSyncer(creds)
    current_syncer.start()
    return jsonify({"status": "Started"})


@app.route("/api/sync/stop", methods=["POST"])
def stop_sync():
    """API endpoint to stop the ongoing background sync."""
    global current_syncer
    if current_syncer and SYNC_STATE["is_running"]:
        current_syncer.stop()
        return jsonify({"status": "Stopping..."})
    return jsonify({"status": "Not running"})


@app.route("/api/sync/status")
def sync_status():
    """API endpoint to poll the status of the sync process."""
    return jsonify(SYNC_STATE)


if __name__ == "__main__":
    # Note: Port 5001 chosen to avoid conflicts with AirPlay/ControlCenter on macOS
    app.run("localhost", 5001, debug=True)
