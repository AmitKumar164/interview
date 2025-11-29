from rest_framework.views import APIView
from .serializers import SignupSerializer, RegisterInterviewerSerializer
from django.http import JsonResponse
import random
from django.core.cache import cache
from .models import *
from rest_framework_simplejwt.tokens import RefreshToken
from event.utils.aws_utils import upload_base64_to_s3
from event.models import *
from user_data.services.email_service import send_professional_mail
from connectify_bulk_hiring.settings import FRONTEND_URL
'''
{
  "first_name": "Amit",
  "last_name": "Kumar",
  "email": "amit@example.com",
  "phone_number": "9876543210",
  "company_name_id": 1,
  "user_type": "Interviewer"
}
'''
class SignupView(APIView):
    def post(self, request):
        try:
            serializer = SignupSerializer(data=request.data)

            if serializer.is_valid():
                user = serializer.save()
                resume = request.data.get("resume")

                return JsonResponse({
                    "message": "User created successfully",
                    "user_id": user.id,
                    "email": user.email
                }, status=201)

            # Extract only the first error message (no field name)
            error_value = next(iter(serializer.errors.values()))[0]

            return JsonResponse({"error": error_value}, status=400)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)



class SendOtpView(APIView):
    def post(self, request):
        phone = request.data.get("phone_number")

        if not phone:
            return JsonResponse({"error": "Phone number is required"}, status=400)

        try:
            profile = UserProfile.objects.get(phone=phone)
        except UserProfile.DoesNotExist:
            return JsonResponse({"error": "User with this phone number does not exist"}, status=404)

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        otp = "111111"

        # Store in cache for 10 minutes (600 seconds)
        cache.set(f"otp_{phone}", otp, timeout=600)

        # TODO: Integrate with SMS gateway to send OTP
        print(f"OTP for {phone} is {otp}")  # For debugging only

        return JsonResponse({"message": f"OTP sent successfully {otp}"}, status=200)

class VerifyOtpView(APIView):
    def post(self, request):
        phone = request.data.get("phone_number")
        otp = request.data.get("otp")

        if not phone or not otp:
            return JsonResponse({"error": "Phone number and OTP are required"}, status=400)

        cached_otp = cache.get(f"otp_{phone}")

        if cached_otp is None:
            return JsonResponse({"error": "OTP expired or not found"}, status=400)

        if str(cached_otp) != str(otp):
            return JsonResponse({"error": "Invalid OTP"}, status=400)

        # OTP verified -> fetch user profile
        try:
            profile = UserProfile.objects.select_related("user", "company_name").get(phone=phone)
            user = profile.user
        except UserProfile.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return JsonResponse({
            "message": "OTP verified successfully",
            "user_id": profile.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "company_id": profile.company_name.id if profile.company_name else None,
            "company_name": profile.company_name.name if profile.company_name else None,
            "user_type": profile.user_type,
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "token_type": "Bearer"
        }, status=200)

class UserDataView(APIView):
    def get(self, request):
        user_type = request.query_params.get("user_type")

        if not user_type:
            users = UserProfile.objects.select_related("user", "company_name").filter(user__is_active=True)
        else:
            users = UserProfile.objects.select_related("user", "company_name").filter(user_type=user_type, user__is_active=True)

        data = [
            {
                "first_name": user.user.first_name,
                "last_name": user.user.last_name,
                "userprofile_id": user.id,
                "user_type": user.user_type,
                "company_name": user.company_name.name if user.company_name else None,
                "company_id": user.company_name.id if user.company_name else None,
            }
            for user in users
        ]

        return JsonResponse({"users": data}, status=200)

class FetchUserView(APIView):
    def get(self, request):
        user_data = UserProfile.objects.filter(user__is_active=True)
        data = [
            {
                "name": f"{user.user.first_name} {user.user.last_name}",
                "id": user.id,
                "user_type": user.user_type,
                "company_name": user.company_name.name if user.company_name else None,
                "company_id": user.company_name.id if user.company_name else None,
                "phone_number": user.phone,
                "email": user.user.email,
                "role": user.user_type,
            }
            for user in user_data
        ]
        return JsonResponse({"users": data}, status=200)
    
    def patch(self, request):
        user_profile = request.data.get("user_profile_id")
        user_profile = UserProfile.objects.get(id=user_profile)
        user_profile.user_type = request.data.get("user_type")
        user_profile.save()
        return JsonResponse({"message": "User type updated successfully"}, status=200)

