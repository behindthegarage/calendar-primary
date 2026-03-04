# Calendar Skill — Example Interactions

> Real-world examples of calendar intent detection and handling.

---

## ✅ Creating Events

### Example 1: Simple Meeting

**User:** "I have a meeting Thursday at 10"

**Detection:**
- Intent: `add_event`
- Confidence: HIGH (0.92)
- Parsed: title="Meeting", date="2026-03-06" (Thursday), time="10:00", category="Work"

**Action:** Auto-add (HIGH confidence)

**Response:**
> ✅ Added "Meeting" to your calendar for Thursday at 10:00 AM (Work).

---

### Example 2: Lunch with Context

**User:** "Lunch with John tomorrow at noon"

**Detection:**
- Intent: `add_event`
- Confidence: MEDIUM (0.78)
- Parsed: title="Lunch with John", date="2026-03-05" (tomorrow), time="12:00", category="Personal"

**Action:** Add with category note

**Response:**
> ✅ Added "Lunch with John" for tomorrow at noon. I categorized it as Personal — let me know if that's wrong.

---

### Example 3: Staff Training

**User:** "Remind me about staff training next Tuesday at 2"

**Detection:**
- Intent: `add_event`
- Confidence: HIGH (0.88)
- Parsed: title="Staff training", date="2026-03-10" (next Tuesday), time="14:00", category="Staff"

**Action:** Auto-add

**Response:**
> ✅ Added "Staff training" to your calendar for next Tuesday at 2:00 PM (Staff).

---

### Example 4: All-Day Event

**User:** "I'm taking a personal day Friday"

**Detection:**
- Intent: `add_event`
- Confidence: MEDIUM (0.72)
- Parsed: title="Personal day", date="2026-03-07" (Friday), all_day=True, category="Personal"

**Action:** Add with note

**Response:**
> ✅ Added "Personal day" for Friday (all day). I marked it as Personal — correct me if that's wrong.

---

### Example 5: Ambiguous Time (Clarification Needed)

**User:** "I have something Wednesday"

**Detection:**
- Intent: `add_event` (inferred)
- Confidence: LOW (0.45)
- Parsed: date="2026-03-11" (Wednesday), time=None, title=None

