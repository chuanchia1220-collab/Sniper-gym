import logging
import traceback
import os
from datetime import datetime

# Define log file path
LOG_FILE = "error_logs.txt"

# Configure logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_error(e, context="General Error"):
    """
    Logs an error with a timestamp, message, and stack trace.
    Args:
        e (Exception): The exception object.
        context (str): A brief description of where the error occurred.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_message = f"[{timestamp}] {context}: {str(e)}\n{traceback.format_exc()}"

    # Log to file
    logging.error(error_message)

    # Also print to console for development visibility
    print(f"ERROR LOGGED: {context} - {e}")
