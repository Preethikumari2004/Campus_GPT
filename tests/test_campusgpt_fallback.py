import json
import sys
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.routers import chat as chat_router
from app.schemas import ChatRequest, ChatTurn
from app.services import live_answers, llm, rag


def test_ask_model_429_falls_back_to_local_guidance(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("CAMPUSGPT_LOCAL_ONLY", "false")

    def fake_urlopen(request, timeout=None):
        raise HTTPError(
            url=request.full_url,
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)

    question = "What campus safety services are available to MCA students, and who should I contact in an emergency?"
    sources = [{
        "source": "06_MCA_Campus_and_Student_Life.pdf",
        "text": "Campus security and emergency support are available to students during working hours and after-hours assistance is available from the student support desk; call 112 for emergencies.",
    }]

    answer = llm.ask_model(question, sources, [])

    assert "campus security" in answer.lower()
    assert "emergency" in answer.lower()
    assert "112" in answer


def test_ask_model_sends_chat_completion_request_to_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("CAMPUSGPT_LOCAL_ONLY", "false")
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return BytesIO(b'{"choices":[{"message":{"content":"Grounded answer."}}]}')

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)

    answer = llm.ask_model("Where is the campus help desk?", [], [])

    assert answer == "Grounded answer."
    request = requests[0]
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    payload = json.loads(request.data)
    assert payload["model"] == "llama-3.3-70b-versatile"
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    assert "information was not available in the campus PDFs/documents" in payload["messages"][0]["content"]


def test_create_embeddings_sends_request_to_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return BytesIO(b'{"data":[{"index":0,"embedding":[0.1,0.2]}]}')

    monkeypatch.setattr(rag, "urlopen", fake_urlopen)

    vectors = rag.create_embeddings(["campus help desk"])

    assert vectors == [[0.1, 0.2]]
    request = requests[0]
    assert request.full_url == "https://api.groq.com/openai/v1/embeddings"
    payload = json.loads(request.data)
    assert payload["model"] == "nomic-embed-text-v1.5"
    assert payload["input"] == ["campus help desk"]


def test_lexical_retrieve_rejects_single_generic_word_match():
    chunks = [
        {"source": "campus.pdf", "text": "Campus services include a student help desk."},
        {
            "source": "eligibility.pdf",
            "text": "MCA eligibility requires an undergraduate degree and minimum qualifying marks.",
        },
    ]

    sources = rag.lexical_retrieve(
        "What are the MCA eligibility requirements and minimum undergraduate marks?",
        chunks,
    )

    assert [source["source"] for source in sources] == ["eligibility.pdf"]


def test_definition_fallback_uses_explanatory_sentence_not_headings():
    sources = [{
        "source": "NLPAA_Module_2_MCA.docx",
        "text": "Advantages of Transformers. Transformer Architecture. Transformers are a deep learning architecture introduced in 2017 through the research paper Attention Is All You Need.",
    }]

    answer = llm.build_local_fallback_answer("What is a transformer?", sources)

    assert answer.startswith("Transformers are a deep learning architecture")
    assert "Advantages of Transformers" not in answer


def test_definition_fallback_answers_glossary_style_python_list_question():
    sources = [{
        "source": "Python_Fundamentals_10_Page_Notes.pdf",
        "text": "Collections store multiple values. List - ordered and changeable subjects = [\"Python\", \"DBMS\"] Tuple - ordered and fixed location = (\"Block A\", 204). Count how many times Python appears in a list of course names.",
    }]

    answer = llm.build_local_fallback_answer("What are Python lists?", sources)

    assert answer == "A Python list is ordered and changeable."


def test_eligibility_question_is_not_treated_as_a_definition():
    assert not rag.is_definition_question("What are the MCA eligibility requirements?")


def test_eligibility_retrieval_prefers_the_admission_document():
    chunks = [
        {
            "source": "04_MCA_Assessment_and_Examinations.pdf",
            "text": "Attendance requirements are prescribed for courses. Students need minimum attendance before an examination.",
        },
        {
            "source": "01_MCA_Admission_and_Eligibility.pdf",
            "text": "Eligibility shown on the MCA programme page. Applicants with BCA, B.E. or B.Tech. in Computer Science (or equivalent) are listed as eligible.",
        },
    ]

    sources = rag.lexical_retrieve("What are the MCA eligibility requirements?", chunks)

    assert sources[0]["source"] == "01_MCA_Admission_and_Eligibility.pdf"


def test_eligibility_fallback_returns_requirements_not_a_heading():
    sources = [{
        "source": "01_MCA_Admission_and_Eligibility.pdf",
        "text": "Eligibility shown on the MCA programme page. Applicants with BCA, B.E. or B.Tech. in Computer Science (or equivalent) are listed as eligible.",
    }]

    answer = llm.build_local_fallback_answer("What are the MCA eligibility requirements?", sources)

    assert "Applicants with BCA" in answer
    assert "Eligibility shown" not in answer


