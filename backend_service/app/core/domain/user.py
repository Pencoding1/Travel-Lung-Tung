import phonenumbers
from typing import Dict
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator


class User(BaseModel):
    id: str = Field(..., alias="ID")
    dob: date 
    email: EmailStr
    phone_number: str = Field(..., alias="PhoneNumber")
    user_preference : Dict

    @field_validator("dob")
    @classmethod
    def validate_age(cls, v: date) -> date:
        today = date.today()
        dob_date = v
        
        age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
        
        if age < 18:
            raise ValueError(f"User must be 18 or older. Calculated age: {age}")
            
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            # Parse the number. (Assuming user includes country code like '+1')
            parsed_number = phonenumbers.parse(v)
            
            # Check if it's an actually valid number
            if not phonenumbers.is_valid_number(parsed_number):
                raise ValueError("Phone number is not valid.")
                
            # Return the fully cleaned, standard E.164 format
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            
        except phonenumbers.phonenumberutil.NumberParseException:
            raise ValueError("Could not parse phone number. Ensure it includes a country code.")