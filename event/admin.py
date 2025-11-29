from django.contrib import admin
from .models import (
    Department,
    Skills,
    Event,
    EventDescription,
    UserRegister,
    Round,
    Interviewer,
    Question,
    ZoomAttendance,
    IntervieweeJoin,
    ResumeProcessingTrack,
    HRUserChatting
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Skills)
class SkillsAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "id", "event_id", "job_title", "job_type", "job_location", 
        "work_experience", "department", "total_rounds", 
        "min_salary", "max_salary", "start_date", "start_time", "status", "created_by"
    )
    list_filter = ("job_type", "job_location", "status", "department")
    search_fields = ("event_id", "job_title")
    readonly_fields = ("event_id",)


@admin.register(EventDescription)
class EventDescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "about_event")
    search_fields = ("event__job_title", "about_event")


@admin.register(UserRegister)
class UserRegisterAdmin(admin.ModelAdmin):
    list_display = ("id","user", "event", "resume", "ats_score", "shortlisted")
    search_fields = ("event__job_title",)


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "round_number")
    search_fields = ("event__job_title",)


@admin.register(Interviewer)
class InterviewerAdmin(admin.ModelAdmin):
    list_display = ("id", "round", "interviewer")
    search_fields = ("round__event__job_title", "interviewer__user__username")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "question")
    search_fields = ("question", "round__job_title")

    def event(self, obj):
        # guard in case round is null (if your FK allows null)
        return obj.round.job_title if obj.round else "-"
    event.short_description = "Event"
    event.admin_order_field = "round__job_title"  # optional: allow column sorting


@admin.register(ZoomAttendance)
class ZoomAttendanceAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "user", "user_type")
    search_fields = ("event__job_title", "user__user__username")

@admin.register(IntervieweeJoin)
class IntervieweeJoinAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "user", "round")
    search_fields = ("event__job_title", "user__user__username")

@admin.register(ResumeProcessingTrack)
class ResumeProcessingTrackAdmin(admin.ModelAdmin):

    list_display = (
        "email",
        "event",
        "status",
        "mail_status",
        "ats_score",
        "task_id",
        "created_at",
    )

    list_filter = (
        "status",
        "mail_status",
        "event",
    )

    search_fields = (
        "email",
        "s3_url",
        "task_id",
    )

    readonly_fields = (
        "task_id",
        "created_at",
        "updated_at",
    )

@admin.register(HRUserChatting)
class HRUserChattingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event",
        "hr",
        "interviewee",
        "message",
        "created_at",
    )
    search_fields = (
        "event__job_title",
        "hr__user__username",
        "interviewee__user__username",
    )
