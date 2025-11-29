# Connectify Bulk Hiring

A Django-based bulk hiring platform that lets HR create hiring events, auto-parse resumes from S3, compute ATS scores using OpenAI, orchestrate interviewer–candidate sessions over WebSockets (Django Channels + Redis), and notify participants via email. It also includes Zoom Web SDK signature generation and Twilio TURN credentials for WebRTC.

---

## Key Features
- **Event Management**: Create events with rounds, interviewers, questions (`event/views.py::EventView`).
- **Resume Intake**: Upload base64 PDFs → store to S3 (`event/utils/aws_utils.py::upload_base64_to_s3`).
- **AI ATS Scoring**: OpenAI-driven scoring and candidate parsing (`event/tasks.py`).
- **Bulk Processing**: Celery workers for parallel resume processing and mailers (`connectify_bulk_hiring/celery.py`, `event/tasks.py`).
- **Real-time Interviews**: Django Channels WebSocket consumer for interview orchestration (`event/consumers.py`).
- **Zoom Web SDK**: JWT signature generator endpoint (`event/views.py::GenerateZoomSignatureView`).
- **TURN/ICE**: Twilio TURN token proxy for WebRTC (`event/views.py::TurnCredentialsAPIView`).
- **Email Notifications**: SMTP HTML emails to interviewers/interviewees (`user_data/services/email_service.py`).

---

## Tech Stack
- Python 3.10+
- Django 5.x, Django REST Framework
- Channels 4, Daphne, Redis (channels_redis)
- Celery 5, django-celery-results
- PostgreSQL
- OpenAI (resume ATS scoring)
- AWS S3 (resume storage)
- Twilio (TURN/ICE)

---

## Project Structure
- `connectify_bulk_hiring/` – Django project (ASGI, Celery, settings)
- `event/` – Events, rounds, interview orchestration, ATS tasks, Zoom/TURN endpoints
- `user_data/` – Signup, OTP login, role management, mail helpers
- `pdf_reader.py` – Local script to parse PDFs from `resumes/` to `parsed_json/`

---

## Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Redis 6+
- AWS account + S3 bucket
- Twilio account (for TURN)
- Zoom Web SDK credentials (optional, if using Zoom signature endpoint)
- OpenAI API key

---

## Database Setup (PostgreSQL)
Replicating the steps found in `setup.py` (adjust version paths as needed):

```bash
sudo apt install postgresql postgresql-contrib
pip install "psycopg[binary]"
sudo -u postgres psql
-- inside psql
CREATE USER bulkhiring WITH PASSWORD 'bulkhiring';
CREATE DATABASE bulkhiring_db OWNER bulkhiring;
GRANT ALL PRIVILEGES ON DATABASE bulkhiring_db TO bulkhiring;
\q

# Ensure pg_hba.conf allows md5 for local connections, then restart
sudo service postgresql restart
```

Default DB settings in `connectify_bulk_hiring/settings.py` expect:
- NAME: `bulkhiring_db`
- USER: `bulkhiring`
- PASSWORD: `bulkhiring`
- HOST: `localhost`
- PORT: `5432`

---

## Environment Configuration
For production, move all secrets out of `connectify_bulk_hiring/settings.py` into environment variables or a secrets manager. The code currently contains hard-coded credentials for convenience; you must rotate them and configure via environment variables before deploying.

Recommended variables (example):
```bash
# Django
SECRET_KEY=replace_me
DEBUG=false
ALLOWED_HOSTS=your.domain.com,localhost,127.0.0.1

# Database
DB_NAME=bulkhiring_db
DB_USER=bulkhiring
DB_PASSWORD=bulkhiring
DB_HOST=localhost
DB_PORT=5432

# Redis / Channels / Celery
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

# AWS S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=...

# OpenAI
OPENAI_API_KEY=sk-...

# Zoom Web SDK + OAuth (if used)
ZOOM_SDK_CLIENT_ID=...
ZOOM_SDK_CLIENT_SECRET=...
ZOOM_CLIENT_ID=...
ZOOM_CLIENT_SECRET=...
ZOOM_ACCOUNT_ID=...

# Twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_API_KEY=...
TWILIO_API_SECRET=...
TURN_LIMIT=1000
TURN_EXPIRY=600

# SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=app_password

# Frontend URL (for email templates & deep links)
FRONTEND_URL=http://localhost:3000
```
Note: The current code reads values directly from settings constants. If you want to consume environment variables, add a small loader (e.g., `os.getenv` or `django-environ`) in `settings.py`.

