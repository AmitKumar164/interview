from rest_framework import serializers

def is_required(value):
    if value is None:
        raise serializers.ValidationError("This field is required.")
    return value


def in_number_array(allowed_values):
    """Validate if value is in allowed number array"""
    def validator(value):
        if value is not None and value not in allowed_values:
            raise serializers.ValidationError(f"Value must be one of {allowed_values}")
        return value
    return validator

def is_between(min_val, max_val):
    """Validate if value is between min and max"""
    def validator(value):
        if value is not None and not (min_val <= value <= max_val):
            raise serializers.ValidationError(f"Value must be between {min_val} and {max_val}")
        return value
    return validator

def is_length_less_than(max_length):
    """Validate if string length is less than max_length"""
    def validator(value):
        if value is not None and len(str(value)) >= max_length:
            raise serializers.ValidationError(f"Length must be less than {max_length}")
        return value
    return validator

def matches_string_array(allowed_values):
    """Validate if value is in allowed string array"""
    def validator(value):
        if value is not None:
            if isinstance(value, list):
                invalid_values = [v for v in value if v not in allowed_values]
                if invalid_values:
                    raise serializers.ValidationError(f"Invalid values: {invalid_values}. Allowed: {allowed_values}")
            else:
                if value not in allowed_values:
                    raise serializers.ValidationError(f"Value must be one of {allowed_values}")
        return value
    return validator
