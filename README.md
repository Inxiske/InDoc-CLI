<img width="200" height="200" alt="InDoc-Cli-Normal" src="https://github.com/user-attachments/assets/c848bffd-f899-4934-a5d6-65fcd2a00b83" />

# InDoc-CLI - *Intelligent Document* `Powered by AI`

![System Ready](https://img.shields.io/badge/Status-System%20Ready-brightgreen)
![Version](https://img.shields.io/badge/Version-1.4.0-blue)

**InDoc-CLI** is a specialized engineering tool designed for high-speed source code auditing, documentation, and security analysis. Engineered to provide deep insights through local AI engines, InDoc-CLI streamlines the workflow of software engineers who demand speed, precision, and privacy.

---

##  Key Features

* **Zero-Touch Engine Setup:** InDoc-CLI automatically manages the Ollama lifecycle. No manual installation hurdles. the engine initializes, verifies, and scales on-demand.
* **Full Model Lifecycle Management:** Browse, pull, and manage models directly from the CLI. No need to switch to a browser or terminal; the entire lifecycle is embedded in InDoc-CLI.
* **Model Agnostic:** Not locked into a single provider. Switch seamlessly between any model installed on your system (e.g., Llama 3.2, Mistral, Phi-3) to balance depth vs. speed.
* **High-Speed Auditing:** Rapid ingestion of project structures for comprehensive analysis.
* **Local Inference:** Powered by Ollama for maximum security and data privacy.
* **Intelligent Documentation:** Automated generation of technical documentation directly from your source code.
* **Seamless Integration:** Native Discord Rich Presence support for real-time activity tracking.

---

## 🛡 Security & Privacy
InDoc-CLI operates entirely locally. Your source code, documentation, and project structures never leave your machine. By leveraging local Ollama instances, we ensure that your intellectual property remains under your absolute control.

## 📈 Roadmap
- [ ] Integrated RAG (Retrieval-Augmented Generation) for codebase Q&A.
- [ ] Support for additional CLI engines beyond Ollama.
- [ ] Export configurations to JSON/YAML for team synchronization.

## 🤝 Contributing
InDoc-CLI is built on the principle of engineering efficiency. Contributions are welcome—whether by submitting issues, proposing features, or refining the core engine. Let's build the future of automated documentation together.

##  Usage

```bash
# Scan a project directory
inx scan <path_to_project>

# Document a specific file
inx gen <path_to_file>

# Browse available models
inx model gallery

# More details
inx help
```
<img width="1437" height="665" alt="Screenshot" src="https://github.com/user-attachments/assets/94ac3205-bdca-44b3-975c-d6fe3f74887a" />
 
 `1.4.0 screenshot`


##  Configuration
InDoc-CLI utilizes a modular architecture. All configurations are handled via the inx command prefix, allowing for environment-specific model optimization (e.g., swapping between high-depth or high-speed configurations).

## 🛡 License
This project is licensed under the MIT License.

*Developed by Inxiske | Engineered for performance.*

<img width="200" height="200" alt="InDoc-Cli-official new" src="https://github.com/user-attachments/assets/3820512d-9074-4a9f-9e00-80d886d97959" />
