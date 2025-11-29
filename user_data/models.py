from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    logo = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} - {self.id}"
    
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
    phone = models.CharField(max_length=15)
    company_name = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='user_company', null=True, blank=True)
    user_type = models.CharField(max_length=100, choices=[
        ('Interviewer', 'Interviewer'),
        ('Interviewee', 'Interviewee'),
        ('Admin', 'Admin'),
        ('Hr', 'Hr')
    ], default='Interviewee')

    def __str__(self):  
        return f"{self.user.first_name} {self.user.last_name} - {self.id}"

class UserResume(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='user_resumes')
    resume = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    