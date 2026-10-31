import asyncio
import json
from app.scanners.osv import run_osv_scanner

async def main():
    # We pass the current directory (".") to the scanner
    print("Testing Python subprocess adapter...")
    result = await run_osv_scanner(".")
    
    # Print the resulting Python dictionary nicely formatted
    print("\nScan Complete. Python parsed this data:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
