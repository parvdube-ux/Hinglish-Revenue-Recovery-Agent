import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# API Credentials
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Stopping & Compliance Rules (Configurable, NOT magic numbers)
MAX_OUTBOUND_MESSAGES = int(os.getenv("MAX_OUTBOUND_MESSAGES", 3))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RECOVERY_TIMEOUT_HOURS = int(os.getenv("RECOVERY_TIMEOUT_HOURS", 24))

# Business Parameters
DEFAULT_CURRENCY = "INR"
MAX_DYNAMIC_DISCOUNT_PERCENT = 10  # Maximum discount the agent is allowed to offer (e.g. 10%)

# Helper properties to determine run state
def is_razorpay_configured() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)

def is_gemini_configured() -> bool:
    return bool(GEMINI_API_KEY)
