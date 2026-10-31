import asyncio
import json
import logging

logger = logging.getLogger(__name__)

async def run_osv_scanner(directory_path: str) -> dict:
    logger.info(f"Starting OSV-Scanner on directory: {directory_path}")
    
    try:
        # FIX: Replaced deprecated '--json' with '--format', 'json'
        process = await asyncio.create_subprocess_exec(
            "osv-scanner",
            "--format", 
            "json",
            "-r",
            directory_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        logger.error("osv-scanner command not found. Is it installed?")
        return {"results": []}

    stdout, stderr = await process.communicate()
    
    if stdout:
        try:
            parsed_data = json.loads(stdout.decode('utf-8'))
            return parsed_data
        except json.JSONDecodeError:
            # We slice the output [:200] so it doesn't flood your terminal if it fails again
            logger.error(f"Failed to parse OSV JSON. Raw output: {stdout.decode('utf-8')[:200]}...")
            return {"results": []}
            
    if stderr:
        logger.error(f"OSV-Scanner execution error: {stderr.decode('utf-8')}")
        
    return {"results": []}
