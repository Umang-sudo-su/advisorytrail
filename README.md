# BuildShield — Security & Reliability Platform


# About this project: -
Build shield is a GitHub- integrated security and reliability platform. Build shield is designed to help small software teams ship safer code with less security-tool noise and minimal manual investigation. It acts as a workflow, prioritization, and reporting layer that sits on top of existing security scanners rather than functioning as a standalone vulnerability scanner.   
         
# Core Problem It Solves: -

Development teams often receive security findings from multiple tools. These reports frequently suffer from:
•	Different, uncoordinated formats. 
•	Repeated duplicate issues from multiple scans. 
•	A lack of pull-request context (making it hard to know if a vulnerability is brand new or pre-existing). 
•	Excessive manual investigation requirements to determine validity and severity.

# How the Project Works (Key Features & Workflow): - 

•	GitHub Integration: It installs as a GitHub App, listens for signed webhooks (such as when a pull request is opened or updated), and processes events asynchronously. 
•	Controlled Scanners: It runs selected dependency scanners (starting with OSV-Scanner for Python and JavaScript/TypeScript projects) inside isolated background workers. 
•	Normalization & Fingerprinting: It translates tool-specific output into a common, normalized finding schema and applies stable finding fingerprints to suppress duplicate alerts. 
•	Baseline Comparison: It compares scan results between the base and head commits of a pull request to reliably distinguish between brand-new findings and pre-existing code issues. 
•	Actionable Reporting: It publishes concise, evidence-backed results directly to GitHub Check Runs and displays a detailed management overview via a React/TypeScript web dashboard. 


#  Build Shield API
A robust backend API service built for secure build automation and management.

# Features
**Secure Authentication:  JWT-based secure user sessions.
       **Build Management:  Real-time tracking and triggering of system builds.
**Environment Control:  Isolated execution environments.



# Prerequisites
Make sure you have the following installed on your machine:
* Python 3.13+
* PowerShell (for Windows) or Bash (for Linux/macOS)



# Installation & Setup
*Clone the repository – 








1. Create and activate a virtual environment:
PowerShell
# On Windows (PowerShell)
python -m venv .venv
. .venv\Scripts\Activate.ps1


2.  Install dependencies:
Bash
pip install -r requirements.txt


3. Run the development server:
Bash
uvicorn main:app –reload


#Usage:-
Once the server is running, you can access:
•	Interactive API Docs (Swagger UI):  http://localhost:8000/docs
•	Alternative Docs (Redoc):  http://localhost:8000/redoc