# Gmail Cleanup Tool

A powerful, efficient web application to help you clean up your Gmail inbox by identifying high-volume senders, filtering by category, and performing bulk actions.

## Features

-   **Dashboard Overview**: Visualize top senders and account statistics.
-   **Bulk Deletion**: Select multiple senders and move their emails to Trash in one go.
-   **Advanced Filtering**: Filter emails by category (Social, Promotions, Updates, Forums) and date.
-   **Background Sync**: Efficiently fetches headers for up to 50,000 emails in the background without blocking the UI.
-   **Rate Limiting**: Intelligent API usage to avoid hitting Google's rate limits.
-   **Local Caching**: Stores email metadata locally for instant analysis and reduced API calls.

## Setup & Installation

For detailed setup instructions, including how to configure Google Cloud credentials, please refer to the [Setup Guide](setup_guide.md).

### Quick Start

1.  **Prerequisites**: Python 3.8+, a Google Cloud Project with Gmail API enabled, and `credentials.json`.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the Application**:
    ```bash
    python -m flask run --port 5001
    ```
4.  **Access the Dashboard**: Open [http://localhost:5001](http://localhost:5001) in your browser.

## Usage

1.  **Login**: Authenticate securely with your Google account.
2.  **Sync**: Click **"Start Sync"** to begin analyzing your inbox. Progress is shown in real-time.
3.  **Analyze**: Use the dashboard to see who is filling up your inbox.
4.  **Filter**: Use the dropdowns to focus on "Promotions" or old emails (e.g., "Before 2023-01-01").
5.  **Clean**: Select senders and click **"Delete Selected"** to move their emails to Trash.
    *   *Note*: Emails are moved to Trash, not permanently deleted, allowing you to recover them if needed.

## Architecture

-   **Frontend**: HTML5, Tailwind CSS, Vanilla JavaScript.
-   **Backend**: Python Flask.
-   **Data**: Local JSON cache for email headers.

## Troubleshooting

-   **403 Forbidden**: Ensure the port (5001) is not in use by AirPlay or other services.
-   **Missing Data**: If categories or specific emails are missing, try clicking **"Refresh Cache"** to re-sync.
