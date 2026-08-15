# East India Company Canton Factory Archives Platform (1792–1793)

**东印度公司广州商馆（1792–1793）档案数字文本与全文检索平台**

<div align="center">
  <img src="./assets/platform-preview.png" alt="Platform Preview" width="100%">
</div>

---

## 📖 Project Overview

A digital humanities platform for digitizing, OCR processing, and full-text search of historical archives from the East India Company's Canton Factory (1792–1793). This platform combines modern OCR technology with LLM-assisted text correction to preserve and make accessible rare historical documents.

**本平台致力于东印度公司广州商馆历史档案的数字化、OCR识别与全文检索，结合现代 OCR 技术与大语言模型辅助纠错，保存并开放珍稀历史文献。**

---

## ✨ Key Features

- **🔍 High-Accuracy OCR**: Powered by PaddleOCR-VL for layout-aware document parsing
- **🤖 LLM-Assisted Correction**: DeepSeek-V3 intelligent text correction with historical context awareness
- **📄 Multi-Format Support**: PDF, images (PNG, JPG) with automatic page splitting
- **🎯 Precise Bbox Rendering**: Accurate text region highlighting with fixed coordinate alignment
- **🌐 Modern Web Interface**: Next.js + React responsive viewer with real-time preview
- **📦 Batch Processing**: Celery-based async task queue for document-level processing
- **💾 Structured Export**: JSON, Markdown, TXT export with customizable formats

---

## 🏗️ Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Frontend      │◄────►│   Backend API    │◄────►│  PaddleOCR-VL   │
│   Next.js       │      │   FastAPI        │      │   Service       │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                 │
                                 ▼
                         ┌──────────────────┐
                         │   PostgreSQL     │
                         │   + Redis        │
                         └──────────────────┘
                                 │
                                 ▼
                         ┌──────────────────┐
                         │   Celery Workers │
                         │   (OCR + LLM)    │
                         └──────────────────┘
```

### Tech Stack

**Frontend**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Lucide Icons

**Backend**
- FastAPI (Python 3.12+)
- SQLAlchemy + PostgreSQL
- Celery + Redis
- httpx (async HTTP client)

**AI Services**
- PaddleOCR-VL 1.6 (Layout parsing + OCR)
- DeepSeek-V3 / OpenAI-compatible LLM (Text correction)

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+
- Python 3.12+
- PostgreSQL 14+
- Redis 7+

### 1. Clone Repository

```bash
git clone https://github.com/yumingjie0405/EIC-Canton-Factory-Archives-1792-1793.git
cd EIC-Canton-Factory-Archives-1792-1793
```

### 2. Configure Environment

**Backend** (`backend/.env`):
```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set:
# - DATABASE_URL
# - PADDLE_OCR_URL (your PaddleOCR service endpoint)
# - GPT_API_KEY (OpenAI-compatible API key)
```

**Frontend** (`frontend/.env.local`):
```bash
cp frontend/.env.example frontend/.env.local
# Edit frontend/.env.local if needed
```

### 3. Deploy PaddleOCR Service (Optional)

See [deploy/paddleocr_vl/README.md](deploy/paddleocr_vl/README.md) for deployment instructions.

Or use the public endpoint (if available).

### 4. Start Services

**Option A: Docker Compose (Recommended)**
```bash
docker-compose up -d
```

**Option B: Manual Start**

```bash
# Start backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Start Celery worker (in another terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Start frontend (in another terminal)
cd frontend
npm install
npm run dev
```

### 5. Access Platform

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

---

## 📚 Usage Guide

### Upload Documents

1. Navigate to **Upload** page
2. Select PDF or image files
3. Configure OCR options (visualization, table merging, etc.)
4. Click **Start OCR**

### Review & Correct

1. Go to **Documents** page
2. Select a document to view OCR results
3. Use the **Viewer** to inspect text blocks with bbox overlays
4. Run **LLM Correction** for intelligent text refinement

### Export Results

1. Open document detail page
2. Choose export format (JSON / Markdown / TXT)
3. Download processed content

---

## 🔧 Configuration

### OCR Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `maxPixels` | 4,200,000 | Max image resolution (~2048×2048) |
| `layoutShapeMode` | `rect` | Bbox shape (`rect` or `poly`) |
| `mergeTables` | `true` | Merge table cells |
| `relevelTitles` | `true` | Normalize heading levels |

### LLM Correction

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gpt_model` | `DeepSeek-V3` | OpenAI-compatible model |
| `gpt_timeout` | 300s | Request timeout |
| `gpt_max_retries` | 3 | Retry attempts for failed pages |
| `gpt_retry_backoff_seconds` | 2.0s | Exponential backoff base |

---

## 🛠️ Recent Improvements (2026-08-13)

### Fixed Issues

1. **Bbox Coordinate Mismatch** (1087/1110 pages affected)
   - Root cause: PaddleOCR's downsampled `inputImage` overwriting high-res source
   - Fix: Always use local high-resolution images; ensure `page.width/height` matches bbox coordinate space
   - Impact: 5% offset eliminated

2. **LLM TLS Fault Blocking**
   - Root cause: Single-page failure aborted entire document processing
   - Fix: Two-pass retry strategy — skip failed pages in first pass, compensate in second round
   - Impact: Improved fault tolerance for intermittent network issues

3. **Unnecessary Downsampling**
   - Increased `maxPixels` from 1.5M to 4.2M to preserve 200 DPI scans
   - Improved image quality for typical A4 documents

### Enhancements

- Better error logging for GPT connection failures
- Exponential backoff tuning for retry stability
- Sanitized default prompts in source code (production prompts via external files)

---

## 📊 Project Status

- ✅ Core OCR pipeline
- ✅ LLM-assisted correction
- ✅ Web viewer with bbox overlay
- ✅ Batch processing
- ✅ Multi-format export
- 🚧 Advanced search (planned)
- 🚧 User annotation system (planned)

---

## 📄 License

[MIT License](LICENSE)

---

## 🙏 Acknowledgments

- **PaddleOCR Team** for the state-of-the-art OCR model
- **DeepSeek AI** for the powerful language model
- **Digital Humanities Community** for inspiration and feedback

---

## 📧 Contact

For questions or collaboration:
- **Author**: 相忘江湖的小余
- **Email**: 1465739029@qq.com
- **GitHub**: [@yumingjie0405](https://github.com/yumingjie0405)

---

<div align="center">
  Made with ❤️ for Digital Humanities Research
</div>
