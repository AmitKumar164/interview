# celery -A connectify_bulk_hiring worker -l info
import io
import json
import uuid
import requests
import pdfplumber

from celery import shared_task
from django.contrib.auth.models import User
from django.utils import timezone

from openai import OpenAI
from connectify_bulk_hiring import settings

from event.models import (
    UserRegister,
    Event,
    EventDescription,
    ResumeProcessingTrack,
    Interviewer,
)
from user_data.models import UserProfile
from user_data.services.email_service import send_professional_mail
from user_data.views import interviewer_mail_body, interviewee_mail_body


# -----------------------------
# OPENAI CLIENT
# -----------------------------
client = OpenAI(api_key=settings.OPENAI_API_KEY)
MODEL = "gpt-4.1-mini"


# -----------------------------
# DOWNLOAD + EXTRACT TEXT FROM PDF (S3 URL)
# -----------------------------
def download_resume_text_from_s3(s3_url: str) -> str:
    """
    Download a PDF from an HTTP(S) S3 URL and extract text using pdfplumber.
    """
    resp = requests.get(s3_url, timeout=30)
    resp.raise_for_status()

    pdf_bytes = resp.content  # IMPORTANT: binary content, not resp.text

    text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    return text.strip()


# -----------------------------
# FETCH JOB DATA
# -----------------------------
def get_job_data(event: Event) -> dict:
    desc = EventDescription.objects.filter(event=event).first()

    return {
        "job_title": event.job_title,
        "job_type": event.job_type,
        "job_location": event.job_location,
        "experience": event.work_experience,
        "department": event.department.name if event.department else "",
        "salary_range": f"{event.min_salary} - {event.max_salary}",
        "about": desc.about_event if desc else "",
        "responsibilities": desc.key_responsibilities if desc else "",
        "skills": desc.skills if desc else [],
    }


# -----------------------------
# IMPROVED ATS PROMPT
# -----------------------------
def build_prompt(resume_text: str, job: dict) -> str:
    return f"""
You are a professional ATS system used by recruiters to assess candidate-job fit.

Your goal:
Analyze the RESUME against the JOB DESCRIPTION and calculate a fair and practical ATS score.
Focus on relevance, transferable skills, and realistic hiring expectations.

---------------- JOB DESCRIPTION ----------------
Job Title: {job["job_title"]}
Department: {job["department"]}
Job Type: {job["job_type"]}
Location: {job["job_location"]}
Required Experience: {job["experience"]} years
Salary Range: {job["salary_range"]}

About Role:
{job["about"]}

Responsibilities:
{job["responsibilities"]}

Required Skills:
{job["skills"]}

------------------ RESUME ------------------
{resume_text}

---------------- OUTPUT ----------------

Return ONLY valid JSON in this EXACT structure.
Do not add extra explanation or markdown.

{{
  "candidate": {{
    "firstName": "string",
    "lastName": "string",
    "email": "string",
    "phone": "string",
    "location": "string",
    "headline": "string",
    "experience_years": "number"
  }},
  "scores": {{
    "skills": "number (0-100)",
    "experience": "number (0-100)",
    "roleRelevance": "number (0-100)"
  }},
  "finalScore": "number (0-100)",
  "matchedSkills": ["array"],
  "missingSkills": ["array"],
  "educationMatch": "boolean",
  "experienceMatch": "boolean",
  "jobFitSummary": "2-3 short sentences",
  "recommendation": "Hire | Consider | Reject",
  "reasons": ["array of short reasons"]
}}

---------------- SCORING GUIDELINES ----------------

Use balanced professional judgement.

1. Weight distribution:
   - Skills relevance: 45%
   - Experience relevance: 35%
   - Role relevance: 20%

2. Give partial credit:
   - for similar technologies
   - for transferable experience
   - for adjacent job roles

3. Penalize ONLY when:
   - core skills are absent
   - experience is far below requirement
   - role mismatch is extreme

4. If information is unclear, assume neutral impact (not negative).

5. Score based on evidence in resume, not assumptions.

6. Avoid extreme scores unless justified:
   - scores above 90 are rare
   - scores below 40 only for clearly unsuitable profiles

7. Prefer fairness over strict filtering.

---------------- EXTRA RULES ----------------

- Do not hallucinate missing fields.
- Empty fields must remain empty.
- Never invent experience or skills.
- Do not exaggerate strengths.
- Job fit summary must be brief and factual.
- Output MUST be valid JSON.

---------------- END ----------------
"""



