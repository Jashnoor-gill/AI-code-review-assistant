Local Llama (ggml) setup

This project supports running a local Llama-compatible model via:
- `llama-cpp-python` (pip package `llama-cpp-python`), or
- a local `llama.cpp` binary (the `main` executable built from https://github.com/ggerganov/llama.cpp).

Manual steps (Windows / general)

1. Download a quantized ggml model
   - Find a model on Hugging Face or community releases (eg `llama-2-7b-chat.ggmlv3.q4_0.bin`).
   - Accept and follow the model license and usage terms.
   - Place the `.bin` file in a safe folder.

2. Set `LLAMA_MODEL_PATH` environment variable to the model path:

PowerShell:
```powershell
$env:LLAMA_MODEL_PATH = "C:\path\to\ggml-model.bin"
```

3. Option A - install Python binding (recommended):
```powershell
pip install llama-cpp-python
```
The binding will be used automatically if available.

3. Option B - build llama.cpp and ensure the `main` executable is on PATH:
- Follow build instructions at https://github.com/ggerganov/llama.cpp
- On Windows you can use MSYS/MinGW or WSL; place the built `main.exe` in a folder on your PATH.

4. Run the project's smoke test or server (after setting `LLAMA_MODEL_PATH`):
```powershell
cd backend
python -m app.smoke
# or to run the server
python -m app.server
```

Notes:
- CPU quantized models are slower but usable for experimentation. Larger models may require a GPU.
- This project will choose a local Llama model if `LLAMA_MODEL_PATH` is set; otherwise it falls back to OpenAI or Mock.
- For production, prefer a dedicated inference host and secure your model files.
