import json
from fastapi import APIRouter, Cookie
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.auth import decode_user_id
from app.api.deps import get_embedding, get_llm, get_reranker
from app.retrieval.filters import build_where
from app.retrieval.search import search
from app.storage.ledger import Conversation, Message, session_scope

router = APIRouter()


class AskRequest(BaseModel):
    query: str
    conversation_id: int | None = None
    sources: list[str] | None = None
    subjects: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None


SYSTEM_PROMPT = (
    "You are a biomedical research assistant for a fixed corpus of preprint "
    "excerpts. Preprints are not peer-reviewed; treat them as primary sources, "
    "not established consensus.\n"
    "\n"
    "How to answer:\n"
    "- If the excerpts contain relevant information, ground your answer in them. "
    "Every factual claim drawn from an excerpt ends with an inline citation in "
    "the form [DOI:<doi>]. If a claim draws from multiple excerpts, cite each.\n"
    "- If excerpts disagree, report the disagreement and cite each side.\n"
    "- If the excerpts only partially cover the question, answer the supported "
    "part with citations, and clearly mark the unsupported part as 'not covered "
    "by the retrieved excerpts' before adding any general context.\n"
    "- If the excerpts are unrelated or empty, you may still respond helpfully: "
    "say briefly that the corpus did not surface relevant papers, then offer a "
    "short general-knowledge answer if you have one, clearly prefaced with "
    "'Outside the corpus:'. Suggest 1–2 reformulated queries the user could try.\n"
    "- For conversational or meta questions ('what is this?', 'what can I ask?', "
    "'hello'), answer naturally without citations. You don't need to force "
    "paper references when none apply.\n"
    "\n"
    "Citations:\n"
    "- Only cite DOIs that appear in the provided excerpts — never fabricate or "
    "guess a DOI.\n"
    "- Excerpts often mention other studies by author name (e.g. 'Smith et al. "
    "2020 found...'). Those are references inside a retrieved paper, not papers "
    "you retrieved. Do NOT list them as separate findings and do NOT assign them "
    "a DOI. Summarise only what the retrieved excerpts themselves report.\n"
    "\n"
    "Style: direct and concise. Quote short phrases when wording matters "
    "(effect sizes, definitions).\n"
)

# ~12k chars leaves ample room for the system prompt + a full LLM response within
# most 8k-token context windows (1 token ≈ 4 chars).
_CONTEXT_BUDGET_CHARS = 12_000
_PER_PAPER_CHARS = 3_000


def _build_prompt(query: str, hits) -> str:
    # Group chunks by DOI so multiple excerpts from the same paper are presented
    # as one context block, preventing the LLM from treating each chunk as a
    # separate paper. Hits arrive sorted best-first; insertion order preserves that.
    seen: dict[str, dict] = {}
    for h in hits:
        if h.doi not in seen:
            seen[h.doi] = {"h": h, "texts": []}
        seen[h.doi]["texts"].append(h.text)

    blocks = []
    total = 0
    for doi, entry in seen.items():
        if total >= _CONTEXT_BUDGET_CHARS:
            break
        h = entry["h"]
        combined = "\n\n".join(entry["texts"])[:_PER_PAPER_CHARS]
        block = f"[DOI:{doi}] {h.title}\n{combined}"
        blocks.append(block)
        total += len(block)

    ctx = "\n\n---\n\n".join(blocks) if blocks else "(no relevant context found)"
    return f"Context:\n{ctx}\n\nQuestion: {query}\n\nAnswer with citations:"


@router.post("/ask")
async def ask(req: AskRequest, session_token: str | None = Cookie(default=None)):
    user_id = decode_user_id(session_token)
    embedding = get_embedding()
    reranker = get_reranker()
    llm = get_llm()

    where = build_where(
        sources=req.sources,
        subjects=req.subjects,
        date_from=req.date_from,
        date_to=req.date_to,
    )
    hits = search(req.query, embedding, reranker, where=where)
    prompt = _build_prompt(req.query, hits)
    retrieved = [{"doi": h.doi, "version": h.version} for h in hits]

    with session_scope() as s:
        if req.conversation_id is None:
            conv = Conversation(title=req.query[:80], user_id=user_id)
            s.add(conv)
            s.flush()
            conv_id = conv.id
        else:
            conv_id = req.conversation_id
        s.add(
            Message(
                conversation_id=conv_id,
                role="user",
                content=req.query,
                gen_model_id=llm.model_id,
                embedding_model_id=embedding.model_id,
                reranker_model_id=reranker.model_id,
                retrieved_doi_versions=retrieved,
            )
        )

    async def event_stream():
        yield {"event": "conversation", "data": json.dumps({"conversation_id": conv_id})}
        yield {"event": "hits", "data": json.dumps([h.to_dict() for h in hits])}

        collected: list[str] = []
        error: str | None = None
        try:
            async for tok in llm.stream(SYSTEM_PROMPT, prompt):
                collected.append(tok)
                yield {"event": "token", "data": tok}
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            yield {"event": "error", "data": json.dumps({"message": error})}
        yield {"event": "done", "data": ""}

        text = "".join(collected)
        with session_scope() as s:
            s.add(
                Message(
                    conversation_id=conv_id,
                    role="assistant",
                    content=text or f"[error: {error}]",
                    gen_model_id=llm.model_id,
                    embedding_model_id=embedding.model_id,
                    reranker_model_id=reranker.model_id,
                    retrieved_doi_versions=retrieved,
                )
            )

    return EventSourceResponse(event_stream())
