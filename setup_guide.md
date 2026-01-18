# Google Cloud Credentials Setup Guide

Follow these steps to generate the `credentials.json` file required for the app.

## 1. Create a Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown in the top bar and select **"New Project"**.
3. Name it `Gmail Cleanup` and click **Create**.
4. Select the newly created project.

## 2. Enable Gmail API
1. Open the "Navigation Menu" (hamburger icon) > **APIs & Services** > **Library**.
2. Search for `Gmail API`.
3. Click on the result and click **Enable**.

## 3. Configure Consent Screen
1. Go to **APIs & Services** > **OAuth consent screen**.
2. Select **External** (unless you have a Google Workspace organization, then Internal might work, but External is standard for personal use).
3. Click **Create**.
4. **App Information**:
   - App Name: `Gmail Cleanup`
   - User support email: Select your email.
   - Developer contact information: Enter your email.
5. Click **Save and Continue**.
6. **Scopes**:
   - Click **Add or Remove Scopes**.
   - Search for `gmail` and select the scope `https://mail.google.com/` (Read, compose, send, and permanently delete all your email).
   - Click **Update**, then **Save and Continue**.
7. **Test Users**:
   - Click **Add Users**.
   - Enter your own Gmail address. **This is crucial** so you can log in while the app is in "Testing" mode.
   - Click **Save and Continue**.

## 4. Create Credentials
1. Go to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. **Application Type**: Select **Web application**.
4. **Name**: `Gmail Cleanup Web Client`.
5. **Authorized Redirect URIs**:
   - Click **Add URI**.
   - Enter: `http://127.0.0.1:5001/callback`
   - (Optional) Add `http://localhost:5001/callback` as well.
6. Click **Create**.

## 5. Download Credentials
1. A popup will appear. Click **Download JSON**.
2. Rename the downloaded file to `credentials.json`.
3. Move this file to your project folder:
   `/Users/boris/Documents/python programs/gmail/credentials.json`
