# Configuration Management Plan
   ## CHORAS Scalability Project
   
   ### My Role Responsibilities s
   As Configuration Manager, I am responsible for:
   - ✅ Define processes and procedures for version control
   - ✅ Ensure all hardware/software components are clearly identified
   - ✅ No modifications without authorization (via PR process)
   - ✅ Apply to all software code, documentation, test results, deliverables
   - ✅ Change and defect tracking activities
   - ✅ Own the tools (Git, Jenkins/GitHub Actions, etc.)
   - ✅ Make sure tools are available, working, and accessible
   
   ### 1. Repository Structure
   - Main repo: https://github.com/Saptarshi666/CHORAS#
   - Submodules: backend/, frontend-v2/,.github,example_geometries
   - NEW: Individual directories for simulation method containers
   - Branch strategy: [To be defined - see below]

   - The default branch of the repo is named as `main` this branch has been forked from the `dev` branch of the original repo
   - `main` - Stable code only, matches upstream CHORAS
   - `dev` - Integration branch for team development
   - `feature/*` - Individual feature branches (e.g., feature/de-container)
   - `bugfix/*` - Bug fix branches
   - `container/*` - Branches for containerization works
   - `testing/*` - Testing branches
   
   ### 3. Environment Management
   - Development: Local Docker containers (multi-container setup)
   - Testing: Isolated Docker test environment
   - CI/CD: GitHub Actions for automated builds
   - Future: SURF research cloud deployment
   
   ### 4. Configuration Files Tracked (tentative)
   - `docker-compose.yml` - Main orchestration (existing)
   - `docker-compose.dev.yml` - Development override (tentative)
   - `docker-compose.test.yml` - Testing environment (tentative)
   - `docker-compose.simulation-methods.yml` - Individual simulation containers
   - `.env.api` - listed
   - `.env.db` - listed
   - `.env.de-simulation` - DE method environment (tentative)
   - `.env.dg-simulation` - DG method environment (tentative)
   - Backend config files in backend/
   - Frontend config in frontend-v2/
   - Celery configuration for task orchestration
   
   ### 5. Technology Stack & Dependencies
   - Docker version: [Note version from your system] Docker version 29.1.5, build 0e6fee6
   - Docker Compose version: Docker Compose version v5.0.1
   - Python 3.10+ (Flask backend)
   - Node.js 18+ (React frontend)
   - PostgreSQL 14 (Database)
   - Celery 
   - Redis or RabbitMQ (Celery broker)
   - **Key Python packages**: Flask, Celery, SQLAlchemy
   
   ### 6. Secrets Management
   - Database credentials: Use .env files (currently on git, not sure if we have to use this itself)
   - Celery broker credentials: Environment variables
   - SURF cloud credentials: [To be obtained]
   - API keys: [To be documented]
   - **Create**: `.env.example` templates for all services
   
   ### 7. Build Process
   - Current: `docker-compose up` (monolithic)
   - Planned: Multi-stage build for simulation containers
   - CI/CD: Automated via GitHub Actions
   - Container registry: Docker Hub or GitHub Container Registry
   
   ### 8. Change Management Process
   - All changes via Pull Requests
   - Minimum 1 reviewer required
   - CI/CD must pass
   - Configuration changes must be documented in CHANGELOG.md
   - Breaking changes require team discussion
   
   ### 9. Tools Ownership 
   - **Git/GitHub**: Ensure all team members have access
   - **Docker Desktop**: Verify everyone can run containers
   - **GitHub Actions**: Set up and maintain CI/CD pipelines
   - **Issue Tracker**: GitHub Issues for defects and features
   - **Documentation**: Maintain in `docs/` directory