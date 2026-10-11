"""Settings for Sky Quest. Fill in your observing location before a real run."""

# Replace None with your location's decimal coordinates.
LATITUDE = 8.1833
LONGITUDE = 77.4119

TIMEZONE = "Asia/Kolkata"
MODEL_NAME = "gemma3:1b"
PERSONA = "calm"  # Choose: calm, coach, precise, or quiet.

# Tune the astronomy-based score. Planet points reach their maximum at 90 degrees.
JUPITER_MAX_SCORE = 10.0
SATURN_MAX_SCORE = 10.0
MOON_MAX_PENALTY = 8.0
ISS_PASS_BONUS = 8.0

# Night scoring uses 15-minute slots and chooses the best consecutive 60 minutes.
SCORING_SLOT_MINUTES = 15
BEST_WINDOW_MINUTES = 60
SCORING_DURATION_HOURS = 3
