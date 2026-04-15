from app.services.llm_service import generate_answer

def test():
    import logging
    logging.basicConfig(filename='llm_debug.log', filemode='w', level=logging.DEBUG)
    try:
        ans = generate_answer("Hello", "Context: Hello World")
        with open('llm_debug.log', 'a', encoding='utf-8') as f:
            f.write("\nFINAL ANSWER: " + ans)
    except Exception as e:
        with open('llm_debug.log', 'a', encoding='utf-8') as f:
            f.write("\nMAIN EXCEPTION: " + str(e))

if __name__ == '__main__':
    test()
