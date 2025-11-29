from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Company

class SignupSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=15)
    company_name_id = serializers.IntegerField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("email already exists")
        return value

    def validate(self, attrs):
        username = attrs["email"].split("@")[0]

        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError("username already exists")
        return attrs

    def create(self, validated_data):
        username = validated_data["email"].split("@")[0]

        # Create user
        user = User.objects.create(
            username=username,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            email=validated_data["email"],
        )

        # Create profile
        UserProfile.objects.create(
            user=user,
            phone=validated_data["phone_number"],
            company_name_id=validated_data["company_name_id"],
            user_type="Interviewee"
        )
        return user

class RegisterInterviewerSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=15)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("email already exists")
        return value

    def validate(self, attrs):
        username = attrs["email"].split("@")[0]

        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError("username already exists")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        company_name_id = request.user.user_profile.company_name_id
        username = validated_data["email"].split("@")[0]

        # Create user
        user = User.objects.create(
            username=username,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            email=validated_data["email"],
        )

        # Create profile
        user_profile = UserProfile.objects.create(
            user=user,
            phone=validated_data["phone_number"],
            company_name_id=company_name_id,
            user_type="Interviewer"
        )

        return user_profile
