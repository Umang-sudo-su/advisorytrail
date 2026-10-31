import asyncio
from app.database import SessionLocal
from app.models import Repository, Scan, Finding, ScanStatus

async def seed_data():
    # HOW IT WORKS: 'async with SessionLocal() as session' opens our database session.
    # It automatically handles closing the connection when the block finishes.
    async with SessionLocal() as session:
        
        print("Injecting fake repository...")
        # 1. Create a Repository Python object in memory
        repo = Repository(
            github_id="github-12345", 
            name="acme/payment-service", 
            url="https://github.com/acme/payment-service"
        )
        
        # 2. Add it to our session ("shopping cart")
        session.add(repo)
        
        # WHAT IS FLUSH?: 'flush()' tells the database "prepare to save this". 
        # We do this because we need PostgreSQL to generate the 'repo.id' right now 
        # so we can attach our Scans to it, but we aren't permanently committing yet.
        await session.flush() 

        print("Injecting fake scan...")
        # 3. Create a Scan object and link it using the repo.id we just generated
        scan = Scan(
            repository_id=repo.id, 
            commit_hash="sha-a9b1c", 
            status=ScanStatus.COMPLETED
        )
        session.add(scan)
        await session.flush() # Flush again to get the scan.id

        print("Injecting fake findings...")
        # 4. Create Findings and link them to the scan.id
        finding1 = Finding(
            scan_id=scan.id,
            osv_id="GHSA-34jh-p97f-mpxf",
            package_name="urllib3",
            package_version="1.26.4",
            severity="High",
            details={"fixed_version": "1.26.19", "status": "NEW"}
        )
        finding2 = Finding(
            scan_id=scan.id,
            osv_id="GHSA-xyz1-2345-abcd",
            package_name="pyjwt",
            package_version="2.3.0",
            severity="High",
            details={"fixed_version": "2.4.0", "status": "NEW"}
        )
        
        # 'add_all' lets us add multiple items to the cart at once
        session.add_all([finding1, finding2])

        # 5. THE COMMIT: This is the "Checkout" button. 
        # It permanently writes everything in the session to the PostgreSQL database.
        await session.commit()
        print("Success! Dummy data saved to database.")

# This tells Python to run our async function if we execute this file directly
if __name__ == "__main__":
    asyncio.run(seed_data())
