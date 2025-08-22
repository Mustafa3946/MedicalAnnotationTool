# Medical Entity and Relation Annotation Tool

This project is a web-based tool for medical experts to annotate medical entities and relationships in clinical narratives. The annotations can be exported for use in healthcare NLP model training and evaluation.

## Project Folder Structure

```
MedicalAnnotationTool/
│
├── backend/                  # Python FastAPI or Flask backend
│   └── ...                   # Backend code (API, models, etc.)
│
├── frontend/                 # React or simple JS frontend
│   └── ...                   # UI code (components, assets, etc.)
│
├── infra/                    # Terraform code for Azure resources
│   └── main.tf               # Main Terraform configuration
│   └── variables.tf          # Variables for Terraform
│   └── outputs.tf            # Outputs for Terraform
│
├── data/                     # Sample medical texts, annotation outputs
│   └── sample_texts.txt
│   └── sample_annotations.json
│
├── docs/                     # Design document, README, and report
│   └── design.md
│   └── README.md
│   └── report.md
│
├── scripts/                  # Utility scripts (optional)
│   └── ...
│
├── tests/                    # Test cases for backend/frontend
│   └── ...
│
├── .gitignore
└── requirements.txt          # Python dependencies for backend
```

## Quick Start

1. Clone the repository.
2. Set up the backend and frontend as described in their respective folders.
3. Use the `infra/` folder to provision Azure resources with Terraform.
4. See `docs/README.md` for detailed setup and usage instructions.

---
No emojis are used in this documentation.
