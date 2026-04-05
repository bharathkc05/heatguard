import os

import httpx
from twilio.rest import Client

FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")


async def send_fcm_push(fcm_token: str, title: str, body: str) -> bool:
    if not fcm_token or not FCM_SERVER_KEY:
        return False
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={
                "Authorization": f"key={FCM_SERVER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "to": fcm_token,
                "notification": {"title": title, "body": body},
                "priority": "high",
            },
        )
    return resp.status_code == 200


def send_supervisor_sms(
    to_number: str,
    worker_name: str,
    risk_label: str,
    risk_score: float,
    lat: float,
    lon: float,
) -> bool:
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, to_number]):
        return False
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        maps_link = f"https://maps.google.com/?q={lat},{lon}"
        client.messages.create(
            to=to_number,
            from_=TWILIO_FROM_NUMBER,
            body=(
                f"HeatGuard ALERT: {worker_name} is at {risk_label} risk "
                f"(Score: {risk_score}/100). "
                f"Location: {maps_link}. "
                f"Immediate action required."
            ),
        )
        return True
    except Exception:
        return False


async def send_sos_alerts(
    worker_name: str,
    supervisor_phone: str,
    fcm_token: str,
    lat: float,
    lon: float,
    risk_score: float,
) -> None:
    # Push notification
    await send_fcm_push(
        fcm_token,
        title=f"SOS - {worker_name}",
        body=f"Emergency alert. Score: {risk_score}. Location sent to supervisor.",
    )
    # SMS to supervisor
    send_supervisor_sms(supervisor_phone, worker_name, "CRITICAL (SOS)", risk_score, lat, lon)
