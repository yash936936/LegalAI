# evaluator.py
import re
import os
from langchain_google_genai import ChatGoogleGenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage

llm_judge = ChatGoogleGenAI(
    model="gemini-3.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"), 
    temperature=0.0, 
    max_tokens=512,
    max_retries=3
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
Reasoning: <one paragraph>
""")


def evaluate_rag(question: str, context: str, answer: str) -> dict:
    """
    Runs LLM-as-Judge evaluation.
    Returns a structured dict with scores + reasoning.
    """
    try:
        prompt = RAG_EVAL_PROMPT.format(
            question=question,
            context=context[:2000],  # Truncate context for judge call efficiency
            answer=answer[:2000],
        )
        response = llm_judge.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        # Parse scores
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

    except Exception as e:
        return {
            "raw": f"Evaluation failed: {str(e)}",
            "scores": {},
            "reasoning": str(e),
            "passed": False,
        }


def format_eval_for_display(eval_result: dict) -> str:
    """Returns a markdown-formatted evaluation summary."""
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
