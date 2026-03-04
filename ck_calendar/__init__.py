"""
calendar/__init__.py — Calendar NLP module.

Wave 1b of the Calendar Primary project.

This module provides natural language parsing and intent detection
for the Kinawa Command Center Calendar system.
"""

from ck_calendar.parsed_event import ParsedEvent, IntentResult, ParseSuggestion
from ck_calendar.nlp_parser import parse_event, batch_parse, suggest_clarification
from ck_calendar.intent_detector import (
    detect_calendar_intent,
    is_likely_event,
    is_query,
    is_modify,
    should_prompt_confirmation
)

__all__ = [
    # Data structures
    'ParsedEvent',
    'IntentResult',
    'ParseSuggestion',
    # Parser
    'parse_event',
    'batch_parse',
    'suggest_clarification',
    # Intent detection
    'detect_calendar_intent',
    'is_likely_event',
    'is_query',
    'is_modify',
    'should_prompt_confirmation',
]
