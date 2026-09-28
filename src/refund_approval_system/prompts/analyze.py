from langchain_core.prompts import ChatPromptTemplate


def get_analyze_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a refund analyst. Analyse the refund request and context "
                    "below and produce a structured recommendation. "
                    "You may recommend: refund, request_information, escalate, or decline. "
                    "You CANNOT execute the refund — your output is advisory only."
                ),
            ),
            (
                "human",
                (
                    "Request: {request}\n"
                    "Order: {order}\n"
                    "Customer: {customer}\n"
                    "Refund history (30d): {history}\n"
                ),
            ),
        ]
    )
