from django.urls import path
from .views import *
app_name = 'event'
urlpatterns = [
    path('v1/event/', EventView.as_view(), name='event'),
    path("v1/skills/", SkillsView.as_view(), name="skills"),
    path("v1/departments/", DepartmentView.as_view(), name="departments"),
    path("v1/event-register/", EventRegisterView.as_view(), name="event-register"),
    path("v1/generate-zoom-signature/", GenerateZoomSignatureView.as_view(), name="generate-zoom-signature"),
    path("v1/application-by-department/", ApplicationByDepartmentView.as_view(), name="application-by-department"),
    path("v1/job-application-status/", JobApplicationStatusView.as_view(), name="job-application-status"),
    path("v1/turn-credentials/", TurnCredentialsAPIView.as_view(), name="turn-credentials"),
    path("v1/zoom-attendance/", ZoomAttendanceView.as_view(), name="zoom-attendance"),
    path("v1/zoom-mapping/", ZoomMapping.as_view(), name="zoom-mapping"),
    path("v1/turn-disconnect/", TurnDisconnect.as_view(), name="turn-disconnect"),
    path("v1/candidate-review/", CandidateReview.as_view(), name="candidate-review"),
    path("v1/interviewee-join/", IntervieweeJoinView.as_view(), name="interviewee-join"),
    path("v1/register_user/", FetchEventRegisteredUser.as_view(), name="registered_user"),
    path("v1/event-detail/", FetchEventDetail.as_view(), name="event-detail"),
    path("v1/application-count/", ApplicationCount.as_view(), name="application-count"),
    path("v1/user-event-data/", FetchUserEventData.as_view(), name="user-event-data"),
    path("v1/modified-shortlisted", ModifyShortlisted.as_view(), name="modify-shortlisted"),
    path("v1/generate-jd/", GenerateJDSections.as_view(), name="generate-jd"),
    path("v1/all-selected-users/", AllSelectedUsers.as_view(), name="all-selected-users"),
    path("v1/assessment-questions/", FetchAssessmentQuestions.as_view(), name="fetch-assessment-questions"),
    path("v1/zoom-joined-user/", FetchZoomJoinedUser.as_view(), name="zoom-joined-user"),
    path("v1/resume-processing-track/", ResumeProcessingTrackAPI.as_view(), name="resume-processing-track"),
    path("v1/hr-user-chatting/", HRUserChattingAPI.as_view(), name="hr-user-chatting"),
]
