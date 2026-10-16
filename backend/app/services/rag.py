from __future__ import annotations
from ..schemas import ChatTurn
from ..config import KNOWLEDGE_DIR, TOKEN_RE, VECTOR_INDEX, logger
from ..services.document_text import accessible_document_rows, extract_document_text
from typing import Any
from collections import Counter
from urllib.error import HTTPError, URLError
from fastapi import HTTPException
from pathlib import Path
from urllib.request import Request as UrlRequest, urlopen
import hashlib, json, math, os, re
from sqlalchemy import text

RAG_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "our", "please", "tell", "that", "the", "this", "to", "what", "when",
    "where", "which", "who", "why", "will", "with", "you", "your", "mca",
    "campus", "university", "course", "courses", "program", "programs", "document",
    "documents", "available", "listed", "information", "student", "students",
}

RAG_SYNONYMS = {
    "eligible": {"eligibility", "admission", "qualify", "qualification", "criteria"},
    "eligibility": {"eligible", "admission", "qualify", "qualification", "criteria", "minimum", "marks", "degree"},
    "requirement": {"requirements", "eligibility", "criteria", "required", "minimum", "must"},
    "admission": {"eligibility", "apply", "application", "qualifications", "criteria"},
    "fee": {"fees", "tuition", "payment", "installment", "instalment", "amount", "finance"},
    "deadline": {"due", "date", "last", "payment", "installment", "instalment"},
    "refund": {"refunds", "cancellation", "cancel", "withdraw", "withdrawal"},
    "syllabus": {"curriculum", "topics", "units", "subject", "content"},
    "subject": {"subjects", "course", "curriculum", "syllabus", "topics"},
    "exam": {"exams", "examination", "assessment", "evaluation", "marks", "test"},
    "assessment": {"exam", "examination", "evaluation", "marks", "test"},
    "safety": {"security", "emergency", "helpline", "support"},
    "emergency": {"safety", "security", "helpline", "contact", "support"},
    "contact": {"contacts", "email", "phone", "telephone", "office", "helpline"},
    "placement": {"placements", "career", "job", "employment", "recruitment"},
    "career": {"placement", "placements", "job", "employment", "recruitment"},
    "rule": {"rules", "regulation", "regulations", "policy", "conduct"},
    "attendance": {"present", "absence", "absent", "minimum", "percentage"},
    "support": {"help", "assistance", "service", "services", "desk"},
}

DEFINITION_PROMPT_WORDS = {"define", "definition", "explain", "meaning"}

def is_definition_question(question: str) -> bool:
    if re.search(
        r"\b(?:what\s+is|define|definition\s+of|meaning\s+of|explain)\b",
        question,
        flags=re.IGNORECASE,
    ):
        return True
    if not re.search(r"\bwhat\s+are\b", question, flags=re.IGNORECASE):
        return False
    # These are information/list questions, not requests to define a term.
    return not bool(re.search(
        r"\b(?:requirements?|eligibility|fees?|deadlines?|dates?|rules?|steps|"
        r"subjects?|courses?|services?|contacts?|documents?|options?)\b",
        question,
        flags=re.IGNORECASE,
    ))

def is_definition_passage(question: str, passage: str) -> bool:
    """Return whether a passage actually defines the main term in a question."""
    if not is_definition_question(question):
        return False

    terms = [
        normalize_rag_term(term)
        for term in TOKEN_RE.findall(question)
        if len(term) > 2
        and normalize_rag_term(term) not in RAG_STOP_WORDS
        and normalize_rag_term(term) not in DEFINITION_PROMPT_WORDS
    ]
    for term in terms:
        term_pattern = rf"{re.escape(term)}(?:s|es)?"
        # Examples: "Transformers are a deep learning architecture" and
        # "NLP stands for Natural Language Processing".
        if re.search(
            rf"\b{term_pattern}\s+(?:is|are|means|refers\s+to|stands\s+for)\b",
            passage,
            flags=re.IGNORECASE,
        ):
            return True
        # Study notes also define concepts in compact glossary form, e.g.
        # "List - ordered and changeable" or "List: ordered, mutable".
        if re.search(
            rf"\b{term_pattern}\s*[:\u2013\u2014-]\s*\S",
            passage,
            flags=re.IGNORECASE,
        ):
            return True
        # Also recognize a full term followed by its acronym, e.g.
        # "Natural Language Processing (NLP) is ...".
        if re.search(
            rf"\b(?:[A-Za-z][A-Za-z-]*\s+){{1,7}}\(\s*{re.escape(term)}\s*\)\s+(?:is|are|means|refers\s+to)\b",
            passage,
            flags=re.IGNORECASE,
        ):
            return True
    return False

