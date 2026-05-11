import sys
import os

# Ensure the app can be imported
sys.path.append(os.path.abspath('.'))

from app.services.vector_store import search_similar_qa

query = "भगवान का नाम कैसे लें?"
print(f"Testing Query: {query}")
results = search_similar_qa(query, top_k=8)

print(f"Found {len(results)} results")
for r in results:
    print(f"--- Score: {r.score} ---")
    print(f"Video: {r.video.title}")
    print(f"Q: {r.question}")
    print(f"A: {r.answer}")

