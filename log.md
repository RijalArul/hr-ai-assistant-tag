Yang gue lakuin                                                             
                                                                                    
  1. .env dibuat dari .env.example
                                                                                    
  - JWT_SECRET di-generate otomatis (32-byte hex)                                   
  - Redis default ke localhost:6379 (dev mode)                                      
  - Semua API key di-mark FILL_ME — masih perlu diisi manual                        
                                                                                    
  2. apps/web/.env.local dibuat                                                     
                                                                                    
  - NEXT_PUBLIC_API_URL=http://localhost:8000                                       
                                                                                  
  3. Python venv dibuat + dependencies diinstall                                    
                                                                                  
  - Venv: apps/api/.venv/                                                           
  - Semua package dari requirements.txt berhasil diinstall (FastAPI, LangChain,
  LangGraph, Gemini, SQLAlchemy, dll)                                               
                                                                                  
  4. Makefile di-fix untuk macOS                                                    
                                                                                  
  - Sebelumnya hanya support Windows path (Scripts/python.exe)                      
  - Ditambah Unix path (bin/python) — sekarang make api, make migrate, dll langsung
  pakai venv yang benar                                                             
                                                                                  
  ---                                                                               
  Yang masih perlu diisi manual di .env                                           
                                                                                  
  ┌─────────────────────┬────────────────────────────────────────────┐
  │      Variable       │                 Keterangan                 │              
  ├─────────────────────┼────────────────────────────────────────────┤
  │ DATABASE_URL        │ Supabase PostgreSQL URL                    │              
  ├─────────────────────┼────────────────────────────────────────────┤            
  │ GEMINI_API_KEY      │ Google AI Studio                           │            
  ├─────────────────────┼────────────────────────────────────────────┤              
  │ MINIMAX_API_KEY     │ MiniMax API (intent classifier)            │
  ├─────────────────────┼────────────────────────────────────────────┤              
  │ HUGGINGFACE_API_KEY │ HuggingFace (embedding fallback)           │            
  ├─────────────────────┼────────────────────────────────────────────┤              
  │ DISCORD_*           │ Bot token & app credentials                │            
  ├─────────────────────┼────────────────────────────────────────────┤              
  │ STORAGE_S3_*        │ Cloudflare R2 / MinIO credentials          │
  ├─────────────────────┼────────────────────────────────────────────┤              
  │ REDIS_*             │ Kalau pakai Redis remote (Railway/Upstash) │            
  └─────────────────────┴────────────────────────────────────────────┘              
                                                                                  
  ---                                                                               
  Cara jalanin setelah .env diisi                                                 
                                                                                    
  # Database migration
  make migrate                                                                      
                                                                                  
  # Seed demo data                                                                
  make seed

  # Jalanin semua (3 terminal terpisah)                                             
  make api    # FastAPI → localhost:8000
  make web    # Next.js → localhost:3000                                            
  make bot    # Discord bot  