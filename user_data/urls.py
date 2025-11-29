from django.urls import path
from .views import SignupView, SendOtpView, VerifyOtpView, UserDataView, FetchUserView, SendEventUserMail, RegisterInterviewer
app_name = 'user_data'
urlpatterns = [
    path('v1/signup/', SignupView.as_view(), name='signup'),
    path("v1/login/send-otp/", SendOtpView.as_view(), name="send-otp"),
    path("v1/login/verify-otp/", VerifyOtpView.as_view(), name="verify-otp"),
    path("v1/user-data/", UserDataView.as_view(), name="user-data"),
    path("v1/fetch-user/", FetchUserView.as_view(), name="fetch-user"),
    path("v1/register-interviewer/", RegisterInterviewer.as_view(), name="register-interviewer"),
    path("v1/send-event-mail/", SendEventUserMail.as_view(), name="send-event-mail"),
]
