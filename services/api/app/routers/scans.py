from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List

# Import our database connection and the models/schemas we built earlier
from app.database import get_db
from app.models import Scan
from app.schemas import ScanResponse

# HOW IT WORKS: We create a router object. 
# 'prefix="/api/v1/scans"' means every URL in this file automatically starts with this path.
# 'tags=["Scans"]' organizes it neatly in the Swagger UI documentation.
router = APIRouter(prefix="/api/v1/scans", tags=["Scans"])

# WHAT THIS DOES: This handles HTTP GET requests to "/api/v1/scans/".
# response_model=List[ScanResponse] tells FastAPI to automatically convert our 
# database results into the exact JSON format the React dashboard expects.
@router.get("/", response_model=List[ScanResponse])
async def get_all_scans(db: AsyncSession = Depends(get_db)):
    """
    Fetches all scans from the PostgreSQL database, including their associated findings.
    """
    
    # WHY WE USE selectinload: 
    # If we just fetch Scans, SQLAlchemy will have to make a separate trip to the 
    # database for EVERY single finding attached to those scans (known as the N+1 problem).
    # 'selectinload(Scan.findings)' tells the database: "Fetch the scans AND all their 
    # findings at the exact same time in one efficient trip."
    query = select(Scan).options(selectinload(Scan.findings))
    
    # Execute the query asynchronously (so the server doesn't freeze while waiting for the DB)
    result = await db.execute(query)
    
    # .scalars().all() extracts the actual Python objects from the raw database response
    return result.scalars().all()
