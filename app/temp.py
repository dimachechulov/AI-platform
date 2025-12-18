import google.generativeai as genai

genai.configure(api_key="AIzaSyCjmRqTQB-0d4EhhzKP7L1xbQWl262IjIk")

for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)