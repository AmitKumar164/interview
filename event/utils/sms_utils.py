# utils/sms.py
from twilio.rest import Client
import random
from connectify_bulk_hiring.settings import OTP_TWILIO_ACCOUNT_SID, OTP_TWILIO_AUTH_TOKEN, OTP_NUMBER

client = Client(OTP_TWILIO_ACCOUNT_SID, OTP_TWILIO_AUTH_TOKEN)

def send_otp(phone, otp):

    message = client.messages.create(
        body=f"Connectify: Your OTP is {otp}. Do not share this code. Valid for 10 minutes.",
        from_=OTP_NUMBER,
        to=phone
    )

    return otp

