# Questions and expected answers for the live RAG demo

Upload the two documents of this folder, not this file (it holds the answers), on the **Documents** page of the
UnifAI **Personal** workspace. Wait until their status is **Done**, then ask the questions in your personal workflow
`<user>-my-documents` (for example `consultant-01-my-documents`). Each answer must cite the document.

Do not use a team workflow `<team>-rag` (for example `consultant-rag`) for these questions. It runs as the team, so it
never finds a member's personal uploads: asked these questions, it must answer that the documents do not say. The
full scenario is [UnifAI live RAG](../unifai-live-rag.md).

| Question | Expected answer | Document |
|---|---|---|
| What is the hotel ceiling in Paris? | 185 EUR per night | travel-and-expense-policy.md |
| Which code goes on a rental car booking? | ZN-CAR-7 | travel-and-expense-policy.md |
| When does the on-call week start? | Tuesday at 09:30 | on-call-rota-handbook.md |
| What is the name of the SEV-1 bridge? | Kestrel | on-call-rota-handbook.md |
| How much does a night with a call-out pay? | 65 EUR, on top of the 420 EUR weekly flat rate | on-call-rota-handbook.md |

A question outside the documents (for example "What is the hotel ceiling in Madrid?") must get "the documents do not say".