---

## Installation
```bash
# From repo root
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Migrations (including django-celery-results tables)
python manage.py migrate
python manage.py migrate django_celery_results

# (Optional) Create superuser
python manage.py createsuperuser
```

---

## Running the Stack
- **Start Redis**: `redis-server` (or via Docker/local service)
- **Start Celery worker**:
```bash
celery -A connectify_bulk_hiring worker -l info
```
- **Start Django (ASGI)**:
```bash
# Dev
python manage.py runserver 0.0.0.0:8000
# or with Daphne
daphne -b 0.0.0.0 -p 8000 connectify_bulk_hiring.asgi:application
```

Channels is configured in `connectify_bulk_hiring/asgi.py` and `connectify_bulk_hiring/settings.py` with Redis channel layer.

---

## Authentication
DRF uses JWT via `djangorestframework_simplejwt` (`settings.py::REST_FRAMEWORK`).
- Login flow is phone-based OTP:
  - `POST /bulk_hiring/user_data/v1/login/send-otp/` with `phone_number`
  - `POST /bulk_hiring/user_data/v1/login/verify-otp/` → returns `access_token` and `refresh_token`
- Include `Authorization: Bearer <access_token>` for protected endpoints.

---

## WebSocket (Interview Orchestration)
- **URL pattern** (`event/routing.py`):
  - `ws://<HOST>/ws/connectify_bulk_hiring/<session_id>/<username>/?token=<JWT>`
- **Auth**: `token` is a JWT signed with `SECRET_KEY` containing `user_id` claim. Middleware checks URL username vs token user (`event/middleware.py::JWTAuthMiddleware`).
- **Consumer**: `event/consumers.py::ConnectifyConsumer`
- **Actions** (messages with JSON `action`):
  - `start_next` (Interviewer starts next candidate)
  - `accept_interview` / `reject_interview` (Interviewee)
  - `complete_interview`
  - `leave`
  - `get_all_queues`, `get_result` (helper fetches)
- Messages are fanned out to a room named like `room_<interviewer_username>_<session_id>`.

---

## REST API (Selected)
Base path prefix from `connectify_bulk_hiring/urls.py`:
- `bulk_hiring/user_data/...`
- `bulk_hiring/event/...`

### user_data
- `POST /v1/signup/` – Create user (HR/Interviewer/Interviewee)
- `POST /v1/login/send-otp/` – Send OTP to phone
- `POST /v1/login/verify-otp/` – Verify OTP, returns JWTs
- `GET /v1/user-data/?user_type=<Hr|Interviewer|Interviewee>` – Filtered users
- `GET /v1/fetch-user/` – Active users
- `PATCH /v1/fetch-user/` – Update `user_type`
- `POST /v1/register-interviewer/` – Register interviewer
- `POST /v1/send-event-mail/` – Send mails to interviewers/interviewees

### event
- `POST /v1/event/` – Create event; body includes job details, rounds, questions, resumes (base64)
- `GET /v1/event/?status=Pending|Active|Inactive` – List events
- `PATCH /v1/event/` – Update event status
- `GET|POST /v1/skills/` – List/create skills
- `GET|POST /v1/departments/` – List/create departments
- `POST /v1/event-register/` – Register a user to event with resume (base64 → S3)
- `GET /v1/application-by-department/?month=&year=` – Department-wise counts
- `GET /v1/job-application-status/?month=&year=` – Status-wise counts
- `POST /v1/generate-zoom-signature/` – Zoom Web SDK JWT signature
- `GET /v1/turn-credentials/?user_id=` – Twilio TURN token (rate-limited by cache)
- `POST /v1/turn-disconnect/` – Release TURN slot
- `POST /v1/zoom-attendance/` – Track event attendance (Interviewee/Interviewer)
- `POST|GET|PATCH /v1/zoom-mapping/` – Map interviewees to interviewers in current round (cache)
- `POST /v1/candidate-review/` – Save review + pass/fail; auto-advance candidates
- `POST /v1/interviewee-join/` – Track interviewee joining round
- `GET /v1/register_user/` – Fetch registered users of event
- `GET /v1/event-detail/` – Event details
- `GET /v1/application-count/` – Total applications
- `GET /v1/user-event-data/` – User-specific event view
- `PATCH /v1/modified-shortlisted` – Toggle shortlist flag
- `GET /v1/all-selected-users/` – Final selected
- `GET /v1/assessment-questions/` – Assessment questions
- `GET /v1/zoom-joined-user/` – Who joined Zoom
- `GET /v1/resume-processing-track/` – Tracks for resume processing (with user mapping)
- `GET|POST /v1/hr-user-chatting/` – HR ↔ Interviewee chat thread

