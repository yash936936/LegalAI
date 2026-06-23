# evaluator.py
import os
import re

# FIX: load .env defensively here as well — see rag_vectorstore.py for why.
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage

from rate_limiter import lite_rate_limiter, RateLimitError

# gemini-2.5-flash-lite is the most generous free-tier model — perfect for a
# cheap, short-output judging task. Routed through its own rate bucket so
# judge calls don't compete with the main advisor/contract-analyzer quota.
llm_judge = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.0,
    max_output_tokens=300,   # trimmed from 512 — the output format is short and fixed
    max_retries=2,
)

RAG_EVAL_PROMPT = PromptTemplate.from_template("""
You are an expert Legal RAG Quality Evaluator for Indian law AI systems.

Question: {question}

Retrieved Context: {context}

Generated Answer: {answer}

Evaluate on these three criteria (score 1-10 each):
1. Faithfulness — Does the answer stay grounded in the retrieved context without hallucinating legal sections?
2. Relevance — How precisely does the answer address the legal question using the retrieved documents?
3. Helpfulness — Is the response professional, actionable, and accessible to a non-lawyer?

Output EXACTLY in this format (no deviation):
Faithfulness: X/10
Relevance: Y/10
Helpfulness: Z/10
Overall Score: W/10
Reasoning: <one or two sentences max>
""")


def evaluate_rag(question: str, context: str, answer: str) -> dict:
    try:
        prompt = RAG_EVAL_PROMPT.format(
            question=question[:500],     # cap input — judge doesn't need the full essay
            context=context[:1200],      # trimmed from 2000
            answer=answer[:1200],        # trimmed from 2000
        )

        input_tokens = len(prompt) // 4
        lite_rate_limiter.acquire(input_tokens, output_buffer=300)

        response = llm_judge.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        scores = {}
        for metric in ["Faithfulness", "Relevance", "Helpfulness", "Overall Score"]:
            match = re.search(rf"{metric}:\s*(\d+(?:\.\d+)?)/10", raw)
            if match:
                scores[metric.lower().replace(" ", "_")] = float(match.group(1))

        reasoning_match = re.search(r"Reasoning:\s*(.+)", raw, re.DOTALL)
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided."

        return {
            "raw": raw,
            "scores": scores,
            "reasoning": reasoning,
            "passed": scores.get("overall_score", 0) >= 6.0,
        }
    except RateLimitError as e:
        return {"raw": str(e), "scores": {}, "reasoning": str(e), "passed": False}
    except Exception as e:
        return {
            "raw": f"Evaluation failed: {str(e)}",
            "scores": {},
            "reasoning": str(e),
            "passed": False,
        }


def format_eval_for_display(eval_result: dict) -> str:
    if not eval_result.get("scores"):
        return f"⚠️ Evaluation unavailable: {eval_result.get('reasoning', 'Unknown error')}"

    s = eval_result["scores"]
    verdict = "✅ Pass" if eval_result.get("passed") else "❌ Needs Improvement"
    lines = [
        f"**Faithfulness:** {s.get('faithfulness', '?')}/10",
        f"**Relevance:** {s.get('relevance', '?')}/10",
        f"**Helpfulness:** {s.get('helpfulness', '?')}/10",
        f"**Overall:** {s.get('overall_score', '?')}/10 — {verdict}",
        "",
        f"**Reasoning:** {eval_result['reasoning']}",
    ]
    return "\n".join(lines)