# -----------------------------
# OPENAI CALL
# -----------------------------
def call_ai(prompt: str) -> str:
    res = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a strict ATS scoring engine."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return res.choices[0].message.content


# -----------------------------
# SAFE JSON PARSER
# -----------------------------
def safe_json_parse(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        try:
            s = text[text.index("{") : text.rindex("}") + 1]
            return json.loads(s)
        except Exception:
            return {"error": "Invalid AI output", "raw": text}


# -----------------------------
# CELERY TASK
# -----------------------------
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 15},
)
def process_bulk_resumes_task(self, s3_urls, event_id, company_name_id, expected_ats_score):
    print("Processing bulk resumes...")
    print(f"Event ID: {event_id}")
    print(f"Company Name ID: {company_name_id}")
    print(f"Expected ATS Score: {expected_ats_score}")
    event = Event.objects.get(id=event_id)
    job = get_job_data(event)

    results = []

    # ===============================
    # STEP 1: PROCESS RESUMES
    # ===============================
    for s3_url in s3_urls:
        track = ResumeProcessingTrack.objects.create(
            event=event,
            s3_url=s3_url,
            status="PENDING",
            task_id=self.request.id,
            mail_status="PENDING",
        )

        try:
            # 1) Extract resume text
            resume_text = download_resume_text_from_s3(s3_url)

            if len(resume_text.strip()) < 200:
                raise ValueError("Resume text too short or unreadable")

            track.status = "DOWNLOADED"
            track.save(update_fields=["status"])

            # 2) Call AI
            prompt = build_prompt(resume_text, job)
            ai_raw = call_ai(prompt)
            parsed = safe_json_parse(ai_raw)
            print("AI Parsed:", parsed)

            if "candidate" not in parsed or "finalScore" not in parsed:
                raise ValueError("Invalid ATS response structure")

            track.raw_ai_response = parsed
            track.status = "AI_DONE"
            track.save(update_fields=["status", "raw_ai_response"])

            c = parsed["candidate"]
            email = (c.get("email") or "").lower().strip()

            if not email:
                raise ValueError("Email missing in ATS response")

            # 3) Track email & score
            track.email = email
            track.ats_score = parsed["finalScore"]
            track.save(update_fields=["email", "ats_score"])

            # 4) User creation / fetch
            user = User.objects.filter(email=email).first()
            print(f"Email: {email}")
            print(f"User: {user}")
            created = False

            if not user:
                base_username = email.split("@")[0] or "user"
                print(f"Base Username: {base_username}")
                username = f"{base_username}_{uuid.uuid4().hex[:6]}"
                print(f"Username: {username}")

                user = User.objects.create(
                    email=email,
                    username=username,
                    first_name=c.get("firstName", "") or "",
                    last_name=c.get("lastName", "") or "",
                )
                created = True

            # 5) Profile creation / fetch
            raw_phone = c.get("phone", "") or ""

            # Remove +91 or leading spaces
            if raw_phone.startswith("+91"):
                phone = raw_phone.replace("+91", "").strip()
            else:
                phone = raw_phone.strip()
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "company_name_id": company_name_id,
                    "phone": phone,
                },
            )

            track.status = "USER_CREATED" if created else "USER_EXISTING"
            track.save(update_fields=["status"])

            # 6) Register user to event
            UserRegister.objects.update_or_create(
                event=event,
                user=profile,
                defaults={
                    "resume": s3_url,
                    "ats_score": parsed["finalScore"],
                    "shortlisted": parsed["finalScore"] >= expected_ats_score,
                    "selected": False,
                },
            )

            # track.status = "REGISTERED"
            # track.save(update_fields=["status"])

            results.append(
                {
                    "email": email,
                    "status": "USER_CREATED" if created else "USER_EXISTING",
                    "ats": parsed["finalScore"],
                }
            )

        except Exception as e:
            track.status = "FAILED"
            track.error = str(e)
            track.mail_status = "SKIPPED"
            track.save(update_fields=["status", "error", "mail_status"])

            results.append({"resume": s3_url, "error": str(e)})

    # ===============================
    # STEP 2: SEND INTERVIEWER MAILS
    # ===============================
    interviewer_ids = Interviewer.objects.filter(
        round__event=event
    ).values_list("interviewer_id", flat=True)

    interviewers = UserProfile.objects.select_related("user").filter(
        id__in=interviewer_ids
    )

    for interviewer in interviewers:
        name = f"{interviewer.user.first_name} {interviewer.user.last_name}".strip()
        subject = f"Invitation to Conduct Interviews for {event.job_title}"
        body = interviewer_mail_body(event, name)

        # Optionally track these separately or just send
        track = ResumeProcessingTrack.objects.create(
            event=event,
            s3_url="INTERVIEWER_MAIL",
            email=interviewer.user.email,
            status="COMPLETED",
            mail_status="PENDING",
            task_id=self.request.id,
        )

        try:
            send_professional_mail(
                interviewer.user.email,
                subject,
                body,
                company_name=event.created_by.company_name.name,
            )
            track.mail_status = "SENT"
            track.mail_sent_at = timezone.now()
            track.save(update_fields=["mail_status", "mail_sent_at"])
        except Exception as e:
            track.mail_status = "FAILED"
            track.mail_error = str(e)
            track.save(update_fields=["mail_status", "mail_error"])

    # ===============================
    # STEP 3: SEND INTERVIEWEE MAILS
    # ===============================
    interviewee_ids = event.user_registers.values_list("user_id", flat=True)
    interviewees = UserProfile.objects.select_related("user").filter(
        id__in=interviewee_ids
    )

    for candidate in interviewees:
        name = f"{candidate.user.first_name} {candidate.user.last_name}".strip()
        subject = f"Congratulations! You Are Shortlisted – {event.job_title}"
        body = interviewee_mail_body(event, name)

        track = ResumeProcessingTrack.objects.filter(
            event=event, email=candidate.user.email
        ).order_by("-created_at").first()

        try:
            send_professional_mail(
                candidate.user.email,
                subject,
                body,
                company_name=event.created_by.company_name.name,
            )

            if track:
                track.mail_status = "SENT"
                track.mail_sent_at = timezone.now()
                track.save(update_fields=["mail_status", "mail_sent_at"])
        except Exception as e:
            if track:
                track.mail_status = "FAILED"
                track.mail_error = str(e)
                track.save(update_fields=["mail_status", "mail_error"])

    return {
        "task_id": self.request.id,
        "processed": len(results),
        "event": event.event_id,
    }


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 2, "countdown": 10})
def process_single_resume_task(self, s3_url, event_id, user_profile_id):
    """
    Process ONE resume only.
    No mail.
    No tracking table.
    Only:
     - ATS calculation
     - User creation
     - UserRegister creation
    """

    event = Event.objects.get(id=event_id)
    user_profile = UserProfile.objects.get(id=user_profile_id)
    job = get_job_data(event)

    # -------------------------
    # EXTRACT Resume
    # -------------------------
    resume_text = download_resume_text_from_s3(s3_url)

    if len(resume_text.strip()) < 200:
        raise ValueError("Resume file could not be read or is empty")

    # -------------------------
    # AI
    # -------------------------
    prompt = build_prompt(resume_text, job)
    ai_raw = call_ai(prompt)
    parsed = safe_json_parse(ai_raw)

    if "candidate" not in parsed or "finalScore" not in parsed:
        raise ValueError("Invalid ATS output")

    c = parsed["candidate"]
    email = (c.get("email") or "").lower().strip()

    if not email:
        raise ValueError("Email missing from resume")

    ats_score = parsed["finalScore"]

    # -------------------------
    # REGISTER USER TO EVENT
    # -------------------------
    user_register, created = UserRegister.objects.update_or_create(
        event=event,
        user=user_profile,
        defaults={
            "resume": s3_url,
            "ats_score": ats_score,
            "shortlisted": ats_score >= (event.expected_ats_score or 0),
            "is_user_registered": True,
        }
    )

    return {
        "email": email,
        "ats": ats_score,
        "registered": True,
        "created": created,
        "shortlisted": ats_score >= (event.expected_ats_score or 70)
    }

