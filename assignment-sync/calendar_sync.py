import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# This tells Google we only need permission to manage calendar events.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# A label we add to events so we can find and update them later.
EVENT_TAG = "[Assignment Sync]"

TIME_ZONE = "US/Eastern"


def get_calendar_service():
    creds = None

    # token.json stores your login after the first time you authenticate.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If no valid token exists, ask you to log in via browser.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_existing_synced_events(service):
    # Find all events we've previously synced so we do not create duplicates.
    events_result = service.events().list(
        calendarId="primary",
        q=EVENT_TAG,
        maxResults=500,
        singleEvents=True,
    ).execute()
    return events_result.get("items", [])


def sync_assignments(assignments):
    print("\nConnecting to Google Calendar...")
    service = get_calendar_service()

    existing = get_existing_synced_events(service)
    existing_titles = {event["summary"] for event in existing}

    added = 0
    skipped = 0

    for assignment in assignments:
        title = f"{EVENT_TAG} {assignment['name']} - {assignment['course']}"

        if title in existing_titles:
            skipped += 1
            continue

        due_str = assignment["due"].isoformat()
        event = {
            "summary": title,
            "description": build_description(assignment),
            "start": {"dateTime": due_str, "timeZone": TIME_ZONE},
            "end": {"dateTime": due_str, "timeZone": TIME_ZONE},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60 * 24},
                    {"method": "popup", "minutes": 60 * 2},
                ],
            },
        }

        service.events().insert(calendarId="primary", body=event).execute()
        print(
            f"  Added: {assignment['name']} ({assignment['course']}) "
            f"- due {assignment['due'].strftime('%b %d %I:%M %p')}"
        )
        added += 1

    print(f"\nDone! Added {added} new events, skipped {skipped} already existing.")


def build_description(assignment):
    lines = [f"Course: {assignment['course']}"]

    if assignment.get("description"):
        lines.extend(["", assignment["description"]])

    if assignment.get("link"):
        lines.extend(["", f"Link: {assignment['link']}"])

    if assignment.get("source"):
        lines.append(f"Source: {assignment['source']}")

    return "\n".join(lines)
