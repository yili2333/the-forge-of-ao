# D&D 5e AI-Powered Online TRPG Platform

**Project for BSAI301 Course - Team 2**

## Team Members
- 谈瑞 (Tan Rui)
- 杨子旭 (Yang Zixu)
- 黎逸 (Li Yi)
- 李思轩 (Li Sixuan)

## Overview

This is an AI-powered online tabletop role-playing game (TRPG) platform specifically designed for Dungeons & Dragons 5th Edition (2024 rules). The platform integrates multiple AI modules to assist both Dungeon Masters (DMs) and players throughout their gaming sessions.

### Core Features

1. **High-Accuracy Rule Query AI** using RAG (Retrieval-Augmented Generation) architecture
2. **Real-time Game State Synchronization Engine** supporting pseudo-P2P multiplayer sessions
3. **AI-Powered Map Generation System** for both world maps and tactical battle maps
4. **Comprehensive Character Sheet Management**

### Technical Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Unity Client
- **Database**: SQLite/MySQL with Qdrant vector database
- **AI Models**: OpenAI GPT-4o, text-embedding-3-small
- **Synchronization**: WebSocket (real-time game state within 500ms)

## Architecture

The system operates within an ecosystem of external actors and services:
- **Players**: Query rules, manage their character sheets, move tokens on maps
- **Dungeon Master (DM)**: Elevated privileges for all operations, imports custom rules, generates maps, controls NPCs/monsters
- **LLM API Service**: External API (OpenAI) for answer generation

## Getting Started

### Prerequisites
- Python 3.8+
- MySQL 8.0+ (optional, for production)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/BSAI301/course-project-ex2-team-2.git
   cd course-project-ex2-team-2
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables in `.env` file:
   ```env
   OPENAI_API_KEY="your_openai_api_key"
   EMBEDDING_API_KEY="your_embedding_api_key"
   # More configurations...
   ```

4. Initialize the database:
   ```bash
   python -c "from src.db import init_db; import asyncio; asyncio.run(init_db())"
   ```

5. Start the backend server:
   ```bash
   cd src
   python main.py
   ```
   The server will start at `http://localhost:8000`

## Project Status

- [x] Core rule query system with RAG
- [x] Real-time game state synchronization
- [x] Map generation from natural language
- [x] Character sheet management
- [x] Conflict detection for custom rules
- [ ] Advanced DM tools
- [ ] Mobile client

## File Structure

```
├── src/                    # Backend source code
│   ├── main.py             # Main FastAPI server
│   ├── sync_engine.py      # WebSocket synchronization
│   ├── retriever.py        # Hybrid retrieval system
│   ├── rule_importer.py    # Rule import system
│   └── ...                 # Other modules
├── Assets/                 # Unity client assets
├── dnd_rules.db           # Pre-populated rule database
├── .env                   # Environment configuration
├── requirements.txt       # Python dependencies
└── MySQL_Deployment_Guide.md # Deployment instructions
```

## Contributing

Please read CONTRIBUTING.md for details on our code of conduct, and the process for submitting pull requests.

## License

This project is part of the BSAI301 course curriculum.

## Acknowledgments

- D&D community for the amazing game system
- OpenAI for providing powerful language models
- The course instructors for guidance and feedback

