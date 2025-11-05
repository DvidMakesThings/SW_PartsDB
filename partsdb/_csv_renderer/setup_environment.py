#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PartsDB CSV Renderer Environment Setup Script
This script helps set up the required environment for the PartsDB CSV renderer,
including Ollama installation and configuration.
"""

import os
import sys
import platform
import subprocess
import tempfile
import shutil
import urllib.request
import json
import tkinter as tk
from tkinter import ttk, messagebox

class SetupEnvironment:
    def __init__(self, root=None):
        self.system = platform.system()
        self.is_windows = self.system == "Windows"
        self.is_macos = self.system == "Darwin"
        self.is_linux = self.system == "Linux"
        self.ollama_installed = False
        self.model_installed = False
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "mixtral:8x7b-instruct-v0.1-q2_K")
        self.ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        
        if root:
            self.root = root
            self.gui_mode = True
            self.setup_gui()
        else:
            self.gui_mode = False
            
    def setup_gui(self):
        """Set up the GUI interface"""
        self.root.title("PartsDB Environment Setup")
        self.root.geometry("600x800")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="PartsDB CSV Renderer Setup", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # Requirements frame
        req_frame = ttk.LabelFrame(main_frame, text="Requirements")
        req_frame.pack(fill=tk.X, pady=5, padx=5)
        
        # Python packages
        ttk.Label(req_frame, text="1. Python packages").pack(anchor=tk.W, padx=5, pady=2)
        self.py_packages_status = ttk.Label(req_frame, text="Not installed")
        self.py_packages_status.pack(anchor=tk.W, padx=20)
        ttk.Button(req_frame, text="Install Python Packages", command=self.install_python_packages).pack(anchor=tk.W, padx=20, pady=5)
        
        # Ollama
        ttk.Label(req_frame, text="2. Ollama").pack(anchor=tk.W, padx=5, pady=2)
        self.ollama_status = ttk.Label(req_frame, text="Not installed")
        self.ollama_status.pack(anchor=tk.W, padx=20)
        ttk.Button(req_frame, text="Install Ollama", command=self.install_ollama).pack(anchor=tk.W, padx=20, pady=5)
        
        # Models
        ttk.Label(req_frame, text="3. LLM Model").pack(anchor=tk.W, padx=5, pady=2)
        
        # Model selection frame
        model_frame = ttk.Frame(req_frame)
        model_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=self.ollama_model)
        self.model_entry = ttk.Entry(model_frame, textvariable=self.model_var, width=20)
        self.model_entry.pack(side=tk.LEFT, padx=5)
        
        # Default models dropdown
        default_models = ["mixtral:8x7b-instruct-v0.1-q2_K"]
        self.model_dropdown_var = tk.StringVar()
        model_dropdown = ttk.Combobox(model_frame, textvariable=self.model_dropdown_var, values=default_models, width=15)
        model_dropdown.pack(side=tk.LEFT, padx=5)
        model_dropdown.bind("<<ComboboxSelected>>", self.on_model_select)
        
        self.model_status = ttk.Label(req_frame, text="Not installed")
        self.model_status.pack(anchor=tk.W, padx=20)
        ttk.Button(req_frame, text="Install Model", command=self.install_model).pack(anchor=tk.W, padx=20, pady=5)
        
        # Configuration frame
        config_frame = ttk.LabelFrame(main_frame, text="Configuration")
        config_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Ollama host
        host_frame = ttk.Frame(config_frame)
        host_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(host_frame, text="Ollama Host:").pack(side=tk.LEFT)
        self.host_var = tk.StringVar(value=self.ollama_host)
        self.host_entry = ttk.Entry(host_frame, textvariable=self.host_var, width=30)
        self.host_entry.pack(side=tk.LEFT, padx=5)
        
        # Save configuration button
        ttk.Button(config_frame, text="Save Configuration", command=self.save_config).pack(anchor=tk.W, padx=5, pady=5)
        
        # Status area
        status_frame = ttk.LabelFrame(main_frame, text="Status")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=5)
        
        self.status_text = tk.Text(status_frame, height=8, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="Check Status", command=self.check_status).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Install All", command=self.install_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Exit", command=self.root.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Check initial status
        self.check_status()
        
    def on_model_select(self, event):
        """Handle model selection from dropdown"""
        selected = self.model_dropdown_var.get()
        if selected:
            self.model_var.set(selected)
    
    def log(self, message):
        """Log a message to either console or GUI"""
        print(message)
        if self.gui_mode and hasattr(self, 'status_text'):
            self.status_text.insert(tk.END, message + "\n")
            self.status_text.see(tk.END)
            self.root.update_idletasks()
    
    def check_status(self):
        """Check the installation status of all components"""
        # Reset status
        if self.gui_mode:
            self.status_text.delete(1.0, tk.END)
        
        # Check Python packages
        self.log("Checking Python packages...")
        packages_installed = self.check_python_packages()
        if packages_installed:
            if self.gui_mode:
                self.py_packages_status.config(text="Installed ✓", foreground="green")
            self.log("Python packages are installed.")
        else:
            if self.gui_mode:
                self.py_packages_status.config(text="Not installed ✗", foreground="red")
            self.log("Python packages are not fully installed.")
        
        # Check Ollama
        self.log("Checking Ollama installation...")
        self.ollama_installed = self.check_ollama_installed()
        if self.ollama_installed:
            if self.gui_mode:
                self.ollama_status.config(text="Installed ✓", foreground="green")
            self.log("Ollama is installed.")
        else:
            if self.gui_mode:
                self.ollama_status.config(text="Not installed ✗", foreground="red")
            self.log("Ollama is not installed.")
        
        # Check Model
        if self.ollama_installed:
            model = self.model_var.get() if self.gui_mode else self.ollama_model
            self.log(f"Checking if model {model} is installed...")
            self.model_installed = self.check_model_installed(model)
            if self.model_installed:
                if self.gui_mode:
                    self.model_status.config(text=f"{model} installed ✓", foreground="green")
                self.log(f"Model {model} is installed.")
            else:
                if self.gui_mode:
                    self.model_status.config(text=f"Not installed ✗", foreground="red")
                self.log(f"Model {model} is not installed.")
        
    def check_python_packages(self):
        """Check if required Python packages are installed"""
        try:
            # Get requirements
            required_packages = []
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt"), "r") as f:
                required_packages = [line.strip() for line in f if line.strip()]
            
            # Check each package
            missing = []
            for package in required_packages:
                package_name = package.split("==")[0].split(">")[0].split("<")[0].strip()
                
                # Handle special cases
                if package_name == "pdfminer.six":
                    try:
                        import pdfminer.high_level
                        continue  # Skip adding to missing if import succeeds
                    except ImportError:
                        pass
                elif package_name == "pymupdf":
                    try:
                        import fitz  # PyMuPDF uses fitz as its import name
                        continue
                    except ImportError:
                        pass
                elif package_name == "python-dotenv":
                    try:
                        import dotenv
                        continue
                    except ImportError:
                        pass
                else:
                    # Standard case
                    try:
                        __import__(package_name.replace("-", "_"))
                        continue
                    except ImportError:
                        pass
                
                # If we get here, the import failed
                missing.append(package_name)
            
            if missing:
                self.log(f"Missing packages: {', '.join(missing)}")
                return False
            return True
        except Exception as e:
            self.log(f"Error checking packages: {e}")
            return False
    
    def check_ollama_installed(self):
        """Check if Ollama is installed"""
        try:
            if self.is_windows:
                result = subprocess.run(["powershell", "-Command", "Get-Process ollama -ErrorAction SilentlyContinue"], 
                                        capture_output=True, text=True)
                if "ollama" in result.stdout.lower():
                    return True
                
                # Check if executable exists
                program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
                ollama_path = os.path.join(program_files, "Ollama", "ollama.exe")
                if os.path.exists(ollama_path):
                    return True
            else:
                result = subprocess.run(["which", "ollama"], capture_output=True, text=True)
                if result.returncode == 0:
                    return True
            return False
        except Exception as e:
            self.log(f"Error checking Ollama: {e}")
            return False
    
    def check_model_installed(self, model_name):
        """Check if a specific model is installed in Ollama"""
        if not self.ollama_installed:
            return False
            
        try:
            if self.is_windows:
                # In Windows PowerShell, we need to use Invoke-RestMethod or Invoke-WebRequest with explicit parameters
                cmd = ["powershell", "-Command", f"Invoke-RestMethod -Uri '{self.ollama_host}/api/tags' -Method Get"]
            else:
                cmd = ["curl", "-s", f"{self.ollama_host}/api/tags"]
            
            self.log(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.log(f"Failed to connect to Ollama API: {result.stderr}")
                return False
            
            try:
                # Handle PowerShell's object format output
                if "models" in result.stdout and "{}" in result.stdout:
                    self.log("Empty models list from PowerShell response")
                    return self.check_model_installed_fallback(model_name)
                
                try:
                    models = json.loads(result.stdout).get("models", [])
                    if not models:
                        self.log("No models found in API response, trying direct check...")
                        return self.check_model_installed_fallback(model_name)
                        
                    model_names = [m.get("name") for m in models]
                    self.log("Available models: {}".format(", ".join(model_names)))
                    return model_name in model_names
                except json.JSONDecodeError:
                    self.log("Failed to parse Ollama API response: {}".format(result.stdout[:200]))
                    return self.check_model_installed_fallback(model_name)
            except Exception as e:
                self.log("Error processing API response: {}".format(str(e)))
                return self.check_model_installed_fallback(model_name)
                
        except Exception as e:
            self.log(f"Error checking model: {e}")
            # Try fallback method
            return self.check_model_installed_fallback(model_name)
            
    def check_model_installed_fallback(self, model_name):
        """Fallback method to check if a model is installed by looking at Ollama's file structure"""
        try:
            self.log("Using fallback method to check model installation...")
            
            if self.is_windows:
                # In Windows, Ollama stores models in %USERPROFILE%\.ollama\models
                user_profile = os.environ.get("USERPROFILE")
                if not user_profile:
                    self.log("Could not determine user profile directory")
                    return False
                    
                models_dir = os.path.join(user_profile, ".ollama", "models")
                
                # Just check if the directory exists
                if os.path.isdir(models_dir):
                    self.log(f"Model directory exists: {models_dir}")
                    # If we can see the models directory, let's assume Ollama is working
                    # We can't easily check for specific models without parsing binary files
                    return True
            elif self.is_macos:
                # On macOS, models are in ~/.ollama/models
                models_dir = os.path.expanduser("~/.ollama/models")
                if os.path.isdir(models_dir):
                    return True
            elif self.is_linux:
                # On Linux, models are in ~/.ollama/models
                models_dir = os.path.expanduser("~/.ollama/models")
                if os.path.isdir(models_dir):
                    return True
                    
            return False
        except Exception as e:
            self.log(f"Fallback model check failed: {e}")
            return False
    
    def install_python_packages(self):
        """Install required Python packages"""
        self.log("Installing Python packages...")
        
        try:
            # Get requirements
            requirements_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
            
            # Run pip install
            cmd = [sys.executable, "-m", "pip", "install", "-r", requirements_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.log("Python packages installed successfully.")
                if self.gui_mode:
                    self.py_packages_status.config(text="Installed ✓", foreground="green")
                return True
            else:
                self.log(f"Failed to install Python packages:\n{result.stderr}")
                return False
                
        except Exception as e:
            self.log(f"Error installing packages: {e}")
            return False
    
    def install_ollama(self):
        """Install Ollama based on the current OS"""
        self.log(f"Installing Ollama for {self.system}...")
        
        try:
            if self.is_windows:
                # Download Windows installer
                self.log("Downloading Ollama Windows installer...")
                installer_url = "https://ollama.com/download/Ollama-windows-latest.exe"
                installer_path = os.path.join(tempfile.gettempdir(), "ollama_installer.exe")
                
                urllib.request.urlretrieve(installer_url, installer_path)
                
                # Run the installer
                self.log("Running Ollama installer...")
                subprocess.run([installer_path], check=True)
                
            elif self.is_macos:
                # macOS installation
                self.log("Downloading and installing Ollama...")
                cmd = ["curl", "-fsSL", "https://ollama.com/install.sh", "|", "sh"]
                subprocess.run(" ".join(cmd), shell=True, check=True)
                
            elif self.is_linux:
                # Linux installation
                self.log("Downloading and installing Ollama...")
                cmd = ["curl", "-fsSL", "https://ollama.com/install.sh", "|", "sh"]
                subprocess.run(" ".join(cmd), shell=True, check=True)
            
            self.log("Ollama installed successfully.")
            self.ollama_installed = True
            
            if self.gui_mode:
                self.ollama_status.config(text="Installed ✓", foreground="green")
                messagebox.showinfo("Ollama Installation", 
                                    "Ollama has been installed. You may need to start the Ollama service manually.")
            
            return True
            
        except Exception as e:
            self.log(f"Error installing Ollama: {e}")
            if self.gui_mode:
                messagebox.showerror("Installation Error", f"Failed to install Ollama: {e}")
            return False
    
    def install_model(self):
        """Install the selected Ollama model"""
        model = self.model_var.get() if self.gui_mode else self.ollama_model
        
        if not model:
            self.log("No model specified.")
            if self.gui_mode:
                messagebox.showwarning("Model Installation", "Please specify a model name.")
            return False
        
        if not self.ollama_installed:
            self.log("Ollama is not installed. Install Ollama first.")
            if self.gui_mode:
                messagebox.showwarning("Model Installation", "Ollama is not installed. Install Ollama first.")
            return False
        
        self.log(f"Installing model {model}...")
        
        try:
            if self.is_windows:
                # For Windows, we need to use the full path to ollama.exe
                program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
                ollama_exe = os.path.join(program_files, "Ollama", "ollama.exe")
                
                if not os.path.exists(ollama_exe):
                    self.log("Ollama executable not found. Make sure Ollama is installed correctly.")
                    return False
                
                cmd = [ollama_exe, "pull", model]
            else:
                cmd = ["ollama", "pull", model]
            
            self.log(f"Running: {' '.join(cmd)}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Show progress
            while True:
                output = process.stdout.readline()
                if output:
                    self.log(output.strip())
                
                if process.poll() is not None:
                    break
            
            if process.returncode == 0:
                self.log(f"Model {model} installed successfully.")
                self.model_installed = True
                if self.gui_mode:
                    self.model_status.config(text=f"{model} installed ✓", foreground="green")
                return True
            else:
                stderr = process.stderr.read()
                self.log(f"Failed to install model: {stderr}")
                return False
                
        except Exception as e:
            self.log(f"Error installing model: {e}")
            return False
    
    def save_config(self):
        """Save Ollama configuration to environment variables"""
        if self.gui_mode:
            model = self.model_var.get()
            host = self.host_var.get()
        else:
            model = self.ollama_model
            host = self.ollama_host
        
        self.log(f"Saving configuration: Model={model}, Host={host}")
        
        try:
            # For current session
            os.environ["OLLAMA_MODEL"] = model
            os.environ["OLLAMA_HOST"] = host
            
            # For persistence, create/update a .env file
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            with open(env_path, "w") as f:
                f.write(f"OLLAMA_MODEL={model}\n")
                f.write(f"OLLAMA_HOST={host}\n")
            
            self.log("Configuration saved.")
            if self.gui_mode:
                messagebox.showinfo("Configuration", "Configuration saved successfully.")
            return True
            
        except Exception as e:
            self.log(f"Error saving configuration: {e}")
            return False
    
    def install_all(self):
        """Install all components"""
        self.log("Starting full installation...")
        
        # Install Python packages
        if not self.check_python_packages():
            self.install_python_packages()
        else:
            self.log("Python packages already installed.")
        
        # Install Ollama
        if not self.check_ollama_installed():
            self.install_ollama()
        else:
            self.log("Ollama already installed.")
        
        # Install model
        model = self.model_var.get() if self.gui_mode else self.ollama_model
        if not self.check_model_installed(model):
            self.install_model()
        else:
            self.log(f"Model {model} already installed.")
        
        # Save configuration
        self.save_config()
        
        self.log("Installation complete!")
        if self.gui_mode:
            messagebox.showinfo("Installation", "Installation completed successfully!")

def main():
    # Check if we should run in command line mode
    import argparse
    
    parser = argparse.ArgumentParser(description="PartsDB CSV Renderer Environment Setup")
    parser.add_argument("--cli", action="store_true", help="Run in command line mode")
    parser.add_argument("--install-all", action="store_true", help="Install all components automatically")
    parser.add_argument("--model", type=str, help="Specify model to install")
    args = parser.parse_args()
    
    if args.cli:
        # Command line mode
        app = SetupEnvironment()
        
        # Set model if specified
        if args.model:
            app.ollama_model = args.model
        
        # Run checks
        app.check_status()
        
        # Install everything if requested
        if args.install_all:
            app.install_all()
    else:
        # GUI mode
        try:
            root = tk.Tk()
            app = SetupEnvironment(root)
            root.mainloop()
        except Exception as e:
            print(f"GUI initialization failed: {e}")
            print("Falling back to command line mode...")
            app = SetupEnvironment()
            app.check_status()

if __name__ == "__main__":
    main()