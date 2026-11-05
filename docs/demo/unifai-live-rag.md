# Showing the UnifAI RAG working live

How to show, in front of an audience, that UnifAI's RAG ingests content and answers from it (WP-200, ADR-0598). There are
two parts:

- **A document upload**, which takes about two minutes.
- **A Confluence resync**, which takes about five minutes for 90 pages.

## Before you start

- **The stack.** Use `unifai-ui-zuno-unifai` on demo333, signed in as **consultant-01**.
- **The workflow: `<user>-my-documents`, in the Personal workspace** (`consultant-01-my-documents`). It runs as you, so
  its retriever searches:
  - the documents **you** uploaded;
  - the Confluence sources that your groups can read (forwarded token).
- **Not the team's `<team>-rag`.** A team workflow runs as the team. It finds the Confluence pages of your groups, but
  never your personal uploads: asked about them, it answers that the documents do not say. A teammate therefore never
  gets your uploads in their own answers.
- **The "RAG Overview" page counts only Slack and Document sources.** That is how the upstream UI works. Confluence and
  web content is indexed but not counted, so a 0 there is not an outage. Read a Confluence or web source's state in its
  `UnifaiRAGSource` status (step 2.3).

## 1. Upload a document and ask about it

1. In the **Personal** workspace, open **Documents** in the sidebar and upload the two files from
   [unifai-rag-upload/](unifai-rag-upload/) (not `questions.md`):
   - `travel-and-expense-policy.md`;
   - `on-call-rota-handbook.md`.
2. Wait until both are **ready**. Behind the scenes:
   - docling converts them;
   - qwen3-embedding (KServe) embeds them;
   - Qdrant stores them.
3. Still in **Personal**, open the workflow `consultant-01-my-documents` and ask the questions of
   [questions.md](unifai-rag-upload/questions.md).
   - Every answer cites its document.
   - A question the documents do not cover gets "the documents do not say".
4. Optional, for isolation:
   - ask the team's `consultant-rag` the same question: it does not find your personal upload;
   - sign in as **sale-01** and ask `sale-01-my-documents`: sale-01 gets no answer from consultant-01's uploads.

## 2. Resync a Confluence source on demand

Two sources sync every 6 hours, both scoped to the `consultant/confluence-*` groups: `tekos-satellite` and
`tekos-openshift`.

1. **Edit a page** in the SXSI space (`Technologie : Satellite`). Note a word that only the new version contains.
2. **Request a sync.** Set or change `resyncToken` on the source in `ansible/clusters/demo333.yml`, under
   `zuno_unifai_values.ragSources`. Then push and run `make d2 install unifai`.

   ```yaml
   - name: tekos-satellite
     resyncToken: demo-2026-11-05-1   # any new value queues a sync at once
   ```

   Do not `oc patch` the object. ArgoCD selfHeal reverts the change, which changes the hash again and queues a second
   sync.
3. **Follow the sync.** Run:

   ```sh
   oc get unifairagsource tekos-satellite -n zuno-unifai -w \
     -o custom-columns=PHASE:.status.phase,PIPELINE:.status.pipelineStatus,MSG:.status.message
   ```

   The message ends with `N pages (1 changed, 0 deleted at the last sync)`.
4. **Ask about the new word** in `consultant-rag` or `consultant-01-my-documents`. The answer quotes the edited page.

## If something goes wrong

- **An upload stays in processing.** Check the logs of `docling-serve`, `unifai-rag-celery` and `unifai-rag-server` in
  `zuno-unifai`.
- **No passage comes back.**
  - Check that the retriever's threshold (0.3) is not filtering everything out.
  - Check that the user is in the source's `aclGroups`, through the `groups` claim of the token.
