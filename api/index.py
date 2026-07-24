import sys
import os

# Add the nimbus_insight directory to the python path so imports work on Vercel
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'nimbus_insight'))

from main import app
