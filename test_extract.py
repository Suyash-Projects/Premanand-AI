import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from app.services.llm_service import extract_qa_pairs

sample = '[83s] स्मृति जी रायबरेली से राधे-राधे महाराज जी हम गृहस्थ में रहते हुए शिवोहम की स्थिति धारण कर सकते हैं [88s] हां क्यों नहीं धारण कर सकते गृहस्थ में शरीर व्यवहार कर रहा है लेकिन तत्व तो आप वही है ना [93s] इसके लिए गुरु चरणों का आश्रय लेकर आराधना कीजिए'
print("Testing extraction...")
pairs = extract_qa_pairs(sample)
print(f"Extracted {len(pairs)} pairs:")
print(json.dumps(pairs, ensure_ascii=False, indent=2))
