from langchain_openai import ChatOpenAI

llm_selector = ChatOpenAI(
    model="gpt-5-mini",
    reasoning_effort='high',

)