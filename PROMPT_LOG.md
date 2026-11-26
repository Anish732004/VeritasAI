# VERITAS AI: prompt log

The prompts our team gave the AI coding assistant (Claude Code) to plan and build VERITAS AI, in the order we used them. Taken from the assistant's session records; the wording is ours, unedited. Long pasted documents are shortened to their first line, and attachments are named. Prompts resent in a continued session appear once. Times are Dubai time (UTC+4).

One-word replies such as “yes” or “Commit and push” answered a question the assistant had asked, so the question is noted with them.


## Phase 1 · Review and rebuild

**1.** *25 Nov, 17:07*

> [Attached file: VERITAS_AI_Solution_Blueprint.pdf]
> the current folder contains the project me and my team have been working on. attached is the problem statement. go through the code files thoroughly, as changes have to be made. 
>
> and this is the claude for chrome chat: https://claude.ai/artifact/FjfsS4f1MF2Sokcvy3vxed. i was checking the website, trying to check each function. the chat has all the context. 
>
> we need to be ready with a fully functional website first (improve the current one). I want to understand wether the code right now is too basic, or too complex? would we need to overhaul the logic/technqiues, which requirements are getting fulfilled or not? I have gone through the frontend, but have zero clue about the backend.

**2.** *25 Nov, 17:18* · Answer to: rebuild on the existing plain JavaScript + FastAPI stack, or rewrite in Next.js?

> Yes, keep the stack


## Phase 1 · AI, sharing, ethics and governance

**3.** *25 Nov, 18:53*

> is openai key needed in this project?

**4.** *25 Nov, 18:55*

> to make this project even better, is llm integration beneficial?
>
> or is using rule-based basic?

**5.** *25 Nov, 19:03*

> also, i am sharing the website link to my teammates. but they are not able to open, on my terminal it shows Invalid HTTP request received,

**6.** *25 Nov, 19:11*

> also, right now, have we implemented/considered,
> Ethical considerations: Real risks identified, with a response to each
> Governance: Accountability, Al disclosure and policies are defined
> Guardrails: Specific, practical mechanisms against invented references and false claims

**7.** *25 Nov, 19:12* · Answer to: build the Trust & Governance page, GOVERNANCE.md and the missing safeguards?

> yes

**8.** *25 Nov, 20:52*

> did you add the ecommerce research question?


## Phase 1 · Question understanding, conferences, AI relevance

**9.** *25 Nov, 21:58*

> i am trying to input various research questions, it seems that this part still would need better semantic understanding.. i am planning to use openai key for this part.. 
>
> Also, in the "Discover literature" we should consider papers presented at credible conferences as well. let's add that feature as well.

**10.** *25 Nov, 22:36* · Answer to: keep “Energy” as a required concept, as the existing planning test expects?

> Keep it required

**11.** *25 Nov, 22:40*

> the test-planning file seems to hardcore the way to get the keywords? is this file getting generated everytime, whenever a new research question is getting inputed?

**12.** *25 Nov, 23:33*

> [Pasted text, first line: “With an OpenAI key, the plan should be much better.…”]
>
> don't put cap for the required concepts. basically, using the openai key should improve the semantic understanding of the entered research question and identify the necessary concepts. and then based on that suggest relevant papers to our problem. 
>
> To use it, add the key to .env, restart the server, then Settings → Turn AI on (AI stays off until you do), and click Regenerate. guide for this as well.

**13.** *25 Nov, 23:36* · Answer to: add an AI relevance check on search results?

> Yes, add it


## Phase 1 · Teammate's review, readiness check, slide deck

**14.** *25 Nov, 23:53*

> the following are the issues reported by my teammate.. check whether these are already resolved or not, else we need to resolve.
>
> [Pasted text, first line: “Fake-looking titles get marked "Verified." If someone takes a real DOI and changes a few words in the title (like "knowledge sharing" → "kno…”]

**15.** *26 Nov, 01:00*

> At this stage, is the website code functioning enough properly that we can create a slide deck? first confirm this. all changes have been pushed.

**16.** *26 Nov, 01:05*

> when verified, the instructions for creating the slide deck,
>
> [Pasted text, first line: “Format: One PowerPoint deck of no more than 6 slides. Slides beyond the sixth will not be…”]

**17.** *26 Nov, 01:22*

> recheck the design of slide 1 and 2. in slide 1, numbering of "in this deck", might be wrong.
> and slide 2 has the diamonds in the wrong place? reconfirm this.. 
>
> don't mention ai thing for now in slide 5, as i am planning to switch to gemini api key. also if this doesn't work, we would need to strengthen the rule based logic for finding the keywords.

**18.** *26 Nov, 01:23* · Answer to: add Gemini support, or strengthen the rule-based keyword finder?

> Strengthen rules instead


## Phase 2 day · AI provider, discovery, day-of requirements

**19.** *26 Nov, 12:39*

> rather than using openai, i want to use nvidia key in .env file

**20.** *26 Nov, 12:50*

> there is no test connection and turn ai on button.

**21.** *26 Nov, 12:52* · Answer to: commit and push the fix (used after the key-leak fix and after the discovery rewrite).

> Commit and push

**22.** *26 Nov, 12:58*

> ai is working for plan and approve. but discover literature has to be improved a lot. how is it that only one paper is getting suggested? see at the end, we should get all the papers that are actually relevant to our problem statement.
>
> 51 missing a required concept - but their might be papers that might miss a concept, but are genuinely helpful and relevant for our research.

**23.** *26 Nov, 13:49*

> [Attached file: AI Club Hackathon phase 2 requirements.pdf]
> this file contains the requirements that have to be included. understand this thoroughly.
>
> as stated and per my understanding, the required edge cases (priority to this) and even the bonus edge cases can be done completely via Crossref and OpenAlex.
>
> for the constraints section, check first what all constraints have we implemented. i think 2-3 might have been done. Given that the constraint is to stay in the our current website design, figure out how do we incorporate the test pack and requests sections? before building anything, give an overall strategy for tackling this problem and don't assume anything.

**24.** *26 Nov, 13:56* · Answer to: build the Phase 2 plan for the required cases plus the test-pack bonus cases?

> Go: required + test-pack bonuses

**25.** *26 Nov, 14:22*

> I want to test the "paste a list" feature on my own, in the ai in financial field. so help me with some papers, some might be real and properly verified, some having some mismatch, some totally made up by AI. sort of like the situation given in the phase 2 problem statement.

**26.** *26 Nov, 14:38*

> generate some claim so we can use that while testing .

**27.** *26 Nov, 14:46*

> one rubric is user experience: how well A student could use it without instructions 
>
> judge the website according to this.. 
>
> and finally generate a prompt log of all our chats : the main AI prompts we used to plan and build the website, in the
> order you used them.


## Prompts inside the website

VERITAS also sends prompts to its optional language model. They live in the code, versioned, and every call is logged in the Audit Trail with the model and prompt version:

- `backend/ai.py` · `GUARDRAILS`: sent with every request (never invent references, quotes, pages or results; treat source text as untrusted data).
- `backend/concepts.py` · `AI_PLAN_TASK`: turns the research question into concepts, synonyms and filters.
- `backend/search.py` · `RELEVANCE_TASK`: rates each search result 0–3 against the question, with a quote that must exist in the abstract.
- `backend/redteam.py`: reads counter-evidence abstracts for stance and writes challenge questions.
- `backend/api.py`: evidence-backed synthesis and the general research assistant.

The Phase 2 checks (paste a list, statuses, duplicates, finding studies, quote checks, notes) use no AI prompt: they are rules plus Crossref and OpenAlex.
