import sys
import os

# Ensure /app is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web_service import app as application