**Action:** Ask for clarification (don't add yet)

**Response:**
> I heard "Wednesday" — what time, and what's the event?

**User:** "Oh right, it's a dentist appointment at 3"

**Action:** Now parse and add

**Response:**
> ✅ Added "Dentist appointment" for Wednesday at 3:00 PM (Personal).

---

## 🔍 Querying Events

### Example 1: Today's Schedule

**User:** "What's on my calendar today?"

**Detection:**
- Intent: `query_events`
- Confidence: HIGH (0.95)
- Parsed: date_range="today"

**Action:** Query and format

**Response:**
> 📅 **Today (March 4)**
> • 10:00 AM — Director meeting (Work)
> • 2:30 PM — Staff training (Staff)
> • 4:00 PM — Pick up kids (Personal)

---

### Example 2: Empty Day

**User:** "Do I have anything tomorrow?"

**Detection:**
- Intent: `query_events`
- Confidence: HIGH (0.93)
- Parsed: date_range="tomorrow"

**Action:** Query and format

**Response:**
> 📅 Nothing on your calendar for tomorrow. You're free!

---

### Example 3: Weekly Overview

**User:** "What does my week look like?"

**Detection:**
- Intent: `query_events`
- Confidence: HIGH (0.90)
- Parsed: date_range="this_week"

**Action:** Query and group by day

**Response:**
> 📅 **This Week**
> 
> **Tuesday, March 4**
> • 10:00 AM — Director meeting (Work)
> 
> **Wednesday, March 5**
> • 9:00 AM — Budget review (Work)
> • 2:00 PM — CPR training (Staff)
> 
> **Thursday, March 6**
> • 3:00 PM — Field trip permission deadline (Deadlines)
> 
> **Friday, March 7**
> • All day — Personal day (Personal)

---

### Example 4: Category Filter

**User:** "Any deadlines coming up?"

**Detection:**
- Intent: `query_events`
- Confidence: HIGH (0.87)
- Parsed: category="Deadlines", date_range="upcoming"

**Action:** Query with filter

**Response:**
> 📅 **Upcoming Deadlines**
> • Thursday — Field trip permission deadline (Deadlines)
> • Monday, March 10 — Staff evaluation forms due (Deadlines)
> • Friday, March 14 — License renewal paperwork (Deadlines)

---

## ✏️ Modifying Events

### Example 1: Move by Time

**User:** "Move my 2pm to 3pm"

**Detection:**
- Intent: `update_event`
- Confidence: HIGH (0.85)
- Parsed: find_time="14:00", new_time="15:00", date="today"

**Action:** Find event at 2pm, move to 3pm

**Response:**
> ✅ Moved "Staff training" from 2:00 PM to 3:00 PM today.

---

### Example 2: Move by Name

**User:** "Reschedule the director meeting to Thursday"

**Detection:**
- Intent: `update_event`
- Confidence: HIGH (0.88)
- Parsed: search="director meeting", new_date="2026-03-06" (Thursday)

**Action:** Search and update

**Response:**
> ✅ Moved "Director meeting" from Tuesday to Thursday. Time still 10:00 AM — correct?

---

### Example 3: Change Time and Date

**User:** "Can we make the lunch meeting next week instead? Say Wednesday at 12:30"

**Detection:**
- Intent: `update_event`
- Confidence: MEDIUM (0.75)
- Parsed: search="lunch meeting", new_date="2026-03-12" (next Wednesday), new_time="12:30"

**Action:** Search, update, confirm details

**Response:**
> ✅ Updated "Lunch meeting" to next Wednesday, March 12 at 12:30 PM. Let me know if I got that wrong.

---

## 🗑️ Canceling Events

### Example 1: Simple Cancel

**User:** "Cancel lunch tomorrow"

**Detection:**
- Intent: `delete_event`
- Confidence: HIGH (0.86)
- Parsed: search="lunch", date="tomorrow"

**Action:** Find and delete

**Response:**
> 🗑️ Cancelled "Lunch with John" for tomorrow at noon.

---

### Example 2: Cancel by Time

**User:** "I can't make it at 3, delete that"

**Detection:**
- Intent: `delete_event`
- Confidence: HIGH (0.82)
- Parsed: time="15:00", date="today"

**Action:** Find event at 3pm and delete

**Response:**
> 🗑️ Cancelled "Staff check-in" for today at 3:00 PM.

---

### Example 3: Ambiguous Cancel (Multiple Matches)

**User:** "Cancel the meeting"

**Detection:**
- Intent: `delete_event`
- Confidence: MEDIUM (0.65)
- Parsed: search="meeting", date=None

**Action:** Find matches, ask for clarification

**Response:**
> I found 3 meetings:
> 1. "Director meeting" — today at 10:00 AM
> 2. "Staff meeting" — Thursday at 2:00 PM
> 3. "Budget meeting" — next Monday at 9:00 AM
> 
> Which one should I cancel? (Say "all" to cancel all three, or 1/2/3)

**User:** "Just the one today"

**Response:**
> 🗑️ Cancelled "Director meeting" for today at 10:00 AM.

---

## ⚠️ Ambiguous Cases

### Example 1: Missing Time

**User:** "I have a dentist appointment Thursday"

**Detection:**
- Intent: `add_event`
- Confidence: LOW (0.48)
- Parsed: title="Dentist appointment", date="2026-03-06" (Thursday), time=None

**Action:** Ask for time rather than guess

**Response:**
> I heard "dentist appointment Thursday" — what time?

**User:** "Oh, 2:30"

**Response:**
> ✅ Added "Dentist appointment" for Thursday at 2:30 PM (Personal).

---

### Example 2: Missing Date

**User:** "Meeting at 3pm"

**Detection:**
- Intent: `add_event`
- Confidence: MEDIUM (0.62)
- Parsed: title="Meeting", time="15:00", date=None

**Action:** Assume today, but ask to confirm

**Response:**
> You said "meeting at 3pm" — is that today?

**User:** "Yes"

**Response:**
> ✅ Added "Meeting" for today at 3:00 PM (Work).

---

### Example 3: Vague Description

**User:** "I need to remember to call someone"

**Detection:**
- Intent: `add_event` (inferred)
- Confidence: LOW (0.35)
- Parsed: title=None, date=None, time=None, action="remember"

**Action:** Ask for specifics

**Response:**
> I can add a reminder. Who do you need to call, and when?

**User:** "The insurance company, tomorrow morning"

**Response:**
> ✅ Added "Call insurance company" for tomorrow at 9:00 AM (Personal). Adjust the time if needed.

---

### Example 4: Past Tense (Ignore)

**User:** "I had a meeting yesterday that ran long"

**Detection:**
- Intent: None (past tense)
- Confidence: LOW (0.15)
- Parsed: past_tense=True, date="yesterday"

**Action:** Note for context, don't add to calendar

**Response:**
> (No calendar action — past tense detected)

---

### Example 5: Third Party (Ask if Relevant)

**User:** "John has a dentist appointment Friday"

**Detection:**
- Intent: None (third party)
- Confidence: LOW (0.25)
- Parsed: subject="John", third_party=True

**Action:** Ask if it's relevant to Adam's calendar

**Response:**
> Is John's dentist appointment something you need on your calendar too? (For coverage or carpool, maybe?)

**User:** "No, just making conversation"

**Response:**
> Got it, no problem!

---

## 🔄 Complex Interactions

### Example 1: Create + Query Chain

**User:** "Add a meeting Friday at 2. Actually, what do I have that day first?"

**Detection:**
- Intent sequence: `add_event` → `query_events`
- Confidence: HIGH for both

**Action:** Execute in order

**Response:**
> 📅 **Friday, March 7**
> • 10:00 AM — Budget review (Work)
> • All day — Personal day (Personal)
> 
> You already have a personal day scheduled. Want me to add the 2:00 PM meeting anyway?

**User:** "Yes, it's work-related"

**Response:**
> ✅ Added "Meeting" for Friday at 2:00 PM (Work).

---

### Example 2: Contextual Reference

**User:** "What's on my calendar?" (Monday morning)

**Response:**
> 📅 **Today (March 3)**
> • 2:00 PM — Staff meeting (Work)

**User:** "Move that to Wednesday"

**Detection:**
- Intent: `update_event`
- Confidence: HIGH (0.90)
- Parsed: reference="that" (last mentioned event), new_date="Wednesday"

**Action:** Resolve "that" to previous event, update

**Response:**
> ✅ Moved "Staff meeting" from today to Wednesday at 2:00 PM.

---

### Example 3: Natural Conversation Flow

**User:** "I'm thinking about visiting my sister this weekend"

**Detection:**
- Intent: `add_event` (inferred from context)
- Confidence: LOW (0.40)
- Parsed: tentative=True, title="Visit sister", date="this weekend"

**Action:** Ask for confirmation

**Response:**
> Sounds nice! Do you want me to block that time on your calendar?

**User:** "Not yet, still figuring out if I can get coverage"

**Response:**
> Got it. Just let me know when you want me to add it — I can block the whole weekend or just the days you'll be gone.

---

## 🎯 Edge Cases

### Example 1: Recurring Event

**User:** "I have staff meetings every Tuesday at 10 starting next week"

**Detection:**
- Intent: `add_event`
- Confidence: HIGH (0.88)
- Parsed: recurring=True, frequency="weekly", day="Tuesday", time="10:00", start="next week"

**Action:** Create with RRULE

**Response:**
> ✅ Added recurring "Staff meeting" every Tuesday at 10:00 AM starting March 11 (Work). 
> 📅 Next 3 occurrences: March 11, 18, 25.

---

### Example 2: Multiple Events Same Day

**User:** "I need to add three things: staff training at 9, a meeting at 11, and lunch at 1"

**Detection:**
- Intent: `add_event` (batch)
- Confidence: HIGH (0.91)
- Parsed: 3 separate events

**Action:** Parse all, add all

**Response:**
> ✅ Added 3 events for today:
> • 9:00 AM — Staff training (Staff)
> • 11:00 AM — Meeting (Work)
> • 1:00 PM — Lunch (Personal)

---

### Example 3: Unclear Category

**User:** "Meeting with the licensing person Thursday"

**Detection:**
- Intent: `add_event`
- Confidence: MEDIUM (0.70)
- Parsed: title="Meeting with licensing person", date="Thursday"
- Category candidates: "Work" (meeting), "Deadlines" (licensing)

**Action:** Add with best guess + note

**Response:**
> ✅ Added "Meeting with licensing person" for Thursday (Work). 
> 🤔 I wasn't sure if this is about a deadline — want me to change the category?

---

## 📋 Quick Reference Card

| Pattern | Confidence | Action |
|---------|------------|--------|
| "X at Y time on Z date" | HIGH | Auto-add |
| "remind me to..." | HIGH | Auto-add |
| "what's on my calendar" | HIGH | Query + format |
| "move/cancel/reschedule..." | HIGH | Find + modify |
| "X tomorrow/next week" | MEDIUM | Add + note |
| "I have something..." | LOW | Ask for details |
| Past tense | LOW | Ignore |
| Third party | LOW | Ask if relevant |

---

*Remember: Parse liberally, confirm lightly. Better false positives than misses.*
