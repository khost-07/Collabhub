from datetime import datetime, timedelta
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

def to_ist_datetime(dt: datetime) -> str:
    if not dt:
        return ""
    # Add 5 hours and 30 minutes to get IST
    ist_dt = dt + timedelta(hours=5, minutes=30)
    return ist_dt.strftime('%b %d, %Y %H:%M')

def to_ist_date(dt: datetime) -> str:
    if not dt:
        return ""
    ist_dt = dt + timedelta(hours=5, minutes=30)
    return ist_dt.strftime('%b %d, %Y')

templates.env.filters["datetime_ist"] = to_ist_datetime
templates.env.filters["date_ist"] = to_ist_date
