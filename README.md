# Mirror Report AI

![Next.js](https://img.shields.io/badge/Next.js_16-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python_3-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenPyXL](https://img.shields.io/badge/OpenPyXL-217346?style=for-the-badge&logo=microsoft-excel&logoColor=white)
![Claude](https://img.shields.io/badge/Claude_API-D97757?style=for-the-badge&logo=anthropic&logoColor=white)

An enterprise document verification dashboard that creates a high-fidelity digital twin of physical manufacturing documents for AI-powered OCR validation and automated Excel template generation.

---

## Features

- **Dual-Pane Verification:** Side-by-side desktop layout comparing physical source images with extracted data.
- **LLM-Powered OCR:** Uses Claude API to parse images into structured datasets.
- **Dynamic Document Routing:** Automatically classifies incoming documents and maps JSON payloads to dedicated React templates.
- **Interactive Browser Editing:** Directly modify text headers, product tags, data cells, and table rows within the high-fidelity preview pane.
- **On-Demand Excel Export:** Automatically re-compiles edited layouts through the Python engine to export newly updated Excel spreadsheets.
- **High-Fidelity UI:** Responsive modular layouts styled entirely with Tailwind CSS that visually mirror the original paper documents.
- **Template-Based Architecture:** Supports multiple manufacturing document types through reusable component designs.

---

## Tech Stack

| Domain                 | Technology                                |
| :--------------------- | :---------------------------------------- |
| **Frontend**           | React, Next.js (App Router), Tailwind CSS |
| **Backend**            | Python, OpenPyXL                          |
| **Type Safety**        | TypeScript                                |
| **AI / OCR Engine**    | Claude API (Anthropic SDK)                |
| **Storage**            | Local / In-Memory                         |
| **Document Rendering** | Dynamic CSS Grid, HTML Tables             |

---

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.10+
- Anthropic API Key (`ANTHROPIC_API_KEY` set in environment)

### Installation

1. Clone the repository and set up environment keys.

2. Install frontend dependencies:

```bash
npm install
```

3. Install backend python dependencies:

```bash
pip install -r requirements.txt
```

4. Run the development server:

```bash
npm run dev
```

5. Open http://localhost:3000 with your browser to see the result.

---

## Available Commands

Here are the scripts available in the project:

- `npm run dev`: Starts the local Next.js development server.
- `npm run build`: Compiles the application for production deployment.
- `npm run start`: Runs the compiled production server.
- `npm run lint`: Performs code style analysis and type checking using ESLint.
- `npm run format`: Formats all code files using Prettier.
- `npx tsc --noEmit`: Runs static TypeScript compiler type assertions.
