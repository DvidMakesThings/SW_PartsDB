# PartsDB CSV Renderer Setup

This directory contains the tools to render and process CSV files for the PartsDB project, including the ability to extract data from PDF datasheets using Ollama and local AI models.

## Prerequisites

- Python 3.8 or newer
- Ollama (will be installed by the setup script)
- Required Python packages (will be installed by the setup script)

## Setup Instructions

### Windows

1. Double-click the `setup.bat` file
2. Follow the on-screen instructions to:
   - Install required Python packages
   - Install Ollama
   - Download and set up a language model
   - Configure settings

### macOS / Linux

1. Open Terminal
2. Navigate to this directory
3. Make the setup script executable: `chmod +x setup.sh`
4. Run the setup script: `./setup.sh`
5. Follow the on-screen instructions

## Manual Setup

If you prefer to set up manually:

1. Install Python packages: `pip install -r requirements.txt`
2. Install Ollama from [ollama.com](https://ollama.com)
3. Pull a language model: `ollama pull gpt-oss:20b` (or another model of your choice)
4. Set environment variables:
   - `OLLAMA_MODEL`: The name of the model to use (default: "gpt-oss:20b")
   - `OLLAMA_HOST`: The Ollama API endpoint (default: "http://localhost:11434")

## Configuration

After installation, you can modify the following settings:

1. **Model**: Choose a different language model
2. **Host**: Change the Ollama API endpoint if running on a different machine

## Troubleshooting

- **PDF processing fails**: Ensure Tesseract OCR is installed for image-based PDF processing
- **Ollama connection error**: Make sure the Ollama service is running
- **Model download issues**: Check your internet connection and available disk space

## Additional Resources

- Ollama documentation: [https://ollama.com/docs](https://ollama.com/docs)
- Available models: [https://ollama.com/library](https://ollama.com/library)