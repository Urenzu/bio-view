import json
import re
from fastapi import APIRouter, Cookie
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.auth import decode_user_id
from app.api.deps import get_embedding, get_llm
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
    "Output structure (use Markdown):\n"
    "1. **Answer** — one or two sentences giving the direct answer up front, "
    "with inline citations.\n"
    "2. **Evidence** — short bullet list. Each bullet states one finding, the "
    "study context in parentheses (e.g. *in vitro*, mouse model, human cohort "
    "n=120, cell line), and ends with [DOI:<doi>]. Preserve exact numerics: "
    "effect sizes, p-values, sample sizes, doses, concentrations.\n"
    "3. **Limitations** — one line. Note when evidence is thin (single preprint, "
    "small n, preclinical only, conflicting results, indirect inference). Omit "
    "only if every claim is well-supported by multiple excerpts.\n"
    "\n"
    "How to answer:\n"
    "- Ground every factual claim in the excerpts. Each claim ends with an "
    "inline [DOI:<doi>] citation; multi-source claims cite each source.\n"
    "- If excerpts disagree, surface the disagreement in Evidence and call it "
    "out in Limitations.\n"
    "- If excerpts partially cover the question, answer the supported part with "
    "citations, then add a short 'Outside the corpus:' paragraph for background "
    "if helpful. Never mix cited and uncited claims in the same sentence.\n"
    "- If excerpts are unrelated or empty, skip the structured format. Say "
    "briefly the corpus did not surface relevant papers, give a short 'Outside "
    "the corpus:' answer if you have one, and suggest 1–2 reformulated queries.\n"
    "- For conversational or meta questions ('what is this?', 'hello'), answer "
    "naturally in plain prose without the structured format or citations.\n"
    "\n"
    "Citations:\n"
    "- Only cite DOIs that appear in the provided excerpts — never fabricate.\n"
    "- Excerpts often mention other studies by author name (e.g. 'Smith et al. "
    "2020 found...'). Those are references inside a retrieved paper, not papers "
    "you retrieved. Do NOT list them as separate findings or assign them a DOI. "
    "Summarise only what the retrieved excerpts themselves report.\n"
    "\n"
    "Style: direct, precise, no hedging filler ('it is important to note', 'as "
    "an AI'). Quote short phrases verbatim when wording matters. Prefer "
    "specifics over generalities.\n"
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


# Tolerant matcher for inline DOI citations. Accepts [DOI:xxx], [doi: xxx],
# and trailing punctuation. DOIs themselves are matched up to a closing bracket
# or whitespace so we don't over-grab.
_DOI_CITE_RE = re.compile(r"\[\s*DOI\s*:\s*([^\]\s]+?)\s*\]", re.IGNORECASE)


def _validate_citations(text: str, allowed_dois: set[str]) -> tuple[str, list[str]]:
    """Replace any [DOI:x] whose DOI isn't in `allowed_dois` with [DOI:†].

    Returns (cleaned_text, list_of_fabricated_dois). DOI comparison is
    case-insensitive since publishers vary on casing.
    """
    allowed_lc = {d.lower() for d in allowed_dois}
    fabricated: list[str] = []

    def _sub(m: re.Match) -> str:
        doi = m.group(1).rstrip(".,;:)")
        if doi.lower() in allowed_lc:
            return f"[DOI:{doi}]"
        fabricated.append(doi)
        return "[DOI:†]"

    return _DOI_CITE_RE.sub(_sub, text), fabricated


@router.post("/ask")
async def ask(req: AskRequest, session_token: str | None = Cookie(default=None)):
    user_id = decode_user_id(session_token)
    embedding = get_embedding()
    llm = get_llm()

    where = build_where(
        sources=req.sources,
        subjects=req.subjects,
        date_from=req.date_from,
        date_to=req.date_to,
    )
    hits = search(req.query, embedding, where=where)
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
        raw_text = "".join(collected)
        allowed = {h.doi for h in hits}
        cleaned_text, fabricated = _validate_citations(raw_text, allowed)
        if fabricated:
            yield {
                "event": "fabricated_dois",
                "data": json.dumps({"dois": fabricated}),
            }
        yield {"event": "done", "data": ""}

        with session_scope() as s:
            s.add(
                Message(
                    conversation_id=conv_id,
                    role="assistant",
                    content=cleaned_text or f"[error: {error}]",
                    gen_model_id=llm.model_id,
                    embedding_model_id=embedding.model_id,
                    retrieved_doi_versions=retrieved,
                    hits_json=[h.to_dict() for h in hits],
                )
            )

    return EventSourceResponse(event_stream())