Refer to `event/urls.py` and `user_data/urls.py` and the corresponding `views.py` for request/response shapes.

---

## Resume Processing & ATS
- Uploads come as base64 PDFs → `S3` via `upload_base64_to_s3()`.
- Celery task `process_bulk_resumes_task`:
  - Downloads PDF, extracts text via `pdfplumber`
  - Builds job context from `Event` + `EventDescription`
  - Calls OpenAI (`gpt-4.1-mini`) with a strict JSON prompt
  - Parses candidate fields + `finalScore`
  - Creates `User`/`UserProfile` if needed and `UserRegister`
  - Sends emails to interviewers and interviewees
- Single resume path: `process_single_resume_task` (no mail)
- Re-score existing: `fetch_only_ats_score_task` (updates `ats_score`, triggers mail)

Ensure `OPENAI_API_KEY` is set and outbound network access is available.

---

## Email
Configured via `SMTP_HOST/PORT/USER/PASSWORD`. HTML template lives in `user_data/services/email_service.py`. For Gmail, use an App Password.

---

## Zoom Web SDK Signature
Endpoint: `POST /bulk_hiring/event/v1/generate-zoom-signature/`
Request body (example):
```json
{
  "role": 1,
  "sessionName": "Interview Room A",
  "expirationSeconds": 7200,
  "userIdentity": "john.doe",
  "sessionKey": "optional-session-key",
  "geoRegions": ["IN","US"],
  "cloudRecordingOption": 1,
  "cloudRecordingElection": 1,
  "videoWebRtcMode": 1,
  "audioCompatibleMode": 0,
  "audioWebRtcMode": 1
}
```
Response contains `{ "signature": "<jwt>" }`.

---

## TURN/ICE via Twilio
- `GET /bulk_hiring/event/v1/turn-credentials/?user_id=<id>` returns `ice_servers` from Twilio. Cache-limited by `TURN_LIMIT` and `TURN_EXPIRY`.
- `POST /bulk_hiring/event/v1/turn-disconnect/` to release capacity when done.

---

## Local PDF Script
`pdf_reader.py` can batch-parse local PDFs in `resumes/` and write JSON to `parsed_json/` (requires DB access to fetch `EventDescription`):
```bash
python pdf_reader.py
```
Edit `EVENT_ID`, `PDF_FOLDER`, `OUTPUT_FOLDER` to suit your environment.

---

## Security & Hardening
- Rotate and move all secrets out of `settings.py` immediately.
- Restrict `ALLOWED_HOSTS` and `CORS_ALLOW_ALL_ORIGINS` for production.
- Enforce HTTPS for APIs and WebSocket.
- Validate S3 uploads (file type/size) before forwarding to `upload_base64_to_s3`.
- Monitor Celery retries; add structured logging.

---

## Troubleshooting
- "Redis connection refused": ensure Redis is running and `CHANNEL_LAYERS`/`CELERY_BROKER_URL` point to it.
- DB auth errors: verify Postgres user/password and `pg_hba.conf`.
- ATS error "Resume text too short": check uploaded PDF readability.
- WebSocket closes with 4003/4004: username/token mismatch or mapping missing; verify JWT and `zoom-mapping` step.
- Emails not sending: verify SMTP creds; for Gmail, enable App Passwords.
- Twilio 401/403: verify `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`.

---

## License
Proprietary (or add your preferred license).
# interview
Video Calling
