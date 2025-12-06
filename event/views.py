from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import *
from event.utils.aws_utils import upload_base64_to_s3
import jwt
import time
import math
import requests
from connectify_bulk_hiring import settings
from django.core.cache import cache
from .serializers import *
from django.db.models import Count
import json
from django.db import transaction
from openai import OpenAI
from user_data.services.prompt_service import GENERATE_ABOUT_AND_RESPONSIBILITIES_PROMPT   # optional
from event.tasks import process_bulk_resumes_task, process_single_resume_task, fetch_only_ats_score_task
from .serializers import ResumeProcessingTrackSerializer
from django.db.models import Avg, Min, Sum
from datetime import date, timedelta

client = OpenAI(api_key=settings.OPENAI_API_KEY)


'''
"previous_resumes": [
    {
        "event_id": 1,
        "user_profile_id": 2
    }
]
'''
class EventView(APIView):
    def post(self, request):
        user_profile = request.user.user_profile
        # user_profile = UserProfile.objects.get(id=1)
        try:
            # Safely load JSON fields
            job_details = request.data.get("job_details", "{}")
            job_description = request.data.get("job_description", "{}")
            rounds = request.data.get("rounds", "[]")
            questions = request.data.get("questions", "[]")

            user_register = request.data.get("resumes", [])
            previous_resumes = request.data.get("previous_resumes", [])
            expected_ats_score = request.data.get("expected_ats_score", 0)
 
            with transaction.atomic():
                # Create event
                event = Event.objects.create(
                    created_by=user_profile,
                    job_title=job_details.get("job_title").strip(),
                    job_type=job_details.get("job_type").strip(),
                    job_location=job_details.get("job_location").strip(),
                    work_experience=job_details.get("work_experience"),
                    department=Department.objects.get(id=job_details.get("department")),
                    total_rounds=job_details.get("total_rounds"),
                    min_salary=job_details.get("min_salary"),
                    max_salary=job_details.get("max_salary"),
                    start_date=job_details.get("start_date"),
                    start_time=job_details.get("start_time"),
                    expected_ats_score=expected_ats_score
                )
                print(12)
                event_description = EventDescription.objects.create(
                    event=event,
                    about_event=job_description.get("about_event"),
                    key_responsibilities=job_description.get("key_responsibilities"),
                    skills=job_description.get("skills")
                )
                if user_register:
                    print(32)
                    s3_urls = []
                    for resume in user_register:
                        s3_url = upload_base64_to_s3(resume)
                        s3_urls.append(s3_url)
                        print(s3_url)
                    print(event.id)
                    task = process_bulk_resumes_task.delay(s3_urls, event_id=event.id, company_name_id=user_profile.company_name_id, expected_ats_score=expected_ats_score)
                    print("Task ID:", task.id)

                if previous_resumes:
                    print(45)
                    print(previous_resumes)

                    event_user_pairs = {
                        (resume.get("event_id"), resume.get("user_profile_id"))
                        for resume in previous_resumes
                    }

                    existing_users = UserRegister.objects.filter(
                        event_id__in=[e for e, _ in event_user_pairs],
                        user_id__in=[u for _, u in event_user_pairs]
                    )

                    lookup_map = {
                        (ur.event_id, ur.user_id): ur
                        for ur in existing_users
                    }

                    bulk_create_list = []

                    for resume in previous_resumes:
                        key = (resume.get("event_id"), resume.get("user_profile_id"))
                        user_register = lookup_map.get(key)

                        if not user_register:
                            continue

                        bulk_create_list.append(
                            UserRegister(
                                event=event,
                                user=user_register.user,
                                resume=user_register.resume,
                                ats_score=user_register.ats_score,
                            )
                        )

                    # ✅ Bulk insert
                    UserRegister.objects.bulk_create(bulk_create_list)

                    # ✅ RE-FETCH inserted rows to collect IDs
                    new_instances = UserRegister.objects.filter(
                        event=event,
                        user_id__in=[obj.user_id for obj in bulk_create_list]
                    ).order_by("-id")[:len(bulk_create_list)]

                    # ✅ Collect instance IDs
                    instance_ids = list(new_instances.values_list("id", flat=True))

                    fetch_only_ats_score_task.delay(instance_ids)

                round_map = {}
                for round_data in rounds:
                    ro = Round.objects.create(event=event, round_number=round_data.get("round_number"))
                    round_map[round_data.get("round_number")] = ro

                    interviewers = round_data.get("interviewers", [])
                    for interviewer_id in interviewers:
                        Interviewer.objects.create(
                            round=ro,
                            interviewer_id=interviewer_id
                        )
                for question in questions:
                    Question.objects.create(event=event, question=question)
                print(21)

            return JsonResponse({
                "message": "Event created successfully",
                "event_id": event.id
            }, status=201)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


    def get(self, request):
        status_filter = request.GET.get("status")

        if status_filter:
            events = Event.objects.filter(status=status_filter).order_by("start_date", "start_time")
        else:
            events = Event.objects.filter(created_by__company_name_id=request.user.user_profile.company_name_id).order_by("start_date", "start_time")

        if request.user.user_profile.user_type == "Hr":
            events = events.filter(created_by=request.user.user_profile).distinct()
        elif request.user.user_profile.user_type == "Interviewer":
            events = events.filter(rounds__interviewers__interviewer=request.user.user_profile).distinct()
        event_list = []
        for event in events:
            description = EventDescription.objects.filter(event=event).first()

            resumes = list(UserRegister.objects.filter(event=event, shortlisted=True).values_list("user__id", flat=True))
            not_shortlisted = list(UserRegister.objects.filter(event=event, shortlisted=False).values_list("user__id", flat=True))
            rounds_data = []
            for round_obj in event.rounds.all():
                interviewers = list(round_obj.interviewers.values(
                    "id", "interviewer__id", "interviewer__user__first_name", "interviewer__user__last_name"
                ))
                questions = list(event.questions.values("id", "question"))

                rounds_data.append({
                    "round_number": round_obj.round_number,
                    "interviewers": interviewers,
                    "questions": questions
                })

            event_list.append({
                "id": event.id,
                "created_at": event.created_at,
                "created_by": event.created_by.user.first_name + " " + event.created_by.user.last_name,
                "company_name": event.created_by.company_name.name,
                "created_by_id": event.created_by.id,
                "event_id": event.event_id if event.event_id else "",
                "job_title": event.job_title,
                "job_type": event.job_type,
                "job_location": event.job_location,
                "work_experience": event.work_experience,
                "department": event.department.name,
                "total_rounds": event.total_rounds,
                "max_salary": event.max_salary,
                "min_salary": event.min_salary,
                "start_date": event.start_date,
                "start_time": event.start_time,
                "status": event.status,
                "description": {
                    "about_event": description.about_event if description else "",
                    "key_responsibilities": description.key_responsibilities if description else "",
                    "skills": description.skills if description else [],
                },
                "resumes": resumes,
                "not_shortlisted": not_shortlisted,
                "rounds": rounds_data
            })

        return JsonResponse({
            "events": event_list
        }, status=200)

    def patch(self, request):
        event_id = request.data.get("event_id")
        event = Event.objects.get(id=event_id)
        status = request.data.get("status")
        if status not in ["Pending", "Active", "Inactive"]:
            return JsonResponse({"error": "Invalid status"}, status=400)
        event.status = status
        event.save()
        return JsonResponse({"event": {"id": event.id, "status": event.status}}, status=200)

