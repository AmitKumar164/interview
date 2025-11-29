from django.db import models
from user_data.models import UserProfile
import random
import string
from django.db.models import UniqueConstraint

class Department(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.id}"    

class Skills(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.id}"    

class Event(models.Model):
    created_by = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='user_events')
    created_at = models.DateTimeField(auto_now_add=True)
    job_title = models.CharField(max_length=100)
    event_id = models.CharField(max_length=10, editable=False)  # Come From Frontend
    job_type = models.CharField(max_length=100, choices=[
        ('Full Time', 'Full Time'),
        ('Part Time', 'Part Time'),
        ('Internship', 'Internship'),
        ('Contract', 'Contract'),
    ])
    job_location = models.CharField(max_length=100, choices=[
        ('Remote', 'Remote'),
        ('Onsite', 'Onsite'),
        ('Hybrid', 'Hybrid'),
    ])
    work_experience = models.IntegerField()
    department = models.ForeignKey("Department", on_delete=models.CASCADE, related_name='events')
    total_rounds = models.IntegerField()
    min_salary = models.IntegerField()
    max_salary = models.IntegerField()
    start_date = models.DateField()
    start_time = models.TimeField()
    status = models.CharField(max_length=100, choices=[
        ('Pending', 'Pending'),
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ], default='Pending')
    expected_ats_score = models.IntegerField()


    def save(self, *args, **kwargs):
        if not self.event_id:
            self.event_id = self.generate_unique_event_id()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_unique_event_id():
        """Generate a unique 10-character uppercase ID"""
        while True:
            event_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            if not Event.objects.filter(event_id=event_id).exists():
                return event_id

    def __str__(self):
        return f"{self.job_title} - {self.event_id}"
   
class EventDescription(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='descriptions')
    about_event = models.TextField()
    key_responsibilities = models.TextField()
    skills = models.JSONField()

class UserRegister(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='user_registers')
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='user_registers')
    resume = models.TextField(blank=True)
    ats_score = models.IntegerField(null=True, blank=True)
    shortlisted = models.BooleanField(default=True)
    selected = models.BooleanField(default=False) # Only if selected at last round
    rejected = models.BooleanField(default=False)
    is_user_registered = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user'],
                name='unique_reg_event_user'
            )
        ]

# Total number of Rounds in that event
class Round(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='rounds')
    round_number = models.IntegerField() # means Round no 1, round no 2, round no 3

# It will store interviewer for each round
class Interviewer(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='interviewers')
    interviewer = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='interviewers')
    
class Question(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()

class IntervieweeJoin(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='interviewee_joins')
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='interviewee_joins')
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='interviewee_joins')

    ###### Result
    interviewer_user = models.ForeignKey(Interviewer, on_delete=models.CASCADE, related_name='interviewer_user', null=True, blank=True)
    score = models.FloatField(null=True, blank=True) #Overall Average
    result = models.CharField(max_length=100, choices=[
        ('pass', 'pass'),
        ('fail', 'fail'),
        ('pending', 'pending'),
    ], null=True, blank=True)
    review = models.TextField(null=True, blank=True)
    result_based_on_question = models.TextField(null=True, blank=True)


    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user', 'round'],
                name='unique_event_user_round'
            )
        ]

class ZoomAttendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='zoom_attendances')
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='zoom_attendances')
    user_type = models.CharField(max_length=100, choices=[
        ('Interviewer', 'Interviewer'),
        ('Interviewee', 'Interviewee'),
        ('Hr', 'Hr')
    ])
    join_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user'],
                name='unique_event_user'
            )
        ]

class ResumeProcessingTrack(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("DOWNLOADED", "Downloaded"),
        ("AI_DONE", "AI Parsed"),
        ("USER_CREATED", "User Created"),
        ("USER_EXISTING", "User Existing"),
        ("REGISTERED", "Registered"),
        ("FAILED", "Failed"),
        ("COMPLETED", "Completed"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    s3_url = models.TextField()
    email = models.EmailField(null=True, blank=True)
    ats_score = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    error = models.TextField(null=True, blank=True)

    raw_ai_response = models.JSONField(null=True, blank=True)

    # ✅ MAIL TRACKING
    mail_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("SENT", "Sent"),
            ("FAILED", "Failed"),
            ("SKIPPED", "Skipped"),
        ],
        default="PENDING"
    )
    mail_error = models.TextField(null=True, blank=True)
    mail_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    task_id = models.CharField(max_length=100, db_index=True, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["task_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["email"]),
            models.Index(fields=["event"]),
        ]
        unique_together = (
            ("event", "email"),
        )

    def __str__(self):
        return f"{self.email} - {self.status}"

class HRUserChatting(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='hr_user_event')
    hr = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='hr_user_chatting')
    interviewee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='interviewee_hr_chatting')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    created_by = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='created_by_hr_chatting')
    