# Video 2: Main flowchart

Mermaid source for the AI response, threaded reply, and memory flow. Regenerate
[`flowchart.svg`](flowchart.svg) after edits.

This keeps the Video 2 AI split visible while adding the current runtime steps
for Slack thread replies and MongoDB Atlas memory.

```mermaid
flowchart LR
    user["Slack user"] --> slack["Slack workspace"]
    slack <-->|Socket Mode events| socket["SocketModeHandler"]
    socket --> main["main.py<br/>Bolt handlers"]

    main --> route["Route event<br/>app_mention or DM"]
    route --> clean["Clean user text<br/>strip bot mention for channel"]
    route --> target["Resolve reply target<br/>channel: thread_ts or ts<br/>DM: existing thread_ts only"]
    target --> memory["MongoDB Atlas memory<br/>load turns by thread or DM key"]
    clean --> ai["ai_handler.py<br/>generate_ai_reply(text, history)"]
    memory --> ai

    env[".env<br/>OPENAI_API_KEY<br/>OPENAI_MODEL optional"] --> ai
    ai --> openai["OpenAI API<br/>Responses API"]
    openai --> ai
    ai --> say["_say_reply()<br/>say(text=reply, thread_ts?)"]
    target --> say
    say --> slack
    say --> save["Save user + assistant turns<br/>after Slack accepts reply"]
    save --> memory
```
