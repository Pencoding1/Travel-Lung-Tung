from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_name = "Qwen/Qwen2.5-3B-Instruct"
local_dir = "./models/Qwen2.5-3B-Instruct"   # thư mục bạn muốn lưu model

tokenizer = AutoTokenizer.from_pretrained(
    model_name,
    cache_dir=local_dir
)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    cache_dir=local_dir,
    torch_dtype=torch.float16,
    device_map="auto"
)

prompt = "Hãy viết 1 đoạn văn tiếng Việt 50 chữ."
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

outputs = model.generate(**inputs, max_new_tokens=200)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
