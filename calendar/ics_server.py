"""ICS HTTP server for calendar subscriptions.

Provides HTTP endpoints for calendar clients to subscribe to calendar feeds.
Supports category filtering, date ranges, and proper ICS format headers.

Usage:
    # Run standalone
    python -m calendar.ics_server
    
    # Or import and mount in another Flask app
    from calendar.ics_server import create_app
    app = create_app()
"""

from __future__ import annotations

import os
import re
from datetime import datetime, date, timedelta
from typing import Any

from flask import Flask, request, Response, jsonify

from .calendar_api import get_events
from .ics_export import export_events, generate_icalendar
from .models import Event


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5005
DEFAULT_CACHE_MINUTES = 15

# Simple token auth (for MVP - can be extended to proper auth)
API_TOKEN = os.environ.get("CALENDAR_API_TOKEN", None)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Register routes
    register_routes(app)
    
    return app


def register_routes(app: Flask) -> None:
    """Register all ICS export routes on the Flask app."""
    
    @app.route("/health")
    def health_check() -> Response:
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "ck-calendar-ics",
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route("/calendar/export.ics")
    def export_all_ics() -> Response:
        """Export all events as ICS.
        
        Query params:
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            category: Filter by single category
            categories: Filter by multiple categories (comma-separated)
            token: API token for authentication (optional)
        """
        # Auth check
        auth_error = _check_auth(request)
        if auth_error:
            return auth_error
        
        # Parse query params
        start, end = _parse_date_range(request)
        categories = _parse_categories(request)
        
        # Fetch events
        events = _fetch_events(start=start, end=end, categories=categories)
        
        # Generate ICS
        ics_content = export_events(events)
        
        # Return with proper headers
        return _ics_response(ics_content, filename="calendar.ics")
    
    @app.route("/calendar/<category>.ics")
    def export_category_ics(category: str) -> Response:
        """Export events for a specific category as ICS.
        
        Path params:
            category: Category name (e.g., 'Work', 'Personal')
            
        Query params:
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            token: API token for authentication (optional)
        """
        # Auth check
        auth_error = _check_auth(request)
        if auth_error:
            return auth_error
        
        # Parse query params
        start, end = _parse_date_range(request)
        
        # Fetch events for category
        events = _fetch_events(start=start, end=end, categories=[category])
        
        # Generate ICS
        ics_content = export_events(events)
        
        # Sanitize filename
        safe_category = re.sub(r'[^\w\-_.]', '_', category)
        filename = f"{safe_category}.ics"
        
        return _ics_response(ics_content, filename=filename)
    
    @app.route("/calendar/categories")
    def list_categories() -> Response:
        """List available categories."""
        from .db import get_db
        
        try:
            with get_db() as conn:
                cursor = conn.execute(
                    "SELECT DISTINCT category FROM events ORDER BY category"
                )
                categories = [row["category"] for row in cursor.fetchall()]
        except Exception:
            categories = []
        
        return jsonify({
            "categories": categories,
            "default_categories": [
                "Work",
                "Personal", 
                "Kids Club",
                "Staff",
                "Deadlines",
                "Projects/OpenClaw"
            ]
        })
    
    @app.route("/calendar/events.json")
    def export_json() -> Response:
        """Export events as JSON (alternative to ICS).
        
        Query params:
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            category: Filter by single category
            categories: Filter by multiple categories (comma-separated)
            token: API token for authentication (optional)
        """
        # Auth check
        auth_error = _check_auth(request)
        if auth_error:
            return auth_error
        
        # Parse query params
        start, end = _parse_date_range(request)
        categories = _parse_categories(request)
        
        # Fetch events
        events = _fetch_events(start=start, end=end, categories=categories)
        
        # Convert to JSON
        events_json = [event.to_dict() for event in events]
        
        response = jsonify({
            "events": events_json,
            "count": len(events_json),
            "filters": {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "categories": categories
            }
        })
        
        # Add cache headers
        response.headers["Cache-Control"] = f"private, max-age={DEFAULT_CACHE_MINUTES * 60}"
        
        return response


def _check_auth(request) -> Response | None:
    """Check authentication if API_TOKEN is configured.
    
    Returns None if authenticated, or a Response if auth failed.
    """
    if API_TOKEN is None:
        # No auth required
        return None
    
    # Check for token in query param or Authorization header
    token = request.args.get("token")
    
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if token != API_TOKEN:
        return Response(
            "Unauthorized",
            status=401,
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return None


def _parse_date_range(request) -> tuple[datetime | None, datetime | None]:
    """Parse start and end date from request query params.
    
    Returns:
        Tuple of (start_datetime, end_datetime) or (None, None)
    """
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    
    start = None
    end = None
    
    if start_str:
        try:
            start_date = date.fromisoformat(start_str)
            start = datetime.combine(start_date, datetime.min.time())
        except ValueError:
            pass
    
    if end_str:
        try:
            end_date = date.fromisoformat(end_str)
            end = datetime.combine(end_date, datetime.max.time().replace(microsecond=0))
        except ValueError:
            pass
    
    # Default range: now to 90 days in future
    if start is None:
        start = datetime.now()
    if end is None:
        end = start + timedelta(days=90)
    
    return start, end


def _parse_categories(request) -> list[str] | None:
    """Parse category filter from request query params.
    
    Handles both 'category' (single) and 'categories' (comma-separated).
    Returns None if no category filter specified.
    """
    # Check for single category
    single = request.args.get("category")
    if single:
        return [single.strip()]
    
    # Check for multiple categories
    multiple = request.args.get("categories")
    if multiple:
        return [c.strip() for c in multiple.split(",") if c.strip()]
    
    return None


def _fetch_events(
    start: datetime | None = None,
    end: datetime | None = None,
    categories: list[str] | None = None
) -> list[Event]:
    """Fetch events from calendar API with optional filters.
    
    Args:
        start: Start datetime filter
        end: End datetime filter
        categories: List of categories to include (None = all)
        
    Returns:
        List of Event objects
    """
    if categories and len(categories) == 1:
        # Single category
        return get_events(start=start, end=end, category=categories[0])
    elif categories and len(categories) > 1:
        # Multiple categories - fetch all and filter
        # Note: calendar_api.get_events doesn't support multiple categories yet
        # So we fetch all and filter manually
        all_events = get_events(start=start, end=end)
        return [e for e in all_events if e.category in categories]
    else:
        # No category filter
        return get_events(start=start, end=end)


def _ics_response(ics_content: str, filename: str = "calendar.ics") -> Response:
    """Create a Flask Response with proper ICS headers.
    
    Args:
        ics_content: The ICS file content
        filename: Filename for the download
        
    Returns:
        Flask Response with proper content-type and cache headers
    """
    response = Response(
        ics_content,
        mimetype="text/calendar",
        headers={
            "Content-Type": "text/calendar; charset=utf-8",
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": f"private, max-age={DEFAULT_CACHE_MINUTES * 60}",
            "X-Content-Type-Options": "nosniff",
        }
    )
    
    return response


def main() -> None:
    """Run the ICS server as a standalone application."""
    import argparse
    
    parser = argparse.ArgumentParser(description="CK Calendar ICS Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind to (default: {DEFAULT_PORT})")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()


__all__ = [
    "create_app",
    "register_routes",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
]