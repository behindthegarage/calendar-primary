#!/usr/bin/env python3
"""
ck_calendar/demo.py — Demo and test of calendar NLP system.

Run: python3 -m ck_calendar.demo
"""

import sys
sys.path.insert(0, '/home/openclaw/.openclaw/workspace')

from ck_calendar import detect_calendar_intent, parse_event, ParsedEvent
from datetime import datetime


def demo_intent_detection():
    """Demonstrate intent detection capabilities."""
    print("=" * 60)
    print("INTENT DETECTION DEMO")
    print("=" * 60)
    
    test_phrases = [
        "I have a meeting with Sarah tomorrow at 2pm",
        "What's on my calendar today?",
        "Move my 3pm to 4pm",
        "Lunch with John",
        "The meeting went well",
        "Remind me to call mom",
    ]
    
    for text in test_phrases:
        result = detect_calendar_intent(text)
        print(f"\n📝 \"{text}\"")
        print(f"   Intent: {result.suggested_action}")
        print(f"   Confidence: {result.confidence:.0%}")
        print(f"   Calendar mention: {result.is_calendar_mention}")
        if result.detected_time_refs:
            print(f"   Time refs: {result.detected_time_refs}")
        if result.detected_event_keywords:
            print(f"   Event keywords: {result.detected_event_keywords}")


def demo_event_parsing():
    """Demonstrate natural language event parsing."""
    print("\n" + "=" * 60)
    print("EVENT PARSING DEMO")
    print("=" * 60)
    print("(Note: Requires KIMI_API_KEY environment variable)")
    print()
    
    test_events = [
        "Team meeting tomorrow at 3pm for 1 hour",
        "Lunch with Sarah next Tuesday at noon",
        "Weekly standup every Monday at 9am",
        "Doctor appointment March 15th at 2:30pm",
    ]
    
    import os
    if not os.environ.get('KIMI_API_KEY'):
        print("⚠️  KIMI_API_KEY not set - LLM parsing demo skipped")
        print("   Set KIMI_API_KEY to enable full parsing")
        return
    
    for text in test_events:
        print(f"\n📝 Input: \"{text}\"")
        try:
            event = parse_event(text)
            print(f"   Title: {event.title}")
            print(f"   Start: {event.start_time}")
            if event.end_time:
                print(f"   End: {event.end_time}")
            if event.category:
                print(f"   Category: {event.category}")
            print(f"   Confidence: {event.confidence:.0%}")
            if event.is_recurring:
                print(f"   Recurring: {event.recurrence_rule}")
        except Exception as e:
            print(f"   Error: {e}")


def demo_parsed_event_structure():
    """Demonstrate ParsedEvent data structure."""
    print("\n" + "=" * 60)
    print("PARSED EVENT STRUCTURE DEMO")
    print("=" * 60)
    
    # Create a sample event
    event = ParsedEvent(
        title="Team Standup",
        start_time=datetime(2026, 3, 5, 9, 0),
        end_time=datetime(2026, 3, 5, 9, 30),
        category="work",
        is_recurring=True,
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
        confidence=0.95,
        raw_text="Team standup every Mon/Wed/Fri at 9am",
        ambiguity_notes=[]
    )
    
    print("\n📅 Parsed Event:")
    print(f"   Title: {event.title}")
    print(f"   Start: {event.start_time}")
    print(f"   End: {event.end_time}")
    print(f"   Category: {event.category}")
    print(f"   Recurring: {event.is_recurring}")
    print(f"   RRULE: {event.recurrence_rule}")
    print(f"   Confidence: {event.confidence}")
    
    print("\n📊 to_event() output (for database):")
    db_event = event.to_event(user_id="adam")
    for key, value in db_event.items():
        print(f"   {key}: {value}")
    
    print("\n📝 Human-readable summary:")
    print(event.summary())


if __name__ == "__main__":
    demo_intent_detection()
    demo_event_parsing()
    demo_parsed_event_structure()
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