class UploadResume(APIView):
    def post(self, request):
        try:
            resume = request.data.get("resume")
            user_profile = request.user.user_profile
            file_url = upload_base64_to_s3(resume, folder="resumes/")
            UserResume.objects.create(user=user_profile, resume=file_url)
            event_id = request.data.get("event_id")
            if event_id:
                event = Event.objects.get(event_id=event_id)
                UserRegister.objects.filter(event=event, user=user_profile).update(resume=file_url)
            return JsonResponse({"message": "Resume uploaded successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    def get(self, request):
        user_profile = request.user.user_profile
        resumes = UserRegister.objects.filter(user=user_profile)
        data = [
            {
                "resume": resume.resume,
                "user_profile_id": resume.user.id,
                "uploaded_at": resume.created_at,
            }
            for resume in resumes
        ]
        return JsonResponse({"resumes": data}, status=200)

class RegisterInterviewer(APIView):
    def post(self, request):
        try:
            serializer = RegisterInterviewerSerializer(
                data=request.data,
                context={"request": request}
            )

            if serializer.is_valid():
                user_profile = serializer.save()

                return JsonResponse({
                    "message": "Interviewer registered successfully",
                    "user_id": user_profile.id,
                    "email": user_profile.user.email
                }, status=201)

            # Extract only the first error message (same logic as SignupView)
            error_value = next(iter(serializer.errors.values()))[0]
            return JsonResponse({"error": error_value}, status=400)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)



def format_event_details(event):
    desc = event.descriptions.first()

    skills = ", ".join(desc.skills) if desc and desc.skills else "Not specified"

    return f"""
        <strong>Company Name:</strong> {event.created_by.company_name.name}<br>
        <strong>Job Title:</strong> {event.job_title}<br>
        <strong>Job Type:</strong> {event.job_type}<br>
        <strong>Location:</strong> {event.job_location}<br>
        <strong>Department:</strong> {event.department.name}<br>
        <strong>Experience Required:</strong> {event.work_experience} years<br>
        <strong>Salary Range:</strong> ₹{event.min_salary} - ₹{event.max_salary}<br>
        <strong>Interview Date:</strong> {event.start_date.strftime("%d %B %Y")}<br>
        <strong>Interview Time:</strong> {event.start_time.strftime("%I:%M %p")}<br><br>

        <strong>About Event:</strong><br>
        {desc.about_event if desc else ''}<br><br>

        <strong>Key Responsibilities:</strong><br>
        {desc.key_responsibilities if desc else ''}<br><br>

        <strong>Required Skills:</strong> {skills}<br>
    """

def interviewer_mail_body(event, interviewer_name):
    event_details = format_event_details(event)
    meeting_url = f"{FRONTEND_URL}/login/"

    return f"""
    <div style="max-width:600px;font-family:Arial,sans-serif;
                border:1px solid #eaeaea;border-radius:8px;padding:20px;">

        <h2 style="color:#2c3e50;">Interview Assignment Notification</h2>

        <p>Dear <strong>{interviewer_name}</strong>,</p>

        <p>
            You have been selected as an interviewer for the recruitment process
            for the position of <strong>{event.job_title}</strong>.
        </p>

        <h3 style="margin-top:20px;">Interview Details</h3>
        <div style="background:#f7f9fc;padding:10px;border-radius:5px;">
            {event_details}
        </div>

        <div style="text-align:center;margin:25px 0;">
            <a href="{meeting_url}"
               style="
               background:#0052cc;
               color:#ffffff;
               padding:12px 22px;
               text-decoration:none;
               font-size:14px;
               font-weight:bold;
               border-radius:6px;
               display:inline-block;">
               Join Interview
            </a>
        </div>

        <p style="font-size:13px;color:#555;">
            If the button does not work, copy and paste this link in your browser:
            <br>
            <a href="{meeting_url}">{meeting_url}</a>
        </p>

        <p>
            Please join on time and ensure a smooth interview experience for the candidate.
        </p>

        <p>
            For any questions, feel free to reach out to the hiring team.
        </p>

        <p style="margin-top:20px;">
            Best regards,<br>
            <strong>Hiring Team</strong>
        </p>

        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">

        <small style="color:#999;">
            This is an automated email. Do not reply directly.
        </small>

    </div>
    """


def interviewee_mail_body(event, candidate_name):
    event_details = format_event_details(event)
    meeting_url = f"{FRONTEND_URL}/login/"

    return f"""
    <div style="max-width:600px;font-family:Arial,sans-serif;
                border:1px solid #eaeaea;border-radius:8px;padding:20px;">

        <h2 style="color:#2c3e50;">Interview Invitation</h2>

        <p>Dear <strong>{candidate_name}</strong>,</p>

        <p>
            Congratulations! You have been shortlisted for the interview process
            for the position of <strong>{event.job_title}</strong>.
        </p>

        <h3 style="margin-top:20px;">Your Interview Details</h3>
        <div style="background:#f7f9fc;padding:10px;border-radius:5px;">
            {event_details}
        </div>

        <div style="text-align:center;margin:25px 0;">
            <a href="{meeting_url}"
               style="
               background:#28a745;
               color:#ffffff;
               padding:12px 22px;
               text-decoration:none;
               font-size:14px;
               font-weight:bold;
               border-radius:6px;
               display:inline-block;">
               Join Interview
            </a>
        </div>

        <p style="font-size:13px;color:#555;">
            If the button does not work, copy and paste this link into your browser:
            <br>
            <a href="{meeting_url}">{meeting_url}</a>
        </p>

        <p>
            Please join the meeting on time and ensure you have a stable
            internet connection.
        </p>

        <p>
            Best of luck! We look forward to speaking with you.
        </p>

        <p style="margin-top:20px;">
            Warm regards,<br>
            <strong>Hiring Team</strong>
        </p>

        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">

        <small style="color:#999;">
            This is an automated invitation. Please do not reply to this message.
        </small>
    </div>
    """


class SendEventUserMail(APIView):
    def post(self, request):
        try:
            event_id = request.data.get("event_id")
            if not event_id:
                return JsonResponse({"error": "event_id is required"}, status=400)

            # Get Event
            event = Event.objects.get(id=event_id)

            # ====== Fetch Interviewers ======
            interviewer_ids = Interviewer.objects.filter(
                round__event=event
            ).values_list("interviewer_id", flat=True)

            interviewers = UserProfile.objects.select_related("user").filter(
                id__in=interviewer_ids
            )

            # ====== Fetch Interviewees ======
            interviewee_ids = event.user_registers.values_list("user_id", flat=True)

            interviewees = UserProfile.objects.select_related("user").filter(
                id__in=interviewee_ids
            )

            # ====== Send Mail to Interviewers ======
            for interviewer in interviewers:
                name = f"{interviewer.user.first_name} {interviewer.user.last_name}".strip()
                body = interviewer_mail_body(event, name)
                subject = f"Invitation to Conduct Interviews for {event.job_title}"

                send_professional_mail(
                    interviewer.user.email,
                    subject,
                    body,
                    company_name=event.created_by.company_name.name
                )

            # ====== Send Mail to Interviewees ======
            for candidate in interviewees:
                name = f"{candidate.user.first_name} {candidate.user.last_name}".strip()
                body = interviewee_mail_body(event, name)
                subject = f"Congratulations! You Are Shortlisted – {event.job_title}"

                send_professional_mail(
                    candidate.user.email,
                    subject,
                    body,
                    company_name=event.created_by.company_name.name
                )

            return JsonResponse(
                {"message": "Interviewers and Interviewees mails sent successfully."},
                status=200
            )

        except Event.DoesNotExist:
            return JsonResponse({"error": "Event not found"}, status=404)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)