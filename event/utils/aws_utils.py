import boto3
from connectify_bulk_hiring import settings
from uuid import uuid4
import base64
from botocore.exceptions import ClientError


def upload_base64_to_s3(base64_string, folder="resumes/", file_ext="pdf"):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

    # Decode base64
    decoded_file = base64.b64decode(base64_string)

    # Create filename
    filename = f"{folder}{uuid4()}.{file_ext}"

    # Upload
    s3.put_object(
        Bucket=settings.AWS_S3_BUCKET_NAME,
        Key=filename,
        Body=decoded_file,
        ContentType="application/pdf",
        ACL="public-read"
    )

    return f"https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{filename}"

from twilio.rest import Client

def send_sms_twilio(to_number, message):
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    twilio_number = '9834843396'

    try:
        client = Client(account_sid, auth_token)
        
        sms = client.messages.create(
            body=message,
            from_=twilio_number,
            to=to_number
        )
        
        return {"status": "success", "sid": sms.sid}

    except Exception as e:
        return {"status": "error", "error": str(e)}
