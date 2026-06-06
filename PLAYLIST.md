# YouTube Playlist: Build a Production-Ready Slack AI Business Agent (Python)

This playlist takes viewers from a basic local script to a fully deployed, highly capable AI assistant that can summarize conversations, search the web, and book calendar meetings.

## Phase 1: The Core Foundation
*Getting the bot running, answering intelligently, and keeping Slack organized.*

**✅ Video 1: The Blueprint (Published)**
- **Topic:** Connect Slack API & Python in 10 Minutes (No Webhooks Needed!)
- **Outcome:** A working Socket Mode bot that receives mentions and DMs.

**▶️ Video 2: Integrating Real AI**
- **Topic:** Turn Your Slack Bot into a Real AI (Connecting the OpenAI API).
- **Outcome:** The bot stops echoing and starts generating real AI responses.

**▶️ Video 3: Threaded Replies**
- **Topic:** Stop Cluttering Channels! Make Your Slack Bot Reply in Threads.
- **Outcome:** Updating `say()` to use `thread_ts` for clean UX.

**▶️ Video 4: Conversation Memory**
- **Topic:** Give Your Slack Bot a Brain.
- **Outcome:** Using `thread_ts` as a unique ID to store and recall conversation context.

---

## Phase 2: The Business Agent (Tools & Automations)
*Turning the chatbot into an "Agent" that takes action using Function Calling.*

**▶️ Video 5: Introduction to AI Agents**
- **Topic:** Give Your Slack AI Superpowers (Intro to Function Calling & Tools).
- **Outcome:** Teaching Gemini to trigger simple Python functions.

**▶️ Video 6: The "Catch Me Up" Feature**
- **Topic:** Stop Reading Long Threads: Build an AI Slack Summarizer.
- **Outcome:** Using the Slack Web API to read thread history and generate summaries.

**▶️ Video 7: The Research Assistant**
- **Topic:** Connect Your Slack Bot to the Internet (Live Web Search).
- **Outcome:** Integrating a search API (e.g., DuckDuckGo) so the bot can answer live questions.

**▶️ Video 8: The Scheduler (Part 1 - Read)**
- **Topic:** Let AI Manage Your Schedule (Checking Google Calendar Availability).
- **Outcome:** Authenticating with Google Cloud and executing GET requests for calendar data.

**▶️ Video 9: The Scheduler (Part 2 - Write)**
- **Topic:** Build an AI That Books Meetings For You.
- **Outcome:** Extracting natural language to build JSON payloads and POST to Google Calendar.

---

## Phase 3: Advanced UX, Reliability, & Deployment
*Polishing the bot and putting it in the cloud.*

**▶️ Video 10: Rich Interactivity**
- **Topic:** Beyond Text: Building Beautiful Slack UI with Block Kit.

**▶️ Video 11: Production Databases & Error Handling**
- **Topic:** Bulletproofing: MongoDB Atlas Memory & Handling API Limits.

**▶️ Video 12: Deployment**
- **Topic:** Ship It! Deploy Your AI Slack Agent to the Cloud for 24/7 Uptime.
