
from rest_framework import serializers
from .validators import (
    is_required, in_number_array, is_between, 
    is_length_less_than, matches_string_array
)
from .models import ResumeProcessingTrack, HRUserChatting
from user_data.models import UserProfile

class ZoomSignatureRequestSerializer(serializers.Serializer):
    meeting_number = serializers.CharField(max_length=32)
    role = serializers.IntegerField(required=False, default=0)

    def validate_role(self, value):
        if value not in (0, 1):
            raise serializers.ValidationError("role must be 0 (attendee) or 1 (host)")
        return value

class ZoomJWTSerializer(serializers.Serializer):
    # Required fields
    role = serializers.IntegerField(validators=[
        is_required, 
        in_number_array([0, 1])
    ])
    sessionName = serializers.CharField(validators=[
        is_required, 
        is_length_less_than(200)
    ])
    
    # Optional fields
    expirationSeconds = serializers.IntegerField(
        required=False, 
        validators=[is_between(1800, 172800)]
    )
    userIdentity = serializers.CharField(
        required=False, 
        validators=[is_length_less_than(35)]
    )
    sessionKey = serializers.CharField(
        required=False, 
        validators=[is_length_less_than(36)]
    )
    geoRegions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        validators=[matches_string_array(['AU', 'BR', 'CA', 'CN', 'DE', 'HK', 'IN', 'JP', 'MX', 'NL', 'SG', 'US'])]
    )
    cloudRecordingOption = serializers.IntegerField(
        required=False,
        validators=[in_number_array([0, 1])]
    )
    cloudRecordingElection = serializers.IntegerField(
        required=False,
        validators=[in_number_array([0, 1])]
    )
    videoWebRtcMode = serializers.IntegerField(
        required=False,
        validators=[in_number_array([0, 1])]
    )
    audioCompatibleMode = serializers.IntegerField(
        required=False,
        validators=[in_number_array([0, 1])]
    )
    audioWebRtcMode = serializers.IntegerField(
        required=False,
        validators=[in_number_array([0, 1])]
    )
    telemetryTrackingId = serializers.CharField(required=False)

    def validate(self, attrs):
        """Custom validation logic"""
        # Convert string numbers to integers if needed
        for field in ['role', 'expirationSeconds', 'cloudRecordingOption', 
                     'cloudRecordingElection', 'videoWebRtcMode', 
                     'audioCompatibleMode', 'audioWebRtcMode']:
            if field in attrs and isinstance(attrs[field], str):
                try:
                    attrs[field] = int(attrs[field])
                except ValueError:
                    raise serializers.ValidationError({field: "Must be a valid integer"})
        
        return attrs

class ResumeProcessingTrackSerializer(serializers.ModelSerializer):

    user_type = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ResumeProcessingTrack
        fields = [
            "id",
            "event",

            # Resume data
            "email",
            "s3_url",
            "ats_score",

            # Processing
            "status",
            "error",
            "raw_ai_response",
            "task_id",

            # Mail tracking
            "mail_status",
            "mail_error",
            "mail_sent_at",

            # ✅ ADDED
            "user_type",
            "user_name",
            # Timestamps
            "created_at",
            "updated_at",
        ]

        read_only_fields = ["id", "created_at", "updated_at"]

    def get_user_type(self, obj):
        """
        Returns:
        - Hr / Interviewer / Interviewee / Admin if user exists
        - 'Not Registered' if email not found
        """
        if not obj.email:
            return None

        try:
            profile = UserProfile.objects.select_related("user").get(user__email=obj.email)
            return profile.user_type
        except UserProfile.DoesNotExist:
            return "Not Registered"
    
    def get_user_name(self, obj):
        """
        Returns:
        - Hr / Interviewer / Interviewee / Admin if user exists
        - 'Not Registered' if email not found
        """
        if not obj.email:
            return None

        try:
            profile = UserProfile.objects.select_related("user").get(user__email=obj.email)
            return profile.user.username
        except UserProfile.DoesNotExist:
            return "Not Registered"
            
class HRUserChattingSerializer(serializers.ModelSerializer):
    sender_type = serializers.SerializerMethodField()
    sender_name = serializers.SerializerMethodField()
    created_by_id = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = HRUserChatting
        fields = [
            "id",
            "message",
            "sender_type",
            "sender_name",
            "created_by_id",
            "created_by_name",
            "is_read",
            "created_at",
        ]

    def get_sender_type(self, obj):
        return "HR" if obj.created_by.user_type == "Hr" else "INTERVIEWEE"

    def get_sender_name(self, obj):
        return obj.created_by.user.username

    def get_created_by_id(self, obj):
        return obj.created_by.id

    def get_created_by_name(self, obj):
        return obj.created_by.user.username