@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 2, "countdown": 10})
def fetch_only_ats_score_task(self, instance_ids):

    instances = UserRegister.objects.filter(id__in=instance_ids).select_related("event")

    results = []

    for instance in instances:

        try:
            event = instance.event
            job = get_job_data(event)

            # -------------------------
            # Extract Resume Text
            # -------------------------
            resume_text = download_resume_text_from_s3(instance.resume)

            if len(resume_text.strip()) < 200:
                raise ValueError("Resume file could not be read or is empty")

            # -------------------------
            # AI Call
            # -------------------------
            prompt = build_prompt(resume_text, job)
            ai_raw = call_ai(prompt)
            parsed = safe_json_parse(ai_raw)

            if "finalScore" not in parsed:
                raise ValueError("Invalid ATS output format")

            ats_score = parsed["finalScore"]

            # -------------------------
            # Update DB
            # -------------------------
            instance.ats_score = ats_score

            threshold = getattr(event, "expected_ats_score", 0)
            instance.shortlisted = ats_score >= threshold

            instance.save(update_fields=["ats_score", "shortlisted"])

            results.append({
                "id": instance.id,
                "ats": ats_score,
                "shortlisted": instance.shortlisted
            })
            name = f"{instance.user.user.first_name} {instance.user.user.last_name}".strip()
            subject = f"Congratulations! You Are Shortlisted – {event.job_title}"
            body = interviewee_mail_body(event, name)

            track, created = ResumeProcessingTrack.objects.get_or_create(
                event=event, email=instance.user.user.email
            )

            try:
                send_professional_mail(
                    instance.user.user.email,
                    subject,
                    body,
                    company_name=event.created_by.company_name.name,
                )

                if track or created:
                    track.status = "USER_EXISTING"
                    track.mail_status = "SENT"
                    track.mail_sent_at = timezone.now()
                    track.save(update_fields=["mail_status", "mail_sent_at", "status"])
            except Exception as e:
                if track:
                    track.status = "FAILED"
                    track.mail_status = "FAILED"
                    track.mail_error = str(e)
                    track.save(update_fields=["mail_status", "mail_error"])

        except Exception as e:
            results.append({
                "id": instance.id,
                "error": str(e)
            })

    # ===============================
    # STEP 2: SEND INTERVIEWER MAILS
    # ===============================
    interviewer_ids = Interviewer.objects.filter(
        round__event=event
    ).values_list("interviewer_id", flat=True)

    interviewers = UserProfile.objects.select_related("user").filter(
        id__in=interviewer_ids
    )

    for interviewer in interviewers:
        name = f"{interviewer.user.first_name} {interviewer.user.last_name}".strip()
        subject = f"Invitation to Conduct Interviews for {event.job_title}"
        body = interviewer_mail_body(event, name)

        # Optionally track these separately or just send
        track = ResumeProcessingTrack.objects.create(
            event=event,
            s3_url="INTERVIEWER_MAIL",
            email=interviewer.user.email,
            status="COMPLETED",
            mail_status="PENDING",
            task_id=self.request.id,
        )

        try:
            send_professional_mail(
                interviewer.user.email,
                subject,
                body,
                company_name=event.created_by.company_name.name,
            )
            track.mail_status = "SENT"
            track.mail_sent_at = timezone.now()
            track.save(update_fields=["mail_status", "mail_sent_at"])
        except Exception as e:
            track.mail_status = "FAILED"
            track.mail_error = str(e)
            track.save(update_fields=["mail_status", "mail_error"])

    return {
        "processed": len(results),
        "results": results
    }
