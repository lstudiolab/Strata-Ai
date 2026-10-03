import os
MODEL=os.getenv('GEMINI_MODEL','gemini-2.5-flash')
API_KEY=os.getenv('GEMINI_API_KEY','')
DB=os.getenv('STRATA_MEMORY_DB','data/strata.db')
