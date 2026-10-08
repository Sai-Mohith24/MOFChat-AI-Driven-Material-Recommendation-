# How to Run the MOFChat Frontend

To run the frontend again, please follow these simple steps in your terminal:

1. **Start Ollama (Required for the AI agent)**:
   Make sure the Ollama application is running on your Mac. You can either open the Ollama app from your Applications folder, or open a new terminal window and run:
   ```bash
   ollama serve
   ```
   Leave that terminal window open in the background.

2. **Open your project terminal** and make sure you are in your project directory:
   ```bash
   cd /Users/saimohith/Documents/Sem-5/Data-Driven/Project-antigravity
   ```

3. **Activate the virtual environment**:
   ```bash
   source venv/bin/activate
   ```

4. **Run the Streamlit application**:
   ```bash
   streamlit run app.py
   ```

Once you run the last command, Streamlit will automatically open your default web browser and load the MOFChat frontend!