class SkillsView(APIView):
    def get(self, request):
        skills = Skills.objects.all()
        return JsonResponse({"skills": list(skills.values("id", "name"))}, status=200)

    def post(self, request):
        name = request.data.get("name")
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        skill = Skills.objects.create(name=name)
        return JsonResponse({"skill": {"id": skill.id, "name": skill.name}}, status=201)
    
class DepartmentView(APIView):
    def get(self, request):
        departments = Department.objects.all()
        return JsonResponse({"departments": list(departments.values("id", "name"))}, status=200)
    
    def post(self, request):
        name = request.data.get("name")
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        department = Department.objects.create(name=name)
        return JsonResponse({"department": {"id": department.id, "name": department.name}}, status=201)

class EventRegisterView(APIView):
    def post(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        event_id = request.data.get("event_id")
        resume = request.data.get("resume")
        if not event_id or not resume:
            return JsonResponse({"error": "Event ID and resume are required"}, status=400)
        event = Event.objects.get(id=event_id)
        s3_url = upload_base64_to_s3(resume)
        process_single_resume_task.delay(s3_url, event_id, user_profile.id)
        user_register = UserRegister.objects.create(event=event, user=user_profile, resume=s3_url)
        return JsonResponse({"message": "User registered successfully"}, status=201)

class ApplicationByDepartmentView(APIView):
    def get(self, request):
        data = []

        departments = Department.objects.all()
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        for dept in departments:
            count = UserRegister.objects.filter(event__department_id=dept.id, event__start_date__month=month, event__start_date__year=year).count()
            data.append({
                "department_id": dept.id,
                "department_name": dept.name,  # adjust if your field name differs
                "application_count": count
            })

        total_count = sum(item["application_count"] for item in data)

        return JsonResponse({
            "success": True,
            "total_applications": total_count,
            "departments": data
        }, status=200)

class JobApplicationStatusView(APIView):
    def get(self, request):
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        if not month or not year:
            return JsonResponse({
                "success": False,
                "message": "Please provide both 'month' and 'year' query parameters."
            }, status=400)

        # All possible statuses
        all_statuses = ['Pending', 'Active', 'Inactive']
        print(123456789)
        print(request.user.user_profile.company_name_id)
        # Query applications grouped by status
        applications = Event.objects.filter(
            start_date__month=month,
            start_date__year=year,
            created_by__company_name_id=request.user.user_profile.company_name_id
        ).values("status").annotate(count=Count("id"))


        # Build dictionary with actual counts
        status_counts = {item["status"]: item["count"] for item in applications}

        # Ensure all statuses exist, even if count = 0
        for status in all_statuses:
            status_counts.setdefault(status, 0)

        total_applications = sum(status_counts.values())

        return JsonResponse({
            "success": True,
            "total_applications": total_applications,
            "status_wise_counts": status_counts
        }, status=200)
            
        
class GenerateZoomSignatureView(APIView):
    def post(self, request):
        print(request)
        serializer = ZoomJWTSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse(
                {'errors': serializer.errors}, 
                status=400
            )
        
        validated_data = serializer.validated_data
        
        # Extract validated data
        role = validated_data['role']
        session_name = validated_data['sessionName']
        expiration_seconds = validated_data.get('expirationSeconds')
        user_identity = validated_data.get('userIdentity')
        session_key = validated_data.get('sessionKey')
        geo_regions = validated_data.get('geoRegions', [])
        cloud_recording_option = validated_data.get('cloudRecordingOption')
        cloud_recording_election = validated_data.get('cloudRecordingElection')
        telemetry_tracking_id = validated_data.get('telemetryTrackingId')
        video_webrtc_mode = validated_data.get('videoWebRtcMode')
        audio_compatible_mode = validated_data.get('audioCompatibleMode')
        audio_webrtc_mode = validated_data.get('audioWebRtcMode')
        
        # Generate timestamps
        iat = int(time.time()) - 30
        exp = iat + expiration_seconds if expiration_seconds else iat + 60 * 60 * 2
        
        # Create JWT header
        header = {
            'alg': 'HS256',
            'typ': 'JWT'
        }
        
        # Create JWT payload
        payload = {
            'app_key': settings.ZOOM_SDK_CLIENT_ID,
            'role_type': role,
            'tpc': session_name,
            'version': 1,
            'iat': iat,
            'exp': exp
        }
        
        # Add optional fields to payload if provided
        if user_identity:
            payload['user_identity'] = user_identity
        if session_key:
            payload['session_key'] = session_key
        if geo_regions:
            payload['geo_regions'] = ','.join(geo_regions)
        if cloud_recording_option is not None:
            payload['cloud_recording_option'] = cloud_recording_option
        if cloud_recording_election is not None:
            payload['cloud_recording_election'] = cloud_recording_election
        if telemetry_tracking_id:
            payload['telemetry_tracking_id'] = telemetry_tracking_id
        if video_webrtc_mode is not None:
            payload['video_webrtc_mode'] = video_webrtc_mode
        
        # Handle audio mode priority (audioWebRtcMode takes precedence over audioCompatibleMode)
        if audio_webrtc_mode is not None:
            payload['audio_webrtc_mode'] = audio_webrtc_mode
        elif audio_compatible_mode is not None:
            payload['audio_webrtc_mode'] = audio_compatible_mode
        
        try:
            # Generate JWT using PyJWT
            sdk_jwt = jwt.encode(
                payload=payload,
                key=settings.ZOOM_SDK_CLIENT_SECRET,
                algorithm='HS256',
                headers=header
            )
            return JsonResponse({'signature': sdk_jwt})
            
        except Exception as e:
            return JsonResponse(
                {'error': f'JWT generation failed: {str(e)}'}, 
                status=500
            )

    def options(self, request):
        """Handle preflight requests"""
        return JsonResponse(status=200)


class TurnCredentialsAPIView(APIView):

    def get(self, request):
        user_id = str(request.query_params.get("user_id"))
        if not user_id:
            return JsonResponse({"error": "user_id is required"}, status=400)

        # Fetch list of active users from cache
        active_users = cache.get("turn_active_users", set())

        # If user already active → deny
        if user_id in active_users:
            return JsonResponse({"error": "TURN access already granted"}, status=403)

        # Check TURN capacity
        if len(active_users) >= settings.TURN_LIMIT:
            return JsonResponse({"error": "TURN server limit reached"}, status=403)

        # ---- Fetch Twilio TURN token ----
        try:
            response = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Tokens.json",
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

        if response.status_code != 201:
            return JsonResponse({
                "error": "Failed to fetch TURN credentials",
                "twilio_message": response.json().get("message", "Unknown error")
            }, status=500)

        turn_data = response.json()

        # Add user to active TURN set
        active_users.add(user_id)

        # Store updated active set with expiry
        cache.set("turn_active_users", active_users, settings.TURN_EXPIRY)

        return JsonResponse(turn_data.get("ice_servers"), safe=False, status=200)

def remove_turn_user(user_id):
    user_id = str(user_id)
    active_users = cache.get("turn_active_users", set())

    if user_id in active_users:
        active_users.remove(user_id)
        cache.set("turn_active_users", active_users, settings.TURN_EXPIRY)

class TurnDisconnect(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        remove_turn_user(user_id)
        return JsonResponse({"status": "removed"})

class ZoomAttendanceView(APIView):
    def post(self, request):
        event_id = request.data.get("event_id")
        try:
            event = Event.objects.get(id=event_id)
            zoom_attendance = ZoomAttendance.objects.create(event=event, user=request.user.user_profile, user_type=request.user.user_profile.user_type)
            return JsonResponse({"message": "Zoom attendance created successfully"}, status=201)
        except Event.DoesNotExist:
            return JsonResponse({"error": "Event not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

class ZoomMapping(APIView):
    def post(self, request):
        event_id = request.data.get("event_id")
        print("Event ID:", event_id)

        if not event_id:
            return JsonResponse({"error": "event_id is required"}, status=400)

        try:
            # Fetch event
            event = Event.objects.filter(id=event_id).first()
            if not event:
                return JsonResponse({"error": "Invalid event_id"}, status=404)

            current_round = 1
            print("Current Round:", current_round)  
            # Fetch all attendance records
            attendees = ZoomAttendance.objects.filter(event=event)

            if not attendees.exists():
                return JsonResponse({"error": "No attendees found for this event"}, status=404)
            print("Attendees:", attendees)
            # All interviewers (regardless of round)
            all_interviewers = list(
                attendees.filter(user_type="Interviewer")
                         .values_list("user__user__username", flat=True)
            )
            print("All Interviewers:", all_interviewers)
            # Interviewees
            interviewees = list(
                attendees.filter(user_type="Interviewee")
                         .values_list("user__user__username", flat=True)
            )
            print("Interviewees:", interviewees)
            if not all_interviewers:
                return JsonResponse({"error": "No Interviewers in the event"}, status=400)
            if not interviewees:
                return JsonResponse({"error": "No Interviewees in the event"}, status=400)

            # Get interviewers for CURRENT round only
            joined_interviewers = set(all_interviewers)
            round_interviewers = set(
                Interviewer.objects.filter(
                    round__event=event,
                    round__round_number=current_round
                ).values_list("interviewer__user__username", flat=True)
            )

            # Only interviewers who are BOTH in round AND in Zoom
            current_round_interviewers = list(round_interviewers & joined_interviewers)

            print("Active Round Interviewers (Joined Zoom):", current_round_interviewers)
            # Shuffle interviewees for randomness
            random.shuffle(interviewees)

            # Prepare mapping: all interviewers included, default empty
            mapping = {str(i): [] for i in all_interviewers}

            # Only assign to interviewers of current round
            idx = 0
            total_current = len(current_round_interviewers)

            if total_current == 0:
                return JsonResponse({"error": "No interviewers assigned for this round"}, status=400)

            for interviewee in interviewees:
                interviewer = current_round_interviewers[idx % total_current]
                mapping[str(interviewer)].append(interviewee)
                idx += 1

            # Save in cache
            cache_key = f"event_{event_id}_connect_mapping"
            cache.set(cache_key, mapping, timeout=60 * 60 * 10)  # save for 10 hrs

            return JsonResponse({
                "message": "Zoom mapping created successfully",
                "mapping": mapping
            }, status=201)

        except Exception as e:
            print(e)
            return JsonResponse({"error": str(e)}, status=500)


    def get(self, request):
        event_id = request.query_params.get("event_id")
        try:
            mapping = cache.get(f"event_{event_id}_connect_mapping", {})
            return JsonResponse({"mapping": mapping}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    def patch(self, request):

        if request.user.user_profile.user_type != "Interviewer":
            return JsonResponse({"error": "Unauthorized"}, status=401)

        event_id = request.data.get("event_id")
        user_profile = request.user.user_profile
        username = request.user.username

        try:
            # ---------------------
            # 1. FIND CURRENT ROUND (TAKE MINIMUM ROUND)
            # ---------------------
            interviewer_qs = Interviewer.objects.filter(
                interviewer=user_profile,
                round__event_id=event_id
            ).select_related("round")

            if not interviewer_qs.exists():
                return JsonResponse({"error": "Interviewer not assigned any round"}, status=404)

            round_obj = interviewer_qs.order_by("round__round_number").first().round
            current_round_no = round_obj.round_number

            # ---------------------
            # 2. FETCH CACHE
            # ---------------------
            cache_key = f"event_{event_id}_connect_mapping"
            mapping = cache.get(cache_key, {})

            # ---------------------
            # 3. FORCE ADD NEW INTERVIEWER IN CACHE (IMPORTANT FIX)
            # ---------------------
            if username not in mapping:
                mapping[username] = []
            def unique_keep_order(seq):
                seen = set()
                return [x for x in seq if not (x in seen or seen.add(x))]


            # ---------------------
            # 4. CLEAN DUPLICATES
            # ---------------------
            for k, v in mapping.items():
                mapping[k] = unique_keep_order(v)

            # ---------------------
            # 5. GET INTERVIEWERS FOR THAT ROUND
            # ---------------------
            round_interviewers = list(
                Interviewer.objects.filter(round=round_obj)
                .values_list("interviewer__user__username", flat=True)
            )

            # ---------------------
            # 6. ROUND LEVEL MAPPING
            # ---------------------
            round_mapping = {k: mapping[k] for k in round_interviewers if k in mapping}

            # ---------------------
            # 7. BALANCE ONLY WITH SAME ROUND IF POSSIBLE
            # ---------------------
            if len(round_mapping) > 1:

                total = sum(len(v) for v in round_mapping.values())
                interviewer_count = len(round_mapping)
                ideal = math.ceil(total / interviewer_count)

                overloaded = sorted(
                    round_mapping.items(),
                    key=lambda x: len(x[1]),
                    reverse=True
                )

                for interviewer, users in overloaded:
                    if interviewer == username:
                        continue

                    while len(users) > ideal and len(mapping[username]) < ideal:
                        user = users.pop()

                        if user not in mapping[username]:
                            mapping[username].append(user)

            # ---------------------
            # 8. FALLBACK TO DB IF HE IS ALONE IN ROUND
            # ---------------------
            if len(round_mapping) == 1:

                prev_round = Round.objects.filter(
                    event_id=event_id,
                    round_number=current_round_no - 1
                ).first()

                if prev_round:

                    eligible_users = IntervieweeJoin.objects.filter(
                        event_id=event_id,
                        round=round_obj,
                        score__isnull=True
                    ).filter(
                        user__interviewee_joins__round=prev_round,
                        user__interviewee_joins__result="pass"
                    ).distinct()

                    interviewer_obj = Interviewer.objects.filter(
                        interviewer=user_profile,
                        round=round_obj
                    ).first()

                    for obj in eligible_users:
                        email = obj.user.user.username

                        if email not in mapping[username]:
                            mapping[username].append(email)

                        obj.interviewer_user = interviewer_obj
                        obj.save()

            # ---------------------
            # 9. FINAL CLEAN (DISTINCT)
            # ---------------------
            for k in mapping:
                mapping[k] = unique_keep_order(mapping[k])

            # ---------------------
            # 10. SAVE IN CACHE
            # ---------------------
            cache.set(cache_key, mapping, timeout=60 * 60 * 10)

            return JsonResponse({
                "message": "Interviewer joined successfully",
                "interviewer": username,
                "round": current_round_no,
                "round_mapping": round_mapping,
                "cache": mapping
            }, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


            
class CandidateReview(APIView):
    def post(self, request):
        event_id = request.data.get("event_id")
        user_name = request.data.get("user_name")
        score = request.data.get("score")
        result = request.data.get("result")  # Pass/Fail
        review = request.data.get("review")
        result_based_on_question = request.data.get("assessment")
        interviewer_name = request.data.get("interviewer_user_name")

        event_data = Event.objects.filter(id=event_id).first()
        max_event_round = event_data.total_rounds
        print(max_event_round)

        try:
            # Latest register for this user
            user_register = IntervieweeJoin.objects.filter(
                event_id=event_id,
                user__user__username=user_name
            ).order_by('-id').first()

            round = user_register.round.round_number

            # Update review data
            user_register.score = score
            user_register.result = result
            user_register.review = review
            user_register.result_based_on_question = result_based_on_question
            user_register.save()

            # Only process if PASS
            if result == "pass":

                # If last round → mark selected
                if round == max_event_round:
                    UserRegister.objects.filter(
                        event_id=event_id,
                        user__user__username=user_name
                    ).update(selected=True)

                else:
                    # Move candidate to next round
                    next_round = Round.objects.filter(
                        event_id=event_id,
                        round_number=round + 1
                    ).first()

                    # Fetch all interviewers of next round
                    next_round_interviewers = list(
                        Interviewer.objects.filter(round=next_round)
                        .values_list("interviewer__user__username", flat=True)
                    )

                    # Load existing mapping
                    cache_key = f"event_{event_id}_connect_mapping"
                    mapping = cache.get(cache_key, {})

                    # Ensure all next-round interviewers have an entry
                    for interviewer in next_round_interviewers:
                        if interviewer not in mapping:
                            mapping[interviewer] = []

                    # Pick interviewer with shortest queue
                    free_interviewer = min(
                        next_round_interviewers,
                        key=lambda name: len(mapping.get(name, []))
                    )

                    # Save new IntervieweeJoin
                    interviewer_obj = Interviewer.objects.filter(
                        round=next_round,
                        interviewer__user__username=free_interviewer
                    ).first()

                    IntervieweeJoin.objects.create(
                        event_id=event_id,
                        user=user_register.user,
                        round=next_round,
                        interviewer_user=interviewer_obj,
                        result="pass"
                    )

                    # Add candidate to queue for selected interviewer
                    mapping[free_interviewer].append(user_register.user.user.username)

                    # Save back to cache
                    cache.set(cache_key, mapping, timeout=60 * 60 * 10)
            elif result == "fail":
                UserRegister.objects.filter(
                    event_id=event_id,
                    user__user__username=user_name
                ).update(rejected=True)

            return JsonResponse({"message": "User register updated successfully"}, status=200)

        except UserRegister.DoesNotExist:
            return JsonResponse({"error": "User register not found"}, status=404)

        except Exception as e:
            print(e)
            return JsonResponse({"error": str(e)}, status=500)


class IntervieweeJoinView(APIView):
    def post(self, request):
        event_id = request.data.get("event_id")
        user_name = request.data.get("user_name")
        interviewer_name = request.data.get("interviewer_user_name")
        
        round = Round.objects.filter(event_id=event_id, round_number=1).first()
        interviewer = Interviewer.objects.filter(round=round, interviewer__user__username=interviewer_name).first()
        try:
            user = UserProfile.objects.filter(user__username=user_name).first()
            if IntervieweeJoin.objects.filter(event_id=event_id, user=user, round=round).exists():
                user_register = IntervieweeJoin.objects.filter(event_id=event_id, user=user).order_by('-id').first()
                user_register.result = "pending"
                user_register.save()

                return JsonResponse({"message": "User already exists in the event"}, status=200)
            user_register = IntervieweeJoin.objects.create(event_id=event_id, user=user, round=round, interviewer_user=interviewer, result="pending")
            return JsonResponse({"message": "User register created successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

class FetchEventRegisteredUser(APIView):
    def get(self, request):

        # Fetch all registrations with user and event data (1 query)
        registrations = (
            UserRegister.objects
            .select_related("event", "user", "user__user")
            .order_by("event__id")  # grouping looks cleaner
        )

        # Build response grouped by event
        event_map = {}  # {event_id: {event_id:..., users:[...] }}

        for reg in registrations:
            event_id = reg.event.id

            # Set up event entry if not exists
            if event_id not in event_map:
                event_map[event_id] = {
                    "event_id": event_id,
                    "event_name": reg.event.title if hasattr(reg.event, "title") else "",
                    "users": []
                }

            # Add user entry
            event_map[event_id]["users"].append({
                "full_name": f"{reg.user.user.first_name} {reg.user.user.last_name}",
                "username": reg.user.user.username,
                "user_profile_id": reg.user.id,
                "shortlisted": reg.shortlisted,
                "selected": reg.selected
            })

        return JsonResponse({"data": list(event_map.values())}, status=200)

class FetchEventDetail(APIView):
    def get(self, request):
        event_id = request.query_params.get("event_id")
        if not event_id:
            return JsonResponse({"error": "Event ID is required"}, status=400)

        event = Event.objects.filter(id=event_id).first()
        if not event:
            return JsonResponse({"error": "Invalid event_id"}, status=404)

        # =============================
        # EVENT DETAILS (FULL)
        # =============================
        event_description = EventDescription.objects.filter(event=event).first()

        event_details = {
            "id": event.id,
            "event_id": event.event_id,
            "created_by": {
                "id": event.created_by.user.id,
                "username": event.created_by.user.username,
                "first_name": event.created_by.user.first_name,
                "last_name": event.created_by.user.last_name,
            },
            "created_at": event.created_at.isoformat(),

            # Job Information
            "job_title": event.job_title,
            "job_type": event.job_type,
            "job_location": event.job_location,
            "work_experience": event.work_experience,
            "department_id": event.department.id,
            "department_name": event.department.name,

            # Rounds & Salary
            "total_rounds": event.total_rounds,
            "min_salary": event.min_salary,
            "max_salary": event.max_salary,

            # Scheduling
            "start_date": event.start_date,
            "start_time": event.start_time,

            # Status
            "status": event.status,

            # Description Model (about, responsibilities, skills)
            "description": {
                "about_event": event_description.about_event if event_description else None,
                "key_responsibilities": event_description.key_responsibilities if event_description else None,
                "skills": event_description.skills if event_description else [],
            }
        }

        # =============================
        # COUNTS
        # =============================
        total_registered_user = UserRegister.objects.filter(event_id=event_id).count()
        total_rounds = event.total_rounds

        all_rounds = Round.objects.filter(event_id=event_id)
        total_interviewers = Interviewer.objects.filter(round__in=all_rounds).count()
        total_joined_user = IntervieweeJoin.objects.filter(event_id=event_id).distinct("user").count()

        # =============================
        # REGISTERED USERS
        # =============================
        registered_users_qs = UserRegister.objects.filter(event_id=event_id).order_by("user").select_related("user__user")
        registered_users = [
            {
                "id": reg.user.id,
                "username": reg.user.user.username,
                "first_name": reg.user.user.first_name,
                "last_name": reg.user.user.last_name,
                "shortlisted": reg.shortlisted,
                "selected": reg.selected,
                "rejected": reg.rejected,
                "self_register": reg.is_user_registered,
                "phone": reg.user.phone,
                "mail": reg.user.user.email,
                "ats_score": reg.ats_score,

            }
            for reg in registered_users_qs
        ]

        # =============================
        # SHORTLISTED USERS
        # =============================
        shortlisted_qs = UserRegister.objects.filter(event_id=event_id, shortlisted=True).select_related("user__user")

        shortlisted_users = [
            {
                "id": reg.user.id,
                "username": reg.user.user.username,
                "first_name": reg.user.user.first_name,
                "last_name": reg.user.user.last_name,
                "phone": reg.user.phone,
                "mail": reg.user.user.email,
                "ats_score": reg.ats_score,
            }
            for reg in shortlisted_qs
        ]

        shortlisted_count = len(shortlisted_users)

        # =============================
        # INTERVIEWERS LIST
        # =============================
        interviewer_qs = Interviewer.objects.filter(round__in=all_rounds).select_related("interviewer__user", "round")

        interviewers = [
            {
                "id": intr.interviewer.id,
                "username": intr.interviewer.user.username,
                "first_name": intr.interviewer.user.first_name,
                "last_name": intr.interviewer.user.last_name,
                "phone": intr.interviewer.phone,
                "mail": intr.interviewer.user.email,
                "round_number": intr.round.round_number
            }
            for intr in interviewer_qs
        ]

        # =============================
        # USER REGISTER MAP (For Status)
        # =============================
        user_register_map = {
            reg.user.id: reg
            for reg in UserRegister.objects.filter(event_id=event_id).select_related("user")
        }

        # =============================
        # JOINED USERS (Grouped)
        # =============================
        joined_qs = IntervieweeJoin.objects.filter(event_id=event_id).select_related(
            "user__user", "round", "interviewer_user__interviewer__user"
        )

        joined_users_dict = {}

        for j in joined_qs:
            user_id = j.user.id

            # Determine final status
            reg = user_register_map.get(j.user.id)
            if reg:
                if reg.selected:
                    final_status = "selected"
                elif reg.rejected:
                    final_status = "rejected"
                else:
                    final_status = "in_progress"
            else:
                final_status = "in_progress"

            # Create user entry once
            if user_id not in joined_users_dict:
                joined_users_dict[user_id] = {
                    "id": user_id,
                    "username": j.user.user.username,
                    "first_name": j.user.user.first_name,
                    "last_name": j.user.user.last_name,
                    "status": final_status,
                    "rounds": []
                }

            # Append round data
            joined_users_dict[user_id]["rounds"].append({
                "round_number": j.round.round_number,
                "score": j.score,
                "result": j.result,
                "review": j.review,
                "assessment": j.result_based_on_question,
                "interviewer": {
                    "id": j.interviewer_user.interviewer.id if j.interviewer_user else None,
                    "username": j.interviewer_user.interviewer.user.username if j.interviewer_user else None,
                    "first_name": j.interviewer_user.interviewer.user.first_name if j.interviewer_user else None,
                    "last_name": j.interviewer_user.interviewer.user.last_name if j.interviewer_user else None,
                } if j.interviewer_user else None,
            })

        joined_users = list(joined_users_dict.values())

        # =============================
        # ZOOM ATTENDANCE
        # =============================
        zoom_qs = ZoomAttendance.objects.filter(event_id=event_id).select_related("user__user")

        zoom_attendance = [
            {
                "id": z.user.id,
                "username": z.user.user.username,
                "first_name": z.user.user.first_name,
                "last_name": z.user.user.last_name,
                "mail": z.user.user.email,
                "user_type": z.user_type,
                "join_time": z.join_time.isoformat()
            }
            for z in zoom_qs
        ]

        zoom_total = len(zoom_attendance)

        # =============================
        # INTERVIEWER PERSPECTIVE
        # =============================
        interviewer_join_dict = {}

        for j in joined_qs:
            if not j.interviewer_user:
                continue

            interviewer_id = j.interviewer_user.interviewer.id

            if interviewer_id not in interviewer_join_dict:
                interviewer_join_dict[interviewer_id] = []

            interviewer_join_dict[interviewer_id].append({
                "id": j.user.id,
                "username": j.user.user.username,
                "first_name": j.user.user.first_name,
                "last_name": j.user.user.last_name,
                "round_number": j.round.round_number,
                "score": j.score,
                "result": j.result,
                "review": j.review,
                "assessment": j.result_based_on_question
            })

        interviewer_details = []

        for intr in interviewer_qs:
            interviewer_details.append({
                "id": intr.interviewer.id,
                "username": intr.interviewer.user.username,
                "first_name": intr.interviewer.user.first_name,
                "last_name": intr.interviewer.user.last_name,
                "phone": intr.interviewer.phone,
                "mail": intr.interviewer.user.email,
                "round_number": intr.round.round_number,
                "interviewed_users": interviewer_join_dict.get(intr.interviewer.id, [])
            })

        # =============================
        # PER-ROUND PASS/FAIL SUMMARY
        # =============================
        round_summary = []
        for r in all_rounds:
            joins = IntervieweeJoin.objects.filter(event_id=event_id, round=r)

            round_summary.append({
                "round_number": r.round_number,
                "pass": joins.filter(result="pass").count(),
                "fail": joins.filter(result="fail").count(),
                "pending": joins.filter(result="pending").count(),
                "total": joins.count(),
            })

        # =============================
        # FUNNEL STATS (Round→Round→Final)
        # =============================
        funnel_stats = {}

        for r in all_rounds:
            funnel_stats[f"round_{r.round_number}"] = IntervieweeJoin.objects.filter(
                event_id=event_id,
                round=r
            ).values("user").distinct().count()

        funnel_stats["selected"] = UserRegister.objects.filter(
            event_id=event_id, selected=True
        ).count()

        ats_stats = UserRegister.objects.filter(
            event_id=event_id,
            ats_score__isnull=False
        ).aggregate(
            average_ats=Avg("ats_score"),
            minimum_ats=Min("ats_score")
        )

        average_score = round(ats_stats["average_ats"], 2) if ats_stats["average_ats"] else 0
        minimum_score = ats_stats["minimum_ats"] if ats_stats["minimum_ats"] else 0

        # =============================
        # FINAL RESPONSE
        # =============================
        return JsonResponse({
            "event_details": event_details,

            "total_registered_user": total_registered_user,
            "total_rounds": total_rounds,
            "total_interviewers": total_interviewers,
            "total_joined_user": total_joined_user,

            "zoom_total": zoom_total,
            "shortlisted_count": shortlisted_count,

            "registered_users": registered_users,
            "shortlisted_users": shortlisted_users,
            "interviewers": interviewers,
            "joined_users": joined_users,
            "zoom_attendance": zoom_attendance,
            "interviewer_details": interviewer_details,

            "round_summary": round_summary,
            "funnel_stats": funnel_stats,

            "minimum_score": event.expected_ats_score,
            "average_score": average_score,
        }, status=200)

class ApplicationCount(APIView):
    def get(self, request):
        today = date.today()   # e.g. 2025-11-22
        day_num = today.day    # 22

        # ===== CURRENT MONTH RANGE =====
        current_month_start = today.replace(day=1)
        current_month_end = today  # always safe

        # ===== PREVIOUS MONTH RANGE =====
        # Step 1: find last day of previous month
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)

        # Step 2: try to create previous_month_start (day=1)
        previous_month_start = last_day_previous_month.replace(day=1)

        # Step 3: try to match "same day number" for end date
        # If day_num (22) exceeds last day of prev month (e.g., Feb has 28),
        # fallback to last day of previous month
        if day_num > last_day_previous_month.day:
            previous_month_end = last_day_previous_month
        else:
            previous_month_end = last_day_previous_month.replace(day=day_num)

        # Fetching Events
        current_month_events = Event.objects.filter(
            start_date__gte=current_month_start,
            start_date__lte=current_month_end,
            created_by__company_name_id=request.user.user_profile.company_name_id
        )

        previous_month_events = Event.objects.filter(
            start_date__gte=previous_month_start,
            start_date__lte=previous_month_end,
            created_by__company_name_id=request.user.user_profile.company_name_id
        )

        this_month_total_events = current_month_events.count()
        previous_month_total_events = previous_month_events.count()
        this_month_total_users = UserRegister.objects.filter(event__in=current_month_events).count()
        previous_month_total_users = UserRegister.objects.filter(event__in=previous_month_events).count()
        this_month_total_selected = UserRegister.objects.filter(event__in=current_month_events, selected=True).count()
        previous_month_total_selected = UserRegister.objects.filter(event__in=previous_month_events, selected=True).count()
        this_month_total_rejected = UserRegister.objects.filter(event__in=current_month_events, rejected=True).count()
        previous_month_total_rejected = UserRegister.objects.filter(event__in=previous_month_events, rejected=True).count()
        this_month_total_shortlisted = UserRegister.objects.filter(event__in=current_month_events, shortlisted=True).count()
        previous_month_total_shortlisted = UserRegister.objects.filter(event__in=previous_month_events, shortlisted=True).count()
        this_month_total_rounds = current_month_events.aggregate(total_rounds=Sum("total_rounds")).get("total_rounds", 0)
        previous_month_total_rounds = previous_month_events.aggregate(total_rounds=Sum("total_rounds")).get("total_rounds", 0)        

        return JsonResponse({
            "current_month_start": current_month_start,
            "current_month_end": current_month_end,
            "previous_month_start": previous_month_start,
            "previous_month_end": previous_month_end,
            "current_month_event_count": current_month_events.count(),
            "previous_month_event_count": previous_month_events.count(),
            "this_month_total_events": this_month_total_events,
            "previous_month_total_events": previous_month_total_events,
            "this_month_total_users": this_month_total_users,
            "previous_month_total_users": previous_month_total_users,
            "this_month_total_selected": this_month_total_selected,
            "previous_month_total_selected": previous_month_total_selected,
            "this_month_total_rejected": this_month_total_rejected,
            "previous_month_total_rejected": previous_month_total_rejected,
            "this_month_total_shortlisted": this_month_total_shortlisted,
            "previous_month_total_shortlisted": previous_month_total_shortlisted,
            "this_month_total_rounds": this_month_total_rounds,
            "previous_month_total_rounds": previous_month_total_rounds if previous_month_total_rounds else 0,
        }, status=200)

class FetchUserEventData(APIView):

    def get_full_event_details(self, event):
        desc = EventDescription.objects.filter(event=event).first()

        return {
            "id": event.id,
            "event_id": event.event_id,
            "job_title": event.job_title,
            "job_type": event.job_type,
            "job_location": event.job_location,
            "work_experience": event.work_experience,
            "total_rounds": event.total_rounds,
            "min_salary": event.min_salary,
            "max_salary": event.max_salary,
            "start_date": event.start_date,
            "start_time": event.start_time,
            "status": event.status,

            "created_by": {
                "id": event.created_by.user.id,
                "username": event.created_by.user.username,
                "first_name": event.created_by.user.first_name,
                "last_name": event.created_by.user.last_name
            },

            "description": {
                "about_event": desc.about_event if desc else None,
                "key_responsibilities": desc.key_responsibilities if desc else None,
                "skills": desc.skills if desc else []
            }
        }

    def get(self, request):
        user_id = request.query_params.get("user_id")
        if not user_id:
            return JsonResponse({"error": "User ID is required"}, status=400)

        user_profile = UserProfile.objects.get(id=user_id)

        # ======================================================
        # CASE 1: INTERVIEWER → events they interviewed in
        # ======================================================
        if user_profile.user_type == "Interviewer":

            interviewer_entries = Interviewer.objects.filter(
                interviewer=user_profile
            ).select_related("round__event")

            response_data = []

            for intr in interviewer_entries:
                event = intr.round.event

                # Fetch interviews taken
                interviews_taken = IntervieweeJoin.objects.filter(
                    interviewer_user=intr
                ).select_related("user__user", "round")

                interviewee_list = []

                for j in interviews_taken:
                    interviewee_list.append({
                        "id": j.user.id,
                        "username": j.user.user.username,
                        "first_name": j.user.user.first_name,
                        "last_name": j.user.user.last_name,
                        "round_number": j.round.round_number,
                        "score": j.score,
                        "result": j.result,
                        "review": j.review,
                        "result_based_on_question": j.result_based_on_question,

                    })

                response_data.append({
                    "event": self.get_full_event_details(event),
                    "round_number": intr.round.round_number,
                    "interviewed_users": interviewee_list
                })

            return JsonResponse({"interviewer_events": response_data}, status=200)

        # ======================================================
        # CASE 2: INTERVIEWEE → events + rounds taken
        # ======================================================
        elif user_profile.user_type == "Interviewee":

            interview_entries = IntervieweeJoin.objects.filter(
                user=user_profile
            ).select_related(
                "round__event",
                "interviewer_user__interviewer__user",
                "user__user"
            ).order_by("round__round_number")

            event_map = {}

            for entry in interview_entries:
                event = entry.round.event
                event_id = event.id

                # Final status from UserRegister
                user_reg = UserRegister.objects.filter(event=event, user=user_profile).first()

                if user_reg:
                    if user_reg.selected:
                        final_status = "selected"
                    elif user_reg.rejected:
                        final_status = "rejected"
                    else:
                        final_status = "in_progress"
                else:
                    final_status = "in_progress"

                # Create event block once
                if event_id not in event_map:
                    event_map[event_id] = {
                        "event": self.get_full_event_details(event),
                        "final_status": final_status,
                        "rounds": []
                    }

                # Add round info
                event_map[event_id]["rounds"].append({
                    "round_number": entry.round.round_number,
                    "score": entry.score,
                    "result": entry.result,
                    "result_based_on_question": entry.result_based_on_question,
                    "review": entry.review,
                    "interviewer": {
                        "id": entry.interviewer_user.interviewer.id if entry.interviewer_user else None,
                        "username": entry.interviewer_user.interviewer.user.username if entry.interviewer_user else None,
                        "first_name": entry.interviewer_user.interviewer.user.first_name if entry.interviewer_user else None,
                        "last_name": entry.interviewer_user.interviewer.user.last_name if entry.interviewer_user else None,
                    } if entry.interviewer_user else None
                })

            return JsonResponse({
                "interviewee_events": list(event_map.values())
            }, status=200)

        # ======================================================
        # CASE 3: HR → events 
        # ======================================================
        elif user_profile.user_type == "Hr":
            events = Event.objects.filter(created_by=user_profile)
            event_list = []
            for event in events:
                event_list.append({
                    "event": self.get_full_event_details(event),
                })
            return JsonResponse({
                "hr_events": event_list
            }, status=200)

class ModifyShortlisted(APIView):
    def patch(self, request):
        try:
            event_id = request.data.get("event_id")
            user_id = request.data.get("user_id")
            print(request.data)

            record = UserRegister.objects.filter(event_id=event_id, user_id=user_id).first()
            print(record)

            if not record:
                return JsonResponse({"error": "Record not found"}, status=404)

            # Toggle shortlisted (True -> False, False -> True)
            record.shortlisted = not record.shortlisted
            record.save()

            return JsonResponse({
                "message": "Shortlisted updated successfully",
                "new_value": record.shortlisted
            }, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

class FetchAssessmentQuestions(APIView):
    def get(self, request):
        event_id = request.query_params.get("event_id")
        event = Event.objects.get(id=event_id)
        questions = Question.objects.filter(event=event)
        return JsonResponse({"questions": list(questions.values("id", "question"))}, status=200)

class GenerateJDSections(APIView):
    def post(self, request):
        try:
            job_title = request.data.get("job_title")
            work_exp = request.data.get("work_experience")
            department = request.data.get("department")
            skills = request.data.get("skills", [])
            job_type = request.data.get("job_type")
            job_location = request.data.get("job_location")
            job_location_type = request.data.get("job_location_type")
            salary = request.data.get("salary", "")

            if not job_title:
                return Response({"error": "job_title is required"}, status=400)

            user_data = f"""
            Job Title: {job_title}
            Experience: {work_exp} years
            Department: {department}
            Skills: {", ".join(skills)}
            Job Type: {job_type}
            Job Location: {job_location}
            Location Type: {job_location_type}
            Salary: {salary}
            """

            final_prompt = GENERATE_ABOUT_AND_RESPONSIBILITIES_PROMPT + user_data

            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "You generate professional HR job descriptions."},
                    {"role": "user", "content": final_prompt}
                ],
                temperature=0.4
            )

            output = response.choices[0].message.content

            # Parse AI output cleanly
            about_text = ""
            responsibilities_list = []

            for line in output.split("\n"):
                if line.startswith("about:"):
                    about_text = line.replace("about:", "").strip()
                elif line.strip().startswith("-") or line.strip().startswith("•"):
                    responsibilities_list.append(line.strip())

            return Response({
                "about": about_text,
                "key_responsibilities": responsibilities_list
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

class ResumeProcessingTrackAPI(APIView):

    def get(self, request):
        try:
            task_id = request.query_params.get("task_id")
            event_id = request.query_params.get("event_id")
            status_filter = request.query_params.get("status")
            email = request.query_params.get("email")

            queryset = ResumeProcessingTrack.objects.all().order_by("-created_at")
            print(queryset)

            if task_id:
                queryset = queryset.filter(task_id=task_id)

            if event_id:
                queryset = queryset.filter(event_id=event_id)

            if status_filter:
                queryset = queryset.filter(status=status_filter)

            if email:
                queryset = queryset.filter(email__icontains=email)
            print(queryset)
            serializer = ResumeProcessingTrackSerializer(queryset, many=True)

            return Response({
                "count": queryset.count(),
                "data": serializer.data
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

class AllSelectedUsers(APIView):
    def get(self, request):
        try:
            user_profile = request.user.user_profile
            queryset = UserRegister.objects.filter(event__created_by=user_profile, selected=True).values("user_id")
            return Response({
                "count": queryset.count(),
                "data": queryset
            }, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class FetchZoomJoinedUser(APIView):
    def get(self, request):
        try:
            event_id = request.query_params.get("event_id")
            event = Event.objects.get(id=event_id)
            actual_interviewer = Interviewer.objects.filter(round__event=event).values("interviewer_id", "interviewer__user__username")
            zoom_joined_users = ZoomAttendance.objects.filter(event=event, user__in=actual_interviewer).values("user_id", "user__user__username")
            return Response({
                "actual_interviewer_count": actual_interviewer.count(),
                "zoom_joined_users_count": zoom_joined_users.count(),
                "zoom_joined_users": zoom_joined_users,
                "actual_interviewer": actual_interviewer,
            }, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class HRUserChattingAPI(APIView):

    def post(self, request):
        try:
            event_id = request.data.get("event_id")
            interviewee_id = request.data.get("interviewee_id")
            message = request.data.get("message")
            sender = request.user.user_profile

            if not event_id or not message:
                return Response({"error": "event_id and message are required"}, status=400)

            # ✅ HR sending to interviewee
            if sender.user_type == "Hr":
                if not interviewee_id:
                    return Response({"error": "interviewee_id required"}, status=400)

                chat = HRUserChatting.objects.create(
                    event_id=event_id,
                    hr=sender,
                    interviewee_id=interviewee_id,
                    message=message,
                    created_by=sender
                )

            # ✅ Interviewee sends first or anytime
            else:
                event = Event.objects.filter(id=event_id).first()
                if not event or not event.created_by:
                    return Response({"error": "HR not assigned for event"}, status=400)

                chat = HRUserChatting.objects.create(
                    event=event,
                    hr=event.created_by,          # ✅ auto routed
                    interviewee=sender,
                    message=message,
                    created_by=sender
                )

            return Response({"message": "Message sent"}, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)


    # ✅ FETCH CHATS
    def get(self, request):
        try:
            event_id = request.query_params.get("event_id")
            interviewee_id = request.query_params.get("interviewee_id")
            profile = request.user.user_profile

            # ---------------- HR SIDE ----------------
            if profile.user_type == "Hr":

                queryset = HRUserChatting.objects.filter(event_id=event_id, hr=profile)

                # GROUPED BY USER
                chat_map = {}
                for chat in queryset.order_by("created_at"):
                    uid = chat.interviewee.id
                    if uid not in chat_map:
                        chat_map[uid] = {
                            "interviewee_id": uid,
                            "interviewee_name": chat.interviewee.user.username,
                            "messages": []
                        }

                    chat_map[uid]["messages"].append(
                        HRUserChattingSerializer(chat, context={"request": request}).data
                    )

                return Response({
                    "type": "HR",
                    "total_users": len(chat_map),
                    "conversations": list(chat_map.values())
                }, status=200)

            # ---------------- INTERVIEWEE SIDE ----------------
            else:
                queryset = HRUserChatting.objects.filter(event_id=event_id, interviewee=profile).order_by("created_at")

                serializer = HRUserChattingSerializer(queryset, many=True, context={"request": request})

                return Response({
                    "type": "INTERVIEWEE",
                    "total_messages": queryset.count(),
                    "messages": serializer.data
                }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    def patch(self, request):
        try:
            hr_chatting_ids = request.data.get("hr_chatting_ids")
            hr_chatting = HRUserChatting.objects.filter(id__in=hr_chatting_ids)
            hr_chatting.update(is_read=True)
            return Response({"message": "Chats marked as read"}, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)