def test_eligibility_question_gets_concise_answer_and_flags_conflicting_guides(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("CAMPUSGPT_LOCAL_ONLY", "false")
    sources = [
        {
            "source": "01_MCA_Admission_and_Eligibility.pdf",
            "text": "Applicants with BCA, B.E. or B.Tech. in Computer Science (or equivalent) are listed as eligible. The published minimum is 50%; the page lists 45% for reserved categories.",
        },
        {
            "source": "alliance_university_mca_fee_payment_refund_2027-29.pdf",
            "text": "Published eligibility summary. Bachelor degree: BCA, B.E./B.Tech. in CSE or equivalent; or B.Sc., B.Com., or B.A.",
        },
    ]

    def unexpected_provider_call(*args, **kwargs):
        raise AssertionError("A deterministic eligibility answer should not call the AI provider")

    monkeypatch.setattr(llm, "urlopen", unexpected_provider_call)
    answer = llm.ask_model("What are the MCA eligibility requirements?", sources, [])

    assert answer.startswith("The uploaded admission summary lists BCA")
    assert "50% as the minimum marks (45% for reserved categories)" in answer
    assert "Another uploaded guide lists additional bachelor’s degrees" in answer


def test_non_admin_faculty_lookup_is_not_answered_from_unrelated_documents(monkeypatch):
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("Private faculty assignment questions must not use document retrieval")

    monkeypatch.setattr(chat_router, "retrieve", unexpected_retrieval)

    result = chat_router.chat(
        ChatRequest(question="Who teaches Deep Learning Models and Applications?"),
        {"id": 9, "role": "faculty"},
    )

    assert result["answer"] == "Faculty assignment details are available to administrators. Please ask your admin."
    assert result["sources"] == []


def test_retrieve_does_not_add_unrelated_history_to_short_standalone_question(monkeypatch):
    monkeypatch.setenv("CAMPUSGPT_LOCAL_ONLY", "true")
    monkeypatch.setattr(rag, "load_chunks", lambda current_user: [{"source": "fees.pdf", "text": "Fee details."}])
    captured_questions = []

    def fake_lexical_retrieve(question, chunks, limit):
        captured_questions.append(question)
        return chunks

    monkeypatch.setattr(rag, "lexical_retrieve", fake_lexical_retrieve)

    rag.retrieve(
        "Fees?",
        {"id": 1, "role": "student"},
        history=[ChatTurn(role="user", content="Where are the campus security offices?")],
    )

    assert captured_questions == ["Fees?"]


def test_retrieve_keeps_history_for_explicit_follow_up(monkeypatch):
    monkeypatch.setenv("CAMPUSGPT_LOCAL_ONLY", "true")
    monkeypatch.setattr(rag, "load_chunks", lambda current_user: [{"source": "fees.pdf", "text": "Fee details."}])
    captured_questions = []

    def fake_lexical_retrieve(question, chunks, limit):
        captured_questions.append(question)
        return chunks

    monkeypatch.setattr(rag, "lexical_retrieve", fake_lexical_retrieve)

    rag.retrieve(
        "What about fees?",
        {"id": 1, "role": "student"},
        history=[ChatTurn(role="user", content="When is admission deadline?")],
    )

    assert "admission deadline" in captured_questions[0]
    assert "Current follow-up: What about fees?" in captured_questions[0]


def test_vector_index_is_rebuilt_when_embedding_model_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "VECTOR_INDEX", tmp_path / "vector_index.json")
    calls = []

    def fake_create_embeddings(texts):
        calls.append(texts)
        return [[float(len(calls)), 1.0] for _ in texts]

    monkeypatch.setattr(rag, "create_embeddings", fake_create_embeddings)
    chunks = [{"source": "fees.pdf", "text": "MCA fee details."}]

    monkeypatch.setenv("GROQ_EMBEDDING_MODEL", "model-a")
    first = rag.build_vector_index(chunks)
    monkeypatch.setenv("GROQ_EMBEDDING_MODEL", "model-b")
    second = rag.build_vector_index(chunks)

    assert len(calls) == 2
    assert first[0]["embedding"] != second[0]["embedding"]


def test_student_subject_question_uses_only_the_students_enrollments(monkeypatch):
    rows = [{"name": "Database Systems", "code": "MCA401", "semester": 4, "term": "Fall 2026"}]

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, params):
            assert params == {"student_id": 27}
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(live_answers, "engine", FakeEngine())

    answer = live_answers.answer_student_subject_question(
        "What subjects do I have this semester?",
        {"id": 27, "role": "student"},
    )

    assert answer == "The subjects currently linked to your account are: Database Systems (Semester 4, Fall 2026, MCA401)."


def test_student_subject_question_handles_no_enrollments(monkeypatch):
    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, params):
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(live_answers, "engine", FakeEngine())

    answer = live_answers.answer_student_subject_question(
        "What subjects do I have this semester?",
        {"id": 27, "role": "student"},
    )

    assert "no subjects are currently linked" in answer.lower()


def test_chat_uses_ai_when_no_pdf_sources_are_retrieved(monkeypatch):
    monkeypatch.setattr(chat_router, "retrieve", lambda *args, **kwargs: [])
    calls = []

    def fake_ask_model(question, sources, history):
        calls.append((question, sources, history))
        return "This was not available in the campus PDFs, but here is general guidance."

    monkeypatch.setattr(chat_router, "ask_model", fake_ask_model)

    result = chat_router.chat(
        ChatRequest(question="What are the MCA eligibility requirements?"),
        {"id": 9, "role": "faculty"},
    )

    assert result["answer"].startswith("This was not available in the campus PDFs")
    assert result["sources"] == []
    assert calls == [("What are the MCA eligibility requirements?", [], [])]