def load_chunks(current_user: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, str]] = []
    documents = accessible_document_rows(current_user)
    for document in documents:
        path = KNOWLEDGE_DIR / document["filename"]
        try:
            text = extract_document_text(path.name, path.read_bytes())
        except Exception as error:
            logger.warning("Skipping unreadable CampusGPT source %s: %s", path.name, error)
            continue
        # Split paragraphs into bounded overlapping word windows. This keeps
        # neighboring context together without sending entire documents to the LLM.
        for paragraph in re.split(r"\n\s*\n", text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            words = paragraph.split()
            chunk_size = 220
            overlap = 40
            start = 0
            while start < len(words):
                excerpt = " ".join(words[start : start + chunk_size]).strip()
                if excerpt:
                    chunks.append({
                        "source": path.name,
                        "text": excerpt,
                        "scope": document["scope"],
                        "subject_id": document["subject_id"],
                    })
                if start + chunk_size >= len(words):
                    break
                start += chunk_size - overlap
    return chunks

def legacy_lexical_retrieve(question: str, chunks: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
        "or", "our", "please", "tell", "that", "the", "this", "to", "what", "when",
        "where", "which", "who", "why", "will", "with", "you", "your",
    }
    query_terms = [
        term.lower() for term in TOKEN_RE.findall(question)
        if len(term) > 2 and term.lower() not in stop_words
    ]
    if not query_terms:
        return []

    if not chunks:
        return []

    tokenized = [
        [term.lower() for term in TOKEN_RE.findall(chunk["text"]) if len(term) > 2]
        for chunk in chunks
    ]
    document_frequency = Counter(
        term for terms in tokenized for term in set(terms)
    )
    average_length = sum(map(len, tokenized)) / max(len(tokenized), 1)
    query_counts = Counter(query_terms)
    ranked: list[tuple[float, int, dict[str, str]]] = []
    for index, (chunk, terms) in enumerate(zip(chunks, tokenized)):
        frequencies = Counter(terms)
        score = 0.0
        matched_terms = 0
        for term, query_frequency in query_counts.items():
            frequency = frequencies[term]
            if not frequency:
                continue
            matched_terms += 1
            inverse_frequency = math.log1p(
                (len(chunks) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            length_factor = frequency + 1.2 * (
                1 - 0.75 + 0.75 * len(terms) / max(average_length, 1)
            )
            score += inverse_frequency * (frequency * 2.2 / length_factor) * min(query_frequency, 2)

        # Prefer exact multiword phrases when the source contains them.
        normalized_question = " ".join(query_terms)
        normalized_chunk = " ".join(terms)
        if len(query_terms) > 1 and normalized_question in normalized_chunk:
            score += 2.0
        # One shared word is too weak evidence for a multi-topic question.
        # Requiring two distinct matches prevents generic terms such as
        # "campus" or "student" from selecting unrelated passages.
        minimum_matches = 1 if len(query_counts) <= 2 else 2
        if matched_terms >= minimum_matches:
            ranked.append((score, index, chunk))

    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [chunk for _, _, chunk in ranked[:limit]]

def normalize_rag_term(term: str) -> str:
    normalized = term.lower()
    if len(normalized) > 5 and normalized.endswith("ies"):
        return normalized[:-3] + "y"
    if len(normalized) > 5 and normalized.endswith("ing"):
        return normalized[:-3]
    if len(normalized) > 4 and normalized.endswith("ed"):
        return normalized[:-2]
    if len(normalized) > 5 and normalized.endswith(("ses", "xes", "zes", "ches", "shes")):
        return normalized[:-2]
    if len(normalized) > 4 and normalized.endswith("s") and not normalized.endswith(("us", "ss", "is")):
        return normalized[:-1]
    return normalized

def rag_query_groups(question: str) -> list[set[str]]:
    groups: list[set[str]] = []
    for raw_term in TOKEN_RE.findall(question):
        term = normalize_rag_term(raw_term)
        if len(term) <= 2 or term in RAG_STOP_WORDS:
            continue
        group = {term}
        group.update(normalize_rag_term(value) for value in RAG_SYNONYMS.get(term, set()))
        if group not in groups:
            groups.append(group)
    return groups

def lexical_retrieve(question: str, chunks: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    """Retrieve matching PDF/DOCX/TXT chunks locally without a paid embeddings service."""
    if not chunks:
        return []
    query_groups = rag_query_groups(question)
    if not query_groups:
        return []

    query_weights: Counter[str] = Counter()
    exact_query_terms: set[str] = set()
    for raw_term in TOKEN_RE.findall(question):
        term = normalize_rag_term(raw_term)
        if len(term) <= 2 or term in RAG_STOP_WORDS:
            continue
        exact_query_terms.add(term)
        query_weights[term] += 1.0
        for synonym in RAG_SYNONYMS.get(term, set()):
            query_weights[normalize_rag_term(synonym)] += 0.35

    # Definition questions should favor explanatory passages over nearby
    # examples such as token embeddings (for example, ``NLP = [0.6, ...]``).
    definition_question = is_definition_question(question)

    tokenized = [
        [normalize_rag_term(term) for term in TOKEN_RE.findall(chunk["text"]) if len(term) > 2]
        for chunk in chunks
    ]
    document_frequency = Counter(term for terms in tokenized for term in set(terms))
    average_length = sum(map(len, tokenized)) / max(len(tokenized), 1)
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, (chunk, terms) in enumerate(zip(chunks, tokenized)):
        frequencies = Counter(terms)
        term_set = set(terms)
        matched_groups = sum(bool(group & term_set) for group in query_groups)
        if not matched_groups:
            continue

        score = 0.0
        for term, query_weight in query_weights.items():
            frequency = frequencies[term]
            if not frequency:
                continue
            inverse_frequency = math.log1p(
                (len(chunks) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            length_factor = frequency + 1.2 * (
                0.25 + 0.75 * len(terms) / max(average_length, 1)
            )
            score += inverse_frequency * (frequency * 2.2 / length_factor) * query_weight

        # Favor passages containing the words the user actually asked about
        # over passages that match only broad synonyms such as "minimum".
        score += sum(1.5 for term in exact_query_terms if term in term_set)

        source_terms = {
            normalize_rag_term(term)
            for term in TOKEN_RE.findall(Path(chunk["source"]).stem.replace("_", " "))
            if len(term) > 2
        }
        title_matches = sum(bool(group & source_terms) for group in query_groups)
        score += title_matches * 1.5 + matched_groups * 0.25

        if definition_question:
            excerpt = str(chunk["text"])
            # Give a strong preference to direct definitions such as
            # "Natural Language Processing (NLP) is ..." or "NLP means ...".
            if is_definition_passage(question, excerpt):
                score += 8.0

            # Do not let numeric embedding demonstrations outrank a prose
            # definition for a basic "what is/define" question.
            if re.search(
                r"\b[A-Za-z][A-Za-z0-9_]*\s*=\s*\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)+\s*\]",
                excerpt,
            ):
                score -= 10.0
        ranked.append((score, index, chunk))

    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [chunk for _, _, chunk in ranked[:limit]]

def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Call Groq's OpenAI-compatible embeddings endpoint for chunks or a query."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    payload = {
        "model": os.getenv("GROQ_EMBEDDING_MODEL", "nomic-embed-text-v1.5"),
        "input": texts,
    }
    request = UrlRequest(
        "https://api.groq.com/openai/v1/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")[:500]
        raise HTTPException(status_code=502, detail=f"Embedding provider error: {detail}") from error
    except (URLError, TimeoutError) as error:
        raise HTTPException(status_code=502, detail="Could not reach the embedding provider.") from error
    try:
        return [item["embedding"] for item in sorted(result["data"], key=lambda item: item["index"])]
    except (KeyError, TypeError) as error:
        raise HTTPException(status_code=502, detail="The embedding provider returned an invalid response.") from error

def build_vector_index(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cache embeddings locally; the digest includes only this user's accessible sources."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    digest_payload = {
        "embedding_model": os.getenv("GROQ_EMBEDDING_MODEL", "nomic-embed-text-v1.5"),
        "chunks": chunks,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if VECTOR_INDEX.is_file():
        try:
            saved = json.loads(VECTOR_INDEX.read_text(encoding="utf-8"))
            if saved.get("digest") == digest:
                return saved["items"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass

    indexed: list[dict[str, Any]] = []
    for offset in range(0, len(chunks), 64):
        batch = chunks[offset:offset + 64]
        vectors = create_embeddings([chunk["text"] for chunk in batch])
        indexed.extend({**chunk, "embedding": vector} for chunk, vector in zip(batch, vectors))
    VECTOR_INDEX.write_text(
        json.dumps({"digest": digest, "items": indexed}, ensure_ascii=False), encoding="utf-8"
    )
    return indexed

def retrieve(
    question: str,
    current_user: dict[str, Any],
    limit: int = 4,
    history: list[ChatTurn] | None = None,
) -> list[dict[str, Any]]:
    chunks = load_chunks(current_user)
    if not chunks:
        return []
    retrieval_question = question
    follow_up_markers = re.compile(r"\b(it|that|those|them|there|this|also|then|same|what about|how about)\b", re.IGNORECASE)
    previous_user_questions = [turn.content for turn in (history or []) if turn.role == "user"]
    if previous_user_questions and follow_up_markers.search(question):
        retrieval_question = f"Related prior question: {previous_user_questions[-1]}\nCurrent follow-up: {question}"
    # Groq generates the answer, but does not provide the embeddings endpoint
    # this project previously called. Retrieve locally so search still works
    # when the Groq key is missing, rate-limited, or chat is disabled.
    return lexical_retrieve(retrieval_question, chunks, limit)
