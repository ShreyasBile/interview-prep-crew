# Presenting Interview Prep Crew (about 6 minutes)

The slides are in `docs/Interview_Prep_Crew_Presentation.pptx` (8 slides, with speaker notes). This page is the plan for the live demo.

## Before you start
- Double-click **Interview Prep Crew** on the Desktop. It opens in the browser (if port 8010 is busy, the console shows the port it used instead). The badge in the top right shows the model (red means it is not configured).
- Do one practice run of each feature before you present, to check the API key and the venue's internet.
- Have a resume ready as a PDF, DOCX or TXT. Use a sample or your own; it is never saved.
- No internet at the venue? Switch `.env` to the local Ollama model (slower, about 6 minutes per run on a laptop CPU). The ATS score still works instantly with no model at all.

## Walkthrough

1. **The problem (30 s).** Interview prep means researching the company, understanding the role, guessing questions and practising answers. Resumes also get filtered by an ATS you cannot see into. We built a crew of specialist agents for both. Open the **Dashboard**: counts, the ATS score trend and recent runs.
2. **Resume ATS (60 s).** Open **Resume ATS**, upload a resume and paste a job description. The score and the six-area breakdown appear instantly because they come from rules, not from a model. Point at the matched and missing keywords. *The score is deterministic, so the same resume always gets the same number.* Then show the **AI review** streaming in: ranked fixes and bullet rewrites that reuse only what is in the resume.
3. **Start an interview prep (15 s).** Open **Interview prep**, type a company and role, keep the resume attached and press run. The four cards are the crew, in order.
4. **Company Researcher (60 s).** Point at the card turning blue (thinking) and orange (using a tool). In **Activity**, open a `web_search` entry and show the exact query the agent chose and the results it got back. *The agent decides what to search, not us.*
5. **Handoff (30 s).** When the card turns green, the arrow lights up and the Role Analyst gets "Handoff from Company Researcher". *CrewAI passes each task's output to the next agent as context.*
6. **Role Analyst → Question Generator → Answer Coach (60 s).** Click a card to filter the feed to that agent. Show the streamed text of an LLM call and the **Task prompt** CrewAI built for the agent. Point out that where the resume would appear, the task prompt shows `[resume hidden: N words]`, because the resume is redacted from the activity log.
7. **Result (60 s).** Walk through the **Prep pack** tabs: Company Brief, Role Analysis, Likely Questions (find the ones marked **From your resume**), Answer Coaching. Open **Sources** to show the links behind the research. Download the pack as Markdown.
8. **History and Agents (20 s).** Open **History** to show saved runs with search and filter, then the **Agents** page for who does what. Toggle the dark theme if there is time.

## Likely questions

- **Why several agents instead of one prompt?** Each agent has one focused job, its own tools and its own instructions. Later agents work from verified research, which gives more specific and less made-up answers. It is also easy to add an agent (for example a mock interviewer).
- **How do agents communicate?** CrewAI sequential process: every task lists the earlier tasks as `context`, so their outputs are inserted into the next agent's prompt.
- **How do you show what agents are doing?** We subscribe to CrewAI's event bus (LLM calls, streamed tokens, tool usage, task completion) and stream those events to the browser with Server-Sent Events.
- **How do you limit hallucination?** The researchers must use search tools and report "not found" when they cannot verify something, and recent news includes source links. The resume reviewer may only rewrite bullets that exist and writes `[add metric]` instead of inventing a number.
- **How is the ATS score calculated?** By deterministic rules over six areas: keyword match (only with a job description), sections, contact info, impact, formatting and language. It is a heuristic, because ATS vendors publish no rules and there is no public benchmark. We say so on the slides.
- **Is my resume stored?** No. It lives in the browser page's memory and is sent to your own server and the model you configured, so Groq or Claude receives it. It is redacted from the activity log and from saved history.
- **Which model?** Any CrewAI-supported model, set in `.env`: Groq or Claude via API, or a local Ollama model for free and offline runs.
- **How is it tested?** 155 automated tests. They run the real crew with a scripted fake LLM and fake search, so the whole pipeline is tested in seconds without network or API costs. A separate opt-in live test runs the crew once against the real model.
- **What are the limitations?** The ATS rules are a heuristic and have not been checked against real ATS software, results depend on web search and model quality, and it has not been tried by real candidates yet. Future scope: a mock interview that scores your answers, a model comparison and user study, a fact-checker agent and Docker deployment.
