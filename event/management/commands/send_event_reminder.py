from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from event.models import Event, UserRegister
from user_data.models import UserProfile

# IMPORT YOUR EXISTING MAIL FUNCTION
from user_data.services.email_service import send_professional_mail   # ✅ Update import path if needed


class Command(BaseCommand):
    help = "Send interview event reminder emails 1 hour before scheduled time."

    def handle(self, *args, **kwargs):

        now = timezone.now()
        reminder_time_start = now + timedelta(minutes=59)
        reminder_time_end = now + timedelta(minutes=61)
        today = now.date()

        # ✅ Find events starting in 1 hour window
        events = Event.objects.filter(
            start_date=today,
            start_time__gte=reminder_time_start.time(),
            start_time__lte=reminder_time_end.time(),
            status="Active"
        )

        if not events.exists():
            self.stdout.write("No events found for reminder window.")
            return

        for event in events:
            self.send_reminder_for_event(event)

        self.stdout.write(self.style.SUCCESS(" Reminder emails sent successfully!"))

    # ✅ Send reminder mail
    def send_reminder_for_event(self, event):

        hr_profile = event.created_by
        company_name = hr_profile.company_name.name if hr_profile.company_name else "Hiring Team"

        subject = f"Reminder: Interview Event Scheduled in One Hour | {company_name}"

        interview_time = event.start_time.strftime("%I:%M %p")
        interview_date = event.start_date.strftime("%d %B %Y")

        # ✅ Professional Mail Body
        body = f"""
Hello,<br><br>

This is a gentle reminder that the interview event for the position
<strong>{event.job_title}</strong> is scheduled to begin in
<strong>1 hour</strong>.

<br><br>

<b>Interview Schedule:</b><br>
• Job Title: {event.job_title}<br>
• Event ID: {event.event_id}<br>
• Date: {interview_date}<br>
• Time: {interview_time}

<br><br>

Kindly ensure that you are available and prepared at least 10 minutes before the scheduled time.

If you experience any technical issues, please reach out to HR immediately.

<br><br>
We wish you all the very best.
"""

        # ✅ COLLECT UNIQUE EMAILS
        emails = set()

        # HR
        emails.add(hr_profile.user.email)

        # Interviewers
        interviewer_profiles = UserProfile.objects.filter(
            interviewers__round__event=event
        ).distinct()

        for interviewer in interviewer_profiles:
            emails.add(interviewer.user.email)

        # Interviewees
        users = UserRegister.objects.filter(
            event=event,
            is_user_registered=True,
            rejected=False
        ).select_related("user")

        for reg in users:
            emails.add(reg.user.user.email)

        # ✅ SEND EMAILS
        for email in emails:
            send_professional_mail(
                to_email=email,
                subject=subject,
                body=body,
                company_name=company_name
            )
