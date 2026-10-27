#!/bin/bash
# Backend setup script

echo "🔧 Setting up backend environment..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Check PostgreSQL connection
echo "🗄️  Checking PostgreSQL connection..."
python -c "
from sqlalchemy import create_engine, text
try:
    engine = create_engine('postgresql://postgres:postgres@localhost:5432/ocr_platform')
    with engine.connect() as conn:
        result = conn.execute(text('SELECT version()'))
        print('✅ PostgreSQL connection successful')
except Exception as e:
    print(f'❌ PostgreSQL connection failed: {e}')
    exit(1)
"

# Run Alembic migrations
echo "🔄 Running database migrations..."
echo "  Step 1: Marking existing tables as baseline..."
alembic stamp 000_initial

echo "  Step 2: Adding knowledge workbench tables..."
alembic upgrade head

echo "✅ Backend setup complete!"
echo ""
echo "To start the backend server:"
echo "  uvicorn app.main:app --reload --port 8000"
