# Presenting Interview Prep Crew (about 5 minutes)

## Before you start
- Double-click **Interview Prep Crew** on the Desktop. It opens in the browser (if port 8010 is busy, the console shows the port it used instead). The badge in the top right shows the model (red means it is not configured).
- Do one practice run before you present, to check the API key and the venue's internet.
- No internet at the venue? Switch `.env` to the local Ollama model (slower, about 6 minutes per run on a laptop CPU).

## Walkthrough

1. **The problem (30 s).** Interview prep means researching the company, understanding the role, guessing questions and practising answers. That is four different jobs, so we built four specialist agents.
2. **Start a run (15 s).** Type a company and role and press **Run crew**. The four cards are the crew, in order.
3. **Company Researcher (60 s).** Point at the card turning blue (thinking) and orange (using a tool). In **Activity**, open a `web_search` entry and show the exact query the agent chose and the results it got back. *The agent decides what to search, not us.*
4. **Handoff (30 s).** When the card turns green, the arrow lights up and the Role Analyst gets "Handoff from Company Researcher". *CrewAI passes each task's output to the next agent as context.*
5. **Role Analyst → Question Generator → Answer Coach (60 s).** Click a card to filter the feed to that agent. Show the streamed text of an LLM call and the **Task prompt** CrewAI built for the agent.
6. **Result (60 s).** Walk through the **Prep pack** tabs: Company Brief (with sources), Role Analysis, Likely Questions, Answer Coaching. Download it as Markdown.

## Likely questions

- **Why several agents instead of one prompt?** Each agent has one focused job, its own tools and its own instructions. Later agents work from verified research, which gives more specific and less made-up answers. It is also easy to add an agent (for example a mock interviewer).
- **How do agents communicate?** CrewAI sequential process: every task lists the earlier tasks as `context`, so their outputs are inserted into the next agent's prompt.
- **How do you show what agents are doing?** We subscribe to CrewAI's event bus (LLM calls, streamed tokens, tool usage, task completion) and stream those events to the browser with Server-Sent Events.
- **How do you limit hallucination?** The researchers must use search tools and report "not found" when they cannot verify something. Recent news includes source links.
- **Which model?** Any CrewAI-supported model, set in `.env`: Groq or Claude via API, or a local Ollama model for free and offline runs.
- **How is it tested?** 79 automated tests. They run the real crew with a scripted fake LLM and fake search, so the whole pipeline is tested in seconds without network or API costs.
